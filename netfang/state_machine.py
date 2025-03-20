import asyncio
import threading
from typing import Dict, Any, Optional, Callable, Union

from netfang.db.database import verify_network_id
from netfang.plugin_manager import PluginManager
from netfang.states.state import State


class StateMachine:
    """
    Handles state transitions and plugin notifications.
    """

    def __init__(self, plugin_manager: PluginManager,
                 state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = None, ) -> None:
        self.plugin_manager = plugin_manager
        self.current_state: State = State.WAITING_FOR_NETWORK
        self.previous_state: State = self.current_state
        self.state_context: Dict[str, Any] = {}
        self.state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = state_change_callback
        self.state_lock: asyncio.Lock = asyncio.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None  # Will be set later
        self.db_path: str = plugin_manager.config.get("database_path", "netfang.db")

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the event loop for scheduling state update tasks."""
        self.loop = loop

    async def flow_loop(self) -> None:
        """
        Main loop that periodically notifies plugins about the current state.
        """
        while True:
            async with self.state_lock:
                await self.frontend_sync(self.current_state)
                await self.notify_plugins(self.current_state)
            await asyncio.sleep(5)

    async def frontend_sync(self, state: State) -> None:
        """
        Notifies plugins about the current state change.
        """
        if self.state_change_callback and self.previous_state != self.current_state:
            self.state_change_callback(self.current_state, self.state_context)

    async def notify_plugins(self, state: State, state_context=Optional[Callable[[State, Dict[str, Any]], None]],
                             mac: str = "", message: str = "", alert_data: Optional[Dict[str, Any]] = None,
                             perform_action_data: list[Union[str, int]] = None, ) -> None:

        """
        Notifies plugins about the current state change.
        """
        if self.plugin_manager is None:
            raise RuntimeError("PluginManager for StateMachine is not set!")
        if self.current_state == self.previous_state and state != state.PERFORM_ACTION and state:
            print(f"[StateMachine] State unchanged: {self.current_state.value}")
            return

        if state == "home_network_connected":
            self.plugin_manager.on_home_network_connected()
        elif state == "disconnected":
            self.plugin_manager.on_disconnected()
        elif state == "reconnecting":
            self.plugin_manager.on_reconnecting()
        elif state == "connected_blacklisted":
            if not mac:
                raise ValueError("on_connected_blacklisted expects a mac address in mac_address:str")
            self.plugin_manager.on_connected_blacklisted(mac)
        elif state == "connected_known":
            self.plugin_manager.on_connected_known()
        elif state == "waiting_for_network":
            self.plugin_manager.on_waiting_for_network()
        elif state == "connecting":
            self.plugin_manager.on_connecting()
        elif state == "scanning_in_progress":
            self.plugin_manager.on_scanning_in_progress()
        elif state == "scan_completed":
            self.plugin_manager.on_scan_completed()
        elif state == "connected_new":
            self.plugin_manager.on_connected_new()
        elif state == "new_network_connected":
            if not mac:
                raise ValueError("on_new_network_connected expects a mac address in mac:str")
            self.plugin_manager.on_new_network_connected(mac)
        elif state == "known_network_connected":
            if not mac:
                raise ValueError("on_known_network_connected expects a mac address in mac:str")
            self.plugin_manager.on_known_network_connected(mac)
        elif state == "alerting":
            if not message:
                raise ValueError("on_alerting expects a message in message:str")
            self.plugin_manager.on_alerting(message)

        elif state == "perform_action":
            plugin = self.plugin_manager.get_plugin_by_name(perform_action_data[0])
            if plugin and verify_network_id(self.db_path, perform_action_data[1]):
                # Run the action in a background thread
                thread = threading.Thread(target=self.plugin_manager.perform_action, args=perform_action_data)
                thread.daemon = True  # Optional: set as daemon thread if appropriate
                thread.start()
            else:
                if not plugin:
                    raise ValueError(f"perform_action expects a plugin_name in args[0]: "
                                     f"{perform_action_data[0]} as specified in the plugin's self.name")
                if not verify_network_id(self.db_path,
                                         perform_action_data[1]):
                    raise ValueError(f"perform_action expects a valid network_id in args[1]: "
                                     f"{perform_action_data[1]} as specified in the database. (see database.py)\nYou can use database.verify_network_id(db_path, network_id) to check if the network_id exists.")
        else:
            print("Event not handled:", state)


def update_state(self, new_state: State, mac: str = "", message: str = "", alert_data: Optional[Dict[str, Any]] = None,
                 perform_action_data: list[Union[str, int]] = None, ) -> None:
    """
    Updates the current state and schedules a task to notify plugins.
    """
    if alert_data is None:
        alert_data = {}
    if perform_action_data is None:
        perform_action_data = []

    async def update() -> None:
        async with self.state_lock:
            if self.current_state == new_state:
                return
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_context = {"mac": mac, "message": message, "alert_data": alert_data, }
            print(f"[StateMachine] State transition: {self.previous_state.value} -> {new_state.value}")
            if self.state_change_callback:
                self.state_change_callback(self.current_state, self.state_context)
            await self.notify_plugins(self.current_state, mac, message, alert_data, perform_action_data)

    if self.loop is None:
        raise RuntimeError("Event loop for StateMachine is not set!")
    self.loop.create_task(update())
