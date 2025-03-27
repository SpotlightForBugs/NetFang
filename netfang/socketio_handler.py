# netfang/socketio_handler.py (Revised)

import asyncio
import json
import subprocess
import shlex
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# Assuming Flask-SocketIO is installed, but not importing directly here
# The 'socketio' instance is injected via set_socketio
# from flask_socketio import SocketIO, emit # Not imported globally

class SocketIOHandler:
    """
    Handles Socket.IO communication and manages background command execution tasks.
    This class serves as a bridge between components and the Flask-SocketIO instance.
    """

    def __init__(self):
        """Initialize the Socket.IO handler"""
        self.socketio = None 
        self.logger = logging.getLogger(__name__)
        self.db_path: Optional[str] = None

        # --- Process Tracking ---
        # Stores info about currently running processes initiated by this handler
        # { process_id: {'process': asyncio.subprocess.Process, 'plugin': str, 'command': str, 'start_time': float} }
        self.active_processes: Dict[str, Dict[str, Any]] = {}
        # Caches recent output lines per process
        # { process_id: [output_line_str, ...] }
        self.process_output_cache: Dict[str, List[str]] = {}
        # Stores completion status (exit code) of finished processes
        # { process_id: {'exit_code': int} }
        self.process_completion_status: Dict[str, Dict[str, int]] = {}
        # ---

        self.logger.info("SocketIO Handler initialized")

    def set_socketio(self, socketio_instance):
        """Set the Flask-SocketIO instance"""
        self.socketio = socketio_instance
        self.logger.info("SocketIO instance set in handler")

    def set_db_path(self, db_path: str):
        """Set the database path for potential future use (e.g., logging to DB)"""
        self.db_path = db_path
        self.logger.info(f"Database path set to: {db_path}")

    # --- Core Emit Methods ---

    async def broadcast_state_change(self, state_value: str, context: Dict[str, Any]) -> None:
        """
        Broadcast a state change to all connected clients.

        Args:
            state_value: The string value of the new state (e.g., State.SCANNING.value).
            context: Additional context information for the state change.
        """
        if not self.socketio:
            self.logger.warning("Cannot broadcast state change: SocketIO instance not set")
            return

        if state_value is None:
            self.logger.warning("Cannot broadcast state change: Received None state_value")
            return

        # Basic context serialization (can be enhanced if needed)
        safe_context = self._serialize_context(context)

        try:
            self.socketio.emit(
                "state_update",
                {"state": state_value, "context": safe_context},
            )
            self.logger.debug(f"Broadcasted state change: {state_value}")
        except Exception as e:
            self.logger.error(f"Error broadcasting state change: {e}", exc_info=True)

    async def broadcast_dashboard_update(self) -> None:
        """
        Triggers clients to request a dashboard data refresh via 'sync_dashboard'.
        (Alternative: Could fetch and broadcast data directly if preferred).
        """
        if not self.socketio:
            self.logger.warning("Cannot trigger dashboard update: SocketIO instance not set")
            return
        try:
            # Instead of fetching data here, tell clients to request it
            self.socketio.emit("request_dashboard_sync", {})
            self.logger.debug("Requested clients to sync dashboard")
        except Exception as e:
            self.logger.error(f"Error requesting dashboard sync: {e}", exc_info=True)

    async def emit_alert(self, alert_data: Dict[str, Any]) -> None:
        """Emit an alert to all connected clients."""
        if not self.socketio:
            self.logger.warning("Cannot emit alert: SocketIO instance not set")
            return
        try:
            self.socketio.emit("alert_sync", alert_data)
            self.logger.debug(f"Emitted alert: {alert_data.get('level', 'N/A')} - {alert_data.get('message', 'N/A')}")
        except Exception as e:
            self.logger.error(f"Error emitting alert: {e}", exc_info=True)

    async def stream_plugin_log(self, plugin_name: str, event: str) -> None:
        """Stream a plugin log event to connected clients."""
        if not self.socketio:
            self.logger.warning("Cannot stream plugin log: SocketIO instance not set")
            return
        try:
            log_data = {
                "plugin_name": plugin_name,
                "event": event,
                "timestamp": datetime.now().isoformat()
            }
            self.socketio.emit("plugin_log", log_data)
            # Avoid overly verbose logging for frequent events
            # self.logger.debug(f"Streamed plugin log: {plugin_name} - {event}")
        except Exception as e:
            self.logger.error(f"Error streaming plugin log: {e}", exc_info=True)

    async def register_dashboard_action(self, action_data: Dict[str, Any]) -> None:
        """
        Register a plugin action (tool) to be shown on the dashboard.

        Args:
            action_data: Dictionary containing action details
                         (plugin_name, action_id, action_name, description, target_type, command?, etc.)
        """
        if not self.socketio:
            self.logger.warning("Cannot register dashboard action: SocketIO instance not set")
            return
        try:
            # Add registration time if not present
            action_data.setdefault("registration_time", datetime.now().isoformat())
            self.socketio.emit("register_action", action_data)
            self.logger.debug(f"Registered dashboard action: {action_data.get('plugin_name')} - {action_data.get('action_name')}")
        except Exception as e:
            self.logger.error(f"Error registering dashboard action: {e}", exc_info=True)

    # --- Command Execution and Streaming ---

    async def _stream_output(self, process_id: str, stream, stream_name: str):
        """Asynchronously read and emit stream output for a given process."""
        MAX_CACHE_LINES = 500 # Limit cache size per process
        while True:
            try:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break # End of stream
                line = line_bytes.decode('utf-8', errors='replace').rstrip()

                # Cache the output
                if process_id not in self.process_output_cache:
                    self.process_output_cache[process_id] = []
                self.process_output_cache[process_id].append(line)
                # Trim cache if it exceeds the limit
                if len(self.process_output_cache[process_id]) > MAX_CACHE_LINES:
                    self.process_output_cache[process_id].pop(0)

                # Emit the output line via SocketIO
                if self.socketio:
                    process_info = self.active_processes.get(process_id, {})
                    output_data = {
                        'process_id': process_id,
                        'output': line,
                        'stream': stream_name, # 'stdout' or 'stderr'
                        'plugin_name': process_info.get('plugin', 'Unknown'),
                        'command': process_info.get('command', 'Unknown'),
                        'is_complete': False,
                        'timestamp': datetime.now().isoformat(),
                    }
                    self.socketio.emit('command_output', output_data)

            except asyncio.CancelledError:
                self.logger.debug(f"Output streaming cancelled for process {process_id} ({stream_name}).")
                break
            except Exception as e:
                self.logger.error(f"Error reading {stream_name} for process {process_id}: {e}", exc_info=True)
                # Attempt to emit an error message to the client for this process
                if self.socketio:
                     try:
                         err_data = {
                            'process_id': process_id,
                            'output': f"--- Error reading {stream_name}: {e} ---",
                            'stream': 'system_error',
                            'plugin_name': self.active_processes.get(process_id, {}).get('plugin', 'Unknown'),
                            'command': self.active_processes.get(process_id, {}).get('command', 'Unknown'),
                            'is_complete': False, # Process might still be running
                            'timestamp': datetime.now().isoformat(),
                         }
                         self.socketio.emit('command_output', err_data)
                     except Exception as emit_err:
                         self.logger.error(f"Failed to emit stream error to client: {emit_err}")
                break # Stop trying to read from this stream

    async def run_command_async(self, command: str, plugin_name: str) -> Optional[str]:
        """
        Runs a shell command asynchronously, streams its output via SocketIO,
        and tracks its execution.

        Args:
            command: The command string to execute.
            plugin_name: The name of the plugin initiating the command.

        Returns:
            The unique process ID for the executed command, or None if execution failed immediately.
        """
        if not self.socketio:
            self.logger.error("Cannot run command: SocketIO instance not set.")
            return None

        process_id = str(uuid.uuid4())
        start_time = datetime.now() # Use datetime object

        try:
            # Use shlex to handle command parsing safely for POSIX systems
            # For Windows, shlex might behave differently; consider platform checks if needed
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                raise ValueError("Command string resulted in empty parts list.")

            self.logger.info(f"Executing command (ID: {process_id}): {' '.join(cmd_parts)} for plugin {plugin_name}")

            # Create the subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Consider environment variables, working directory if needed
            )

            # Store process information
            self.active_processes[process_id] = {
                'process': process,
                'plugin': plugin_name,
                'command': command, # Store original command string
                'start_time': start_time.timestamp(), # Store timestamp
            }
            self.process_output_cache[process_id] = [] # Initialize cache
            self.process_completion_status.pop(process_id, None) # Clear any old status

            # Emit process start event
            start_event_data = {
                'process_id': process_id,
                'plugin_name': plugin_name,
                'command': command,
                'start_time': start_time.isoformat(), # Send ISO format time
            }
            self.socketio.emit('current_process', start_event_data)

            # --- Create tasks for streaming and cleanup ---
            stdout_task = asyncio.create_task(self._stream_output(process_id, process.stdout, 'stdout'))
            stderr_task = asyncio.create_task(self._stream_output(process_id, process.stderr, 'stderr'))

            # Task to wait for completion and emit final status
            async def wait_and_cleanup():
                exit_code = -1 # Default exit code in case of errors waiting
                try:
                    exit_code = await process.wait()
                    self.logger.info(f"Process {process_id} completed with exit code {exit_code}.")
                    # Ensure streaming tasks are finished before emitting completion
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

                except asyncio.CancelledError:
                    self.logger.warning(f"Wait task cancelled for process {process_id}.")
                    # Attempt to terminate the process if cancelled
                    if process.returncode is None:
                        try:
                            process.terminate()
                            await asyncio.wait_for(process.wait(), timeout=2.0)
                        except Exception as term_err:
                            self.logger.error(f"Error terminating process {process_id} on cancellation: {term_err}")
                            process.kill() # Force kill if terminate fails
                    exit_code = -2 # Indicate cancellation
                except Exception as e:
                    self.logger.error(f"Error waiting for process {process_id}: {e}", exc_info=True)
                    exit_code = -3 # Indicate wait error
                finally:
                    # Store completion status
                    self.process_completion_status[process_id] = {'exit_code': exit_code}

                    # Emit completion event
                    if self.socketio:
                        process_info = self.active_processes.get(process_id, {})
                        completion_data = {
                            'process_id': process_id,
                            'output': f"--- Process finished with exit code {exit_code} ---",
                            'stream': 'system',
                            'plugin_name': process_info.get('plugin', 'Unknown'),
                            'command': process_info.get('command', 'Unknown'),
                            'is_complete': True,
                            'exit_code': exit_code,
                            'timestamp': datetime.now().isoformat(),
                        }
                        self.socketio.emit('command_output', completion_data)

                    # Clean up active process entry after a short delay (allows UI to receive completion)
                    await asyncio.sleep(5) # Keep basic info for 5 seconds
                    self.active_processes.pop(process_id, None)
                    # Optionally schedule cache/status cleanup later
                    # await asyncio.sleep(300) # e.g., clear cache after 5 mins
                    # self.process_output_cache.pop(process_id, None)
                    # self.process_completion_status.pop(process_id, None)

            asyncio.create_task(wait_and_cleanup())

            return process_id # Return the ID successfully

        except FileNotFoundError:
            error_msg = f"Error: Command not found - '{cmd_parts[0]}'. Ensure it's in the system PATH."
            self.logger.error(error_msg)
            if self.socketio:
                 await self.emit_alert({'level': 'ERROR', 'message': error_msg, 'category': 'SYSTEM'})
                 # Emit completion immediately for UI consistency
                 err_data = {
                    'process_id': process_id, # Still use the generated ID
                    'output': error_msg, 'stream': 'system_error',
                    'plugin_name': plugin_name, 'command': command,
                    'is_complete': True, 'exit_code': -4, # Specific code for FileNotFoundError
                    'timestamp': datetime.now().isoformat(),
                 }
                 self.socketio.emit('command_output', err_data)
            return None # Indicate immediate failure
        except Exception as e:
            error_msg = f"Failed to start command '{command}': {e}"
            self.logger.error(error_msg, exc_info=True)
            if self.socketio:
                await self.emit_alert({'level': 'ERROR', 'message': error_msg, 'category': 'SYSTEM'})
                err_data = {
                    'process_id': process_id,
                    'output': error_msg, 'stream': 'system_error',
                    'plugin_name': plugin_name, 'command': command,
                    'is_complete': True, 'exit_code': -5, # Specific code for other start errors
                    'timestamp': datetime.now().isoformat(),
                 }
                self.socketio.emit('command_output', err_data)
            return None # Indicate immediate failure

    async def send_cached_output_to_client(self, sid: str):
        """
        Sends cached output and status of active/recently completed processes
        tracked by *this handler* to a specific client.

        Args:
            sid: Socket ID of the client to send to.
        """
        if not self.socketio:
            self.logger.warning("Cannot send cached output: SocketIO instance not set")
            return

        try:
            # Combine active and recently completed processes for the initial sync
            # Use keys from handler's own tracking dictionaries
            all_relevant_pids = set(self.active_processes.keys()) | set(self.process_completion_status.keys())

            if not all_relevant_pids:
                self.logger.debug(f"No tracked processes with output to send to SID {sid}")
                return

            self.logger.info(f"Sending cached output for {len(all_relevant_pids)} processes to SID {sid}")

            for process_id in all_relevant_pids:
                process_info = self.active_processes.get(process_id)
                completion_info = self.process_completion_status.get(process_id)
                cached_lines = self.process_output_cache.get(process_id, [])

                # Determine the base info (prefer active, fallback needed if only completion exists)
                base_info = None
                if process_info:
                    base_info = {
                        'process_id': process_id,
                        'plugin_name': process_info.get('plugin', 'Unknown'),
                        'command': process_info.get('command', 'Unknown'),
                        'start_time': datetime.fromtimestamp(process_info.get('start_time', 0)).isoformat(),
                    }
                elif completion_info and cached_lines:
                    # If only completion info exists, try to reconstruct basic info from cache/logs if possible
                    # This is difficult. For now, we might just send the cached lines and completion status.
                    # Let's assume the first cached line might contain useful info or we just use placeholders.
                    # A better approach would be to store basic info alongside completion status.
                    self.logger.warning(f"Process {process_id} completed, reconstructing basic info might be incomplete.")
                    # Placeholder reconstruction:
                    base_info = {
                         'process_id': process_id,
                         'plugin_name': 'Unknown (Completed)',
                         'command': 'Unknown (Completed)',
                         'start_time': None, # Cannot reliably know start time
                    }


                if base_info:
                     # Send the initial process info first
                     self.socketio.emit('current_process', base_info, room=sid)

                     # Send cached output lines
                     for line in cached_lines:
                         # Reconstruct the output data structure
                         output_data = {
                             'process_id': process_id,
                             'output': line,
                             'stream': 'cached', # Indicate it's cached
                             'plugin_name': base_info['plugin_name'],
                             'command': base_info['command'],
                             'is_complete': False, # Assume not complete unless status says otherwise
                             'timestamp': datetime.now().isoformat(), # Timestamp of sending cache
                         }
                         self.socketio.emit('command_output', output_data, room=sid)

                     # If completed, send the completion status too
                     if completion_info:
                         completion_data = {
                             'process_id': process_id,
                             'output': f"--- Process finished with exit code {completion_info['exit_code']} (Cached Status) ---",
                             'stream': 'system',
                             'plugin_name': base_info['plugin_name'],
                             'command': base_info['command'],
                             'is_complete': True,
                             'exit_code': completion_info['exit_code'],
                             'timestamp': datetime.now().isoformat(),
                         }
                         self.socketio.emit('command_output', completion_data, room=sid)

        except Exception as e:
            self.logger.error(f"Error sending cached output to client SID {sid}: {e}", exc_info=True)

    # --- Helper Methods ---

    def _serialize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Basic serialization for context dictionary."""
        if not isinstance(context, dict):
            return {} # Return empty dict if context is not a dict

        safe_context = {}
        for key, value in context.items():
            try:
                # Attempt to JSON encode/decode to check serializability
                # This is a bit heavy but safer than basic type checking for nested structures
                json.dumps({key: value})
                safe_context[key] = value
            except (TypeError, OverflowError):
                # If not serializable, convert to string
                safe_context[key] = str(value)
        return safe_context

# --- Singleton Instance ---
# Create a single instance to be imported and used throughout the application
handler = SocketIOHandler()
