from datetime import datetime
import logging
from typing import Dict, Any, Optional, Callable
import json

# This class will serve as a bridge between the state machine and Flask-SocketIO
# The actual Flask-SocketIO instance will be passed in from main.py
class SocketIOHandler:
    """
    Handles Socket.IO communication throughout the application.
    This class serves as a bridge between components and the Flask-SocketIO instance.
    """
    
    def __init__(self):
        """Initialize the Socket.IO handler"""
        self.socketio = None
        self.logger = logging.getLogger(__name__)
        self.logger.info("SocketIO Handler initialized")
        self.db_path = None  # Will be set from main.py
        self.current_process = None  # To track currently running process
        
    def set_socketio(self, socketio_instance):
        """Set the Flask-SocketIO instance"""
        self.socketio = socketio_instance
        self.logger.info("SocketIO instance set in handler")
        
    def set_db_path(self, db_path: str):
        """Set the database path for dashboard queries"""
        self.db_path = db_path
        self.logger.info(f"Database path set to: {db_path}")
        
    async def broadcast_state_change(self, state, context: Dict[str, Any]) -> None:
        """
        Broadcast a state change to all connected clients.
        
        Args:
            state: The new state
            context: Additional context information for the state change
        """
        if not self.socketio:
            self.logger.warning("Cannot broadcast state change: SocketIO instance not set")
            return
            
        # Check if state is None and log a warning
        if state is None:
            self.logger.warning("Cannot broadcast state change: Received None state")
            return
            
        # Convert context to a JSON-serializable format if needed
        safe_context = {}
        for key, value in context.items():
            if isinstance(value, dict):
                # For nested dictionaries, we need to make them serializable too
                safe_context[key] = {}
                for k, v in value.items():
                    if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                        safe_context[key][k] = v
                    else:
                        safe_context[key][k] = str(v)
            elif isinstance(value, (str, int, float, bool, list)) or value is None:
                safe_context[key] = value
            else:
                safe_context[key] = str(value)

        # Emit the state update
        try:
            self.socketio.emit(
                "state_update",
                {"state": state.value, "context": safe_context},
            )
            self.logger.debug(f"Broadcasted state change: {state.value}")
        except Exception as e:
            self.logger.error(f"Error broadcasting state change: {str(e)}")
            
    async def broadcast_dashboard_update(self) -> None:
        """
        Broadcast dashboard updates to all connected clients.
        This is called periodically to keep the dashboard up to date.
        """
        if not self.socketio:
            self.logger.warning("Cannot broadcast dashboard update: SocketIO instance not set")
            return
            
        if not self.db_path:
            self.logger.warning("Cannot broadcast dashboard update: DB path not set")
            return
            
        # Import here to avoid circular imports
        from netfang.db.database import get_dashboard_data
        
        try:
            # Get dashboard data from database using the configured db_path
            dashboard_data = get_dashboard_data(self.db_path)
            
            # Emit the dashboard update
            self.socketio.emit("dashboard_data", dashboard_data)
            self.logger.debug("Broadcasted dashboard update")
        except Exception as e:
            self.logger.error(f"Error broadcasting dashboard update: {str(e)}")
            
    async def emit_alert(self, alert_data: Dict[str, Any]) -> None:
        """
        Emit an alert to all connected clients.
        
        Args:
            alert_data: Alert information
        """
        if not self.socketio:
            self.logger.warning("Cannot emit alert: SocketIO instance not set")
            return
            
        try:
            self.socketio.emit("alert_sync", alert_data)
            self.logger.debug(f"Emitted alert: {alert_data.get('message', 'No message')}")
        except Exception as e:
            self.logger.error(f"Error emitting alert: {str(e)}")
            
    async def stream_plugin_log(self, plugin_name: str, event: str) -> None:
        """
        Stream a plugin log event to connected clients.
        
        Args:
            plugin_name: The name of the plugin generating the log
            event: The log message/event description
        """
        if not self.socketio:
            self.logger.warning("Cannot stream plugin log: SocketIO instance not set")
            return
            
        try:
            from datetime import datetime
            log_data = {
                "plugin_name": plugin_name,
                "event": event,
                "timestamp": datetime.now().isoformat()
            }
            self.socketio.emit("plugin_log", log_data)
            self.logger.debug(f"Streamed plugin log: {plugin_name} - {event}")
        except Exception as e:
            self.logger.error(f"Error streaming plugin log: {str(e)}")
    
    # Add non-async version for synchronous contexts
    def sync_stream_plugin_log(self, plugin_name: str, event: str) -> None:
        """
        Synchronous version of stream_plugin_log for use in non-async contexts.
        """
        if not self.socketio:
            self.logger.warning("Cannot stream plugin log: SocketIO instance not set")
            return
            
        try:
            from datetime import datetime
            log_data = {
                "plugin_name": plugin_name,
                "event": event,
                "timestamp": datetime.now().isoformat()
            }
            self.socketio.emit("plugin_log", log_data)
            self.logger.debug(f"Streamed plugin log (sync): {plugin_name} - {event}")
        except Exception as e:
            self.logger.error(f"Error streaming plugin log (sync): {str(e)}")
            
    async def stream_command_output(self, plugin_name: str, command: str, output: str, is_complete: bool = False, process_id: str = None) -> None:
        """
        Stream command output to connected clients.
        
        Args:
            plugin_name: The name of the plugin running the command
            command: The command being executed
            output: The command output line
            is_complete: Whether the command execution is complete
            process_id: Unique identifier for the process
        """
        if not self.socketio:
            self.logger.warning("Cannot stream command output: SocketIO instance not set")
            return
            
        try:
            output_data = {
                "plugin_name": plugin_name,
                "command": command,
                "output": output,
                "is_complete": is_complete,
                "timestamp": datetime.now().isoformat(),
                "process_id": process_id
            }
            self.socketio.emit("command_output", output_data)
            self.logger.debug(f"Streamed command output: {plugin_name} - {command}")
        except Exception as e:
            self.logger.error(f"Error streaming command output: {str(e)}")
    
    # Add non-async version for synchronous contexts
    def sync_stream_command_output(self, plugin_name: str, command: str, output: str, is_complete: bool = False, process_id: str = None) -> None:
        """
        Synchronous version of stream_command_output for use in non-async contexts.
        """
        if not self.socketio:
            self.logger.warning("Cannot stream command output: SocketIO instance not set")
            return
            
        try:
            from datetime import datetime
            output_data = {
                "plugin_name": plugin_name,
                "command": command,
                "output": output,
                "is_complete": is_complete,
                "timestamp": datetime.now().isoformat(),
                "process_id": process_id
            }
            self.socketio.emit("command_output", output_data)
            self.logger.debug(f"Streamed command output (sync): {plugin_name} - {command}")
        except Exception as e:
            self.logger.error(f"Error streaming command output (sync): {str(e)}")
            
    async def set_current_process(self, plugin_name: str, command: str, pid: int = None, process_id: str = None) -> None:
        """
        Update the current running process information.
        
        Args:
            plugin_name: The name of the plugin running the command
            command: The command being executed
            pid: Process ID if available
            process_id: Unique identifier for the process
        """
        if not self.socketio:
            self.logger.warning("Cannot update current process: SocketIO instance not set")
            return
            
        try:
            process_data = {
                "plugin_name": plugin_name,
                "command": command,
                "pid": pid,
                "process_id": process_id,
                "start_time": datetime.now().isoformat()
            }
            self.current_process = process_data
            self.socketio.emit("current_process", process_data)
            self.logger.debug(f"Updated current process: {plugin_name} - {command}")
        except Exception as e:
            self.logger.error(f"Error updating current process: {str(e)}")
            
    async def clear_current_process(self, process_id: str = None) -> None:
        """
        Clear the current process information.
        
        Args:
            process_id: The ID of the process to clear. If None, clears current process.
        """
        if not self.socketio:
            self.logger.warning("Cannot clear current process: SocketIO instance not set")
            return
            
        try:
            # Only clear if this is the current process
            if not process_id or (self.current_process and self.current_process.get("process_id") == process_id):
                self.current_process = None
                self.socketio.emit("current_process", None)
                self.logger.debug("Cleared current process")
        except Exception as e:
            self.logger.error(f"Error clearing current process: {str(e)}")
            
    async def register_dashboard_action(self, plugin_name: str, action_id: str, action_name: str, 
                                        description: str, target_type: str, target_id: str = None) -> None:
        """
        Register a plugin action that can be shown on the dashboard.
        
        Args:
            plugin_name: The name of the plugin registering the action
            action_id: Unique identifier for the action
            action_name: Display name for the action
            description: Description of what the action does
            target_type: Type of target (network, device, system)
            target_id: Optional ID of the specific target
        """
        if not self.socketio:
            self.logger.warning("Cannot register dashboard action: SocketIO instance not set")
            return
            
        try:
            action_data = {
                "plugin_name": plugin_name,
                "action_id": action_id,
                "action_name": action_name,
                "description": description,
                "target_type": target_type,
                "target_id": target_id,
                "registration_time": datetime.now().isoformat()
            }
            self.socketio.emit("register_action", action_data)
            self.logger.debug(f"Registered dashboard action: {plugin_name} - {action_name}")
        except Exception as e:
            self.logger.error(f"Error registering dashboard action: {str(e)}")
            
    async def send_cached_output_to_client(self, sid: str = None) -> None:
        """
        Send cached output of active processes to a newly connected client.
        
        Args:
            sid: Socket ID of the client to send to, or None for all clients
        """
        if not self.socketio:
            self.logger.warning("Cannot send cached output: SocketIO instance not set")
            return
            
        try:
            # Import here to avoid circular imports
            from netfang.streaming_subprocess import StreamingSubprocess
            
            # Get all active processes
            active_processes = StreamingSubprocess.get_active_processes()
            
            if not active_processes:
                self.logger.debug("No active processes with cached output to send")
                return
                
            self.logger.info(f"Sending cached output for {len(active_processes)} active processes to client")
            
            # For each active process, send its cached output
            for process_id, process in active_processes.items():
                # Get cached output for this process
                cached_output = StreamingSubprocess.get_cached_output(process_id)
                
                if not cached_output:
                    continue
                    
                # Send the current process info first
                process_data = {
                    "plugin_name": process.plugin_name,
                    "command": process.cmd_str,
                    "start_time": datetime.now().isoformat(),
                    "process_id": process_id
                }
                
                # Send to specific client or broadcast
                if sid:
                    self.socketio.emit("current_process", process_data, to=sid)
                else:
                    self.socketio.emit("current_process", process_data)
                
                # Send all cached output lines
                for output_line in cached_output:
                    # Output line is already a dictionary with all required fields
                    if sid:
                        self.socketio.emit("command_output", output_line, to=sid)
                    else:
                        self.socketio.emit("command_output", output_line)
                
                self.logger.debug(f"Sent {len(cached_output)} cached output lines for process {process_id}")
                
        except Exception as e:
            self.logger.error(f"Error sending cached output to client: {str(e)}")
            
    async def notify_scanning_complete(self) -> None:
        """
        Notify clients that all scanning processes have completed.
        This updates the state machine to transition from SCANNING_IN_PROGRESS to SCAN_COMPLETED.
        """
        if not self.socketio:
            self.logger.warning("Cannot notify scan completion: SocketIO instance not set")
            return
            
        try:
            # Import here to avoid circular imports
            from netfang.state_machine import State
            from netfang.network_manager import NetworkManager
            
            # Check if NetworkManager instance exists
            if not NetworkManager.instance:
                self.logger.warning("Cannot notify scan completion: NetworkManager instance not available")
                return
                
            # Get the current state
            current_state = NetworkManager.instance.state_machine.current_state
            
            # Only notify if we're in scanning state
            if current_state and current_state.name == "SCANNING_IN_PROGRESS":
                self.logger.info("All scanning processes complete, transitioning to SCAN_COMPLETED state")
                
                # Transition to scan completed state
                await NetworkManager.instance.state_machine.update_state(State.SCAN_COMPLETED)
                
                
        except Exception as e:
            self.logger.error(f"Error notifying scan completion: {str(e)}")

# Create a singleton instance to be used throughout the application
handler = SocketIOHandler()