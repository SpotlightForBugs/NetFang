import asyncio
from enum import Enum
from typing import Awaitable

import netifaces
import psutil  # used to check interface status
import scapy.layers.l2
from scapy.layers.l2 import *

from netfang.db import get_network_by_mac

# ------------------------------------------------------------------------------
# AsyncTrigger and TriggerManager to allow async condition checking and actions
# ------------------------------------------------------------------------------
ConditionFunc = Callable[[], Union[bool, Awaitable[bool]]]
ActionFunc = Callable[[], Union[None, Awaitable[None]]]


class AsyncTrigger:
    def __init__(self, name: str, condition: ConditionFunc, action: ActionFunc):
        self.name = name
        self.condition = condition
        self.action = action

    async def check_and_fire(self):
        # Support both sync and async conditions
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


# ------------------------------------------------------------------------------
# Example sensor condition functions
# ------------------------------------------------------------------------------
async def condition_battery_low() -> bool:
    """
    Checks if battery level (simulated from an INA219 reading) is below 20%.
    Replace get_battery_percentage() with a real sensor call.
    """
    battery_percentage = await asyncio.to_thread(get_battery_percentage)
    return battery_percentage < 20


def get_battery_percentage() -> float:
    """
    Dummy battery percentage calculation.
    In practice, instantiate and use your INA219 instance.
    For example:
      p = (bus_voltage - 3) / 1.2 * 100
    """
    return 15.0  # Simulated low battery


async def condition_interface_unplugged() -> bool:
    """
    Checks if any of the monitored interfaces (e.g. eth0, wlan0) are down.
    """
    monitored = NetworkManager.global_monitored_interfaces
    stats = psutil.net_if_stats()
    for iface in monitored:
        # If interface isn’t found or isn’t up, report as unplugged.
        if iface not in stats or not stats[iface].isup:
            return True
    return False


async def condition_cpu_temp_high() -> bool:
    """
    Checks if the CPU temperature exceeds 70°C.
    On Linux, read from /sys/class/thermal/thermal_zone0/temp.
    """
    try:
        # Read synchronously in a thread
        cpu_temp = await asyncio.to_thread(
            lambda: float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000.0
        )
    except Exception:
        cpu_temp = 50.0  # Default if error occurs
    return cpu_temp > 70.0


# ------------------------------------------------------------------------------
# Example action functions for triggers
# ------------------------------------------------------------------------------
async def action_alert_battery_low():
    print("[TriggerManager] ACTION: Battery is too low!")
    # Update state to ALERTING with extra context
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


# ------------------------------------------------------------------------------
# Define network states
# ------------------------------------------------------------------------------
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
    # You can add extra states if needed


# ------------------------------------------------------------------------------
# The main NetworkManager that ties triggers, state changes, and plugins together.
# ------------------------------------------------------------------------------
class NetworkManager:
    # Global references to support triggers reading config
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

        # Initialize TriggerManager with our triggers.
        self.trigger_manager = TriggerManager([
            AsyncTrigger("BatteryLow", condition_battery_low, action_alert_battery_low),
            AsyncTrigger("InterfaceUnplugged", condition_interface_unplugged, action_alert_interface_unplugged),
            AsyncTrigger("CpuTempHigh", condition_cpu_temp_high, action_alert_cpu_temp),
            # Add more triggers as needed
        ])

        # Async loop tasks
        self.running = False
        self.flow_task: Optional[asyncio.Task] = None
        self.trigger_task: Optional[asyncio.Task] = None

        # Set the global instance to allow triggers/actions to access this manager
        NetworkManager.instance = self

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.flow_task = asyncio.create_task(self.flow_loop())
        self.trigger_task = asyncio.create_task(self.trigger_loop())

    async def stop(self) -> None:
        self.running = False
        if self.flow_task:
            self.flow_task.cancel()
        if self.trigger_task:
            self.trigger_task.cancel()

    async def flow_loop(self) -> None:
        """
        Main loop to handle state updates and to notify plugins.
        """
        while self.running:
            async with self.state_lock:
                current = self.current_state
                print(f"[NetworkManager] (Flow Loop) Current state: {current.value}")
                await self.notify_plugins(current)
            await asyncio.sleep(5)

            await asyncio.sleep(5)  # Broadcast current state every 5 seconds

        def _run_async_loop(self) -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.create_task(self._state_flow_loop())
            self._loop.run_forever()

    async def trigger_loop(self) -> None:
        """
        Loop to periodically check and fire triggers.
        """
        while self.running:
            await self.trigger_manager.check_triggers()
            await asyncio.sleep(2)  # Adjust polling frequency as needed

    async def notify_plugins(self, state: State) -> None:
        """
        Dispatch the current state (with context) to all plugin callbacks.
        """
        # Plugins get extra context via keyword arguments.
        if state == State.WAITING_FOR_NETWORK:
            self.plugin_manager.on_waiting_for_network(**self.state_context)
        elif state == State.CONNECTING:
            self.plugin_manager.on_connecting(**self.state_context)
        elif state == State.CONNECTED_HOME:
            self.plugin_manager.on_connected_home(**self.state_context)
        elif state == State.CONNECTED_NEW:
            self.plugin_manager.on_connected_new(**self.state_context)
        elif state == State.CONNECTED_KNOWN:
            self.plugin_manager.on_connected_known(**self.state_context)
        elif state == State.CONNECTED_BLACKLISTED:
            self.plugin_manager.on_connected_blacklisted(**self.state_context)
        elif state == State.DISCONNECTED:
            self.plugin_manager.on_disconnected(**self.state_context)
        elif state == State.ALERTING:
            self.plugin_manager.on_alerting(**self.state_context)
        elif state == State.RECONNECTING:
            self.plugin_manager.on_reconnecting(**self.state_context)
        elif state == State.SCANNING_IN_PROGRESS:
            self.plugin_manager.on_scanning_in_progress(**self.state_context)
        elif state == State.SCAN_COMPLETED:
            self.plugin_manager.on_scan_completed(**self.state_context)

    def _update_state(self, new_state: State, mac: str = "", ssid: str = "", message: str = "") -> None:
        async def update():
            async with self.state_lock:
                old_state = self.current_state
                if old_state == new_state:
                    return
                print(f"[NetworkManager] State transition: {old_state.value} -> {new_state.value}")
                self.current_state = new_state
                print(f"[NetworkManager] New state set: {self.current_state.value}")

        # Use the background loop if available:
        if hasattr(self, "_loop") and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(update(), self._loop)
        else:
            # Fallback: run the coroutine synchronously
            asyncio.run(update())

    def handle_network_connection(self, interface_name: str):
        """
        Process a network connection event.
        """

        gateways = netifaces.gateways()
        default_gateway = gateways.get('default', [])
        if default_gateway and netifaces.AF_INET in default_gateway:
            gateway_ip = default_gateway[netifaces.AF_INET][0]
            print(f"Default gateway IP: {gateway_ip}")

            broadcast = "ff:ff:ff:ff:ff:ff"
            arp_request = scapy.layers.l2.ARP(pdst=gateway_ip)
            broadcast = scapy.layers.l2.Ether(dst=broadcast)
            arp_request_broadcast = broadcast / arp_request
            answered_list = scapy.layers.l2.srp(arp_request_broadcast, timeout=1, verbose=False)[0]
            for element in answered_list:
                if element[1].psrc == gateway_ip:
                    mac_address = element[1].hwsrc
                else:
                    self.plugin_manager.on_alerting("Could not find gateway mac address EXITING FOR NOW")
                    return


        else:
            print("No default gateway found!")
            NetworkManager.handle_network_disconnection()
            return







        mac_upper = mac_address.upper()
        is_blacklisted = mac_upper in self.blacklisted_macs
        is_home = (mac_upper == self.home_mac)
        net_info = get_network_by_mac(self.db_path, mac_upper)
        if is_blacklisted:
            self._update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper)
        elif is_home:
            self._update_state(State.CONNECTED_HOME, mac=mac_upper)
        elif not net_info:
            self._update_state(State.CONNECTED_NEW, mac=mac_upper)
        else:
            self._update_state(State.CONNECTED_KNOWN, mac=mac_upper)

    @classmethod
    def handle_network_disconnection(cls):
        cls.instance._update_state(State.DISCONNECTED)

    @classmethod
    def handle_cable_inserted(cls, interface_name: str):
        cls.instance._update_state(State.CONNECTING)
