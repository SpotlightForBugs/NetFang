# netfang/main.py

import os

from flask import Flask, request, jsonify, render_template, session, redirect, url_for

from netfang.db import init_db
from netfang.plugin_manager import PluginManager
from netfang.state_machine import NetworkManager, ConnectionState

app = Flask(__name__)
app.secret_key = os.urandom(24) # Required for session management
app.config['SESSION_COOKIE_NAME'] = 'NETFANG_SECURE_SESSION'

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

manager = PluginManager(CONFIG_PATH)
network_manager = NetworkManager(manager)

# Load configuration, initialize database, and load plugins BEFORE starting the server
manager.load_config()
init_db(manager.config.get("database_path", "netfang.db"))
manager.load_plugins()

# Register plugin routes (for plugins that provide blueprints) immediately
for plugin in manager.plugins.values():
    if hasattr(plugin, "register_routes"):
        plugin.register_routes(app)

# Now start the network state-machine loop
network_manager.start_flow_loop()


@app.teardown_appcontext
def teardown(exception):
    network_manager.stop_flow_loop()

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

    #TODO Implement proper authentication
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
    return jsonify({"state": network_manager.current_state.value})


@app.route("/plugins", methods=["GET"])
def list_plugins():
    response = []
    for plugin_name, plugin_obj in manager.plugins.items():
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
    manager.enable_plugin(plugin_name)
    _set_plugin_enabled_in_config(plugin_name, True)
    return jsonify({"status": f"{plugin_name} enabled"}), 200

@app.route("/plugins/disable", methods=["POST"])
def disable_plugin():
    data = request.get_json() or {}
    plugin_name = data.get("plugin_name")
    if not plugin_name:
        return jsonify({"error": "No plugin_name provided"}), 400
    manager.disable_plugin(plugin_name)
    _set_plugin_enabled_in_config(plugin_name, False)
    return jsonify({"status": f"{plugin_name} disabled"}), 200

@app.route("/network/connect", methods=["POST"])
def simulate_network_connection():
    """
    Simulate a network connection event.
    JSON payload: { "mac_address": "00:11:22:33:44:55", "ssid": "OfficeWifi" }
    """
    data = request.get_json() or {}
    mac = data.get("mac_address", "00:11:22:33:44:55")
    ssid = data.get("ssid", "UnknownNetwork")
    network_manager.handle_network_connection(mac, ssid)
    return jsonify({"status": "Connection processed"}), 200

@app.route("/test/<int:state_num>", methods=["GET"])
def test_state(state_num: int):
    """
    Test route to force the NetworkManager into a specific state based on the numeric index
    (in the order defined in ConnectionState). For example, /test/0 forces WAITING_FOR_NETWORK,
    /test/1 forces CONNECTING, etc.
    """
    # Get the list of states in the order defined by the enum.
    states = list(ConnectionState)
    if state_num < 0 or state_num >= len(states):
        return jsonify({"error": f"Invalid state number. Valid numbers are 0 to {len(states)-1}"}), 400
    new_state = states[state_num]
    # Update the state (using the internal _update_state for testing).
    network_manager._update_state(new_state)
    # Optionally, trigger some event callbacks based on the state.
    if new_state == ConnectionState.CONNECTED_HOME:
        network_manager.plugin_manager.on_home_network_connected()
    elif new_state == ConnectionState.CONNECTED_NEW:
        network_manager.plugin_manager.on_new_network_connected("00:00:00:00:00:00", "TestNewNetwork")
    elif new_state == ConnectionState.CONNECTED_KNOWN:
        network_manager.plugin_manager.on_known_network_connected("00:00:00:00:00:00", "TestKnownNetwork", False)
    # You can extend this if/elif block to simulate actions for other states.
    return jsonify({
        "status": f"State forced to {new_state.value}",
        "state_number": state_num
    }), 200

def _is_plugin_enabled(plugin_name: str) -> bool:
    d_conf = manager.config.get("default_plugins", {})
    o_conf = manager.config.get("optional_plugins", {})
    pl_lower = plugin_name.lower()
    if pl_lower in d_conf:
        return d_conf[pl_lower].get("enabled", True)
    elif pl_lower in o_conf:
        return o_conf[pl_lower].get("enabled", False)
    return False

def _set_plugin_enabled_in_config(plugin_name: str, enabled: bool) -> None:
    pl_lower = plugin_name.lower()
    d_conf = manager.config.get("default_plugins", {})
    o_conf = manager.config.get("optional_plugins", {})
    if pl_lower in d_conf:
        d_conf[pl_lower]["enabled"] = enabled
    elif pl_lower in o_conf:
        o_conf[pl_lower]["enabled"] = enabled
    manager.save_config()

if __name__ == "__main__":
    # For production, consider using gunicorn or similar.
    app.run(host="0.0.0.0", port=80, debug=False)
