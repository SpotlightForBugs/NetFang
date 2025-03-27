# netfang/plugins/defaults/plugin_rustscan.py

import subprocess
import logging
from typing import Any, Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor

from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin


class RustScanPlugin(BasePlugin):
    name = "RustScan"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        self.scan_in_progress = False
        self.thread_pool = ThreadPoolExecutor(max_workers=3)

    def on_setup(self) -> None:
        self.logger.info(f"[{self.name}] Setup complete.")
        add_plugin_log(self.config["database_path"], self.name, "Setup complete")

    def on_enable(self) -> None:
        self.logger.info(f"[{self.name}] Enabled.")
        add_plugin_log(self.config["database_path"], self.name, "RustScan enabled")

    def on_disable(self) -> None:
        self.logger.info(f"[{self.name}] Disabled.")
        add_plugin_log(self.config["database_path"], self.name, "RustScan disabled")
        
    def on_home_network_connected(self) -> None:
        """Handle home network connection - DO NOT scan home networks"""
        self.logger.info(f"[{self.name}] Home network connected - not scanning for security reasons")
        add_plugin_log(self.config["database_path"], self.name, "Home network connected - not scanning")

    def on_known_network_connected(self, mac: str) -> None:
        """Handle known network connection - DO NOT scan unless specified in UI/config"""
        self.logger.info(f"[{self.name}] Known network connected with MAC {mac} - not scanning")
        add_plugin_log(self.config["database_path"], self.name, f"Known network connected - not scanning: {mac}")
        
    def on_connected_blacklisted(self, mac: str) -> None:
        """Handle blacklisted network connection - DO NOT scan blacklisted networks"""
        self.logger.info(f"[{self.name}] Blacklisted network connected with MAC {mac} - not scanning")
        add_plugin_log(self.config["database_path"], self.name, f"Blacklisted network connected - not scanning: {mac}")

    def on_new_network_connected(self, mac: str) -> None:
        """Handle new network connection by scanning it"""
        self.logger.info(f"[{self.name}] New network connected with MAC {mac} - initiating scan...")
        # Scan handled by state machine, no need for direct action here

    def on_scanning_in_progress(self) -> None:
        """Handle scanning state"""
        # This method being overridden signals to the system that this is a scanning plugin
        self.logger.debug(f"[{self.name}] Scanning in progress state detected")
        
    def on_scan_completed(self) -> None:
        """Reset scan flag when scan is complete"""
        self.scan_in_progress = False
        self.logger.info(f"[{self.name}] Scan completed")
        add_plugin_log(self.config["database_path"], self.name, "Scan completed")

    def perform_action(self, args: list) -> None:
        """
        Run Rustscan on a target.

        @param args[0]: The plugin name the action is intended for.
        @param args[1]: The action type ('scan').
        @param args[2]: The target or network ID to scan.
        @param args[3]: The port range to scan, e.g. "1-1000" (optional).
        """
        if args[0] != self.name:
            return

        db_path = self.config["database_path"]
        self.scan_in_progress = True
        
        try:
            # Extract target
            target = "localhost"  # Default target
            if len(args) > 2:
                if args[1] == "scan":
                    # For now, just scan localhost for testing
                    target = "localhost"
                else:
                    target = args[2]

            # Port range
            port_range = None
            if len(args) > 3:
                port_range = args[3]

            self.logger.info(f"[{self.name}] Running rustscan on {target}...")
            add_plugin_log(db_path, self.name, f"Starting RustScan on {target}")

            # Check if rustscan is available
            try:
                from netfang.streaming_subprocess import run_subprocess_sync
                
                # Check if rustscan is installed
                check_result = run_subprocess_sync(
                    self.name,
                    ["which", "rustscan"],
                    db_path=db_path,
                    timeout=5
                )
                
                rustscan_available = check_result["status"] == "completed" and check_result["return_code"] == 0
                
                if not rustscan_available:
                    self.logger.warning("RustScan not found. It appears to be not installed.")
                    add_plugin_log(db_path, self.name, "RustScan not found. Please install rustscan.")
                else:
                    # Execute scan with RustScan
                    cmd = ["rustscan", "-a", target]
                    if port_range:
                        cmd.extend(["-p", port_range])

                    self.logger.info(f"[{self.name}] Running: {' '.join(cmd)}")
                    add_plugin_log(db_path, self.name, f"Running command: {' '.join(cmd)}")

                    # Run the scan with streaming output
                    scan_result = run_subprocess_sync(
                        self.name,
                        cmd,
                        db_path=db_path,
                        timeout=60  # Longer timeout for network scanning
                    )
                    
                    if scan_result["status"] == "completed" and scan_result["return_code"] == 0:
                        self.logger.info(f"[{self.name}] RustScan complete on {target}")
                        add_plugin_log(db_path, self.name, f"RustScan completed successfully on {target}")
                    else:
                        error = scan_result["stderr"] if scan_result["stderr"] else f"RustScan failed with code {scan_result['return_code']}"
                        self.logger.error(f"Error during RustScan: {error}")
                        add_plugin_log(db_path, self.name, f"Error during RustScan: {error}")
            except Exception as e:
                self.logger.error(f"Error checking/running rustscan: {str(e)}")
                add_plugin_log(db_path, self.name, f"Error checking/running rustscan: {str(e)}")
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Error during scan: {str(e)}")
            add_plugin_log(db_path, self.name, f"Error during scan: {str(e)}")
        finally:
            # Always mark scan as complete and notify
            self.scan_in_progress = False
            self._notify_scan_complete()

    def _notify_scan_complete(self) -> None:
        """
        Notify the plugin manager that the scan is complete.
        """
        try:
            # Get plugin manager instance and notify scan completion
            from netfang.plugin_manager import PluginManager
            manager = PluginManager.instance
            if manager:
                manager.notify_scan_complete(self.name)
            else:
                self.logger.warning("Cannot notify scan completion: PluginManager instance not available")
        except Exception as e:
            self.logger.error(f"Error notifying scan completion: {str(e)}")
            add_plugin_log(self.config["database_path"], self.name, f"Error notifying scan completion: {str(e)}")
