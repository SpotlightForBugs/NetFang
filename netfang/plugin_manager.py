# netfang/plugin_manager.py

import importlib
import json
import os
import logging
import inspect
from typing import Any, Dict, List, Optional

from netfang.alert_manager import AlertManager, Alert
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
        self.logger = logging.getLogger(__name__)

    def load_config(self) -> None:
        with open(self.config_path, 'r') as f:
            # Load YAML instead of JSON
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

    def get_scanning_plugin_names(self) -> List[str]:
        """
        Returns a list of names of plugins that have scanning capabilities.
        
        Currently identifies plugins that have an on_scanning_in_progress method
        that is not inherited from BasePlugin.
        """
        scanning_plugins = []
        for name, plugin in self.plugins.items():
            if hasattr(plugin, 'on_scanning_in_progress'):
                # Check if method is overridden (not the base class implementation)
                # Use a safer approach to determine if method is overridden
                base_method_code = inspect.getsource(BasePlugin.on_scanning_in_progress)
                try:
                    # Get the source code of the plugin's method
                    plugin_method = getattr(plugin, 'on_scanning_in_progress')
                    plugin_method_code = inspect.getsource(plugin_method)
                    
                    # If the method code is different from base class, it's overridden
                    if plugin_method_code != base_method_code:
                        scanning_plugins.append(name)
                        self.logger.debug(f"Identified scanning plugin: {name}")
                except (TypeError, OSError):
                    # If we can't get the source (e.g., for built-in or C methods),
                    # try another approach: check if method implementation is non-empty
                    try:
                        # Check if method does more than just pass
                        if plugin_method.__code__.co_code != BasePlugin.on_scanning_in_progress.__code__.co_code:
                            scanning_plugins.append(name)
                            self.logger.debug(f"Identified scanning plugin via bytecode: {name}")
                    except (AttributeError, TypeError):
                        # As a fallback, assume it's a scanning plugin if it has the method
                        # This is less precise but won't cause crashes
                        self.logger.debug(f"Assuming {name} is a scanning plugin (fallback detection)")
                        scanning_plugins.append(name)
        
        self.logger.info(f"Found {len(scanning_plugins)} scanning plugins: {', '.join(scanning_plugins)}")
        return scanning_plugins
        
    def perform_plugin_scan(self, plugin_name: str) -> bool:
        """
        Execute a scan using the specified plugin.
        
        Returns:
            True if scan was initiated, False otherwise
        """
        plugin = self.get_plugin_by_name(plugin_name)
        if not plugin:
            self.logger.warning(f"Plugin {plugin_name} not found for scanning")
            return False
            
        try:
            # Get database path
            db_path = self.config.get("database_path", "netfang.db")
            
            # Execute the plugin's scan action
            self.logger.info(f"Initiating scan with plugin {plugin_name}")
            
            # Standard approach for plugins like ArpScan
            if plugin_name.lower() == "arpscan":
                self.perform_action([plugin_name, "localnet", "all"])
            elif plugin_name.lower() == "rustscan":
                self.perform_action([plugin_name, "scan", "all"])
            else:
                # Generic approach for any plugin
                self.perform_action([plugin_name, "scan", "all"])
                
            return True
        except Exception as e:
            self.logger.error(f"Error executing scan with plugin {plugin_name}: {str(e)}")
            return False

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

    def disable_plugin(self, plugin_name: str) -> bool:
        plugin_obj = self.get_plugin_by_name(plugin_name)
        if plugin_obj:
            plugin_obj.on_disable()
            return True
        return False

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

    # TODO: Allow for more complex dependencies (Enabling a plugin only if another plugin is enabled or a shell command etc.)
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

    def on_new_network_connected(self, mac: str) -> None:
        for p in self.plugins.values():
            p.on_new_network_connected(mac)

    def on_known_network_connected(self, mac: str) -> None:
        for p in self.plugins.values():
            p.on_known_network_connected(mac)

    def on_disconnected(self):
        for p in self.plugins.values():
            p.on_disconnected()

    def on_alerting(self, alert:Alert):
        for p in self.plugins.values():
            p.on_alerting(alert)

    def on_alert_resolved(self, alert:Alert):
        for p in self.plugins.values():
            p.on_alert_resolved(alert)

    def on_reconnecting(self):
        for p in self.plugins.values():
            p.on_connected_home()

    def on_connected_blacklisted(self, mac_address):
        for p in self.plugins.values():
            p.on_connected_blacklisted(mac_address)

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

    def is_device_enabled(self, param):
        # following structure is assumed: "hardware": {"device_name": {"enabled": true|false}}
        return self.config.get("hardware", {}).get(param, {}).get("enabled", False)

    def notify_scan_complete(self, plugin_name: str) -> None:
        """
        Notify the state machine that a scan has completed.
        This should be called by plugins when they finish scanning.
        
        Args:
            plugin_name: Name of the plugin that completed scanning
        """
        try:
            # Get the StateMachine instance from NetworkManager instead
            from netfang.network_manager import NetworkManager
            
            if NetworkManager.instance and NetworkManager.instance.state_machine:
                NetworkManager.instance.state_machine.mark_scan_complete(plugin_name)
            else:
                self.logger.warning(f"Cannot notify scan completion: NetworkManager instance not available")
        except Exception as e:
            self.logger.error(f"Error notifying scan completion: {str(e)}")
