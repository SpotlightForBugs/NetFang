# netfang/plugins/optional/plugin_fierce.py

import subprocess
from typing import Any, Dict
from netfang.plugins.base_plugin import BasePlugin
from netfang.db import add_plugin_log

class FiercePlugin(BasePlugin):
    name = "Fierce"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "Fierce enabled")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "Fierce disabled")

    def run_fierce(self, domain: str) -> None:
        """
        Manual run triggered via the Web UI: e.g. /plugins/fierce/run
        """
        db_path = self.config["database_path"]
        print(f"[{self.name}] Running fierce on domain={domain}... (placeholder)")
        add_plugin_log(db_path, self.name, f"Fierce run on {domain}")

        # Example:
        # subprocess.run(["fierce", "--domain", domain], capture_output=True, text=True)
