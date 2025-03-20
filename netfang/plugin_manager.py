# netfang/plugin_manager.py

import importlib
import json
import os
from typing import Any, Dict, List, Optional

from netfang.plugins.base_plugin import BasePlugin


def _expand_env_in_config(obj: Any) -> Any:
    """
    Recursively expand config strings of the form "env:VAR_NAME" using os.environ.
    """
    if isinstance(obj, dict):
        return {k: _expand_env_in_config(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_in_config(i) for i in obj]
    elif isinstance(obj, str) and obj.startswith("env:"):
        var_name = obj.split(":", 1)[1]
        return os.environ.get(var_name, "")
    else:
        return obj

class PluginManager:
    def __init__(self, config_path: str) -> None:
        self.config_path: str = config_path
        self.config: Dict[str, Any] = {}
        self.plugins: Dict[str, BasePlugin] = {}

    def load_config(self) -> None:
        with open(self.config_path, 'r') as f:
            raw_config = json.load(f)
        self.config = _expand_env_in_config(raw_config)

    def save_config(self) -> None:
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def load_plugins(self) -> None:
        """
        Discover, instantiate, and set up plugins.
        """
        db_path = self.config.get("database_path", "netfang.db")
        # Load default plugins
        default_dir = os.path.join(os.path.dirname(__file__), "plugins", "defaults")
        default_conf = self.config.get("default_plugins", {})
        self._load_plugins_from_dir(default_dir, default_conf, db_path)
        # Load optional plugins
        optional_dir = os.path.join(os.path.dirname(__file__), "plugins", "optional")
        optional_conf = self.config.get("optional_plugins", {})
        self._load_plugins_from_dir(optional_dir, optional_conf, db_path)

        for plugin_name, plugin in self.plugins.items():
            # Only set up plugins that will be enabled
            d_conf = self.config.get("default_plugins", {})
            o_conf = self.config.get("optional_plugins", {})
            pl_lower = plugin_name.lower()

            is_enabled = False
            if pl_lower in d_conf:
                is_enabled = d_conf[pl_lower].get("enabled", True)
            elif pl_lower in o_conf:
                is_enabled = o_conf[pl_lower].get("enabled", False)

            if is_enabled:
                plugin.on_setup()


        self._apply_enable_disable()

    def _load_plugins_from_dir(self, directory: str, plugin_config: Dict[str, Any], db_path: str) -> None:
        if not os.path.exists(directory):
            return
        for filename in os.listdir(directory):
            if filename.startswith("plugin_") and filename.endswith(".py"):
                module_name = filename[:-3]
                module_path = f"netfang.plugins.{os.path.basename(directory)}.{module_name}"
                module = importlib.import_module(module_path)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                        plugin_class = attr
                        p_name = plugin_class.name.lower()
                        conf_entry = plugin_config.get(p_name, {})
                        if "plugin_config" not in conf_entry:
                            conf_entry["plugin_config"] = {}
                        conf_entry["database_path"] = db_path
                        instance = plugin_class(conf_entry)
                        self.plugins[plugin_class.name] = instance

    def _apply_enable_disable(self) -> None:
        # For default plugins
        d_conf = self.config.get("default_plugins", {})
        for name, conf in d_conf.items():
            plugin_obj = self.get_plugin_by_name(name)
            if plugin_obj:
                if conf.get("enabled", True):
                    self.enable_plugin(plugin_obj.name)
                else:
                    self.disable_plugin(plugin_obj.name)
        # For optional plugins
        o_conf = self.config.get("optional_plugins", {})
        for name, conf in o_conf.items():
            plugin_obj = self.get_plugin_by_name(name)
            if plugin_obj:
                if conf.get("enabled", False):
                    self.enable_plugin(plugin_obj.name)
                else:
                    self.disable_plugin(plugin_obj.name)

    def get_plugin_by_name(self, plugin_name: str) -> Optional[BasePlugin]:
        for k, v in self.plugins.items():
            if k.lower() == plugin_name.lower():
                return v
        return None

    def enable_plugin(self, plugin_name: str) -> bool:
        plugin_obj = self.get_plugin_by_name(plugin_name)
        if plugin_obj:
            # Satisfy dependencies if any
            deps = self._get_plugin_dependencies(plugin_name)
            for d in deps:
                self._satisfy_dependency(d)
            plugin_obj.on_enable()
            return True
        return False

    def disable_plugin(self, plugin_name: str) -> None:
        plugin_obj = self.get_plugin_by_name(plugin_name)
        if plugin_obj:
            plugin_obj.on_disable()

    def _get_plugin_dependencies(self, plugin_name: str) -> List[str]:
        d_conf = self.config.get("default_plugins", {})
        o_conf = self.config.get("optional_plugins", {})
        plugin_conf: Dict[str, Any] = {}
        p_lower = plugin_name.lower()
        if p_lower in d_conf:
            plugin_conf = d_conf[p_lower]
        elif p_lower in o_conf:
            plugin_conf = o_conf[p_lower]
        return plugin_conf.get("dependencies", [])

    def _satisfy_dependency(self, dependency: str) -> None:
        parts = dependency.split(".")
        if len(parts) != 4:
            print(f"Invalid dependency format: {dependency}")
            return
        plugin_name = parts[2]
        method_name = parts[3]
        plugin_obj = self.get_plugin_by_name(plugin_name)
        if plugin_obj:
            method = getattr(plugin_obj, method_name, None)
            if callable(method):
                method()
            else:
                print(f"Method {method_name} not found in plugin {plugin_name}")
        else:
            print(f"Plugin {plugin_name} not found")

    # Event dispatchers
    def on_home_network_connected(self) -> None:
        for p in self.plugins.values():
            p.on_home_network_connected()

    def on_new_network_connected(self, mac: str, name: str) -> None:
        for p in self.plugins.values():
            p.on_new_network_connected(mac, name)

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        for p in self.plugins.values():
            p.on_known_network_connected(mac, name, is_blacklisted)

    def on_disconnected(self):
        for p in self.plugins.values():
            p.on_disconnected()

    def on_alerting(self, message: str):
        for p in self.plugins.values():
            p.on_alerting(message)

    def on_reconnecting(self):
        for p in self.plugins.values():
            p.on_connected_home()

    def on_connected_blacklisted(self, mac_address="", ssid="", *args, **kwargs):
        for p in self.plugins.values():
            p.on_connected_blacklisted(mac_address, ssid, *args, **kwargs)

    def on_connected_known(self):
        for p in self.plugins.values():
            p.on_connected_known()

    def on_waiting_for_network(self):
        for p in self.plugins.values():
            p.on_waiting_for_network()

    def on_connecting(self):
        for p in self.plugins.values():
            p.on_connecting()

    def on_scanning_in_progress(self):
        for p in self.plugins.values():
            p.on_scanning_in_progress()

    def on_scan_completed(self):
        for p in self.plugins.values():
            p.on_scan_completed()

    def on_connected_new(self):
        for p in self.plugins.values():
            p.on_connected_new()

    def perform_action(self, args: list) -> None:
        for p in self.plugins.values():
            p.perform_action(args)
