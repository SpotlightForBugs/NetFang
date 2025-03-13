# netfang/plugins/base_plugin.py

from abc import ABC, abstractmethod
from typing import Any, Dict


class BasePlugin(ABC):
    """
    Abstract base class for all NetFang plugins.
    """
    name: str = "BasePlugin"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config

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

    def on_new_network_connected(self, mac: str, name: str) -> None:
        pass

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        pass

    def on_disconnected(self) -> None:
        """Triggered when the network is disconnected from the observed network."""
        pass

    def on_alerting(self, message: str) -> None:
        """Triggered when there is an alert message to display. We loop it through all plugins in case one wants to display it."""
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

    def on_connected_blacklisted(self, mac_address="", ssid="", *args, **kwargs):
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
        """
        pass
