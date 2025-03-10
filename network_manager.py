# netfang/network_manager.py

import time
import threading
from enum import Enum
from typing import Optional

from netfang.db import add_or_update_network, get_network_by_mac
from netfang.plugin_manager import PluginManager

class ConnectionState(Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED_HOME = "CONNECTED_HOME"
    CONNECTED_NEW = "CONNECTED_NEW"
    CONNECTED_KNOWN = "CONNECTED_KNOWN"
    CONNECTED_BLACKLISTED = "CONNECTED_BLACKLISTED"
    DISCONNECTED = "DISCONNECTED"

class NetworkManager:
    def __init__(self, manager: PluginManager) -> None:
        self.manager = manager
        self.config = manager.config
        self.db_path = self.config.get("database_path", "netfang.db")
        flow_cfg = self.config.get("network_flows", {})
        self.blacklisted_macs = [m.upper() for m in flow_cfg.get("blacklisted_macs", [])]
        self.home_mac = flow_cfg.get("home_network_mac", "").upper()
        self.current_state = ConnectionState.IDLE
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start_flow_loop(self) -> None:
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
        A state-machine loop that periodically checks network status.
        Replace this polling with real network detection as needed.
        """
        while self.running:
            # (Placeholder) In a real implementation, check if network is still connected.
            # For example, if disconnected, update state and trigger events.
            # Here, we simply print the current state every 5 seconds.
            print(f"[NetworkManager] Current state: {self.current_state.value}")
            time.sleep(5)

    def handle_network_connection(self, mac_address: str, ssid: str) -> None:
        """
        Process a network connection event.
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
                self._update_state(ConnectionState.CONNECTED_BLACKLISTED)
                print("[NetworkManager] Connected to blacklisted network. Aborting scans.")
                return
            elif is_home:
                self._update_state(ConnectionState.CONNECTED_HOME)
                self.manager.on_home_network_connected()
                return
            else:
                self._update_state(ConnectionState.CONNECTED_NEW)
                print("[NetworkManager] New network connected; running scans.")
        else:
            # Known network
            add_or_update_network(self.db_path, mac_upper, ssid, is_blacklisted, is_home)
            if is_blacklisted:
                self._update_state(ConnectionState.CONNECTED_BLACKLISTED)
                print("[NetworkManager] Reconnected to blacklisted network. Aborting scans.")
                return
            elif is_home:
                self._update_state(ConnectionState.CONNECTED_HOME)
                self.manager.on_home_network_connected()
                return
            else:
                self._update_state(ConnectionState.CONNECTED_KNOWN)
                self.manager.on_known_network_connected(mac_upper, ssid, is_blacklisted)

    def _update_state(self, new_state: ConnectionState) -> None:
        if self.current_state != new_state:
            print(f"[NetworkManager] State transition: {self.current_state.value} -> {new_state.value}")
            self.current_state = new_state
