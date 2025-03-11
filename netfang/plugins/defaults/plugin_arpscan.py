import re
import subprocess
from typing import Any, Dict

import netfang.db
from netfang.db import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


def parse_arp_scan(output: str, mode: str) -> Dict[str, Any]:
    parsed_result = {
        "interface": None,
        "mac_address": None,
        "ipv4": None,
        "devices": []
    }

    lines = output.strip().split("\n")

    # Extract interface information
    interface_match = re.search(r"Interface: (\S+), type: \S+, MAC: (\S+), IPv4: (\S+)", lines[0])
    if interface_match:
        parsed_result["interface"] = interface_match.group(1)
        parsed_result["mac_address"] = interface_match.group(2)
        parsed_result["ipv4"] = interface_match.group(3)

    # Process each detected device
    for line in lines[2:]:
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+([\w:]+)\s+(.*)", line)
        if match:
            ip_address, mac_address, vendor = match.groups()
            device = {"ip": ip_address, "mac": mac_address, "vendor": vendor.strip()}

            # Check for duplicates
            if "(DUP:" in vendor:
                vendor = vendor.split(" (DUP:")[0]
                device["vendor"] = vendor.strip()
                device["duplicate"] = True
            else:
                device["duplicate"] = False

            parsed_result["devices"].append(device)

    return parsed_result


class ArpScanPlugin(BasePlugin):
    name = "ArpScan"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

    def on_setup(self) -> None:
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        print(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpScan enabled")

    def on_disable(self) -> None:
        print(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpScan disabled")

    def perform_action(self, args: list) -> None:


        """
        Run an arp-scan command.
        args[0] for checking if we should perform the action.
        This way, we can easily hook into other actions.

        args[1] should be the mode to run in. (e.g. localnet)
        args[2] is the network-id (for the database)
        """
        if args[0] == self.name:
            print(f"[{self.name}] Running arp-scan...")
            db_path = self.config["database_path"]

            if args[1] == "localnet":
                # Run arp-scan -l using subprocess
                # if we are not in linux, then print the command we would have run

                result = subprocess.run(["arp-scan", "-l"], capture_output=True, text=True)
                parsed_data = parse_arp_scan(result.stdout, mode="localnet")
                # save the result to the database
                print(f"[{self.name}] Found {len(parsed_data['devices'])} devices on {parsed_data['interface']}")
                for device in parsed_data["devices"]:
                    netfang.db.add_or_update_device(db_path, device["ip"], device["mac"], hostname=None, services=None,
                                                    network_id=args[2], vendor=device["vendor"], deviceclass=None)

            add_plugin_log(db_path, self.name, "Executed run_arpscan")
