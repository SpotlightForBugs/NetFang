# netfang/main.py

from flask import Flask, request, jsonify, render_template
import os

from netfang.db import init_db
from netfang.plugin_manager import PluginManager
from netfang.network_manager import NetworkManager
from netfang.plugins.optional.plugin_fierce import FiercePlugin

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Setup plugin manager and network manager
manager = PluginManager(CONFIG_PATH)
network_manager = NetworkManager(manager)

@app.before_first_request
def startup():
    """
    Called once, before the first request. This ensures:
    1) Config is loaded (with environment expansions).
    2) Database is initialized.
    3) Plugins are loaded.
    4) The background flow loop is started.
    """
    manager.load_config()
    init_db(manager.config.get("database_path", "netfang.db"))
    manager.load_plugins()

    # Start the background state-machine loop
    network_manager.start_flow_loop()

@app.teardown_appcontext
def teardown(exception):
    # Potentially stop threads if needed on shutdown
    network_manager.stop_flow_loop()

@app.route("/")
def router_home():
    """
    Render a minimal HTML that looks like a router admin page.
    """
    return render_template("router_home.html")

@app.route("/plugins", methods=["GET"])
def list_plugins():
    """
    Return a JSON list of loaded plugins and their enabled states.
    """
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
    Endpoint to simulate or manually trigger a new network connection event.
    JSON:
    {
      "mac_address": "00:11:22:33:44:55",
      "ssid": "OfficeWifi"
    }
    """
    data = request.get_json() or {}
    mac = data.get("mac_address", "00:11:22:33:44:55")
    ssid = data.get("ssid", "UnknownNetwork")
    network_manager.handle_network_connection(mac, ssid)
    return jsonify({"status": "Connection processed"}), 200

@app.route("/plugins/fierce/run", methods=["POST"])
def run_fierce():
    """
    Manual trigger to run Fierce plugin if it's enabled.
    JSON:
    {
      "domain": "example.com"
    }
    """
    data = request.get_json() or {}
    domain = data.get("domain", "")
    if not domain:
        return jsonify({"error": "No domain provided"}), 400

    # Check if fierce is enabled
    fierce_plugin = manager.get_plugin_by_name("fierce")
    if not fierce_plugin:
        return jsonify({"error": "Fierce plugin not loaded"}), 404

    # If it's disabled, we might allow manual run anyway, or block:
    if not _is_plugin_enabled("fierce"):
        return jsonify({"error": "Fierce plugin is disabled"}), 403

    # Now run fierce
    if isinstance(fierce_plugin, FiercePlugin):
        fierce_plugin.run_fierce(domain)
        return jsonify({"status": f"Fierce scanning {domain} started"}), 200
    return jsonify({"error": "Unexpected plugin type"}), 500

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
    # For production, use gunicorn or similar. Debug=False recommended if stealth is desired.
    app.run(host="0.0.0.0", port=80, debug=False)
