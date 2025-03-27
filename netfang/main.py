# main.py

import asyncio
import os
import platform
import subprocess # Keep for sync calls like MAC address if needed
import sys
import socket
import secrets
from functools import wraps
from platform import system
from typing import Dict, Any, Optional, Callable, Union, Tuple, List
import json # For plugin action handling
import logging # Use standard logging

from flask import (
    request, jsonify, render_template, session, redirect, url_for, abort,
    Flask, Response, send_from_directory, flash
)
from flask_socketio import SocketIO, emit

# --- NetFang Core Imports ---
try:
    from netfang.alert_manager import AlertManager, Alert, AlertCategory, AlertLevel
    from netfang.api import pi_utils
    from netfang.db.database import init_db, get_dashboard_data
    from netfang.network_manager import NetworkManager
    from netfang.plugin_manager import PluginManager
    from netfang.socketio_handler import handler # Import the INSTANCE
    from netfang.states.state import State
except ImportError as e:
    print(f"Error importing NetFang core modules: {e}")
    print("Please ensure the netfang package is correctly installed and structured.")
    sys.exit(1)

# --- Optional Sentry Setup ---
try:
    import sentry_sdk
    sentry_sdk.init(
        # --- DSN UPDATED HERE ---
        dsn="https://80c9a50a96245575dc2414b9de48e2b2@o1363527.ingest.us.sentry.io/4508971050860544",
        # ------------------------
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=False,
        server_name=f"{system()} on {platform.node()}",
        # Consider enabling performance monitoring
        # traces_sample_rate=1.0,
    )
    print("Sentry SDK initialized.")
except ImportError:
    print("Sentry SDK not found. Error tracing is disabled.")
except Exception as e:
    print(f"Error initializing Sentry SDK: {e}")

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Configuration ---
# Generate a secure secret key
app.secret_key = os.environ.get("NETFANG_SECRET_KEY", secrets.token_hex(32))

# Session Cookie Configuration (Adjust 'Secure' based on HTTPS usage)
app.config['SESSION_COOKIE_NAME'] = 'NETFANG_SESSION' # Less suspicious name
app.config['SESSION_COOKIE_SECURE'] = os.environ.get("FLASK_ENV") == "production" # Secure only in production (assuming HTTPS)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Base directory and config path
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Use absolute path
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# --- Logging Setup ---
# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO) # Use Flask's logger

# --- SocketIO Initialization ---
# Ensure async_mode is set for asyncio compatibility
socketio = SocketIO(app, async_mode='asyncio', cors_allowed_origins="*") # Allow all origins for now, restrict in production

# --- Initialize Core Managers & Handler ---
try:
    # Instantiate PluginManager first
    plugin_manager = PluginManager(CONFIG_PATH)
    plugin_manager.load_config()
    app.logger.info("PluginManager config loaded.")

    # Define callbacks BEFORE passing them
    def state_change_callback(state: State, context: Dict[str, Any]) -> None:
        """Callback function for state changes."""
        app.logger.info(f"State changed to: {state.value}")
        socketio.emit(
            "state_update",
            {"state": state.value, "context": context or {}}, # Ensure context is dict
        )

    def alert_callback(alert: Alert) -> None:
        """Callback function for alerts."""
        app.logger.info(f"Alert generated: {alert.level} - {alert.message}")
        socketio.emit(
            "alert_sync",
            alert.to_dict(),
        )

    # Instantiate NetworkManager
    network_manager = NetworkManager(plugin_manager, plugin_manager.config, state_change_callback)
    app.logger.info("NetworkManager instantiated.")

    # Get DB path and initialize DB
    db_path = plugin_manager.config.get("database_path", os.path.join(BASE_DIR, "netfang.db")) # Default path relative to main.py
    init_db(db_path)
    app.logger.info(f"Database initialized at: {db_path}")

    # Set dependencies in SocketIOHandler (the imported instance)
    handler.set_socketio(socketio)
    handler.set_db_path(db_path)
    app.logger.info("SocketIOHandler configured.")

    # Load plugins AFTER DB init and handler setup
    plugin_manager.load_plugins()
    app.logger.info("Plugins loaded.")

    # Instantiate AlertManager
    alert_manager = AlertManager(plugin_manager, db_path, alert_callback)
    app.logger.info("AlertManager instantiated.")

except Exception as e:
    app.logger.exception("CRITICAL ERROR during manager initialization.")
    print(f"CRITICAL ERROR during manager initialization: {e}")
    sys.exit(1)


# --- Register Plugin Blueprints ---
try:
    for plugin_name, plugin in plugin_manager.plugins.items():
        if hasattr(plugin, "register_routes"):
            app.logger.info(f"Registering routes for plugin: {plugin_name}")
            plugin.register_routes(app) # Pass the Flask app instance
except Exception as e:
    app.logger.exception(f"Error registering plugin routes.")


# --- Start Background Tasks (NetworkManager) ---
# Using socketio.start_background_task is generally safer than before_first_request for async
@socketio.on('connect') # Trigger NetworkManager start on first client connect (or use a dedicated startup event)
def handle_first_connect_startup():
    # Ensure this runs only once
    if not getattr(handle_first_connect_startup, 'has_run', False):
         app.logger.info("First client connected, starting NetworkManager background task.")
         socketio.start_background_task(network_manager.start)
         handle_first_connect_startup.has_run = True
    # Proceed with normal connect logic (moved to separate handler below)
    _handle_connect_logic()


# --- Cleanup ---
# Note: Proper cleanup on shutdown can be tricky depending on deployment.
# atexit might not work reliably with async or worker processes.
# Consider signal handling (SIGTERM, SIGINT) if needed.
# import atexit
# atexit.register(cleanup_resources)


# --- Decorators ---
def login_required(f: Callable) -> Callable:
    """Decorator that enforces user authentication."""
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not session.get('logged_in'):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('frontpage'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f: Callable) -> Callable:
    """Decorator that enforces admin authentication."""
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not session.get('logged_in'):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('frontpage'))
        if session.get('username') != 'admin':
            flash("Admin privileges required for this action.", "danger")
            # Redirect to dashboard instead of login if already logged in but not admin
            return redirect(url_for('dashboard'))
            # Or use abort(403) if preferred
        return f(*args, **kwargs)
    return decorated_function


# --- Flask Routes ---

@app.route("/")
def frontpage() -> str:
    """Renders the DECOY router front page."""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    # Decoy data
    data: Dict[str, str] = {
        "hostname": "SecureHomeGateway", # Fake router name
        "mac_address": "00:1A:2B:3C:4D:5E", # Fake default MAC
        "ip_address": "192.168.1.1"  # Fake default IP
    }
    # Optionally try to get real info but don't rely on it
    try:
        data["hostname"] = platform.node() # Use real hostname for decoy? Or keep fake?
        # ... (code to get real MAC/IP can stay here if desired) ...
        pass
    except Exception as e:
        app.logger.debug(f"Could not get real system info for decoy page: {e}")

    return render_template("router_home.html", **data)


@app.route("/login", methods=["GET", "POST"])
def login() -> Union[str, Response]:
    """Handle login requests (checks against actual admin credentials)."""
    if request.method == "GET":
        # If someone tries to GET /login, just send them to the frontpage
        return redirect(url_for("frontpage"))

    # Get credentials from environment or config
    admin_username = os.environ.get("NETFANG_ADMIN_USER", plugin_manager.config.get("admin_username", "admin"))
    admin_password = os.environ.get("NETFANG_ADMIN_PASSWORD", plugin_manager.config.get("admin_password"))

    if not admin_password:
        app.logger.warning("SECURITY WARNING: No admin password set in environment or config. Using default.")
        # Use a slightly better default, but strongly recommend setting one
        admin_password = "NetFang_Default_Password_ChangeMe"

    # Get username/password from form or JSON
    username = None
    password = None
    if request.content_type == 'application/json':
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")
    else: # Assume form data
        username = request.form.get("username")
        password = request.form.get("password")

    if username == admin_username and password == admin_password:
        session['logged_in'] = True
        session['username'] = username
        app.logger.info(f"Successful login for user '{username}' from IP {request.remote_addr}")
        # Redirect to the actual dashboard
        return redirect(url_for("dashboard"))
    else:
        app.logger.warning(f"Failed login attempt for user '{username}' from IP {request.remote_addr}")
        # Render a generic login failed page that looks like a router's
        flash("Invalid username or password.", "danger") # Add flash message
        return render_template("login_failed.html"), 401


@app.route("/dashboard")
@login_required
def dashboard() -> str:
    """Render the actual analysis dashboard page."""
    current_state_value = "UNKNOWN" # Default
    try:
        if network_manager and network_manager.state_machine:
             current_state_value = network_manager.state_machine.current_state.value
    except Exception as e:
        app.logger.error(f"Error getting current state for dashboard: {e}")

    return render_template("hidden/index.html",
                          hostname=platform.node(), # Real hostname
                          state=current_state_value)


@app.route("/logout")
def logout() -> Response:
    """Handle logout requests."""
    username = session.get('username', 'Unknown user')
    session.clear()
    flash("You have been logged out.", "info")
    app.logger.info(f"User '{username}' logged out.")
    # Redirect back to the decoy page
    return redirect(url_for('frontpage'))


@app.route("/state")
@login_required
def get_current_state() -> Response:
    """API endpoint to get current analysis state."""
    current_state_value = "UNKNOWN"
    try:
        if network_manager and network_manager.state_machine:
             current_state_value = network_manager.state_machine.current_state.value
    except Exception as e:
        app.logger.error(f"Error getting current state for API: {e}")
        return jsonify({"error": "Could not retrieve state"}), 500
    return jsonify({"state": current_state_value})


@app.route("/service/restart", methods=["POST"])
@admin_required
def restart_service() -> Response:
    """Restart the netfang service using systemctl (if applicable)."""
    # Check if running in a Linux environment with systemd likely available
    if not pi_utils.is_linux(): # Keep this check
        return jsonify({"status": "error", "message": "Service restart only supported on Linux systems"}), 400

    service_name = plugin_manager.config.get("service_name", "netfang.service") # Make service name configurable

    try:
        # Ensure sudo is configured to allow the app user to restart this specific service without a password
        cmd = ["sudo", "systemctl", "restart", service_name]
        app.logger.info(f"Attempting to restart service: {' '.join(cmd)} by user '{session.get('username')}'")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)

        if result.returncode == 0:
            app.logger.info(f"Service '{service_name}' restart initiated successfully.")
            return jsonify({
                "status": "success",
                "message": f"{service_name} service restart initiated successfully."
            })
        else:
            error_msg = f"Failed to restart service '{service_name}'. Exit code: {result.returncode}. Stderr: {result.stderr.strip()}"
            app.logger.error(error_msg)
            return jsonify({
                "status": "error",
                "message": error_msg
            }), 500
    except FileNotFoundError:
         error_msg = "Error: 'sudo' or 'systemctl' command not found. Cannot restart service."
         app.logger.error(error_msg)
         return jsonify({"status": "error", "message": error_msg}), 500
    except subprocess.TimeoutExpired:
        error_msg = f"Timeout waiting for service '{service_name}' restart command to complete."
        app.logger.error(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    except Exception as e:
        error_msg = f"An unexpected error occurred during service restart: {str(e)}"
        app.logger.exception("Service restart error") # Log full traceback
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500


@app.route("/plugins", methods=["GET"])
@login_required
def list_plugins() -> Response:
    """List available plugins and their status."""
    response: List[Dict[str, Any]] = []
    try:
        for plugin_name, plugin_obj in plugin_manager.plugins.items():
            response.append({
                "name": plugin_name,
                "enabled": _is_plugin_enabled(plugin_name), # Use helper
                "description": getattr(plugin_obj, "description", "No description available"),
            })
    except Exception as e:
        app.logger.exception("Error listing plugins")
        return jsonify({"error": "Could not retrieve plugin list"}), 500
    return jsonify(response)


@app.route("/plugins/enable", methods=["POST"])
@admin_required
def enable_plugin() -> Response:
    """Enable a plugin."""
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"status": "error", "message": "No plugin_name provided"}), 400

    try:
        if plugin_manager.enable_plugin(plugin_name): # Assumes this method exists
            _set_plugin_enabled_in_config(plugin_name, True) # Use helper
            plugin_manager.save_config() # Ensure config is saved
            app.logger.info(f"Plugin '{plugin_name}' enabled by user '{session.get('username')}'")
            # Consider adding logic to reload the plugin or notify NetworkManager
            return jsonify({"status": "success", "message": f"Plugin '{plugin_name}' enabled. Restart may be required for full effect."}), 200
        else:
            app.logger.error(f"Failed to enable plugin '{plugin_name}'.")
            return jsonify({"status": "error", "message": f"Failed to enable plugin '{plugin_name}'. Does it exist?"}), 404
    except Exception as e:
        app.logger.exception(f"Error enabling plugin {plugin_name}")
        return jsonify({"status": "error", "message": f"An error occurred: {e}"}), 500


@app.route("/plugins/disable", methods=["POST"])
@admin_required
def disable_plugin() -> Response:
    """Disable a plugin."""
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"status": "error", "message": "No plugin_name provided"}), 400

    try:
        if plugin_manager.disable_plugin(plugin_name): # Assumes this method exists
            _set_plugin_enabled_in_config(plugin_name, False) # Use helper
            plugin_manager.save_config() # Ensure config is saved
            app.logger.info(f"Plugin '{plugin_name}' disabled by user '{session.get('username')}'")
            # Consider adding logic to unload the plugin or notify NetworkManager
            return jsonify({"status": "success", "message": f"Plugin '{plugin_name}' disabled. Restart may be required for full effect."}), 200
        else:
            app.logger.error(f"Failed to disable plugin '{plugin_name}'.")
            return jsonify({"status": "error", "message": f"Failed to disable plugin '{plugin_name}'. Does it exist?"}), 404
    except Exception as e:
        app.logger.exception(f"Error disabling plugin {plugin_name}")
        return jsonify({"status": "error", "message": f"An error occurred: {e}"}), 500


@app.route("/plugin/action", methods=["POST"])
@login_required # Allow any logged-in user to run actions? Or use @admin_required?
def execute_plugin_action() -> Response:
    """ Executes an action (tool) defined by a plugin. """
    if not request.is_json:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    plugin_name = data.get("plugin_name")
    action_id = data.get("action_id")
    target_type = data.get("target_type") # e.g., 'system', 'network', 'device'
    target_id = data.get("target_id")     # e.g., MAC address, IP address, 'system'

    if not all([plugin_name, action_id, target_type]):
        return jsonify({"status": "error", "message": "Missing required fields: plugin_name, action_id, target_type"}), 400

    try:
        # Find the action definition
        action_info = plugin_manager.get_action_info(action_id)

        if not action_info or action_info['plugin_name'] != plugin_name:
            return jsonify({"status": "error", "message": f"Action '{action_id}' not found or doesn't belong to plugin '{plugin_name}'"}), 404

        # Check if the action involves running a command
        command_template = action_info.get("command")

        if command_template:
            # Basic templating - WARNING: Ensure target_id is validated/sanitized if used directly!
            # A safer approach is for the plugin action definition to include a function
            # that *builds* the command safely based on the target_id and type.
            # For now, proceed with caution.
            final_command = command_template.replace("{target_id}", str(target_id) if target_id else "")
            final_command = final_command.replace("{target_type}", str(target_type) if target_type else "")
            # Add more replacements as needed based on action_info

            app.logger.info(f"User '{session.get('username')}' initiating action '{action_id}' with command: {final_command}")

            # Run the command asynchronously using the handler
            # Use start_background_task for async operations triggered by sync events
            socketio.start_background_task(handler.run_command_async, final_command, plugin_name)

            return jsonify({
                "status": "success",
                "message": f"Action '{action_info.get('action_name', action_id)}' initiated.",
            }), 202 # Accepted
        else:
            # Handle actions defined by functions (not implemented here)
            app.logger.warning(f"Action {action_id} requested but has no associated command.")
            return jsonify({"status": "error", "message": "Action type not supported (only command execution implemented)"}), 400

    except Exception as e:
         app.logger.exception(f"Error executing plugin action {action_id}")
         return jsonify({"status": "error", "message": f"Error executing action: {e}"}), 500


@app.route("/favicon.ico")
def favicon() -> Response:
    """Serve favicon."""
    # Ensure the logo exists in static/
    return send_from_directory(os.path.join(app.root_path, 'static'), 'router_logo.png',
                               mimetype='image/png') # Correct mimetype


@app.route("/api/network-event", methods=["POST"])
def api_network_event() -> Response:
    """ API endpoint for receiving network state updates (e.g., from external monitor). """
    # Access control: Only allow from localhost or trusted proxies
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    remote_addr = request.remote_addr
    # Define trusted proxies if needed, e.g., TRUSTED_PROXIES = {'10.0.0.1'}
    is_local = remote_addr in ('127.0.0.1', '::1')
    is_trusted_proxy = x_forwarded_for and x_forwarded_for.split(',')[0].strip() in ('127.0.0.1', '::1') # Basic check

    if not (is_local or is_trusted_proxy):
        app.logger.warning(f"Unauthorized access attempt to /api/network-event from {remote_addr}")
        return jsonify({"error": "Unauthorized access."}), 403

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    event_data = request.get_json()
    event_type = event_data.get("event_type")
    interface_name = event_data.get("interface_name")
    details = event_data.get("details", {}) # Optional details

    if not event_type or not interface_name:
        return jsonify({"error": "Missing required fields: event_type, interface_name"}), 400

    app.logger.info(f"Received network event via API: {event_type} on {interface_name}")

    # Ensure NetworkManager instance exists and has the methods
    if not network_manager:
         return jsonify({"error": "NetworkManager not initialized"}), 500

    try:
        # Use start_background_task if handler methods are async
        if event_type == "connected":
            if hasattr(network_manager, 'handle_network_connection'):
                 # Assuming handle_network_connection is sync for now
                 network_manager.handle_network_connection(interface_name, details)
                 # If async: socketio.start_background_task(network_manager.handle_network_connection, interface_name, details)
            else: raise NotImplementedError("handle_network_connection not found")
        elif event_type == "disconnected":
             if hasattr(network_manager, 'handle_network_disconnection'):
                 # Assuming handle_network_disconnection is sync
                 network_manager.handle_network_disconnection(details)
                 # If async: socketio.start_background_task(network_manager.handle_network_disconnection, details)
             else: raise NotImplementedError("handle_network_disconnection not found")
        # Add other event types if needed
        else:
            return jsonify({"error": "Invalid event type"}), 400

        return jsonify({"status": "Event processed", "event_type": event_type}), 200
    except NotImplementedError as e:
         app.logger.error(f"NetworkManager method not implemented: {e}")
         return jsonify({"error": f"Internal error: {e}"}), 501 # Not Implemented
    except Exception as e:
        app.logger.exception("Error processing network event from API")
        return jsonify({"error": f"Error processing event: {e}"}), 500


# --- SocketIO Event Handlers ---

# Separate connect logic from startup logic
def _handle_connect_logic():
    """Handles the logic for a client connecting via SocketIO."""
    if not session.get('logged_in'):
        app.logger.warning(f"Unauthorized SocketIO connection attempt from {request.remote_addr}.")
        return False # Reject connection

    username = session.get('username', 'Unknown')
    sid = request.sid
    app.logger.info(f"Client connected: SID={sid}, User='{username}', IP={request.remote_addr}")

    # 1. Emit current state
    current_state_value = "UNKNOWN"
    current_context = {}
    try:
        if network_manager and network_manager.state_machine:
             current_state_value = network_manager.state_machine.current_state.value
             current_context = network_manager.state_machine.state_context or {}
    except Exception as e:
        app.logger.error(f"Error getting current state for connect event: {e}")
    emit("state_update", {"state": current_state_value, "context": current_context})

    # 2. Emit recent alerts
    try:
        recent_alerts = alert_manager.get_alerts(limit=50) # Get recent alerts
        emit("all_alerts", recent_alerts)
    except Exception as e:
        app.logger.error(f"Error getting alerts for connect event: {e}")

    # 3. Emit registered actions (tools)
    try:
        all_actions = plugin_manager.get_registered_actions()
        emit("registered_actions", all_actions)
    except Exception as e:
        app.logger.error(f"Error getting registered actions for connect event: {e}")

    # 4. Send cached output of active/recent processes to *this specific client*
    # Use start_background_task for the async handler method
    socketio.start_background_task(handler.send_cached_output_to_client, sid)

    return None # Explicitly allow connection


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handle SocketIO disconnect events."""
    username = session.get('username', 'Unknown')
    app.logger.info(f"Client disconnected: SID={request.sid}, User='{username}'")
    # No specific cleanup needed per user session for now


@socketio.on("sync_dashboard")
def handle_sync_dashboard() -> Optional[bool]:
    """Handle dashboard data sync request."""
    if not session.get('logged_in'):
        return False # Unauthorized

    app.logger.info(f"Dashboard sync requested by user '{session.get('username')}' (SID={request.sid})")
    try:
        dashboard_data = get_dashboard_data(db_path)

        # Also include current state and registered actions in the sync data
        if network_manager and network_manager.state_machine:
            dashboard_data['state'] = network_manager.state_machine.current_state.value
        dashboard_data['registered_actions'] = plugin_manager.get_registered_actions()

        emit("dashboard_data", dashboard_data)
    except Exception as e:
        app.logger.exception("Error during dashboard sync")
        emit("alert_sync", Alert(level=AlertLevel.ERROR, message=f"Error syncing dashboard: {e}", category=AlertCategory.SYSTEM).to_dict())

    return None


# --- Helper Functions ---
def _is_plugin_enabled(plugin_name: str) -> bool:
    """Check if a plugin is enabled in the configuration."""
    try:
        d_conf = plugin_manager.config.get("default_plugins", {})
        o_conf = plugin_manager.config.get("optional_plugins", {})
        pl_lower = plugin_name.lower()
        if pl_lower in d_conf:
            # Default plugins are enabled unless explicitly set to false
            return d_conf[pl_lower].get("enabled", True)
        elif pl_lower in o_conf:
            # Optional plugins are disabled unless explicitly set to true
            return o_conf[pl_lower].get("enabled", False)
    except Exception as e:
        app.logger.error(f"Error checking if plugin '{plugin_name}' is enabled: {e}")
    return False # Default to false if not found or error


def _set_plugin_enabled_in_config(plugin_name: str, enabled: bool) -> None:
    """Set a plugin's enabled status in the configuration dictionary."""
    try:
        pl_lower = plugin_name.lower()
        # Ensure the dictionaries exist in the config
        if "default_plugins" not in plugin_manager.config:
            plugin_manager.config["default_plugins"] = {}
        if "optional_plugins" not in plugin_manager.config:
            plugin_manager.config["optional_plugins"] = {}

        d_conf = plugin_manager.config["default_plugins"]
        o_conf = plugin_manager.config["optional_plugins"]

        found = False
        if pl_lower in d_conf:
            d_conf[pl_lower]["enabled"] = enabled
            found = True
        elif pl_lower in o_conf:
            o_conf[pl_lower]["enabled"] = enabled
            found = True

        if not found:
            # If plugin config doesn't exist, maybe add it to optional?
            app.logger.warning(f"Plugin '{plugin_name}' not found in config, adding to optional_plugins.")
            o_conf[pl_lower] = {"enabled": enabled}
            # Or choose to raise an error / do nothing
    except Exception as e:
         app.logger.error(f"Error setting enabled status for plugin '{plugin_name}' in config: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    host = os.environ.get("NETFANG_HOST", "0.0.0.0")
    port = int(os.environ.get("NETFANG_PORT", 8080))
    debug_mode = os.environ.get("FLASK_ENV") == "development"

    app.logger.warning("--- Starting NetFang Analyzer ---")
    app.logger.warning(f"Running in {'DEBUG' if debug_mode else 'PRODUCTION'} mode.")
    app.logger.warning("Using Flask development server via socketio.run().")
    app.logger.warning("Use a production WSGI server (like Gunicorn + Uvicorn/Eventlet/Gevent) for deployment.")

    # Use socketio.run() for development as it handles WebSockets correctly
    socketio.run(app, host=host, port=port, debug=debug_mode, use_reloader=debug_mode)
