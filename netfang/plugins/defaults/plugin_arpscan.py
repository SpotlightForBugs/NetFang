import re
import subprocess
import time
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import netfang.db
from netfang.db.database import add_plugin_log, add_or_update_device, add_or_update_network, get_network_by_mac
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
        else:
            # Handle space-separated format like "192.168.178.1   01000000000     UNKNOWN"
            parts = line.strip().split()
            if len(parts) >= 3:
                fingerprint["ip"] = parts[0]
                fingerprint["fingerprint"] = parts[1]
                fingerprint["type"] = parts[2] 
    
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
        """Detect available ethernet network interfaces (never WiFi)"""
        interfaces = []
        db_path = self.config.get("database_path", "netfang.db")
        
        try:
            # First get all interfaces
            try:
                result = subprocess.run(["ip", "-o", "link", "show"], 
                                       capture_output=True, text=True, timeout=5)
                
                # Log the command output to database
                add_plugin_log(db_path, self.name, f"Command output [ip -o link show]: {result.stdout}")
                
                all_interfaces = []
                for line in result.stdout.split("\n"):
                    if line.strip():
                        # Extract interface name
                        match = re.match(r"\d+:\s+([^:@]+)[@:]", line)
                        if match and match.group(1) != "lo":  # Skip loopback
                            all_interfaces.append(match.group(1))
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                self.logger.error(f"Error running ip command: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error running ip command: {str(e)}")
                all_interfaces = []
            
            # Filter out WiFi interfaces - improved approach
            for interface in all_interfaces:
                # Skip this interface if it's clearly a WiFi interface based on name
                if (interface.startswith(("wlan", "wlp", "wifi", "wl")) or
                    "wifi" in interface.lower() or 
                    "wlan" in interface.lower() or
                    "wireless" in interface.lower()):
                    self.logger.info(f"Skipping WiFi interface: {interface}")
                    continue
                
                # Additional check for wireless capability
                try:
                    # Check if interface is in /sys/class/net/{interface}/wireless/ directory
                    try:
                        wireless_check = subprocess.run(
                            ["test", "-d", f"/sys/class/net/{interface}/wireless"],
                            capture_output=True, text=True, timeout=2
                        )
                        
                        # Log test command output
                        add_plugin_log(db_path, self.name, f"Command [test -d /sys/class/net/{interface}/wireless] returned code: {wireless_check.returncode}")
                        
                        if wireless_check.returncode == 0:
                            self.logger.info(f"Skipping WiFi interface detected via sysfs: {interface}")
                            continue
                    except (subprocess.SubprocessError, FileNotFoundError) as e:
                        self.logger.debug(f"Error checking wireless via sysfs: {str(e)}")
                    
                    # Try using iw to check if interface is wireless
                    try:
                        iw_check = subprocess.run(
                            ["iw", "dev", interface, "info"],
                            capture_output=True, text=True, timeout=2
                        )
                        
                        # Log iw command output
                        add_plugin_log(db_path, self.name, f"Command output [iw dev {interface} info]: {iw_check.stdout}")
                        
                        if iw_check.returncode == 0:
                            self.logger.info(f"Skipping WiFi interface detected via iw: {interface}")
                            continue
                    except (subprocess.SubprocessError, FileNotFoundError) as e:
                        self.logger.debug(f"Error checking wireless via iw: {str(e)}")
                        
                    # Only add to our list if we're sure it's ethernet
                    interfaces.append(interface)
                    self.logger.info(f"Using ethernet interface: {interface}")
                    
                except Exception as e:
                    # If we can't determine for sure, check if it looks like ethernet
                    if (interface.startswith(("eth", "en", "em", "eno", "ens"))):
                        interfaces.append(interface)
                        self.logger.info(f"Using likely ethernet interface: {interface}")
                    else:
                        self.logger.info(f"Skipping interface of unknown type: {interface}")
            
            # If no ethernet interfaces found, log a warning
            if not interfaces:
                self.logger.warning("No ethernet interfaces found!")
                add_plugin_log(db_path, self.name, "No ethernet interfaces found during detection")
                
        except Exception as e:
            self.logger.error(f"Error detecting interfaces: {str(e)}")
            # Log the error to database
            add_plugin_log(db_path, self.name, f"Error during interface detection: {str(e)}")
            
            # Fallback to common ethernet interface names if detection fails
            interfaces = ["eth0"]
            self.logger.info("Falling back to default ethernet interface: eth0")
        
        return interfaces

    def on_setup(self) -> None:
        self.logger.info(f"[{self.name}] Setup complete. Available interfaces: {', '.join(self.interfaces)}")
        add_plugin_log(self.config["database_path"], self.name, f"Setup complete. Found ethernet interfaces: {', '.join(self.interfaces)}")
        # Initial scan on setup
        self.perform_action([self.name, "localnet", "all"])

    def on_enable(self) -> None:
        self.logger.info(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "ArpScan enabled")
        # Scan when plugin is enabled
        self.perform_action([self.name, "localnet", "all"])

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
            # Changed to scan all networks
            self.perform_action([self.name, "localnet", "all"])
        elif self.scan_in_progress:
            self.logger.debug(f"[{self.name}] Scan already in progress")
        else:
            self.logger.debug(f"[{self.name}] Scan throttled - last scan was {current_time - self.last_scan_time:.1f}s ago")

    def on_new_network_connected(self, mac: str) -> None:
        """Handle new network connection by scanning it"""
        self.logger.info(f"[{self.name}] New network connected with MAC {mac} - initiating scan...")
        # Scan on new network connection
        self.perform_action([self.name, "localnet", "all"])

    def on_known_network_connected(self, mac: str) -> None:
        """Handle known network connection (not scanning the home network)"""
        self.logger.info(f"[{self.name}] Known network connected with MAC {mac} - not scanning")
        
    def on_home_network_connected(self) -> None:
        """Handle home network connection by scanning it"""
        self.logger.info(f"[{self.name}] Home network connected - initiating scan...")
        # Scan on home network connection
        self.perform_action([self.name, "localnet", "all"])

    def on_connected_new(self) -> None:
        """Handle generic new connection by scanning"""
        self.logger.info(f"[{self.name}] New connection detected - initiating scan...")
        # Scan on any new connection
        self.perform_action([self.name, "localnet", "all"])

    def on_scan_completed(self) -> None:
        """Reset scan flag when scan is complete"""
        self.scan_in_progress = False
        self.logger.info(f"[{self.name}] Scan completed")

    def fingerprint_device(self, ip_address: str) -> Optional[Dict[str, str]]:
        """Get the ARP fingerprint for a specific IP address"""
        db_path = self.config.get("database_path", "netfang.db")
        try:
            # First check if arp-fingerprint tool exists
            try:
                check_cmd = subprocess.run(["which", "arp-fingerprint"], 
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
                result = subprocess.run(["arp-fingerprint", ip_address], 
                                       capture_output=True, text=True, timeout=10)
                
                # Log the fingerprinting command output
                output_log = result.stdout if result.stdout else "No output"
                add_plugin_log(db_path, self.name, f"Command output [arp-fingerprint {ip_address}]: {output_log}")
                
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

    def run_arp_scan(self, interface: str) -> Dict[str, Any]:
        """Run arp-scan on the specified interface
        
        Returns:
            Parsed scan results
        """
        db_path = self.config.get("database_path", "netfang.db")
        
        try:
            cmd = ["arp-scan", "-l", f"--interface={interface}"]
            cmd_str = " ".join(cmd)
            self.logger.debug(f"Running arp-scan command: {cmd_str}")
            add_plugin_log(db_path, self.name, f"Running command: {cmd_str}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # Log the complete command output to database
                output_log = result.stdout if result.stdout else "No output"
                error_log = result.stderr if result.stderr else "No error output"
                add_plugin_log(db_path, self.name, f"Command output [arp-scan]: {output_log}")
                if error_log != "No error output":
                    add_plugin_log(db_path, self.name, f"Command stderr [arp-scan]: {error_log}")
                
                if result.returncode == 0:
                    parsed_data = parse_arp_scan(result.stdout, mode="localnet")
                    self.logger.info(f"arp-scan found {len(parsed_data['devices'])} devices on {interface}")
                    # Log the parsed data summary
                    device_macs = [dev["mac"] for dev in parsed_data.get("devices", [])]
                    add_plugin_log(db_path, self.name, f"arp-scan found {len(parsed_data['devices'])} devices on {interface}: {', '.join(device_macs)}")
                    return parsed_data
                else:
                    self.logger.warning(f"arp-scan error: {result.stderr}")
                    add_plugin_log(db_path, self.name, f"arp-scan error (return code {result.returncode}): {result.stderr}")
                    return {"devices": []}
            except subprocess.TimeoutExpired:
                self.logger.warning(f"arp-scan timed out on interface {interface}")
                add_plugin_log(db_path, self.name, f"arp-scan timed out on interface {interface}")
                return {"devices": []}
            except FileNotFoundError:
                self.logger.error("arp-scan command not found. Please install arp-scan package.")
                add_plugin_log(db_path, self.name, "arp-scan command not found. Please install arp-scan package.")
                return {"devices": []}
            except Exception as e:
                self.logger.error(f"Error running arp-scan subprocess: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error running arp-scan subprocess: {str(e)}")
                return {"devices": []}
        except Exception as e:
            self.logger.error(f"Error in run_arp_scan: {str(e)}")
            add_plugin_log(db_path, self.name, f"Error in run_arp_scan: {str(e)}")
            return {"devices": []}

    def get_mac_for_ip(self, ip: str) -> Optional[str]:
        """Get MAC address for an IP from the ARP cache"""
        db_path = self.config.get("database_path", "netfang.db")
        
        try:
            cmd = ["arp", "-n", ip]
            cmd_str = " ".join(cmd)
            self.logger.debug(f"Running arp command: {cmd_str}")
            add_plugin_log(db_path, self.name, f"Running command: {cmd_str}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                # Log the complete command output to database
                output_log = result.stdout if result.stdout else "No output"
                add_plugin_log(db_path, self.name, f"Command output [arp -n {ip}]: {output_log}")
                
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

    def _get_or_create_network_id(self, db_path: str, mac_address: str) -> Optional[int]:
        """Get the network ID for a MAC address or create a new network entry
        
        Returns:
            Network ID if available, otherwise None
        """
        try:
            # First try to get existing network
            network = get_network_by_mac(db_path, mac_address)
            if network:
                return network.get('id')
                
            # If not found, create a new network entry
            add_or_update_network(db_path, mac_address)
            add_plugin_log(db_path, self.name, f"Created new network entry for MAC: {mac_address}")
            
            # Get the newly created network
            network = get_network_by_mac(db_path, mac_address)
            if network:
                return network.get('id')
            else:
                self.logger.error(f"Failed to create or retrieve network for MAC: {mac_address}")
                add_plugin_log(db_path, self.name, f"Failed to create or retrieve network for MAC: {mac_address}")
                return None
        except Exception as e:
            self.logger.error(f"Error getting or creating network for MAC {mac_address}: {str(e)}")
            add_plugin_log(db_path, self.name, f"Error getting or creating network for MAC {mac_address}: {str(e)}")
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
            add_plugin_log(db_path, self.name, "Starting network scan")

            if args[1] == "localnet":
                try:
                    all_ips = set()
                    all_devices = []
                    
                    # Try scanning on all available ethernet interfaces
                    if not self.interfaces:
                        self.logger.warning("No ethernet interfaces available for scanning")
                        add_plugin_log(db_path, self.name, "No ethernet interfaces available for scanning")
                        self.scan_in_progress = False
                        return
                        
                    for interface in self.interfaces:
                        # Use arp-scan for detailed info
                        arp_scan_results = self.run_arp_scan(interface)
                        
                        # Add devices from arp-scan
                        for device in arp_scan_results.get("devices", []):
                            all_ips.add(device["ip"])
                            all_devices.append(device)
                    
                    self.logger.info(f"[{self.name}] Scan found {len(all_ips)} unique devices")
                    add_plugin_log(db_path, self.name, f"Found {len(all_ips)} unique devices across all ethernet interfaces")
                    
                    # Create mapping of IP to devices for easy lookup
                    ip_to_device = {device["ip"]: device for device in all_devices}
                    
                    # Store router network info if we have it
                    for result in arp_scan_results:
                        router_mac = arp_scan_results.get("mac_address")
                        router_ip = arp_scan_results.get("ipv4")
                        if router_mac and router_ip:
                            # Create or update the network for the router
                            router_network_id = self._get_or_create_network_id(db_path, router_mac)
                            
                            # Add router as a device too
                            add_or_update_device(
                                db_path,
                                router_ip,
                                router_mac,
                                hostname="Router",
                                services=None,
                                network_id=router_network_id,
                                vendor="NetFang Router",
                                deviceclass="Router",
                                fingerprint=None
                            )
                            add_plugin_log(db_path, self.name, f"Stored router info: IP={router_ip}, MAC={router_mac}")
                    
                    # Process and save all discovered devices
                    for ip in all_ips:
                        device = ip_to_device.get(ip)
                        
                        if device:
                            # We have detailed info from arp-scan
                            mac = device["mac"]
                            vendor = device["vendor"]
                        else:
                            # We only have the IP, get MAC from ARP cache
                            mac = self.get_mac_for_ip(ip) or "Unknown"
                            vendor = "Unknown vendor"
                        
                        # Skip if we couldn't determine a MAC address
                        if mac == "Unknown":
                            self.logger.warning(f"Skipping device with IP {ip} - could not determine MAC address")
                            add_plugin_log(db_path, self.name, f"Skipping device with IP {ip} - could not determine MAC address")
                            continue
                        
                        # Get fingerprint (try a few times with backoff)
                        fingerprint = None
                        retries = 3
                        for attempt in range(retries):
                            fingerprint = self.fingerprint_device(ip)
                            if fingerprint:
                                add_plugin_log(db_path, self.name, f"Successfully fingerprinted {ip} on attempt {attempt+1}")
                                break
                            if attempt < retries - 1:
                                time.sleep(1)  # Wait before retry
                        
                        fingerprint_str = str(fingerprint) if fingerprint else None
                        
                        # Get or create a network ID for this MAC address
                        network_id = self._get_or_create_network_id(db_path, mac)
                        
                        # Add device to database
                        add_or_update_device(
                            db_path, 
                            ip, 
                            mac, 
                            hostname=None,
                            services=None,
                            network_id=network_id, 
                            vendor=vendor,
                            deviceclass=None,
                            fingerprint=fingerprint_str
                        )
                        
                        self.logger.debug(f"Stored device: IP={ip}, MAC={mac}, vendor={vendor}, network_id={network_id}")
                        add_plugin_log(db_path, self.name, f"Stored device: IP={ip}, MAC={mac}, vendor={vendor}, network_id={network_id}")
                    
                    # Scan complete
                    self.scan_in_progress = False
                    self.logger.info(f"[{self.name}] Network scan complete - saved {len(all_ips)} devices to database")
                    add_plugin_log(db_path, self.name, f"Scan complete - stored {len(all_ips)} devices in database")
                
                except Exception as e:
                    self.scan_in_progress = False
                    self.logger.error(f"[{self.name}] Error during scan: {str(e)}")
                    add_plugin_log(db_path, self.name, f"Scan error: {str(e)}")
