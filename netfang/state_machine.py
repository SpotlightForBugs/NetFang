import asyncio
import json
import os
import subprocess
from enum import Enum
from typing import Awaitable

import netifaces
import psutil
from scapy.layers.l2 import *

from netfang.db import get_network_by_mac

# -------------------------------------------------------------------------------
# Type Aliases for Conditions and Actions
# -------------------------------------------------------------------------------
ConditionFunc = Callable[[], Union[bool, Awaitable[bool]]]
ActionFunc = Callable[[], Union[None, Awaitable[None]]]


# -------------------------------------------------------------------------------
# Async Trigger and Trigger Manager
# -------------------------------------------------------------------------------
class AsyncTrigger:
    def __init__(self, name: str, condition: ConditionFunc, action: ActionFunc):
        self.name = name
        self.condition = condition
        self.action = action

    async def check_and_fire(self):
        cond_result = self.condition()
        if asyncio.iscoroutine(cond_result):
            cond_result = await cond_result
        if cond_result:
            act_result = self.action()
            if asyncio.iscoroutine(act_result):
                await act_result

class TriggerManager:
    def __init__(self, triggers: List[AsyncTrigger]):
        self.triggers = triggers

    async def check_triggers(self):
        for trigger in self.triggers:
            await trigger.check_and_fire()


# -------------------------------------------------------------------------------
# Sensor Conditions and Action Functions
# -------------------------------------------------------------------------------
async def condition_battery_low() -> bool:
    battery_percentage = await asyncio.to_thread(get_battery_percentage)
    return battery_percentage < 20

def get_battery_percentage() -> float:
    # Replace with real sensor call/calculation (e.g., from INA219)
    return 15.0  # Simulated low battery

async def condition_interface_unplugged() -> bool:
    monitored = NetworkManager.global_monitored_interfaces
    stats = psutil.net_if_stats()
    for iface in monitored:
        if iface not in stats or not stats[iface].isup:
            return True
    return False

async def condition_cpu_temp_high() -> bool:
    try:
        cpu_temp = await asyncio.to_thread(
            lambda: float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000.0
        )
    except Exception:
        cpu_temp = 50.0
    return cpu_temp > 70.0

async def action_alert_battery_low():
    print("[TriggerManager] ACTION: Battery is too low!")
    NetworkManager.instance.update_state(
        State.ALERTING, alert_data={"type": "battery", "message": "Battery level is low!"}
    )

async def action_alert_interface_unplugged():
    print("[TriggerManager] ACTION: A monitored interface is unplugged!")
    NetworkManager.instance.update_state(
        State.ALERTING, alert_data={"type": "interface", "message": "Interface unplugged!"}
    )

async def action_alert_cpu_temp():
    print("[TriggerManager] ACTION: CPU temperature is too high!")
    NetworkManager.instance.update_state(
        State.ALERTING, alert_data={"type": "temperature", "message": "CPU temperature is high!"}
    )


# -------------------------------------------------------------------------------
# State Definitions
# -------------------------------------------------------------------------------
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


# -------------------------------------------------------------------------------
# Network Manager with Dedicated State Handlers
# -------------------------------------------------------------------------------
class NetworkManager:
    instance: "NetworkManager" = None
    global_monitored_interfaces: List[str] = ["eth0"]

    def __init__(self, plugin_manager, config: Dict[str, Any]) -> None:
        self.plugin_manager = plugin_manager
        self.config = config
        self.db_path = config.get("database_path", "netfang.db")
        flow_cfg = config.get("network_flows", {})
        self.blacklisted_macs = [m.upper() for m in flow_cfg.get("blacklisted_macs", [])]
        self.home_mac = flow_cfg.get("home_network_mac", "").upper()
        self.monitored_interfaces = flow_cfg.get("monitored_interfaces", ["eth0"])
        NetworkManager.global_monitored_interfaces = self.monitored_interfaces

        self.current_state = State.WAITING_FOR_NETWORK
        self.state_lock = asyncio.Lock()
        self.state_context: Dict[str, Any] = {}

        # Initialize TriggerManager with triggers
        self.trigger_manager = TriggerManager([
            AsyncTrigger("BatteryLow", condition_battery_low, action_alert_battery_low),
            AsyncTrigger("InterfaceUnplugged", condition_interface_unplugged, action_alert_interface_unplugged),
            AsyncTrigger("CpuTempHigh", condition_cpu_temp_high, action_alert_cpu_temp),
        ])

        self.running = False
        self.flow_task: Optional[asyncio.Task] = None
        self.trigger_task: Optional[asyncio.Task] = None

        # Set the global instance
        NetworkManager.instance = self

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.flow_task = asyncio.create_task(self.flow_loop())
        self.trigger_task = asyncio.create_task(self.trigger_loop())
        self.check_initial_state()

    async def stop(self) -> None:
        self.running = False
        if self.flow_task:
            self.flow_task.cancel()
        if self.trigger_task:
            self.trigger_task.cancel()

    async def flow_loop(self) -> None:
        """
        Main loop to handle state updates and notify plugins.
        """
        while self.running:
            async with self.state_lock:
                current = self.current_state
                print(f"[NetworkManager] (Flow Loop) Current state: {current.value}")
                await self.handle_state_change(current)
            await asyncio.sleep(5)

    async def trigger_loop(self) -> None:
        """
        Loop to periodically check and fire triggers.
        """
        while self.running:
            await self.trigger_manager.check_triggers()
            await asyncio.sleep(2)

    async def handle_state_change(self, state: State) -> None:
        """
        Dispatch to the dedicated state handler and then notify plugins.
        """
        # Call the dedicated handler if it exists
        handler_name = f"handle_{state.value.lower()}"
        handler = getattr(self, handler_name, None)
        if callable(handler):
            await handler()
        # Notify plugins
        await self.notify_plugins(state)

    async def notify_plugins(self, state: State) -> None:
        """
        Dispatch the current state (and context) to the plugin callbacks.
        """
        plugin_callbacks = {
            State.WAITING_FOR_NETWORK: self.plugin_manager.on_waiting_for_network,
            State.CONNECTING: self.plugin_manager.on_connecting,
            State.CONNECTED_HOME: self.plugin_manager.on_connected_home,
            State.CONNECTED_NEW: self.plugin_manager.on_connected_new,
            State.CONNECTED_KNOWN: self.plugin_manager.on_connected_known,
            State.CONNECTED_BLACKLISTED: self.plugin_manager.on_connected_blacklisted,
            State.DISCONNECTED: self.plugin_manager.on_disconnected,
            State.ALERTING: self.plugin_manager.on_alerting,
            State.RECONNECTING: self.plugin_manager.on_reconnecting,
            State.SCANNING_IN_PROGRESS: self.plugin_manager.on_scanning_in_progress,
            State.SCAN_COMPLETED: self.plugin_manager.on_scan_completed,
        }
        callback = plugin_callbacks.get(state)
        if callback:
            if asyncio.iscoroutinefunction(callback):
                await callback(**self.state_context)
            else:
                callback(**self.state_context)

    # ---------------------------------------------------------------------------
    # Dedicated State Handlers
    # ---------------------------------------------------------------------------
    async def handle_waiting_for_network(self) -> None:
        print("[NetworkManager] Handling WAITING_FOR_NETWORK state.")
        # Add any custom logic for waiting state

    async def handle_connecting(self) -> None:
        print("[NetworkManager] Handling CONNECTING state.")
        # Add logic for connecting state

    async def handle_connected_home(self) -> None:
        print("[NetworkManager] Handling CONNECTED_HOME state.")
        # Custom logic when connected to the home network

    async def handle_connected_new(self) -> None:
        print("[NetworkManager] Handling CONNECTED_NEW state.")
        # Custom logic for connecting to a new network

    async def handle_connected_known(self) -> None:
        print("[NetworkManager] Handling CONNECTED_KNOWN state.")
        # Custom logic for connecting to a known network

    async def handle_connected_blacklisted(self) -> None:
        print("[NetworkManager] Handling CONNECTED_BLACKLISTED state.")
        # Custom logic for blacklisted network connection

    async def handle_alerting(self) -> None:
        print("[NetworkManager] Handling ALERTING state.")
        # Custom alerting logic

    async def handle_disconnected(self) -> None:
        print("[NetworkManager] Handling DISCONNECTED state.")
        # Custom disconnection logic

    async def handle_reconnecting(self) -> None:
        print("[NetworkManager] Handling RECONNECTING state.")
        # Custom reconnecting logic

    async def handle_scanning_in_progress(self) -> None:
        print("[NetworkManager] Handling SCANNING_IN_PROGRESS state.")
        # Custom scanning logic

    async def handle_scan_completed(self) -> None:
        print("[NetworkManager] Handling SCAN_COMPLETED state.")
        # Custom logic after scan completion

    # ---------------------------------------------------------------------------
    # State Update and Network Event Handlers
    # ---------------------------------------------------------------------------
    def update_state(self, new_state: State, **context) -> None:
        async def update():
            async with self.state_lock:
                if self.current_state == new_state:
                    return
                print(f"[NetworkManager] State transition: {self.current_state.value} -> {new_state.value}")
                self.current_state = new_state
                self.state_context.update(context)
                print(f"[NetworkManager] New state set: {self.current_state.value}")

        if hasattr(self, "_loop") and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(update(), self._loop)
        else:
            asyncio.run(update())

    def handle_network_connection(self, interface_name: str) -> None:
        """
        Process a network connection event.
        """
        gateways = netifaces.gateways()
        default_gateway = gateways.get('default', [])
        if default_gateway and netifaces.AF_INET in default_gateway:
            gateway_ip = default_gateway[netifaces.AF_INET][0]
            print(f"Default gateway IP: {gateway_ip}")

            # Build the helper script path relative to this file’s directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            helper_script = os.path.join(script_dir, "netfang/setup/arp_helper.py")

            try:
                result = subprocess.run(
                    ["sudo", "python3", helper_script, gateway_ip],
                    capture_output=True,
                    text=True,
                    check=True
                )
                response = json.loads(result.stdout)
                if response.get("success"):
                    mac_address = response["mac_address"]
                    print(f"MAC address of default gateway: {mac_address}")
                else:
                    error_msg = response.get("error", "Unknown error in ARP discovery")
                    self.plugin_manager.on_alerting(f"ARP helper error: {error_msg}")
                    return
            except subprocess.SubprocessError as e:
                self.plugin_manager.on_alerting(f"Failed to run ARP helper: {str(e)}")
                return
            except json.JSONDecodeError:
                self.plugin_manager.on_alerting("Failed to parse ARP helper output")
                return
        else:
            print("No default gateway found!")
            self.handle_network_disconnection()
            return

        mac_upper = mac_address.upper()
        is_blacklisted = mac_upper in self.blacklisted_macs
        is_home = (mac_upper == self.home_mac)
        net_info = get_network_by_mac(self.db_path, mac_upper)
        if is_blacklisted:
            self.update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper)
        elif is_home:
            self.update_state(State.CONNECTED_HOME, mac=mac_upper)
        elif not net_info:
            self.update_state(State.CONNECTED_NEW, mac=mac_upper)
        else:
            self.update_state(State.CONNECTED_KNOWN, mac=mac_upper)

    def handle_network_disconnection(self) -> None:
        self.update_state(State.DISCONNECTED)

    def handle_cable_inserted(self, interface_name: str) -> None:
        self.update_state(State.CONNECTING)
