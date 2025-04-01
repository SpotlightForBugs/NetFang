# netfang/plugins/base_plugin.py

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from netfang.alert_manager import Alert


class BasePlugin(ABC):
    """
    Abstract base class for all NetFang plugins.
    """
    name: str = "BasePlugin"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config
        self.callbacks: List[Callable] = []

    def register_callback(self, callback: Callable) -> None:
        """Register a callback function to be executed by the plugin."""
        self.callbacks.append(callback)

    def execute_callbacks(self, *args, **kwargs) -> None:
        """Execute all registered callback functions with the provided arguments."""
        for callback in self.callbacks:
            callback(*args, **kwargs)
            
    @abstractmethod
    def on_setup(self) -> None:
        """Called once after plugin is loaded."""
        pass

    @abstractmethod
    def on_enable(self) -> None:
        """Called when the plugin is enabled."""
        pass

    @abstractmethod
    def on_disable(self) -> None:
        """Called when the plugin is disabled."""
        pass

    # Event callbacks
    def on_home_network_connected(self) -> None:
        pass

    def on_new_network_connected(self, mac: str) -> None:
        pass

    def on_known_network_connected(self, mac: str) -> None:
        """Triggered when the network is connected to a known network that is not blacklisted."""
        pass

    def on_disconnected(self) -> None:
        """Triggered when the network is disconnected from the observed network."""
        pass

    def on_alerting(self, alert: Alert) -> None:
        """Triggered when there is an alert message to display. We loop it through all plugins in case one wants to display it."""
        pass

    def on_alert_resolved(self, alert: Alert) -> None:
        """Triggered when an alert is resolved."""
        pass

    def on_reconnecting(self) -> None:
        """Triggered when the network connection is lost and the system is attempting to reconnect."""
        pass

    def register_routes(self, app: Any) -> None:
        """
        Optionally, a plugin can register its own Flask routes.
        """
        pass

    def on_connected_home(self):
        pass

    def on_connected_blacklisted(self, mac_address):
        """Triggered when the network is connected to a blacklisted network."""
        pass

    def on_connected_known(self):
        pass

    def on_waiting_for_network(self):
        pass

    def on_connecting(self):
        pass

    def on_scanning_in_progress(self):
        pass

    def on_scan_completed(self):
        pass

    def on_connected_new(self):
        pass

    def perform_action(self, args: list) -> None:
        """
        Perform a specific action based on the provided arguments.
        args[0] is the self.name of the plugin that should perform the action.
        @args[1] is the Network ID for the network
        """
        pass

    def register_action(self, action_id: str, action_name: str, description: str, 
                       target_type: str = "system", target_id: Optional[str] = None, 
                       icon: Optional[str] = None) -> Dict[str, Any]:
        """
        Register an action that can be performed by this plugin.
        This action will be displayed in the UI and can be triggered by the user.
        
        Args:
            action_id: Unique identifier for the action
            action_name: Display name for the action
            description: Description of what the action does
            target_type: Type of target (network, device, system)
            target_id: Optional ID of the specific target
            icon: Optional icon name (FontAwesome class)
            
        Returns:
            Dict containing the action data that was registered
        """
        action_data = {
            "plugin_name": self.name,
            "action_id": action_id,
            "action_name": action_name,
            "description": description,
            "target_type": target_type,
            "target_id": target_id,
        }
        
        if icon:
            action_data["icon"] = icon
            
        # Let the plugin manager handle the registration
        from netfang.plugin_manager import PluginManager
        if PluginManager.instance:
            return PluginManager.instance.register_action(action_data)
        
        return action_data