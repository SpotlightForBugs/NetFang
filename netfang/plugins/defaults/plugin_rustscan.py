# netfang/plugins/defaults/plugin_rustscan.py

from typing import Any, Dict

from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


# TODO: Implement RustScan plugin and adapt it to the NetFang plugin system.

class RustScanPlugin(BasePlugin):
    name = "RustScan"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "RustScan enabled")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "RustScan disabled")

    def perform_action(self, args: list) -> None:
        """
        Run Rustscan on a target (placeholder).

        @param args[0]: The plugin name the action is intended for.
        @param args[1]: The Network ID to run the action on.
        @param args[2]: The target to run the action on.
        @param args[3]: The port range to scan, e.g. "1-1000" (optional).
        """
        if args[0] != self.name:
            return

        db_path = self.config["database_path"]
        print(f"[{self.name}] Running rustscan on {args[2]}...")

        add_plugin_log(db_path, self.name, f"Starting RustScan on {args[2]}")

        if args[3]:
            print(
                f"[{self.name}] RustScan system not implemented yet. \nThe command we would run is:\nrustscan -a {args[2]} -p {args[3]}")
        else:
            print(
                f"[{self.name}] RustScan system not implemented yet. \nThe command we would run is:\nrustscan -a {args[2]} (default ports)")
