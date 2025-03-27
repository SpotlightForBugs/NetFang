import logging
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from netfang.db.database import add_plugin_log, add_or_update_device, get_devices
from netfang.plugins.base_plugin import BasePlugin


def parse_arp_fingerprint(output: str) -> Dict[str, str]:
    """Parse the output of arp-fingerprint command."""
    fingerprint = {}
    
    # Parse the arp-fingerprint output
    lines = output.strip().split("\n")
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            fingerprint[key.strip()] = value.strip()
        else:
            # Handle space-separated format like "192.168.178.1   01000000000     UNKNOWN"
            parts = line.strip().split()
            if len(parts) >= 3:
                fingerprint["ip"] = parts[0]
                fingerprint["fingerprint"] = parts[1]
                fingerprint["type"] = parts[2] 
    
    return fingerprint


class ArpFingerprintPlugin(BasePlugin):
    """Plugin for fingerprinting devices using arp-fingerprint"""
    name = "ArpFingerprint"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.scan_in_progress = False
        self.logger = logging.getLogger(__name__)
        self.thread_pool = ThreadPoolExecutor(max_workers=5)
        
        # Get plugin-specific config
        plugin_cfg = self.config.get("plugin_config", {})
        self.max_devices_per_scan = plugin_cfg.get("max_devices_per_scan", 10)
        self.fingerprint_timeout = plugin_cfg.get("fingerprint_timeout", 10)

    def on_setup(self) -> None:
        self.logger.info(f"[{self.name}] Setup complete.")
        add_plugin_log(self.config["database_path"], self.name, "Setup complete.")

    def on_enable(self) -> None:
        self.logger.info(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpFingerprint enabled")

    def on_disable(self) -> None:
        self.logger.info(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpFingerprint disabled")

    def on_scan_completed(self) -> None:
        """When the ArpScan plugin completes a scan, fingerprint the discovered devices"""
        if self.scan_in_progress:
            self.logger.debug(f"[{self.name}] Fingerprinting already in progress, skipping")
            return
            
        self.logger.info(f"[{self.name}] ArpScan completed, starting fingerprinting...")
        self.thread_pool.submit(self.perform_action, [self.name, "fingerprint", "all"])

    def fingerprint_device(self, ip_address: str) -> Optional[Dict[str, str]]:
        """Get the ARP fingerprint for a specific IP address"""
        db_path = self.config.get("database_path", "netfang.db")
        
        try:
            # First check if arp-fingerprint tool exists
            try:
                check_cmd = subprocess.run(["sudo", "which", "arp-fingerprint"], 
                                          capture_output=True, text=True)
                if check_cmd.returncode != 0:
                    self.logger.warning("arp-fingerprint tool not found, skipping fingerprinting")
                    add_plugin_log(db_path, self.name, "arp-fingerprint tool not found, skipping fingerprinting")
                    return None
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                self.logger.warning(f"Error checking for arp-fingerprint: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error checking for arp-fingerprint: {str(e)}")
                return None
                
            # Run the fingerprinting with timeout
            try:
                result = subprocess.run(["sudo", "arp-fingerprint", ip_address], 
                                       capture_output=True, text=True, timeout=self.fingerprint_timeout)
                
                # Log the fingerprinting command output
                output_log = result.stdout if result.stdout else "No output"
                add_plugin_log(db_path, self.name, f"Command output [sudo arp-fingerprint {ip_address}]: {output_log}")
                
                if result.returncode == 0 and result.stdout.strip():
                    fingerprint = parse_arp_fingerprint(result.stdout)
                    return fingerprint
                else:
                    error_log = result.stderr if result.stderr else "No error output"
                    self.logger.debug(f"No fingerprint data for {ip_address}: {error_log}")
                    add_plugin_log(db_path, self.name, f"No fingerprint data for {ip_address}: {error_log}")
                    return None
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                self.logger.error(f"Error fingerprinting {ip_address}: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error fingerprinting {ip_address}: {str(e)}")
                return None
        except Exception as e:
            self.logger.error(f"Error in fingerprint_device for {ip_address}: {str(e)}")
            add_plugin_log(db_path, self.name, f"Error in fingerprint_device for {ip_address}: {str(e)}")
            return None

    def get_recent_devices(self, db_path: str, limit: int) -> List[Dict[str, Any]]:
        """Get most recent devices from database to fingerprint"""
        return get_devices(db_path, limit=limit)

    def perform_action(self, args: list) -> None:
        """
        Run fingerprinting on devices.
        args[0] for checking if we should perform the action.
        args[1] should be 'fingerprint'
        args[2] is ignored
        """
        if args[0] == self.name and args[1] == "fingerprint":
            db_path = self.config["database_path"]
            self.logger.info(f"[{self.name}] Starting fingerprinting of devices...")
            add_plugin_log(db_path, self.name, "Starting fingerprinting of devices")
            
            # Set scan flag so we know fingerprinting is in progress
            self.scan_in_progress = True
            
            try:
                # Get recent devices to fingerprint
                devices = self.get_recent_devices(db_path, self.max_devices_per_scan)
                if not devices:
                    self.logger.info(f"[{self.name}] No devices found to fingerprint")
                    add_plugin_log(db_path, self.name, "No devices found to fingerprint")
                    self.scan_in_progress = False
                    return
                
                self.logger.info(f"[{self.name}] Starting fingerprinting of {len(devices)} devices")
                
                # Process each device in parallel
                futures = {}
                for device in devices:
                    ip = device.get("ip_address")
                    if not ip:
                        continue
                    
                    futures[ip] = {
                        "future": self.thread_pool.submit(self.fingerprint_device, ip),
                        "device": device
                    }
                
                # Collect results and update devices
                fingerprinted_count = 0
                for ip, data in futures.items():
                    try:
                        fingerprint = data["future"].result()
                        device = data["device"]
                        
                        if fingerprint:
                            fingerprint_str = str(fingerprint)
                            mac = device.get("mac_address")
                            
                            # Update device with fingerprint
                            add_or_update_device(
                                db_path,
                                ip,
                                mac,
                                hostname=device.get("hostname"),
                                services=device.get("services"),
                                network_id=device.get("network_id"),
                                vendor=device.get("vendor"),
                                deviceclass=device.get("deviceclass"),
                                fingerprint=fingerprint_str
                            )
                            
                            fingerprinted_count += 1
                            self.logger.debug(f"Updated fingerprint for device: IP={ip}, MAC={mac}")
                            add_plugin_log(db_path, self.name, f"Updated fingerprint for device: IP={ip}, MAC={mac}")
                    except Exception as e:
                        self.logger.error(f"[{self.name}] Error processing fingerprint for {ip}: {str(e)}")
                        add_plugin_log(db_path, self.name, f"Error processing fingerprint for {ip}: {str(e)}")
                
                # Fingerprinting complete
                self.scan_in_progress = False
                self.logger.info(f"[{self.name}] Fingerprinting complete - updated {fingerprinted_count} devices")
                add_plugin_log(db_path, self.name, f"Fingerprinting complete - updated {fingerprinted_count} devices")
                
            except Exception as e:
                self.scan_in_progress = False
                self.logger.error(f"[{self.name}] Error during fingerprinting: {str(e)}")
                add_plugin_log(db_path, self.name, f"Fingerprinting error: {str(e)}")