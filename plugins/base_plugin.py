# netfang/plugins/base_plugin.py

from abc import ABC, abstractmethod
from typing import Any, Dict

class BasePlugin(ABC):
    """
    Abstract base class for NetFang plugins.
    """
    name: str = "BasePlugin"

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        :param config: Plugin-specific config (may include 'plugin_config', 'database_path', etc.)
        """
        self.config: Dict[str, Any] = config

    @abstractmethod
    def on_setup(self) -> None:
        """
        Called once after the plugin is loaded (before enable/disable).
        """
        pass

    @abstractmethod
    def on_enable(self) -> None:
        """
        Called when the plugin is enabled in config.
        """
        pass

    @abstractmethod
    def on_disable(self) -> None:
        """
        Called when the plugin is disabled.
        """
        pass

    # Event callbacks
    def on_home_network_connected(self) -> None:
        pass

    def on_new_network_connected(self, mac: str, name: str) -> None:
        pass

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        pass
