import threading
import time
from enum import Enum
from typing import Optional

from netfang.db import add_or_update_network, get_network_by_mac
from netfang.plugin_manager import PluginManager


class State(Enum):
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
        self.current_state = State.WAITING_FOR_NETWORK
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
        add_or_update_network(self.db_path, mac_upper, ssid, is_blacklisted, is_home)

        if is_blacklisted:
            self._update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper, ssid=ssid)
        if is_home:
            self._update_state(State.CONNECTED_HOME, mac=mac_upper, ssid=ssid)

        if not net_info:
            self._update_state(State.CONNECTED_NEW, mac=mac_upper, ssid=ssid)
        else:
            self._update_state(State.CONNECTED_KNOWN, mac=mac_upper, ssid=ssid)

    def _update_state(self, new_state: State, mac: str, ssid: str, message: str = "", ) -> None:
        with self.state_lock:
            if self.current_state == new_state:
                return

            old_state = self.current_state
            print(f"[NetworkManager] State transition: {old_state.value} -> {new_state.value} (id: {id(old_state)})")

            self.current_state = new_state
            print(f"[NetworkManager] New state set: {self.current_state.value} (id: {id(self.current_state)})")

            # TODO: Unexpected arguments (mac, ssid, message) in the following method calls:

            # Connection Lifecycle States
            if new_state in [State.WAITING_FOR_NETWORK, State.CONNECTING,
                             State.RECONNECTING]:
                if new_state == State.WAITING_FOR_NETWORK:
                    self.plugin_manager.on_waiting_for_network(mac, ssid)
                elif new_state == State.CONNECTING:
                    self.plugin_manager.on_connecting(mac, ssid)
                elif new_state == State.RECONNECTING:
                    self.plugin_manager.on_reconnecting(mac, ssid)

            elif new_state in [State.CONNECTED_HOME, State.CONNECTED_NEW,
                               State.CONNECTED_KNOWN, State.CONNECTED_BLACKLISTED]:
                if new_state == State.CONNECTED_HOME:
                    self.plugin_manager.on_connected_home(mac, ssid)
                elif new_state == State.CONNECTED_NEW:
                    self.plugin_manager.on_connected_new(mac, ssid)
                elif new_state == State.CONNECTED_KNOWN:
                    self.plugin_manager.on_connected_known(mac, ssid)
                elif new_state == State.CONNECTED_BLACKLISTED:
                    self.plugin_manager.on_connected_blacklisted(mac, ssid)

            elif new_state == State.DISCONNECTED:
                self.plugin_manager.on_disconnected(mac, ssid)

            # Scanning Operations
            elif new_state in [State.SCANNING_IN_PROGRESS, State.SCAN_COMPLETED]:
                if new_state == State.SCANNING_IN_PROGRESS:
                    self.plugin_manager.on_scanning_in_progress(mac, ssid)
                elif new_state == State.SCAN_COMPLETED:
                    self.plugin_manager.on_scan_completed(mac, ssid)

            # Special Events
            elif new_state == State.ALERTING:
                self.plugin_manager.on_alerting(message=message)
