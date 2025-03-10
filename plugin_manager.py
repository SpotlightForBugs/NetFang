# netfang/plugin_manager.py

import importlib
import json
import os
from typing import Any, Dict, List, Optional, Union

from netfang.plugins.base_plugin import BasePlugin

def _expand_env_in_config(obj: Any) -> Any:
    """
    Recursively expand any config values that match "env:VAR_NAME"
    into os.environ[VAR_NAME] (defaulting to "" if not set).
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            obj[k] = _expand_env_in_config(v)
        return obj
    elif isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = _expand_env_in_config(obj[i])
        return obj
    elif isinstance(obj, str):
        if obj.startswith("env:"):
            var_name = obj.split(":", 1)[1]
            return os.environ.get(var_name, "")
        else:
            return obj
    else:
        return obj

class PluginManager:
    def __init__(self, config_path: str) -> None:
        self.config_path: str = config_path
        self.config: Dict[str, Any] = {}
        self.plugins: Dict[str, BasePlugin] = {}  # key = plugin's .name

    def load_config(self) -> None:
        with open(self.config_path, 'r') as f:
            raw_config = json.load(f)
        # Expand environment variables in config
        self.config = _expand_env_in_config(raw_config)

    def save_config(self) -> None:
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def load_plugins(self) -> None:
        """
        1) Discover plugin files in defaults/optional
        2) Instantiate plugin classes
        3) on_setup()
        4) Apply enable/disable
        """
        db_path = self.config.get("database_path", "netfang.db")

        # Default plugins
        default_dir = os.path.join(os.path.dirname(__file__), "plugins", "defaults")
        default_conf = self.config.get("default_plugins", {})
        self._load_plugins_from_dir(default_dir, default_conf, db_path)

        # Optional plugins
        optional_dir = os.path.join(os.path.dirname(__file__), "plugins", "optional")
        optional_conf = self.config.get("optional_plugins", {})
        self._load_plugins_from_dir(optional_dir, optional_conf, db_path)

        # on_setup
        for plugin in self.plugins.values():
            plugin.on_setup()

        # enable/disable
        self._apply_enable_disable()

    def _load_plugins_from_dir(self, directory: str, plugin_config: Dict[str, Any], db_path: str) -> None:
        if not os.path.exists(directory):
            return

        for filename in os.listdir(directory):
            if filename.startswith("plugin_") and filename.endswith(".py"):
                module_name = filename[:-3]  # strip .py
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
        # Default
        d_conf = self.config.get("default_plugins", {})
        for name, conf in d_conf.items():
            plugin_obj = self.get_plugin_by_name(name)
            if plugin_obj:
                if conf.get("enabled", True):
                    self.enable_plugin(plugin_obj.name)
                else:
                    self.disable_plugin(plugin_obj.name)

        # Optional
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

    def enable_plugin(self, plugin_name: str) -> None:
        plugin_obj = self.get_plugin_by_name(plugin_name)
        if plugin_obj:
            # dependencies
            deps = self._get_plugin_dependencies(plugin_name)
            for d in deps:
                self._satisfy_dependency(d)

            plugin_obj.on_enable()

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
        """
        For example: "plugins.defaults.arpscan.run_arpscan"
        => we call run_arpscan() in the ArpScan plugin.
        """
        parts = dependency.split(".")
        if len(parts) == 3:
            # e.g. ["plugins", "defaults", "arpscan.run_arpscan"]
            last_part = parts[2]  # "arpscan.run_arpscan"
            if "." in last_part:
                plugin_name, method_name = last_part.split(".", 1)
                plugin_obj = self.get_plugin_by_name(plugin_name)
                if plugin_obj:
                    method = getattr(plugin_obj, method_name, None)
                    if callable(method):
                        method()

    # Event Dispatch
    def on_home_network_connected(self) -> None:
        for p in self.plugins.values():
            p.on_home_network_connected()

    def on_new_network_connected(self, mac: str, name: str) -> None:
        for p in self.plugins.values():
            p.on_new_network_connected(mac, name)

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        for p in self.plugins.values():
            p.on_known_network_connected(mac, name, is_blacklisted)
