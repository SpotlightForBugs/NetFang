import asyncio
import os
import platform
import sys
from functools import wraps
from platform import system

from flask import request, jsonify, render_template, session, redirect, url_for, render_template_string, abort, Flask
from flask import send_from_directory
from flask_socketio import SocketIO, emit

from netfang.api import pi_utils
from netfang.db import init_db
from netfang.plugin_manager import PluginManager
from netfang.state_machine import NetworkManager, State  # Note: NetworkManager here is our refactored version

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
socketio = SocketIO(app)
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


# Instantiate PluginManager and NetworkManager
PluginManager = PluginManager(CONFIG_PATH)
PluginManager.load_config()
NetworkManager = NetworkManager(PluginManager, PluginManager.config, state_change_callback)

# Load configuration, initialize database, and load plugins BEFORE starting the server
PluginManager.load_config()
init_db(PluginManager.config.get("database_path", "netfang.db"))
PluginManager.load_plugins()

# Register plugin routes (for plugins that provide blueprints) immediately
for plugin in PluginManager.plugins.values():
    if hasattr(plugin, "register_routes"):
        plugin.register_routes(app)

asyncio.run(NetworkManager.start())  # Start the NetworkManager


def cleanup_resources():
    """Clean up resources when the application exits."""
    if NetworkManager:
        asyncio.run(NetworkManager.stop())


def local_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow both IPv4 and IPv6 localhost addresses
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)  # Forbidden
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def frontpage():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template("router_home.html")


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
    return render_template("hidden/index.html")


@app.route("/state")
def get_current_state():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"state": NetworkManager.current_state.value})


@socketio.on("connect")
def handle_connect():
    if not session.get('logged_in'):
        return False
    emit("state_update", {"state": NetworkManager.current_state.value, "context": NetworkManager.state_context})


@socketio.on("disconnect")
def handle_disconnect():
    # TODO: Handle disconnect or cleanup
    pass


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


# ---------------------
# Test Routes
# ---------------------
@app.route("/test", methods=["GET"])
def test_page():
    if not session.get('logged_in'):
        return redirect(url_for('frontpage'))
    """Render a test page with a button for each state."""
    states = list(State)
    return render_template("hidden/test.html", states=enumerate(states))


@app.route("/test/<int:state_num>", methods=["GET"])
def test_state(state_num: int):
    if not session.get('logged_in'):
        return redirect(url_for('frontpage'))
    """
    Force the NetworkManager into a specific state and trigger corresponding plugin callbacks.
    Each state test uses distinct values where needed.
    """
    states = list(State)
    if state_num < 0 or state_num >= len(states):
        return jsonify({"error": f"Invalid state number. Valid numbers are 0 to {len(states) - 1}"}), 400

    new_state = states[state_num]
    status_msg = ""
    if new_state == State.WAITING_FOR_NETWORK:
        NetworkManager._update_state(new_state)
        status_msg = f"State forced to {new_state.value}"
    elif new_state == State.CONNECTING:
        NetworkManager._update_state(new_state)
        status_msg = f"State forced to {new_state.value}"
    elif new_state == State.CONNECTED_HOME:
        home_mac = PluginManager.config.get("network_flows", {}).get("home_network_mac", "AA:BB:CC:11:22:33")
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_home_network_connected()
        status_msg = f"Simulated connection to home network with MAC {home_mac}"
    elif new_state == State.CONNECTED_NEW:
        new_mac = "00:00:00:00:00:01"
        new_ssid = "TestNewNetwork"
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_new_network_connected(new_mac, new_ssid)
        status_msg = f"Simulated connection to new network with MAC {new_mac} and SSID {new_ssid}"
    elif new_state == State.SCANNING_IN_PROGRESS:
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_scanning_in_progress()
        status_msg = f"Simulated scanning in progress."
    elif new_state == State.SCAN_COMPLETED:
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_scan_completed()
        status_msg = f"Simulated scan completed."
    elif new_state == State.CONNECTED_KNOWN:
        known_mac = "00:00:00:00:00:02"
        known_ssid = "TestKnownNetwork"
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_known_network_connected(known_mac, known_ssid, False)
        status_msg = f"Simulated connection to known network with MAC {known_mac} and SSID {known_ssid}"
    elif new_state == State.RECONNECTING:
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_reconnecting()
        status_msg = f"Simulated reconnecting state."
    elif new_state == State.CONNECTED_BLACKLISTED:
        blacklisted_mac = "DE:AD:BE:EF:CA:FE"
        ssid = "TestBlacklistedNetwork"
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_connected_blacklisted(blacklisted_mac, ssid)
        status_msg = f"Simulated connection to blacklisted network with MAC {blacklisted_mac} and SSID {ssid}"
    elif new_state == State.ALERTING:
        alert_msg = "Test Alert: Something went wrong!"
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_alerting(message=alert_msg)
        status_msg = f"Simulated alerting state with message: {alert_msg}"
    elif new_state == State.DISCONNECTED:
        NetworkManager._update_state(new_state)
        NetworkManager.plugin_manager.on_disconnected()
        status_msg = f"Simulated disconnected state."

    html_result = """
    <html>
      <head><title>State Test Result</title>
      <link rel="stylesheet" href="{{ url_for('static', filename='css/hidden.css') }}">
      </head>
      
      <body>
        <h1>Test Result</h1>
        <p>{{ status_msg }}</p>
        <a href="{{ url_for('test_page') }}">Back to Test Page</a>
        <a href="{{ url_for('dashboard') }}">Back to Dashboard</a>
      </body>
    </html>
    """
    return render_template_string(html_result, status_msg=status_msg)


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


if __name__ == "__main__":
    # TODO: this is not safe for production, add Gunicorn or similar
    socketio.run(app=app, host="0.0.0.0", port=80, debug=False, allow_unsafe_werkzeug=True)
