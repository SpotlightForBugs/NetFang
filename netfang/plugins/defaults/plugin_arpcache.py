import logging
import re
import subprocess
from typing import Any, Dict, Optional

from netfang.db.database import add_plugin_log
from netfang.plugins.defaults.plugin_arpscan import BaseArpPlugin


class ArpCachePlugin(BaseArpPlugin):
    """Plugin for querying the ARP cache to find MAC addresses for IP addresses"""
    name = "ArpCache"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        # Get plugin-specific config
        plugin_cfg = self.config.get("plugin_config", {})
        self.arp_timeout = plugin_cfg.get("arp_timeout", 5)
        self.max_ping_attempts = plugin_cfg.get("max_ping_attempts", 3)
        self.use_ping_first = plugin_cfg.get("use_ping_first", True)

    def on_setup(self) -> None:
        self.logger.info(f"[{self.name}] Setup complete.")
        add_plugin_log(self.config["database_path"], self.name, "Setup complete.")

    def on_enable(self) -> None:
        self.logger.info(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpCache enabled")

    def on_disable(self) -> None:
        self.logger.info(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpCache disabled")

    def get_mac_for_ip(self, ip: str) -> Optional[str]:
        """Get MAC address for an IP from the ARP cache"""
        db_path = self.config.get("database_path", "netfang.db")
        
        try:
            # Optionally ping the host first to make sure it's in the ARP table
            if self.use_ping_first:
                ping_cmd = ["ping", "-c", "1", "-W", "1", ip]
                if subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                    # If first ping fails, try a couple more times to be sure
                    for attempt in range(1, self.max_ping_attempts):
                        if subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                            break
                        
            # Run the ARP command
            cmd = ["sudo", "arp", "-n", ip]
            cmd_str = " ".join(cmd)
            self.logger.debug(f"Running arp command: {cmd_str}")
            add_plugin_log(db_path, self.name, f"Running command: {cmd_str}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.arp_timeout)
                
                # Log the complete command output to database
                output_log = result.stdout if result.stdout else "No output"
                add_plugin_log(db_path, self.name, f"Command output [sudo arp -n {ip}]: {output_log}")
                
                mac_match = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", result.stdout)
                if mac_match:
                    mac_address = mac_match.group(1)
                    add_plugin_log(db_path, self.name, f"Found MAC {mac_address} for IP {ip}")
                    return mac_address
                else:
                    add_plugin_log(db_path, self.name, f"No MAC address found for IP {ip}")
                    return None
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                self.logger.error(f"Error running arp command for {ip}: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error running arp command for {ip}: {str(e)}")
                return None
        except Exception as e:
            self.logger.error(f"Error getting MAC for {ip}: {str(e)}")
            add_plugin_log(db_path, self.name, f"Error getting MAC for {ip}: {str(e)}")
            return None

    def perform_action(self, args: list) -> None:
        """
        Look up a MAC address for an IP address.
        args[0] should be the plugin name.
        args[1] should be "lookup"
        args[2] should be the IP address to look up.
        """
        if args[0] == self.name and args[1] == "lookup" and len(args) > 2:
            ip = args[2]
            db_path = self.config["database_path"]
            self.logger.info(f"[{self.name}] Looking up MAC address for IP: {ip}")
            add_plugin_log(db_path, self.name, f"Looking up MAC address for IP: {ip}")
            
            try:
                mac = self.get_mac_for_ip(ip)
                if mac:
                    self.logger.info(f"[{self.name}] Found MAC {mac} for IP {ip}")
                    add_plugin_log(db_path, self.name, f"Found MAC {mac} for IP {ip}")
                    return mac
                else:
                    self.logger.info(f"[{self.name}] No MAC address found for IP {ip}")
                    add_plugin_log(db_path, self.name, f"No MAC address found for IP {ip}")
                    return None
            except Exception as e:
                self.logger.error(f"[{self.name}] Error looking up MAC for IP {ip}: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error looking up MAC for IP {ip}: {str(e)}")
                return None