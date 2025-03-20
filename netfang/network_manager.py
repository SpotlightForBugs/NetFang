import asyncio
import json
import os
import subprocess
import threading
from typing import Dict, Any, Optional, Callable, List

import netifaces

from netfang.api.pi_utils import is_pi
from netfang.db.database import get_network_by_mac, add_or_update_network
from netfang.states.state import State
from netfang.triggers.actions import (
    action_alert_interface_unplugged,
    action_alert_cpu_temp,
    action_alert_battery_low,
)
from netfang.triggers.async_trigger import AsyncTrigger
from netfang.triggers.conditions import (
    condition_interface_unplugged,
    condition_cpu_temp_high,
    condition_battery_low,
)
from netfang.triggers.trigger_manager import TriggerManager


class NetworkManager:
    """Manages network states, triggers, and plugin notifications."""

    instance: Optional["NetworkManager"] = None
    global_monitored_interfaces: List[str] = ["eth0"]

    def __init__(
            self,
            plugin_manager: Any,
            config: Dict[str, Any],
            state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = None,
    ) -> None:
        self.plugin_manager = plugin_manager
        self.config = config
        self.db_path: str = config.get("database_path", "netfang.db")
        flow_cfg: Dict[str, Any] = config.get("network_flows", {})
        self.blacklisted_macs: List[str] = [
            m.upper() for m in flow_cfg.get("blacklisted_macs", [])
        ]
        self.home_mac: str = flow_cfg.get("home_network_mac", "").upper()
        self.monitored_interfaces: List[str] = flow_cfg.get(
            "monitored_interfaces", ["eth0"]
        )
        NetworkManager.global_monitored_interfaces = self.monitored_interfaces

        self.current_state: State = State.WAITING_FOR_NETWORK
        self.state_context: Dict[str, Any] = {}

        self.state_change_callback = state_change_callback

        self.trigger_manager = TriggerManager(
            [
                AsyncTrigger(
                    "InterfaceUnplugged",
                    condition_interface_unplugged,
                    action_alert_interface_unplugged,
                ),
                AsyncTrigger(
                    "CpuTempHigh", condition_cpu_temp_high, action_alert_cpu_temp
                ),
            ]
        )

        if is_pi() and config.get("hardware", {}).get("ups-hat-c", False):
            self.trigger_manager.add_trigger(
                AsyncTrigger(
                    "BatteryLow", condition_battery_low, action_alert_battery_low
                )
            )

        self.running: bool = False
        self.flow_task: Optional[asyncio.Task] = None
        self.trigger_task: Optional[asyncio.Task] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.state_lock: Optional[asyncio.Lock] = None

        NetworkManager.instance = self

    async def start(self) -> None:
        """Starts the network manager's background tasks."""
        if self.running:
            return

        if not self._thread:
            self._thread = threading.Thread(
                target=self._run_async_loop,
                name="NetworkManagerEventLoop",
                daemon=True,
            )
            self._thread.start()
            await asyncio.sleep(0.1)

    def _run_async_loop(self) -> None:
        """Runs the asyncio event loop in a separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.state_lock = asyncio.Lock()

        self.running = True
        self.flow_task = self._loop.create_task(self.flow_loop())
        self.trigger_task = self._loop.create_task(self.trigger_loop())

        print("[NetworkManager] Event loop started in background thread")
        self._loop.run_forever()
        print("[NetworkManager] Event loop stopped")

    async def stop(self) -> None:
        """Stops the network manager and its background tasks."""
        self.running = False

        if self.flow_task:
            self.flow_task.cancel()
        if self.trigger_task:
            self.trigger_task.cancel()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    async def flow_loop(self) -> None:
        """Main loop to handle state updates and notify plugins."""
        while self.running:
            async with self.state_lock:
                current = self.current_state
                print(f"[NetworkManager] (Flow Loop) Current state: {current.value}")
                await self.notify_plugins(current)
            await asyncio.sleep(5)

    async def trigger_loop(self) -> None:
        """Loop to periodically check and fire triggers."""
        while self.running:
            await self.trigger_manager.check_triggers()
            await asyncio.sleep(2)

    async def notify_plugins(self, state: State) -> None:
        """Dispatches the current state to all plugin callbacks."""
        method_name = f"on_{state.value.lower()}"
        callback = getattr(self.plugin_manager, method_name, None)
        if callback:
            callback(**self.state_context)

    def update_state(
            self,
            new_state: State,
            mac: str = "",
            ssid: str = "",
            message: str = "",
            alert_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Updates the current state and notifies plugins."""
        if alert_data is None:
            alert_data = {}

        async def update() -> None:
            async with self.state_lock:
                old_state = self.current_state
                if old_state == new_state:
                    return
                print(
                    f"[NetworkManager] State transition: {old_state.value} -> {new_state.value}"
                )
                self.current_state = new_state
                self.state_context = {
                    "mac": mac,
                    "ssid": ssid,
                    "message": message,
                    "alert_data": alert_data,
                }

                if self.state_change_callback:
                    self.state_change_callback(self.current_state, self.state_context)

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(update(), self._loop)
        else:
            print("[NetworkManager] ERROR: No event loop available for state update")

    def handle_network_connection(self, interface_name: str) -> None:
        """Processes a network connection event."""
        gateways = netifaces.gateways()
        default_gateway = gateways.get("default", [])
        if default_gateway and netifaces.AF_INET in default_gateway:
            gateway_ip = default_gateway[netifaces.AF_INET][0]
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            helper_script = os.path.join(script_dir, "netfang/scripts/arp_helper.py")

            try:
                result = subprocess.run(
                    ["sudo", "python3", helper_script, gateway_ip],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                response = json.loads(result.stdout)

                if response["success"]:
                    mac_address = response["mac_address"]
                else:
                    error_msg = response.get("error", "Unknown ARP error")
                    self.plugin_manager.on_alerting(f"ARP helper error: {error_msg}")
                    return
            except (subprocess.SubprocessError, json.JSONDecodeError) as e:
                self.plugin_manager.on_alerting(f"ARP helper failed: {str(e)}")
                return
        else:
            print("No default gateway found!")
            self.handle_network_disconnection()
            return

        mac_upper = mac_address.upper()
        is_blacklisted = mac_upper in self.blacklisted_macs
        is_home = mac_upper == self.home_mac
        net_info = get_network_by_mac(self.db_path, mac_upper)

        if is_blacklisted:
            add_or_update_network(self.db_path, mac_upper, True, False)
            self.update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper)
        elif is_home:
            add_or_update_network(self.db_path, mac_upper, False, True)
            self.update_state(State.CONNECTED_HOME, mac=mac_upper)
        elif not net_info:
            add_or_update_network(self.db_path, mac_upper, False, False)
            self.update_state(State.CONNECTED_NEW, mac=mac_upper)
        else:
            add_or_update_network(self.db_path, mac_upper, False, False)
            self.update_state(State.CONNECTED_KNOWN, mac=mac_upper)

    @classmethod
    def handle_network_disconnection(cls) -> None:
        """Handles network disconnection events."""
        cls.instance.update_state(State.DISCONNECTED)

    @classmethod
    def handle_cable_inserted(cls, interface_name: str) -> None:
        """Handles cable insertion events."""
        cls.instance.update_state(State.CONNECTING)
