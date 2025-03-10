# netfang/plugins/optional/plugin_pushover.py

import os
import requests
from typing import Any, Dict
from netfang.plugins.base_plugin import BasePlugin
from netfang.db import add_plugin_log

class PushoverPlugin(BasePlugin):
    name = "Pushover"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "Pushover plugin enabled")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "Pushover plugin disabled")

    def send_alert(self, message: str) -> None:
        """
        Send an alert via Pushover using credentials from plugin_config.
        """
        plugin_cfg = self.config.get("plugin_config", {})
        api_token = plugin_cfg.get("api_token", "")
        user_key = plugin_cfg.get("user_key", "")

        if not api_token or not user_key:
            print(f"[{self.name}] Missing Pushover credentials.")
            return

        add_plugin_log(self.config["database_path"], self.name, f"Sending Pushover alert: {message}")

        # Example:
        # requests.post("https://api.pushover.net/1/messages.json", data={
        #     "token": api_token,
        #     "user": user_key,
        #     "message": message
        # })
