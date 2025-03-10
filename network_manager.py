# netfang/network_manager.py

import time
import threading
from enum import Enum
from typing import Optional, Dict, Any

from netfang.db import add_or_update_network, get_network_by_mac
from netfang.plugin_manager import PluginManager

class ConnectionState(Enum):
    IDLE = 0
    CONNECTING = 1
    CONNECTED_HOME = 2
    CONNECTED_NEW = 3
    CONNECTED_KNOWN = 4
    CONNECTED_BLACKLISTED = 5

class NetworkManager:
    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager
        self.config = manager.config
        self.db_path = self.config.get("database_path", "netfang.db")
        self.flow_cfg = self.config.get("network_flows", {})
        self.blacklisted_macs = [m.upper() for m in self.flow_cfg.get("blacklisted_macs", [])]
        self.home_mac = self.flow_cfg.get("home_network_mac", "").upper()

        self.current_state = ConnectionState.IDLE
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start_flow_loop(self) -> None:
        """
        Start a background thread to continuously check network status 
        and transition states. This is just an example.
        """
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._flow_loop, daemon=True)
        self.thread.start()

    def stop_flow_loop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join()

    def _flow_loop(self) -> None:
        """
        A mock flow that simulates checking for network connections every few seconds.
        In real usage, you might read from wpa_supplicant or ifconfig/iwconfig 
        to see if you're connected, then call handle_network_connection().
        """
        while self.running:
            # In a real scenario, you'd detect active network here:
            # e.g. check gateway MAC, SSID, etc. For demonstration, we remain idle.
            time.sleep(5)

            # Example: we remain in IDLE or process any queued "network connected" events
            # This is up to you to implement real detection logic.

    def handle_network_connection(self, mac_address: str, ssid: str) -> None:
        """
        The synchronous logic for when we realize we've connected to a new network:
          1) check DB
          2) dispatch events
          3) update state
        """
        mac_upper = mac_address.upper()
        is_blacklisted = mac_upper in self.blacklisted_macs
        is_home = (mac_upper == self.home_mac)

        net_info = get_network_by_mac(self.db_path, mac_upper)

        if net_info is None:
            # New network
            add_or_update_network(self.db_path, mac_upper, ssid, is_blacklisted, is_home)
            self.manager.on_new_network_connected(mac_upper, ssid)

            if is_blacklisted:
                self.current_state = ConnectionState.CONNECTED_BLACKLISTED
                # Possibly forcibly disconnect or do nothing further
                print("[NetworkManager] Connected to blacklisted network. Aborting further scans.")
                return
            elif is_home:
                self.current_state = ConnectionState.CONNECTED_HOME
                self.manager.on_home_network_connected()
                return
            else:
                self.current_state = ConnectionState.CONNECTED_NEW
                print("[NetworkManager] New (non-home) network connected.")
                # Automatic scans or plugin actions can happen here
        else:
            # Known network => update
            add_or_update_network(self.db_path, mac_upper, ssid, is_blacklisted, is_home)

            if is_blacklisted:
                self.current_state = ConnectionState.CONNECTED_BLACKLISTED
                print("[NetworkManager] Known blacklisted network reconnected. Aborting further scans.")
                return
            elif is_home:
                self.current_state = ConnectionState.CONNECTED_HOME
                self.manager.on_home_network_connected()
                return
            else:
                self.current_state = ConnectionState.CONNECTED_KNOWN
                print("[NetworkManager] Known network reconnected.")
                self.manager.on_known_network_connected(mac_upper, ssid, is_blacklisted)
