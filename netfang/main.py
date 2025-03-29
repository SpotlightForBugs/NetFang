import asyncio
import datetime
import os
import platform
import subprocess
import sys
import socket
from functools import wraps
from platform import system

from flask import request, jsonify, render_template, session, redirect, url_for, \
    render_template_string, abort, Flask
from flask import send_from_directory
from flask_socketio import SocketIO, emit
from flask_minify import minify
from netfang.alert_manager import AlertManager, Alert
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
    print(e)  # for debugging purposes only
    print("Error tracing is disabled by default. To enable, install the sentry-sdk package.")

app = Flask(__name__)
minify(app=app, html=True, js=True, cssless=True)
socketio = SocketIO(app)
# Set the SocketIO instance in our handler
socketio_handler.set_socketio(socketio)

if pi_utils.is_pi():
    # TODO: EVALUATE SAFETY OF THIS SECRET KEY GENERATION METHOD
    app.secret_key = pi_utils.get_pi_serial()
elif pi_utils.is_linux() and not pi_utils.is_pi():
    app.secret_key = pi_utils.linux_machine_id()
elif sys.platform in ["win32", "cygwin"]:
    app.secret_key = os.environ.get("NETFANG_SECRET_KEY", "SFB{D3f4ult_N37F4N6_S3cr3t_K3y}")
app.config['SESSION_COOKIE_NAME'] = 'NETFANG_SECURE_SESSION'

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def state_change_callback(state, context):
    socketio.emit(
        "state_update",
        {"state": state.value, "context": context},
    )


def alert_callback(alert: Alert):
    socketio.emit(
        "alert_sync",
        alert.to_dict(),
    )


# Instantiate PluginManager and NetworkManager
PluginManager = PluginManager(CONFIG_PATH)
PluginManager.load_config()

# Get the database path from config before initializing NetworkManager
db_path = PluginManager.config.get("database_path", "netfang.db")

# Important: Set the database path in the SocketIO handler BEFORE initializing other components
socketio_handler.set_socketio(socketio)
socketio_handler.set_db_path(db_path)
print(f"SocketIO handler initialized with DB path: {db_path}")

# Now initialize NetworkManager after handler is configured
NetworkManager = NetworkManager(PluginManager, PluginManager.config, state_change_callback)

init_db(db_path)
PluginManager.load_plugins()

AlertManager = AlertManager(PluginManager, db_path, alert_callback)

# Register plugin routes (for plugins that provide blueprints) immediately
for plugin in PluginManager.plugins.values():
    if hasattr(plugin, "register_routes"):
        plugin.register_routes(app)

asyncio.run(NetworkManager.start())  # Start the NetworkManager


def cleanup_resources():
    """Clean up resources when the application exits."""
    if NetworkManager:
        asyncio.run(NetworkManager.stop())


## TODO: SECURITY VULNERABILITY - The local_only decorator can be bypassed by setting
# a spoofed X-Forwarded-For header. This allows remote attackers to access restricted
# endpoints. Before release, replace with a login system (needs to generate the password somehow though)
def local_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow both IPv4 and IPv6 localhost addresses
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)  # Forbidden
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or session.get('username') != 'admin':
            abort(403)  # Forbidden - requires admin login
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def frontpage():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    # Get real system information
    data = {
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
def login():
    if request.method == "GET":
        return redirect(url_for("frontpage"))
    if request.content_type == 'application/json':
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")
    else:
        username = request.form.get("username")
        password = request.form.get("password")

    # TODO: Implement proper authentication
    if username == "admin" and password == "password":
        session['logged_in'] = True
        session['username'] = username
        return redirect(url_for("dashboard"))
    return render_template("login_failed.html"), 401


@app.route("/dashboard")
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('frontpage'))
    return render_template("hidden/index.html",hostname=platform.node(),state=NetworkManager.instance.state_machine.current_state.value)


@app.route("/state")
def get_current_state():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"state": NetworkManager.instance.state_machine.current_state.value})


@socketio.on("connect")
def handle_connect():
    if not session.get('logged_in'):
        return False
    emit("state_update", {"state": NetworkManager.instance.state_machine.current_state.value,
                          "context": NetworkManager.instance.state_machine.state_context})
    emit("all_alerts", AlertManager.get_alerts(limit_to_this_session=True))
    
    # Send cached output of active processes to the newly connected client
    asyncio.run(socketio_handler.send_cached_output_to_client(request.sid))


@socketio.on("disconnect")
def handle_disconnect():
    # TODO: Handle disconnect or cleanup
    pass


@socketio.on("sync_dashboard")
def handle_sync_dashboard():
    """
    Handle WebSocket sync request from the dashboard.
    This sends all relevant database data to the client.
    """
    if not session.get('logged_in'):
        return False
    
    # Create a debug log when dashboard is synced
    from netfang.db.database import add_plugin_log
    global db_path  # Use the global db_path variable
    add_plugin_log(db_path, "Dashboard", "Dashboard sync requested")
    
    dashboard_data = get_dashboard_data(db_path)
    emit("dashboard_data", dashboard_data)


@app.route("/update", methods=["POST"])
@admin_required
def update_service():
    """
    Restart the netfang service using systemctl.
    Requires admin privileges.
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


@app.route("/reinit", methods=["POST"])
@admin_required
def reinit_netfang():
    """
    Delete the database and restart the NetFang service.
    This completely resets NetFang to its initial state.
    Requires admin privileges.
    """
    try:
        # Get the database path from config
        db_path = PluginManager.config.get("database_path", "netfang.db")
        
        # Ensure the path exists and is a file
        if os.path.isfile(db_path):
            # Delete the database file
            if pi_utils.is_pi():
                # On Raspberry Pi, use sudo to ensure we have permissions
                result = subprocess.run(
                    ["sudo", "rm", db_path], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                if result.returncode == 0:
                    app.logger.info(f"Database file deleted via sudo: {db_path}")
                else:
                    app.logger.error(f"Failed to delete database: {result.stderr}")
            else:
                # On other systems, use regular os.remove
                os.remove(db_path)
                app.logger.info(f"Database file deleted: {db_path}")
            
            # Re-initialize the database with empty tables
            init_db(db_path)
            app.logger.info(f"Database recreated: {db_path}")
        else:
            app.logger.warning(f"Database file not found at {db_path}, creating new one")
            init_db(db_path)
        
        # Check if running in a Linux environment for service restart
        if pi_utils.is_linux():
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
                    "message": "NetFang database deleted and service restarted successfully"
                })
            else:
                return jsonify({
                    "status": "partial",
                    "message": f"Database reset but service restart failed: {result.stderr}"
                }), 500
        else:
            # For non-Linux systems, just return success for the database reset
            return jsonify({
                "status": "success",
                "message": "NetFang database reset successfully. Please restart the application manually."
            })
            
    except Exception as e:
        app.logger.error(f"Error during NetFang reinitialization: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }), 500


@app.route("/plugins", methods=["GET"])
def list_plugins():
    response = []
    for plugin_name, plugin_obj in PluginManager.plugins.items():
        response.append({
            "name": plugin_name,
            "enabled": _is_plugin_enabled(plugin_name),
        })
    return jsonify(response)


@app.route("/plugins/enable", methods=["POST"])
def enable_plugin():
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"error": "No plugin_name provided"}), 400
    if PluginManager.enable_plugin(plugin_name):
        _set_plugin_enabled_in_config(plugin_name, True)
        return jsonify({"status": f"{plugin_name} enabled"}), 200
    else:
        return jsonify({"error": f"Failed to enable {plugin_name}, does the plugin exist?"}), 200


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'router_logo.png',
                               mimetype='image/vnd.microsoft.icon')


@app.route('/api/version', methods=['GET'])
@admin_required
def get_version():
    """
    API endpoint to fetch the current git commit hash and return it as JSON.
    """
    try:
        # Run the git command to get the commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True, # Raise an exception if the command fails
            encoding='utf-8'
        )
        # Get the hash, removing any trailing newline
        commit_hash = result.stdout.strip()
        return jsonify({'version': commit_hash})
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        # Handle cases where git command fails or git is not installed
        print(f"Error getting git hash: {e}")
        # Return an error response if the hash couldn't be retrieved
        return jsonify({'error': 'Could not retrieve version information'}), 500


@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('frontpage'))

@app.route("/plugins/disable", methods=["POST"])
def disable_plugin():
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"error": "No plugin_name provided"}), 400
    if PluginManager.disable_plugin(plugin_name):
        _set_plugin_enabled_in_config(plugin_name, False)
        return jsonify({"status": f"{plugin_name} disabled"}), 200
    else:
        return jsonify({"error": f"Failed to disable {plugin_name}, does the plugin exist?"}), 200


def _is_plugin_enabled(plugin_name: str) -> bool:
    d_conf = PluginManager.config.get("default_plugins", {})
    o_conf = PluginManager.config.get("optional_plugins", {})
    pl_lower = plugin_name.lower()
    if pl_lower in d_conf:
        return d_conf[pl_lower].get("enabled", True)
    elif pl_lower in o_conf:
        return o_conf[pl_lower].get("enabled", False)
    return False


def _set_plugin_enabled_in_config(plugin_name: str, enabled: bool) -> None:
    pl_lower = plugin_name.lower()
    d_conf = PluginManager.config.get("default_plugins", {})
    o_conf = PluginManager.config.get("optional_plugins", {})
    if pl_lower in d_conf:
        d_conf[pl_lower]["enabled"] = enabled
    elif pl_lower in o_conf:
        o_conf[pl_lower]["enabled"] = enabled
    PluginManager.save_config()


@local_only
@app.route("/api/network-event", methods=["POST"])
def api():
    """The Api endpoint is used to receive state updates"""

    event_type = request.json["event_type"]
    interface_name = request.json["interface_name"]
    if event_type == "connected":
        NetworkManager.handle_network_connection(interface_name)
    elif event_type == "disconnected":
        NetworkManager.handle_network_disconnection()
    elif event_type == "cable_inserted":
        NetworkManager.handle_cable_inserted(interface_name)
    else:
        return jsonify({"error": "Invalid event type", "event_type": event_type, "interface_name": interface_name}), 400
    return jsonify({"status": "Event processed", "event_type": event_type, "interface_name": interface_name}), 200


@app.route("/test/register-action", methods=["GET"])
@admin_required
def test_register_action():
    """
    Test endpoint to register a simple action.
    This helps diagnose UI action display issues.
    """
    try:
        # Create a simple test action
        action_data = {
            "plugin_name": "TestPlugin",
            "action_id": "test_action_" + str(int(datetime.datetime.now().timestamp())),
            "action_name": "Test Action",
            "description": "This is a test action to verify the action registration system",
            "target_type": "system",
            "icon": "fa-vial"
        }
        
        # Emit the action registration event
        socketio.emit('register_action', action_data)
        
        # Also log this action registration for debugging
        from netfang.db.database import add_plugin_log
        add_plugin_log(db_path, "TestPlugin", f"Registered test action: {action_data['action_id']}")
        
        return jsonify({
            "status": "success",
            "message": "Test action registered successfully",
            "action": action_data
        })
    except Exception as e:
        app.logger.error(f"Error registering test action: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500


if __name__ == "__main__":
    # TODO: this is not safe for production, add Gunicorn or similar
    socketio.run(app=app, host="0.0.0.0", port=80, debug=False, allow_unsafe_werkzeug=True)
