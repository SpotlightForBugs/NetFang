import re
import subprocess
import time
import logging
from typing import Any, Dict, List, Optional, Set

import netfang.db
from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


def parse_arp_scan(output: str, mode: str) -> Dict[str, Any]:
    parsed_result = {
        "interface": None,
        "mac_address": None,
        "ipv4": None,
        "devices": []
    }

    lines = output.strip().split("\n")
    if not lines:
        return parsed_result

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
            device = {"ip": ip_address, "mac": mac_address, "vendor": vendor.strip(), "fingerprint": None}

            # Check for duplicates
            if "(DUP:" in vendor:
                vendor = vendor.split(" (DUP:")[0]
                device["vendor"] = vendor.strip()
                device["duplicate"] = True
            else:
                device["duplicate"] = False

            parsed_result["devices"].append(device)

    return parsed_result


def parse_arp_fingerprint(output: str) -> Dict[str, str]:
    fingerprint = {}
    
    # Parse the arp-fingerprint output
    lines = output.strip().split("\n")
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            fingerprint[key.strip()] = value.strip()
    
    return fingerprint


class ArpScanPlugin(BasePlugin):
    name = "ArpScan"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.scan_in_progress = False
        self.logger = logging.getLogger(__name__)
        self.interfaces = self._detect_interfaces()
        self.last_scan_time = 0
        self.scan_throttle = 60  # Minimum seconds between scans

    def _detect_interfaces(self) -> List[str]:
        """Detect available network interfaces"""
        interfaces = []
        try:
            result = subprocess.run(["ip", "-o", "link", "show"], 
                                   capture_output=True, text=True, timeout=5)
            for line in result.stdout.split("\n"):
                if line.strip():
                    # Extract interface name
                    match = re.match(r"\d+:\s+([^:@]+)[@:]", line)
                    if match and match.group(1) != "lo":  # Skip loopback
                        interfaces.append(match.group(1))
        except Exception as e:
            self.logger.error(f"Error detecting interfaces: {str(e)}")
            # Fallback to common interface names
            interfaces = ["eth0"]
        
        return interfaces

    def on_setup(self) -> None:
        self.logger.info(f"[{self.name}] Setup complete. Available interfaces: {', '.join(self.interfaces)}")
        add_plugin_log(self.config["database_path"], self.name, f"Setup complete. Found interfaces: {', '.join(self.interfaces)}")

    def on_enable(self) -> None:
        self.logger.info(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpScan enabled")

    def on_disable(self) -> None:
        self.logger.info(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpScan disabled")
        
    def on_scanning_in_progress(self) -> None:
        """Handle scanning state"""
        current_time = time.time()
        # Throttle scans to prevent too frequent execution
        if not self.scan_in_progress and (current_time - self.last_scan_time) > self.scan_throttle:
            self.scan_in_progress = True
            self.last_scan_time = current_time
            self.logger.info(f"[{self.name}] Network scanning state detected - initiating scan...")
            # Schedule scan after a brief delay
            time.sleep(1)
            self.perform_action([self.name, "localnet", "current"])
        elif self.scan_in_progress:
            self.logger.debug(f"[{self.name}] Scan already in progress")
        else:
            self.logger.debug(f"[{self.name}] Scan throttled - last scan was {current_time - self.last_scan_time:.1f}s ago")

    def on_scan_completed(self) -> None:
        """Reset scan flag when scan is complete"""
        self.scan_in_progress = False
        self.logger.info(f"[{self.name}] Scan completed")

    def fingerprint_device(self, ip_address: str) -> Optional[Dict[str, str]]:
        """Get the ARP fingerprint for a specific IP address"""
        try:
            # First check if arp-fingerprint tool exists
            check_cmd = subprocess.run(["which", "arp-fingerprint"], 
                                      capture_output=True, text=True)
            if check_cmd.returncode != 0:
                self.logger.warning("arp-fingerprint tool not found, skipping fingerprinting")
                return None
                
            # Run the fingerprinting with timeout
            result = subprocess.run(["arp-fingerprint", ip_address], 
                                   capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                fingerprint = parse_arp_fingerprint(result.stdout)
                return fingerprint
            else:
                self.logger.debug(f"No fingerprint data for {ip_address}: {result.stderr}")
                return None
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            self.logger.error(f"Error fingerprinting {ip_address}: {str(e)}")
            return None

    def run_arping(self, interface: str, target: str = "-b") -> Set[str]:
        """Run arping to discover hosts on the network
        
        Args:
            interface: Network interface to use
            target: Target to ping, default is broadcast (-b)
            
        Returns:
            Set of IP addresses discovered
        """
        found_ips = set()
        try:
            cmd = ["arping", "-c", "3", "-I", interface, target]
            self.logger.debug(f"Running arping command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0 or result.returncode == 1:  # arping returns 1 if any hosts respond
                found_ips = self._parse_arping_output(result.stdout)
                self.logger.info(f"arping found {len(found_ips)} devices on {interface}")
            else:
                self.logger.warning(f"arping error: {result.stderr}")
        except FileNotFoundError:
            self.logger.error("arping command not found. Please install arping package.")
        except subprocess.TimeoutExpired:
            self.logger.warning(f"arping timed out on interface {interface}")
        except Exception as e:
            self.logger.error(f"Error running arping: {str(e)}")
            
        return found_ips

    def run_arp_scan(self, interface: str) -> Dict[str, Any]:
        """Run arp-scan on the specified interface
        
        Returns:
            Parsed scan results
        """
        try:
            cmd = ["arp-scan", "-l", f"--interface={interface}"]
            self.logger.debug(f"Running arp-scan command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                parsed_data = parse_arp_scan(result.stdout, mode="localnet")
                self.logger.info(f"arp-scan found {len(parsed_data['devices'])} devices on {interface}")
                return parsed_data
            else:
                self.logger.warning(f"arp-scan error: {result.stderr}")
                return {"devices": []}
        except FileNotFoundError:
            self.logger.error("arp-scan command not found. Please install arp-scan package.")
            return {"devices": []}
        except subprocess.TimeoutExpired:
            self.logger.warning(f"arp-scan timed out on interface {interface}")
            return {"devices": []}
        except Exception as e:
            self.logger.error(f"Error running arp-scan: {str(e)}")
            return {"devices": []}

    def get_mac_for_ip(self, ip: str) -> Optional[str]:
        """Get MAC address for an IP from the ARP cache"""
        try:
            result = subprocess.run(["arp", "-n", ip], 
                                  capture_output=True, text=True, timeout=5)
            mac_match = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", result.stdout)
            if mac_match:
                return mac_match.group(1)
            else:
                return None
        except Exception as e:
            self.logger.error(f"Error getting MAC for {ip}: {str(e)}")
            return None

    def perform_action(self, args: list) -> None:
        """
        Run an arp-scan command.
        args[0] for checking if we should perform the action.
        This way, we can easily hook into other actions.

        args[1] should be the mode to run in. (e.g. localnet)
        args[2] is the network-id (for the database)
        """
        if args[0] == self.name:
            self.logger.info(f"[{self.name}] Starting network scan...")
            db_path = self.config["database_path"]
            add_plugin_log(db_path, self.name, "Starting comprehensive network scan")

            if args[1] == "localnet":
                try:
                    all_ips = set()
                    all_devices = []
                    
                    # Try scanning on all available interfaces
                    for interface in self.interfaces:
                        # First use arping for quick discovery
                        found_ips_arping = self.run_arping(interface)
                        all_ips.update(found_ips_arping)
                        
                        # Then use arp-scan for more detailed info
                        arp_scan_results = self.run_arp_scan(interface)
                        
                        # Add devices from arp-scan
                        for device in arp_scan_results.get("devices", []):
                            all_ips.add(device["ip"])
                            all_devices.append(device)
                    
                    self.logger.info(f"[{self.name}] Combined scan found {len(all_ips)} unique devices")
                    add_plugin_log(db_path, self.name, f"Found {len(all_ips)} unique devices across all interfaces")
                    
                    # Create mapping of IP to devices for easy lookup
                    ip_to_device = {device["ip"]: device for device in all_devices}
                    
                    # Process and save all discovered devices
                    for ip in all_ips:
                        device = ip_to_device.get(ip)
                        
                        if device:
                            # We have detailed info from arp-scan
                            mac = device["mac"]
                            vendor = device["vendor"]
                        else:
                            # We only have the IP from arping, get MAC from ARP cache
                            mac = self.get_mac_for_ip(ip) or "Unknown"
                            vendor = "Discovered via arping"
                        
                        # Get fingerprint (try a few times with backoff)
                        fingerprint = None
                        retries = 3
                        for attempt in range(retries):
                            fingerprint = self.fingerprint_device(ip)
                            if fingerprint:
                                break
                            if attempt < retries - 1:
                                time.sleep(1)  # Wait before retry
                        
                        fingerprint_str = str(fingerprint) if fingerprint else None
                        
                        # Save to database
                        netfang.db.database.add_or_update_device(
                            db_path, 
                            ip, 
                            mac, 
                            hostname=None,
                            services=None,
                            network_id=args[2], 
                            vendor=vendor,
                            deviceclass=None,
                            fingerprint=fingerprint_str
                        )
                    
                    # Scan complete
                    self.scan_in_progress = False
                    self.logger.info(f"[{self.name}] Network scan complete")
                    add_plugin_log(db_path, self.name, f"Scan complete - stored {len(all_ips)} devices")
                
                except Exception as e:
                    self.scan_in_progress = False
                    self.logger.error(f"[{self.name}] Error during scan: {str(e)}")
                    add_plugin_log(db_path, self.name, f"Scan error: {str(e)}")

    def _parse_arping_output(self, output: str) -> Set[str]:
        """Parse the output of an arping command to extract IP addresses"""
        ips = set()
        lines = output.strip().split("\n")
        for line in lines:
            # Look for lines with an IP address responding to ping
            if "bytes from" in line:
                match = re.search(r"from (\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    ips.add(match.group(1))
        return ips
