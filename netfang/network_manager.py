import asyncio
import json
import os
import subprocess
import threading
from typing import Dict, Any, Optional, Callable, List, Tuple, Set, Union, Type

import netifaces

from netfang.alert_manager import Alert, AlertCategory, AlertLevel
from netfang.api.pi_utils import is_pi
from netfang.db.database import get_network_by_mac, add_or_update_network, get_devices
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
            state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = None
        ) -> None:
        """
        Initialize the NetworkManager.
        
        Args:
            plugin_manager: The plugin manager instance
            config: Configuration dictionary
            state_change_callback: Optional callback function for state changes
        """
        self.plugin_manager: PluginManager = plugin_manager
        plugin_manager.load_config()
        plugin_manager.load_plugins()
        self.config: Dict[str, Any] = config
        self.db_path: str = config.get("database_path", "netfang.db")
        flow_cfg: Dict[str, Any] = config.get("network_flows", {})
        self.blacklisted_macs: List[str] = [m.upper() for m in flow_cfg.get("blacklisted_macs", [])]
        self.home_mac: str = flow_cfg.get("home_network_mac", "").upper()
        self.monitored_interfaces: List[str] = flow_cfg.get("monitored_interfaces", ["eth0"])
        # Get the config value for scan_known_networks with default of False
        self.scan_known_networks: bool = flow_cfg.get("scan_known_networks", False)
        # Get the config value for scan_timeout with default of -1 (wait forever)
        self.scan_timeout: int = flow_cfg.get("scan_timeout", -1)  # Safety timeout in seconds to avoid scan hang
        NetworkManager.global_monitored_interfaces = self.monitored_interfaces

        # Instantiate the state machine
        self.state_machine: StateMachine = StateMachine(plugin_manager, state_change_callback)

        # Initialize trigger manager with default triggers
        self.trigger_manager: TriggerManager = TriggerManager(
            [AsyncTrigger("InterfaceUnplugged", condition_interface_unplugged, action_alert_interface_unplugged),
             AsyncTrigger("InterfaceReplugged", condition_interface_replugged, action_alert_interface_replugged),
             AsyncTrigger("CpuTempHigh", condition_cpu_temp_high, action_alert_cpu_temp),
             AsyncTrigger("CpuTempSafe", condition_cpu_temp_safe, action_alert_cpu_temp_resolved),
             ])

        # Add UPS monitoring triggers if the device is a Raspberry Pi with the UPS HAT
        if is_pi() and plugin_manager.is_device_enabled("ups_hat_c"):
            self.trigger_manager.add_trigger(
                AsyncTrigger("BatteryLow", condition_battery_low, action_alert_battery_low))
            self.trigger_manager.add_trigger(
                AsyncTrigger("OnBattery", condition_on_battery, action_alert_on_battery))
            self.trigger_manager.add_trigger(
                AsyncTrigger("PowerConnected", condition_power_connected, action_alert_power_connected))

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
                daemon=True
            )
            self._thread.start()
            await asyncio.sleep(0.1)  # Give thread time to start

    def _run_async_loop(self) -> None:
        """
        Internal method to run the asyncio event loop.
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.running = True

        # Set the event loop for StateMachine
        self.state_machine.set_loop(self._loop)
        
        self.flow_task = self._loop.create_task(self.trigger_loop())
        self.state_machine.register_scanning_plugins()

        try:
            self._loop.run_forever()
        except Exception as e:
            import logging
            logging.error(f"Error in NetworkManager event loop: {str(e)}")
        finally:
            self.running = False
            self._loop.close()
            self._loop = None

    async def stop(self) -> None:
        """
        Stops the network manager and its background tasks.
        """
        self.running = False

        if self.flow_task:
            self.flow_task.cancel()
            try:
                await self.flow_task
            except asyncio.CancelledError:
                pass

        if self.trigger_task:
            self.trigger_task.cancel()
            try:
                await self.trigger_task
            except asyncio.CancelledError:
                pass

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    async def trigger_loop(self) -> None:
        """
        Loop to periodically check and execute triggers.
        """
        while self.running:
            try:
                await self.trigger_manager.check_triggers()
            except Exception as e:
                import logging
                logging.error(f"Error checking triggers: {str(e)}")
            await asyncio.sleep(2)

    def handle_network_connection(self, interface_name: str) -> None:
        """
        Handles network connection events.
        
        1. If connected to home network: no scanning
        2. If connected to blacklisted network: no scanning
        3. If connected to known network: scan only if explicitly configured
        4. If connected to new network: always scan
        
        Args:
            interface_name: Name of the network interface
        """
        import logging
        logging.info(f"Connection detected on interface {interface_name}")

        try:
            gateways: Dict[int, Dict[int, Tuple[str, str, bool]]] = netifaces.gateways()
            if 'default' in gateways:
                try:
                    ipa = netifaces.ifaddresses(interface_name)
                    local_ip: Optional[str] = None
                    if netifaces.AF_INET in ipa:
                        local_ip = ipa[netifaces.AF_INET][0]["addr"]
                        logging.info(f"Local IP: {local_ip}")
                    
                    default_interface = gateways['default'][netifaces.AF_INET][1]
                    logging.info(f"Default interface: {default_interface}")
                    gateway_ip: str = gateways['default'][netifaces.AF_INET][0]
                    logging.info(f"Gateway IP: {gateway_ip}")
                    
                    # Try to get MAC address using ip neighbor
                    mac_address: Optional[str] = None
                    result = subprocess.run(
                        ["ip", "neigh", "show", gateway_ip], 
                        capture_output=True, 
                        text=True, 
                        check=True
                    )
                    
                    if result.stdout:
                        mac_parts = result.stdout.split()
                        # Find the MAC address in the output
                        for i, part in enumerate(mac_parts):
                            if i > 0 and part.lower() == "lladdr" and i + 1 < len(mac_parts):
                                mac_address = mac_parts[i + 1]
                                break
                        # If not found with lladdr pattern, try position-based approach
                        if not mac_address and len(mac_parts) >= 5:
                            mac_address = mac_parts[4]
                    
                    # If ip neigh failed, try using ping and arp
                    if not mac_address:
                        subprocess.run(
                            ["ping", "-c", "1", gateway_ip], 
                            capture_output=True, 
                            check=False
                        )
                        result = subprocess.run(
                            ["arp", "-a", gateway_ip], 
                            capture_output=True, 
                            text=True, 
                            check=True
                        )
                        try:
                            mac_address = result.stdout.split("at ")[1].split(" ")[0]
                        except (IndexError, AttributeError):
                            logging.error(f"Could not parse MAC address from: {result.stdout}")
                            self.handle_network_disconnection()
                            return
                except (subprocess.SubprocessError, IndexError, KeyError, json.JSONDecodeError) as e:
                    from netfang.alert_manager import AlertManager
                    AlertManager.instance.alert_manager.raise_alert(
                        AlertCategory.NETWORK, 
                        AlertLevel.WARNING,
                        f"Error while fetching MAC address: {e}"
                    )
                    return
            else:
                logging.warning("No default gateway found!")
                self.handle_network_disconnection()
                return

            mac_upper: str = mac_address.upper()
            is_blacklisted: bool = mac_upper in self.blacklisted_macs
            is_home: bool = mac_upper == self.home_mac
            net_info: Optional[Dict[str, Any]] = get_network_by_mac(self.db_path, mac_upper)
            
            # Determine if this is a truly new network (not home, not blacklisted, and either not in DB or has no devices)
            is_new_network: bool = False
            if not is_home and not is_blacklisted:
                if not net_info:
                    # Network not in DB
                    is_new_network = True
                else:
                    # Check if there are any devices saved for this network
                    network_id = net_info["id"]
                    devices = get_devices(self.db_path, network_id)
                    if not devices:
                        is_new_network = True

            # Update network in the database
            if is_blacklisted:
                add_or_update_network(self.db_path, mac_upper, True, False)
                self.state_machine.update_state(State.CONNECTED_BLACKLISTED, mac=mac_upper)
            elif is_home:
                add_or_update_network(self.db_path, mac_upper, False, True)
                self.state_machine.update_state(State.CONNECTED_HOME, mac=mac_upper)
            elif is_new_network:
                add_or_update_network(self.db_path, mac_upper, False, False)
                self.state_machine.update_state(State.CONNECTED_NEW, mac=mac_upper)
            else:
                add_or_update_network(self.db_path, mac_upper, False, False)
                # If we want to scan known networks based on config, use CONNECTED_NEW state to trigger scanning
                # Otherwise use CONNECTED_KNOWN state which doesn't trigger scanning
                if self.scan_known_networks:
                    self.state_machine.update_state(State.CONNECTED_NEW, mac=mac_upper)
                else:
                    self.state_machine.update_state(State.CONNECTED_KNOWN, mac=mac_upper)
                
        except Exception as e:
            logging.error(f"Error handling network connection: {str(e)}")
            from netfang.alert_manager import AlertManager
            AlertManager.instance.alert_manager.raise_alert(
                AlertCategory.NETWORK, 
                AlertLevel.WARNING,
                f"Error handling network connection: {str(e)}"
            )

    @classmethod
    def handle_network_disconnection(cls) -> None:
        """
        Handles network disconnection events.
        Updates the state machine to DISCONNECTED state.
        """
        if cls.instance is not None:
            cls.instance.state_machine.update_state(State.DISCONNECTED)

    @classmethod
    def handle_cable_inserted(cls, interface_name: str) -> None:
        """
        Handles cable insertion events.
        Updates the state machine to CONNECTING state.
        
        Args:
            interface_name: Name of the network interface
        """
        if cls.instance is not None:
            cls.instance.state_machine.update_state(State.CONNECTING)
