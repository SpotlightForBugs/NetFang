import asyncio
import json
import os
import subprocess
import threading
from typing import Dict, Any, Optional, Callable, List

import netifaces

from netfang.api.pi_utils import is_pi
from netfang.db.database import get_network_by_mac, add_or_update_network
from netfang.plugin_manager import PluginManager
from netfang.state_machine import StateMachine
from netfang.states.state import State
from netfang.triggers.actions import *
from netfang.triggers.async_trigger import AsyncTrigger
from netfang.triggers.conditions import *
from netfang.triggers.trigger_manager import TriggerManager


class NetworkManager:
    """
    Manages network events and delegates state transitions to the StateMachine.
    """
    instance: Optional["NetworkManager"] = None
    global_monitored_interfaces: List[str] = ["eth0"]

    def __init__(
            self,
            plugin_manager: PluginManager,
            config: Dict[str, Any],
            state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = None,
    ) -> None:
        self.plugin_manager = plugin_manager
        plugin_manager.load_config()
        plugin_manager.load_plugins()
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

        # Instantiate the state machine
        self.state_machine: StateMachine = StateMachine(plugin_manager, state_change_callback)

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

        NetworkManager.instance = self

    async def start(self) -> None:
        """
        Starts the network manager's background tasks.
        """
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
        """
        Runs the asyncio event loop in a separate thread.
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        # Set the loop in the state machine
        self.state_machine.set_loop(self._loop)
        self.running = True

        # Schedule the state machine's flow loop and the triggers loop.
        # self.flow_task = self._loop.create_task(self.state_machine.flow_loop())
        self.trigger_task = self._loop.create_task(self.trigger_loop())

        print("[NetworkManager] Event loop started in background thread")
        self._loop.run_forever()
        print("[NetworkManager] Event loop stopped")

    async def stop(self) -> None:
        """
        Stops the network manager and its background tasks.
        """
        self.running = False

        if self.flow_task:
            self.flow_task.cancel()
        if self.trigger_task:
            self.trigger_task.cancel()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    async def trigger_loop(self) -> None:
        """
        Loop to periodically check and execute triggers.
        """
        while self.running:
            await self.trigger_manager.check_triggers()
            await asyncio.sleep(2)

    def handle_network_connection(self, interface_name: str) -> None:
        """
        Processes a network connection event.
        """
        gateways = netifaces.gateways()
        default_gateway = gateways.get("default", [])
        if default_gateway and netifaces.AF_INET in default_gateway:
            gateway_ip: str = default_gateway[netifaces.AF_INET][0]
            script_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            helper_script: str = os.path.join(script_dir, "netfang/scripts/arp_helper.py")

            try:
                result = subprocess.run(
                    ["sudo", "python3", helper_script, gateway_ip],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                response = json.loads(result.stdout)

                if response["success"]:
                    mac_address: str = response["mac_address"]
                else:
                    error_msg: str = response.get("error", "Unknown ARP error")
                    self.plugin_manager.on_alerting(f"ARP helper error: {error_msg}")
                    return
            except (subprocess.SubprocessError, json.JSONDecodeError) as e:
                self.plugin_manager.on_alerting(f"ARP helper failed: {str(e)}")
                return
        else:
            print("No default gateway found!")
            self.handle_network_disconnection()
            return

        mac_upper: str = mac_address.upper()
        is_blacklisted: bool = mac_upper in self.blacklisted_macs
        is_home: bool = mac_upper == self.home_mac
        net_info = get_network_by_mac(self.db_path, mac_upper)

        if is_blacklisted:
            add_or_update_network(self.db_path, mac_upper, True, False)
            self.state_machine.update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper)
        elif is_home:
            add_or_update_network(self.db_path, mac_upper, False, True)
            self.state_machine.update_state(State.CONNECTED_HOME, mac=mac_upper)
        elif not net_info:
            add_or_update_network(self.db_path, mac_upper, False, False)
            self.state_machine.update_state(State.CONNECTED_NEW, mac=mac_upper)
        else:
            add_or_update_network(self.db_path, mac_upper, False, False)
            self.state_machine.update_state(State.CONNECTED_KNOWN, mac=mac_upper)

    @classmethod
    def handle_network_disconnection(cls) -> None:
        """
        Handles network disconnection events.
        """
        if cls.instance is not None:
            cls.instance.state_machine.update_state(State.DISCONNECTED)

    @classmethod
    def handle_cable_inserted(cls, interface_name: str) -> None:
        """
        Handles cable insertion events.
        """
        if cls.instance is not None:
            cls.instance.state_machine.update_state(State.CONNECTING)
