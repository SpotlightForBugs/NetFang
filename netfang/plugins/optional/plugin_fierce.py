# netfang/plugins/optional/plugin_fierce.py

from typing import Any, Dict

from flask import Blueprint, request, jsonify

from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


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
        Run the fierce scan on a given domain (placeholder).
        """
        db_path = self.config["database_path"]
        print(f"[{self.name}] Running fierce on domain: {domain}...")
        add_plugin_log(db_path, self.name, f"Fierce run on {domain}")
        # Example: subprocess.run(["fierce", "--domain", domain])

    def register_routes(self, app: Any) -> None:
        """
        Register the routes for the Fierce plugin.
        """
        bp = Blueprint("fierce", __name__, url_prefix="/fierce")

        @bp.route("/run", methods=["POST"])
        def run():
            data = request.get_json() or {}
            domain = data.get("domain", "")
            if not domain:
                return jsonify({"error": "No domain provided"}), 400
            self.run_fierce(domain)
            return jsonify({"status": f"Fierce scan on {domain} started"}), 200

        app.register_blueprint(bp)
