import time
import threading
from enum import Enum
from typing import Optional

from netfang.db import add_or_update_network, get_network_by_mac
from netfang.plugin_manager import PluginManager


class ConnectionState(Enum):
    WAITING_FOR_NETWORK = "WAITING_FOR_NETWORK"
    CONNECTING = "CONNECTING"
    CONNECTED_HOME = "CONNECTED_HOME"
    CONNECTED_NEW = "CONNECTED_NEW"
    SCANNING_IN_PROGRESS = "SCANNING_IN_PROGRESS"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    CONNECTED_KNOWN = "CONNECTED_KNOWN"
    RECONNECTING = "RECONNECTING"
    CONNECTED_BLACKLISTED = "CONNECTED_BLACKLISTED"
    ALERTING = "ALERTING"
    DISCONNECTED = "DISCONNECTED"


class NetworkManager:
    def __init__(self, manager: PluginManager) -> None:
        self.plugin_manager = manager
        self.config = manager.config
        self.db_path = self.config.get("database_path", "netfang.db")
        flow_cfg = self.config.get("network_flows", {})
        self.blacklisted_macs = [m.upper() for m in flow_cfg.get("blacklisted_macs", [])]
        self.home_mac = flow_cfg.get("home_network_mac", "").upper()
        self.current_state = ConnectionState.WAITING_FOR_NETWORK
        self.state_lock = threading.Lock()
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
        while self.running:
            with self.state_lock:
                current = self.current_state
                print(f"[NetworkManager] (Flow Loop) Current state: {current.value} (id: {id(current)})")
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
            self.plugin_manager.on_new_network_connected(mac_upper, ssid)
            if is_blacklisted:
                self._update_state(ConnectionState.CONNECTED_BLACKLISTED)
                print("[NetworkManager] Connected to blacklisted network. Aborting scans.")
                return
            elif is_home:
                self._update_state(ConnectionState.CONNECTED_HOME)
                self.plugin_manager.on_home_network_connected()
                return
            else:
                self._update_state(ConnectionState.CONNECTED_NEW)
                print("[NetworkManager] New network connected; starting scan.")
                self._update_state(ConnectionState.SCANNING_IN_PROGRESS)
                # Trigger your scanning process here if needed.
        else:
            # Known network
            add_or_update_network(self.db_path, mac_upper, ssid, is_blacklisted, is_home)
            if is_blacklisted:
                self._update_state(ConnectionState.CONNECTED_BLACKLISTED)
                print("[NetworkManager] Reconnected to blacklisted network. Aborting scans.")
                return
            elif is_home:
                self._update_state(ConnectionState.CONNECTED_HOME)
                self.plugin_manager.on_home_network_connected()
                return
            else:
                self._update_state(ConnectionState.CONNECTED_KNOWN)
                self.plugin_manager.on_known_network_connected(mac_upper, ssid, is_blacklisted)

    def _update_state(self, new_state: ConnectionState) -> None:
        with self.state_lock:
            if self.current_state == new_state:
                return  # No change
            old_state = self.current_state
            print(f"[NetworkManager] State transition: {old_state.value} -> {new_state.value} (id: {id(old_state)})")

            self.current_state = new_state
            print(f"[NetworkManager] New state set: {self.current_state.value} (id: {id(self.current_state)})")
            # TODO: FUNCTION PARAMETER AND FUNCTION CALLS
            if new_state == ConnectionState.WAITING_FOR_NETWORK:
                self.plugin_manager.on_waiting_for_network()
            elif new_state == ConnectionState.CONNECTING:
                self.plugin_manager.on_connecting()
            elif new_state == ConnectionState.CONNECTED_HOME:
                self.plugin_manager.on_connected_home()
            elif new_state == ConnectionState.CONNECTED_NEW:
                self.plugin_manager.on_connected_new()
            elif new_state == ConnectionState.SCANNING_IN_PROGRESS:
                self.plugin_manager.on_scanning_in_progress()
            elif new_state == ConnectionState.SCAN_COMPLETED:
                self.plugin_manager.on_scan_completed()
            elif new_state == ConnectionState.CONNECTED_KNOWN:
                self.plugin_manager.on_connected_known()
            elif new_state == ConnectionState.RECONNECTING:
                self.plugin_manager.on_reconnecting()
            elif new_state == ConnectionState.CONNECTED_BLACKLISTED:
                self.plugin_manager.on_connected_blacklisted()
            elif new_state == ConnectionState.ALERTING:
                self.plugin_manager.on_alerting("TODO MESSAGE PARAMETER")
            elif new_state == ConnectionState.DISCONNECTED:
                self.plugin_manager.on_disconnected()
