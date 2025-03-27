import asyncio
import threading
import logging
from typing import Dict, Any, Optional, Callable, Union, List

# Remove the websockets import and use our SocketIO handler instead
from netfang.socketio_handler import handler as socketio_handler
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
        self.active_scans: Dict[str, bool] = {}  # Track active scans by plugin name
        self.scan_timeout: int = 120  # Safety timeout in seconds to avoid scan hang
        self.last_network_mac: str = ""  # Track last network MAC to prevent redundant scans
        self.already_scanned: Dict[str, bool] = {}  # Track networks that have already been scanned

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the event loop for scheduling state update tasks."""
        self.loop = loop
        self.logger.info("Event loop has been set in StateMachine")

    async def flow_loop(self) -> None:
        """
        Main loop that periodically notifies plugins about the current state.
        """
        while True:
            try:
                async with self.state_lock:
                    # Ensure current_state is not None before broadcasting
                    if self.current_state is None:
                        self.logger.error("Current state is None, resetting to WAITING_FOR_NETWORK")
                        self.current_state = State.WAITING_FOR_NETWORK
                    
                    # Use the SocketIO handler for broadcasting state changes
                    await socketio_handler.broadcast_state_change(self.current_state, self.state_context)
                    
                    # Only notify plugins about the current state, don't trigger scans from flow_loop
                    # This prevents the endless scanning loop
                    await self.notify_plugins_basic(self.current_state)
                    
                    # Check if we're in scanning state and need to manage the scan sequence
                    if self.current_state == State.SCANNING_IN_PROGRESS and self.scanning_plugins:
                        await self.manage_scan_sequence()
                    
                    # Regularly broadcast dashboard updates
                    await socketio_handler.broadcast_dashboard_update()
                        
            except Exception as e:
                self.logger.error(f"Error in state machine flow loop: {str(e)}")
                add_plugin_log(self.db_path, "StateMachine", f"Error in flow loop: {str(e)}")
                    
            await asyncio.sleep(5)

    async def notify_plugins_basic(self, state: State) -> None:
        """
        Basic notification for the flow loop - doesn't trigger scans.
        Only used by the flow_loop to avoid repeated scan triggers.
        """
        try:
            if state == State.WAITING_FOR_NETWORK:
                self.plugin_manager.on_waiting_for_network()
            elif state == State.DISCONNECTED:
                self.plugin_manager.on_disconnected()
                # Reset network tracking on disconnect to ensure we scan on next connect
                self.last_network_mac = ""
            elif state == State.RECONNECTING:
                self.plugin_manager.on_reconnecting()
            elif state == State.CONNECTING:
                self.plugin_manager.on_connecting()
            elif state == State.SCANNING_IN_PROGRESS:
                self.plugin_manager.on_scanning_in_progress()
            # Don't handle connection states here to avoid redundant scans
            # They are handled by the full notify_plugins method
        except Exception as e:
            self.logger.error(f"Error in basic plugin notification for state {state}: {str(e)}")

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
            # Wait for all active scans to complete before transitioning
            if any(self.active_scans.values()):
                self.logger.info("Waiting for active scans to complete...")
                return
                
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
            # Mark scan as active
            self.active_scans[current_plugin_name] = True
            
            # Pass appropriate arguments based on plugin type
            self.plugin_manager.perform_plugin_scan(current_plugin_name)
            self.logger.info(f"Scan with {current_plugin_name} initiated")
            add_plugin_log(self.db_path, current_plugin_name, f"Scan initiated by state machine")
            
            # Set timeout to ensure scan completion even if a plugin fails to report completion
            if self.loop:
                self.loop.call_later(self.scan_timeout, 
                                    lambda: self.mark_scan_complete(current_plugin_name, timed_out=True))
        except Exception as e:
            self.logger.error(f"Error executing scan plugin {current_plugin_name}: {str(e)}")
            add_plugin_log(self.db_path, current_plugin_name, f"Scan error: {str(e)}")
            # Mark as complete even if it failed so we can move on
            self.mark_scan_complete(current_plugin_name)
        
        # Move to the next plugin
        self.current_scan_index += 1

    def mark_scan_complete(self, plugin_name: str, timed_out: bool = False) -> None:
        """
        Marks a scan as complete.
        Called by plugins when they finish scanning or by timeout.
        
        Args:
            plugin_name: Name of the plugin that completed scanning
            timed_out: Whether the scan timed out
        """
        if timed_out:
            self.logger.warning(f"Scan by {plugin_name} timed out after {self.scan_timeout} seconds")
            add_plugin_log(self.db_path, plugin_name, f"Scan timed out after {self.scan_timeout} seconds")
        
        # Update active scans tracking
        if plugin_name in self.active_scans:
            self.active_scans[plugin_name] = False
            self.logger.info(f"Scan by {plugin_name} completed")

    def register_scanning_plugins(self) -> None:
        """
        Registers all plugins that support scanning functionality.
        """
        self.scanning_plugins = self.plugin_manager.get_scanning_plugin_names()
        self.logger.info(f"Registered scanning plugins: {', '.join(self.scanning_plugins)}")
        
        # Initialize active scans tracking
        self.active_scans = {plugin_name: False for plugin_name in self.scanning_plugins}

    async def notify_plugins(self, state: State, state_context=None,
                             mac: str = "", message: str = "", alert_data: Optional[Dict[str, Any]] = None,
                             perform_action_data: list[Union[str, int]] = None, ) -> None:

        """
        Notifies plugins about the current state change.
        """
        if self.plugin_manager is None:
            raise RuntimeError("PluginManager for StateMachine is not set!")
        
        # Ensure state is not None
        if state is None:
            self.logger.error("notify_plugins received None state, using WAITING_FOR_NETWORK as fallback")
            state = State.WAITING_FOR_NETWORK
            
        # Use provided state_context or default to instance variable
        if state_context is None:
            state_context = self.state_context
            
        # Prepare default values for optional parameters
        if alert_data is None:
            alert_data = {}
        if perform_action_data is None:
            perform_action_data = []

        # Handle new network connections - but only scan if it's a new connection or we haven't scanned this network recently
        network_mac = mac or state_context.get('mac', '')
        
        if (state == State.CONNECTED_NEW or state == State.CONNECTED_HOME or state == State.CONNECTED_KNOWN) and network_mac:
            # Check if this is a new network connection that needs scanning
            if network_mac != self.last_network_mac or network_mac not in self.already_scanned:
                self.logger.info(f"New network connection detected ({state}, MAC: {network_mac}), initiating scan sequence...")
                self.last_network_mac = network_mac
                self.already_scanned[network_mac] = True
                # Save the connection state to return to after scanning
                self.start_scan_sequence(state)
                return
            else:
                self.logger.info(f"Network already scanned ({state}, MAC: {network_mac}), skipping scan")

        # Pass state to appropriate plugin callbacks
        try:
            if state == State.WAITING_FOR_NETWORK:
                self.plugin_manager.on_waiting_for_network()
                # Clear network tracking on disconnection
                self.last_network_mac = ""
            elif state == State.DISCONNECTED:
                self.plugin_manager.on_disconnected()
                # Clear network tracking on disconnection
                self.last_network_mac = ""
            elif state == State.RECONNECTING:
                self.plugin_manager.on_reconnecting()
            elif state == State.CONNECTING:
                self.plugin_manager.on_connecting()
            elif state == State.CONNECTED_KNOWN:
                self.plugin_manager.on_connected_known()
                
                # Get MAC address from context if available
                network_mac = mac or state_context.get('mac', '')
                if network_mac:
                    self.plugin_manager.on_known_network_connected(network_mac)
                
            elif state == State.CONNECTED_HOME:
                self.plugin_manager.on_home_network_connected()
            elif state == State.CONNECTED_NEW:
                self.plugin_manager.on_connected_new()
                
                # Get MAC address from context if available
                network_mac = mac or state_context.get('mac', '')
                if network_mac:
                    self.plugin_manager.on_new_network_connected(network_mac)
                    
            elif state == State.CONNECTED_BLACKLISTED:
                network_mac = mac or state_context.get('mac', '')
                if network_mac:
                    self.plugin_manager.on_connected_blacklisted(network_mac)
                else:
                    self.logger.error("Cannot notify plugins about blacklisted network - MAC address missing")
                    
            elif state == State.SCANNING_IN_PROGRESS:
                self.plugin_manager.on_scanning_in_progress()
            elif state == State.SCAN_COMPLETED:
                self.plugin_manager.on_scan_completed()
                
                # If we have a return state after scan, transition to it
                if self.return_state_after_scan:
                    self.logger.info(f"Scan completed, returning to {self.return_state_after_scan.value} state")
                    # Schedule state transition after a short delay to ensure plugins process scan completion
                    if self.loop:
                        next_state = self.return_state_after_scan
                        self.return_state_after_scan = None
                        self.loop.call_later(2, lambda: self.update_state(next_state))
                        
            elif state == State.PERFORM_ACTION:
                if not perform_action_data or len(perform_action_data) < 2:
                    self.logger.error("perform_action requires at least plugin_name and network_id")
                    return
                    
                plugin = self.plugin_manager.get_plugin_by_name(perform_action_data[0])
                if plugin and verify_network_id(self.db_path, perform_action_data[1]):
                    # Run the action in a background thread
                    thread = threading.Thread(target=self.plugin_manager.perform_action, args=perform_action_data)
                    thread.daemon = True
                    thread.start()
                else:
                    if not plugin:
                        self.logger.error(f"Plugin not found: {perform_action_data[0]}")
                    if not verify_network_id(self.db_path, perform_action_data[1]):
                        self.logger.error(f"Invalid network ID: {perform_action_data[1]}")
            else:
                self.logger.warning(f"Unhandled state: {state}")
                
        except Exception as e:
            self.logger.error(f"Error notifying plugins about state {state}: {str(e)}")
            add_plugin_log(self.db_path, "StateMachine", f"Error in notify_plugins: {str(e)}")

    def start_scan_sequence(self, return_state: Optional[State] = None) -> None:
        """
        Starts a scan sequence and sets the state to return to after scanning.
        
        Args:
            return_state: The state to transition to after scanning completes.
        """
        # Ensure return_state is not None
        if return_state is None:
            return_state = self.current_state
            
        self.logger.info(f"Starting scan sequence, will return to {return_state.value}")
        self.return_state_after_scan = return_state
        self.current_scan_index = 0
        self.register_scanning_plugins()
        self.update_state(State.SCANNING_IN_PROGRESS)

    def reset_network_tracking(self) -> None:
        """
        Resets the network tracking to force a fresh scan on the next connection.
        """
        self.last_network_mac = ""
        self.already_scanned = {}
        self.logger.info("Network tracking reset, next connection will trigger a scan")

    def update_state(self, new_state: State, mac: str = "", message: str = "",
                     alert_data: Optional[Dict[str, Any]] = None,
                     perform_action_data: list[Union[str, int]] = None, ) -> None:
        """
        Updates the current state and schedules a task to notify plugins.
        """
        # Ensure new_state is not None
        if new_state is None:
            self.logger.error("Attempted to update state to None, using WAITING_FOR_NETWORK as fallback")
            new_state = State.WAITING_FOR_NETWORK
            
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
                
                # Broadcast state change using SocketIO
                await socketio_handler.broadcast_state_change(self.current_state, self.state_context)
                
                # Reset network tracking on disconnect states to ensure scan on next connection
                if new_state in [State.DISCONNECTED, State.WAITING_FOR_NETWORK]:
                    self.reset_network_tracking()
                
                await self.notify_plugins(self.current_state, self.state_context, mac, message, alert_data,
                                          perform_action_data)

        if self.loop is None:
            self.logger.error("Event loop for StateMachine is not set!")
            return
            
        self.loop.create_task(update())
