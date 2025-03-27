import asyncio
import os
import platform
import subprocess
import sys
import socket
import secrets
from functools import wraps
from platform import system
from typing import Dict, Any, Optional, Callable, Union, Tuple, List

from flask import request, jsonify, render_template, session, redirect, url_for, abort, Flask, Response
from flask import send_from_directory
from flask_socketio import SocketIO, emit

from netfang.alert_manager import AlertManager, Alert, AlertCategory, AlertLevel
from netfang.api import pi_utils
from netfang.db.database import init_db, get_dashboard_data
from netfang.network_manager import NetworkManager
from netfang.plugin_manager import PluginManager
from netfang.socketio_handler import handler as socketio_handler
from netfang.states.state import State

try:
    import sentry_sdk

    sentry_sdk.init(
        dsn="https://80c9a50a96245575dc2414b9de48e2b2@o1363527.ingest.us.sentry.io/4508971050860544",
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=False,
        server_name=f"{system()} on {platform.node()}",
    )
except ImportError as e:
    print(f"Error importing Sentry SDK: {e}")
    print("Error tracing is disabled. To enable, install the sentry-sdk package.")

app = Flask(__name__)
socketio = SocketIO(app)
# Set the SocketIO instance in our handler
socketio_handler.set_socketio(socketio)

# Generate a secure secret key
if pi_utils.is_pi():
    # Use hardware-specific identifier for Raspberry Pi
    pi_serial = pi_utils.get_pi_serial()
    app.secret_key = secrets.token_hex(32) + (pi_serial if pi_serial else "")
elif pi_utils.is_linux() and not pi_utils.is_pi():
    # Use machine ID for Linux
    machine_id = pi_utils.linux_machine_id()
    app.secret_key = secrets.token_hex(32) + (machine_id if machine_id else "")
elif sys.platform in ["win32", "cygwin"]:
    # Use environment variable or generate a secure key for Windows
    app.secret_key = os.environ.get("NETFANG_SECRET_KEY", secrets.token_hex(32))
app.config['SESSION_COOKIE_NAME'] = 'NETFANG_SECURE_SESSION'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def state_change_callback(state: State, context: Dict[str, Any]) -> None:
    """
    Callback function for state changes in the state machine.
    Emits state update events through SocketIO.
    
    Args:
        state: The current state
        context: Context data related to the state change
    """
    socketio.emit(
        "state_update",
        {"state": state.value, "context": context},
    )


def alert_callback(alert: Alert) -> None:
    """
    Callback function for alerts.
    Emits alert events through SocketIO.
    
    Args:
        alert: Alert object to be emitted
    """
    socketio.emit(
        "alert_sync",
        alert.to_dict(),
    )


# Instantiate PluginManager and NetworkManager
PluginManager = PluginManager(CONFIG_PATH)
PluginManager.load_config()
NetworkManager = NetworkManager(PluginManager, PluginManager.config, state_change_callback)

# Get the database path from config
db_path = PluginManager.config.get("database_path", "netfang.db")
# Set the database path in the SocketIO handler
socketio_handler.set_db_path(db_path)

init_db(db_path)
PluginManager.load_plugins()

AlertManager = AlertManager(PluginManager, db_path, alert_callback)

# Register plugin routes (for plugins that provide blueprints) immediately
for plugin in PluginManager.plugins.values():
    if hasattr(plugin, "register_routes"):
        plugin.register_routes(app)

asyncio.run(NetworkManager.start())  # Start the NetworkManager


def cleanup_resources() -> None:
    """Clean up resources when the application exits."""
    if NetworkManager:
        asyncio.run(NetworkManager.stop())


def login_required(f: Callable) -> Callable:
    """
    Decorator that enforces user authentication.
    
    Args:
        f: The function to decorate
        
    Returns:
        The decorated function
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not session.get('logged_in'):
            return redirect(url_for('frontpage'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f: Callable) -> Callable:
    """
    Decorator that enforces admin authentication.
    
    Args:
        f: The function to decorate
        
    Returns:
        The decorated function
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not session.get('logged_in') or session.get('username') != 'admin':
            abort(403)  # Forbidden - requires admin login
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
def frontpage() -> str:
    """
    Renders the front page of the application.
    
    Returns:
        The rendered template
    """
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    # Get real system information
    data: Dict[str, str] = {
        "hostname": platform.node(),
        "mac_address": "Unknown",
        "ip_address": "192.168.1.1"  # Default fallback
    }
    
    # Try to get the actual MAC address
    try:
        if pi_utils.is_pi():
            # For Raspberry Pi, get the eth0 MAC address if available
            result = subprocess.run(
                ["cat", "/sys/class/net/eth0/address"], 
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                data["mac_address"] = result.stdout.strip().upper()
        else:
            # For non-Pi systems, try a more generic approach
            import uuid
            data["mac_address"] = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                                         for elements in range(0, 48, 8)][::-1]).upper()
    except Exception as e:
        app.logger.error(f"Error getting MAC address: {str(e)}")
    
    # Try to get the actual IP address (preference for ethernet)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a public address to determine which interface would be used
        s.connect(("8.8.8.8", 80))
        data["ip_address"] = s.getsockname()[0]
        s.close()
    except Exception as e:
        app.logger.error(f"Error getting IP address: {str(e)}")
        # Try alternative method to get IP
        try:
            hostname = socket.gethostname()
            data["ip_address"] = socket.gethostbyname(hostname)
        except Exception:
            pass  # Keep the default IP
    
    return render_template("router_home.html", **data)


@app.route("/login", methods=["GET", "POST"])
def login() -> Union[str, Response]:
    """
    Handle login requests.
    
    Returns:
        Redirect to dashboard on success, or login failed page on failure
    """
    if request.method == "GET":
        return redirect(url_for("frontpage"))
    
    if request.content_type == 'application/json':
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")
    else:
        username = request.form.get("username")
        password = request.form.get("password")

    # Get credentials from environment or config
    admin_username = os.environ.get("NETFANG_ADMIN_USER", PluginManager.config.get("admin_username", "admin"))
    admin_password = os.environ.get("NETFANG_ADMIN_PASSWORD", PluginManager.config.get("admin_password"))
    
    # If admin password is not set in environment or config, use hardcoded fallback
    # This should be discouraged in production
    if not admin_password:
        app.logger.warning("No admin password set in environment or config. Using default password!")
        admin_password = "NetFang_Default_Password_2023"  # More secure than "password"
    
    if username == admin_username and password == admin_password:
        session['logged_in'] = True
        session['username'] = username
        return redirect(url_for("dashboard"))
    return render_template("login_failed.html"), 401


@app.route("/dashboard")
@login_required
def dashboard() -> str:
    """
    Render the dashboard page.
    
    Returns:
        The rendered dashboard template
    """
    return render_template("hidden/index.html",
                          hostname=platform.node(),
                          state=NetworkManager.instance.state_machine.current_state.value)


@app.route("/logout")
def logout() -> Response:
    """
    Handle logout requests.
    
    Returns:
        Redirect to frontpage
    """
    session.clear()
    return redirect(url_for('frontpage'))


@app.route("/state")
@login_required
def get_current_state() -> Response:
    """
    Get current state of the application.
    
    Returns:
        JSON response with current state
    """
    return jsonify({"state": NetworkManager.instance.state_machine.current_state.value})


@socketio.on("connect")
def handle_connect() -> Optional[bool]:
    """
    Handle SocketIO connect events.
    
    Returns:
        False if unauthorized, None otherwise
    """
    if not session.get('logged_in'):
        return False
    emit("state_update", {"state": NetworkManager.instance.state_machine.current_state.value,
                          "context": NetworkManager.instance.state_machine.state_context})
    emit("all_alerts", AlertManager.get_alerts(limit_to_this_session=True))
    
    # Send cached output of active processes to the newly connected client
    asyncio.run(socketio_handler.send_cached_output_to_client(request.sid))
    return None


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handle SocketIO disconnect events."""
    # Clean up any user-specific resources or connection state
    pass


@socketio.on("sync_dashboard")
def handle_sync_dashboard() -> Optional[bool]:
    """
    Handle WebSocket sync request from the dashboard.
    This sends all relevant database data to the client.
    
    Returns:
        False if unauthorized, None otherwise
    """
    if not session.get('logged_in'):
        return False
    
    db_path = PluginManager.config.get("database_path", "netfang.db")
    dashboard_data = get_dashboard_data(db_path)
    emit("dashboard_data", dashboard_data)
    return None


@app.route("/update", methods=["POST"])
@admin_required
def update_service() -> Response:
    """
    Restart the netfang service using systemctl.
    Requires admin privileges.
    
    Returns:
        JSON response with result of restart operation
    """
    try:
        # Check if running in a Linux environment
        if not pi_utils.is_linux():
            return jsonify({"error": "Service restart only supported on Linux systems"}), 400
        
        # Execute the systemctl restart command
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "netfang.service"], 
            capture_output=True, 
            text=True, 
            check=False
        )
        
        if result.returncode == 0:
            return jsonify({
                "status": "success",
                "message": "Netfang service restarted successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"Failed to restart service: {result.stderr}"
            }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }), 500


@app.route("/plugins", methods=["GET"])
@login_required
def list_plugins() -> Response:
    """
    List all available plugins and their enabled status.
    
    Returns:
        JSON response with list of plugins
    """
    response: List[Dict[str, Any]] = []
    for plugin_name, plugin_obj in PluginManager.plugins.items():
        response.append({
            "name": plugin_name,
            "enabled": _is_plugin_enabled(plugin_name),
        })
    return jsonify(response)


@app.route("/plugins/enable", methods=["POST"])
@admin_required
def enable_plugin() -> Response:
    """
    Enable a plugin.
    
    Returns:
        JSON response with result of operation
    """
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"error": "No plugin_name provided"}), 400
    if PluginManager.enable_plugin(plugin_name):
        _set_plugin_enabled_in_config(plugin_name, True)
        return jsonify({"status": f"{plugin_name} enabled"}), 200
    else:
        return jsonify({"error": f"Failed to enable {plugin_name}, does the plugin exist?"}), 404


@app.route("/favicon.ico", methods=["GET"])
def favicon() -> Response:
    """
    Serve favicon.
    
    Returns:
        The favicon file
    """
    return send_from_directory(os.path.join(app.root_path, 'static'), 'router_logo.png',
                               mimetype='image/vnd.microsoft.icon')


@app.route("/plugins/disable", methods=["POST"])
@admin_required
def disable_plugin() -> Response:
    """
    Disable a plugin.
    
    Returns:
        JSON response with result of operation
    """
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"error": "No plugin_name provided"}), 400
    if PluginManager.disable_plugin(plugin_name):
        _set_plugin_enabled_in_config(plugin_name, False)
        return jsonify({"status": f"{plugin_name} disabled"}), 200
    else:
        return jsonify({"error": f"Failed to disable {plugin_name}, does the plugin exist?"}), 404


def _is_plugin_enabled(plugin_name: str) -> bool:
    """
    Check if a plugin is enabled in the configuration.
    
    Args:
        plugin_name: The name of the plugin to check
        
    Returns:
        True if the plugin is enabled, False otherwise
    """
    d_conf = PluginManager.config.get("default_plugins", {})
    o_conf = PluginManager.config.get("optional_plugins", {})
    pl_lower = plugin_name.lower()
    if pl_lower in d_conf:
        return d_conf[pl_lower].get("enabled", True)
    elif pl_lower in o_conf:
        return o_conf[pl_lower].get("enabled", False)
    return False


def _set_plugin_enabled_in_config(plugin_name: str, enabled: bool) -> None:
    """
    Set a plugin's enabled status in the configuration.
    
    Args:
        plugin_name: The name of the plugin to set
        enabled: Whether the plugin should be enabled
    """
    pl_lower = plugin_name.lower()
    d_conf = PluginManager.config.get("default_plugins", {})
    o_conf = PluginManager.config.get("optional_plugins", {})
    if pl_lower in d_conf:
        d_conf[pl_lower]["enabled"] = enabled
    elif pl_lower in o_conf:
        o_conf[pl_lower]["enabled"] = enabled
    PluginManager.save_config()


@app.route("/api/network-event", methods=["POST"])
def api() -> Response:
    """
    API endpoint for receiving network state updates.
    
    Returns:
        JSON response with result of operation
    """
    # Check for X-Forwarded-For header to prevent header spoofing
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    remote_addr = request.remote_addr
    
    # Only allow connections from localhost or trusted proxies
    if not (remote_addr in ('127.0.0.1', '::1') or 
            (x_forwarded_for and x_forwarded_for.split(',')[0].strip() in ('127.0.0.1', '::1'))):
        return jsonify({"error": "Unauthorized access. This endpoint requires authentication."}), 403

    # Validate request JSON
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    event_data = request.get_json()
    event_type = event_data.get("event_type")
    interface_name = event_data.get("interface_name")
    
    if not event_type or not interface_name:
        return jsonify({"error": "Missing required fields: event_type, interface_name"}), 400

    if event_type == "connected":
        NetworkManager.handle_network_connection(interface_name)
    elif event_type == "disconnected":
        NetworkManager.handle_network_disconnection()
    elif event_type == "cable_inserted":
        NetworkManager.handle_cable_inserted(interface_name)
    else:
        return jsonify({"error": "Invalid event type", "event_type": event_type, "interface_name": interface_name}), 400
    return jsonify({"status": "Event processed", "event_type": event_type, "interface_name": interface_name}), 200


if __name__ == "__main__":
    # Use gunicorn for production deployment
    # For development only:
    from waitress import serve
    app.logger.warning("Starting development server. NOT RECOMMENDED FOR PRODUCTION USE!")
    serve(app, host="0.0.0.0", port=8080, threads=4)
