# netfang/plugins/optional/plugin_macchanger.py

from typing import Any, Dict

from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


class MacChangerPlugin(BasePlugin):
    name = "MacChanger"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "MacChanger enabled")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "MacChanger disabled")

    def change_mac(self) -> None:
        """
        Change the MAC address using macchanger (placeholder).
        """
        plugin_cfg = self.config.get("plugin_config", {})
        interface = plugin_cfg.get("interface", "wlan0")
        print(f"[{self.name}] Changing MAC on interface {interface}...")
        add_plugin_log(self.config["database_path"], self.name, f"Changed MAC on {interface}")
        # Example: subprocess.run(["macchanger", "-r", interface])
