import asyncio
import threading
import logging
from typing import Dict, Any, Optional, Callable, Union, List

from netfang.db.database import verify_network_id, add_plugin_log
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
        self.logger = logging.getLogger(__name__)
        self.scanning_plugins: List[str] = []
        self.current_scan_index: int = 0
        self.return_state_after_scan: Optional[State] = None
        
        # Initialize WebSocket handler

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the event loop for scheduling state update tasks."""
        self.loop = loop
        
        # Start WebSocket server
        if self.loop:
            self.loop.create_task(self.start_websocket_server())

    async def start_websocket_server(self) -> None:
        """Start the WebSocket server."""
        await self.websocket_handler.start(self.db_path)

    async def flow_loop(self) -> None:
        """
        Main loop that periodically notifies plugins about the current state.
        """
        while True:
            async with self.state_lock:
                await self.frontend_sync(self.current_state)
                await self.notify_plugins(self.current_state)
                
                # Check if we're in scanning state and need to manage the scan sequence
                if self.current_state == State.SCANNING_IN_PROGRESS and self.scanning_plugins:
                    await self.manage_scan_sequence()
                
                # Regularly broadcast dashboard updates
                await self.websocket_handler.broadcast_dashboard_update()
                    
            await asyncio.sleep(5)

    async def manage_scan_sequence(self) -> None:
        """
        Manages the sequential execution of scanning plugins.
        """
        if not self.scanning_plugins:
            self.logger.info("No scanning plugins registered")
            self.update_state(State.SCAN_COMPLETED)
            return
            
        # Check if all plugins have been executed
        if self.current_scan_index >= len(self.scanning_plugins):
            self.logger.info("All scanning plugins completed, moving to SCAN_COMPLETED state")
            self.update_state(State.SCAN_COMPLETED)
            # Reset for next scan sequence
            self.current_scan_index = 0
            return
            
        # Get the current plugin to execute
        current_plugin_name = self.scanning_plugins[self.current_scan_index]
        plugin = self.plugin_manager.get_plugin_by_name(current_plugin_name)
        
        if not plugin:
            self.logger.warning(f"Plugin {current_plugin_name} not found, skipping")
            self.current_scan_index += 1
            return
            
        self.logger.info(f"Executing scanning plugin {current_plugin_name} ({self.current_scan_index + 1}/{len(self.scanning_plugins)})")
        
        # Execute the plugin's scan action
        try:
            # Pass appropriate arguments based on plugin type
            self.plugin_manager.perform_plugin_scan(current_plugin_name)
            self.logger.info(f"Scan with {current_plugin_name} initiated")
            add_plugin_log(self.db_path, current_plugin_name, f"Scan initiated by state machine")
        except Exception as e:
            self.logger.error(f"Error executing scan plugin {current_plugin_name}: {str(e)}")
            add_plugin_log(self.db_path, current_plugin_name, f"Scan error: {str(e)}")
        
        # Move to the next plugin
        self.current_scan_index += 1

    def register_scanning_plugins(self) -> None:
        """
        Registers all plugins that support scanning functionality.
        """
        self.scanning_plugins = self.plugin_manager.get_scanning_plugin_names()
        self.logger.info(f"Registered scanning plugins: {', '.join(self.scanning_plugins)}")

    async def frontend_sync(self, state: State) -> None:
        """
        Notifies the frontend about state changes via WebSocket.
        """
        if self.previous_state != self.current_state:
            await self.websocket_handler.broadcast_state_change(self.current_state, self.state_context)
            
            if self.state_change_callback:
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
            self.logger.debug(f"State unchanged: {self.current_state.value}")
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
            # If we have a return state after scan, transition to it
            if self.return_state_after_scan:
                self.logger.info(f"Scan completed, returning to {self.return_state_after_scan.value} state")
                self.update_state(self.return_state_after_scan)
                self.return_state_after_scan = None
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
                if not verify_network_id(self.db_path, perform_action_data[1]):
                    raise ValueError(f"perform_action expects a valid network_id in args[1]: "
                                     f"{perform_action_data[1]} as specified in the database. (see database.py)\nYou can use database.verify_network_id(db_path, network_id) to check if the network_id exists.")
        else:
            self.logger.warning(f"Event not handled: {state}")

    def start_scan_sequence(self, return_state: Optional[State] = None) -> None:
        """
        Starts a scan sequence and sets the state to return to after scanning.
        
        Args:
            return_state: The state to transition to after scanning completes.
        """
        self.logger.info(f"Starting scan sequence, will return to {return_state.value if return_state else 'previous state'}")
        self.return_state_after_scan = return_state if return_state else self.current_state
        self.current_scan_index = 0
        self.register_scanning_plugins()
        self.update_state(State.SCANNING_IN_PROGRESS)

    def update_state(self, new_state: State, mac: str = "", message: str = "",
                     alert_data: Optional[Dict[str, Any]] = None,
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
                self.logger.info(f"State transition: {self.previous_state.value} -> {new_state.value}")
                
                # Log state transition
                add_plugin_log(self.db_path, "StateMachine", f"State changed: {self.previous_state.value} -> {new_state.value}")
                
                if self.state_change_callback:
                    self.state_change_callback(self.current_state, self.state_context)
                
                # Broadcast state change to WebSocket clients
                await self.websocket_handler.broadcast_state_change(self.current_state, self.state_context)
                
                await self.notify_plugins(self.current_state, self.state_context, mac, message, alert_data,
                                          perform_action_data)

        if self.loop is None:
            raise RuntimeError("Event loop for StateMachine is not set!")
        self.loop.create_task(update())
