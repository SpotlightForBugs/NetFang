# netfang/plugins/optional/plugin_debug.py

import subprocess
from typing import Any, Dict
from netfang.plugins.base_plugin import BasePlugin
from netfang.db import add_plugin_log

class DebugPlugin(BasePlugin):
    name = "Debug"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        print(f"[{self.name}] __init__ complete.")

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "Debug received enable signal")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "Debug received disable signal")

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        print(f"[{self.name}] Debug received known network connection event: {mac=}, {name=}, {is_blacklisted=}")

    def on_new_network_connected(self, mac: str, name: str) -> None:
        print(f"[{self.name}] Debug received new network connection event: {mac=}, {name=}")

    def on_home_network_connected(self) -> None:
        print(f"[{self.name}] Debug received home network connection event")


