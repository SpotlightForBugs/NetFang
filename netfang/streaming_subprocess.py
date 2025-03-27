import asyncio
import logging
import subprocess
from typing import List, Optional, Callable, Dict, Any, Deque
from collections import deque
from datetime import datetime

from netfang.socketio_handler import handler


class StreamingSubprocess:
    """
    Executes a subprocess command and streams its output to the dashboard in real-time.
    """

    # Class variable to track all running processes
    _active_processes = {}
    _output_cache = {}  # Cache for storing output when no clients are connected
    _max_cache_lines = 1000  # Maximum number of lines to cache per process

    def __init__(
        self,
        plugin_name: str,
        command: List[str],
        db_path: Optional[str] = None,
        on_complete: Optional[Callable[[int], None]] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize the streaming subprocess.

        Args:
            plugin_name: Name of the plugin running the command
            command: Command to execute as a list of strings
            db_path: Optional database path for logging
            on_complete: Optional callback function to call when the process completes
            timeout: Optional timeout in seconds
        """
        self.plugin_name = plugin_name
        self.command = command
        self.cmd_str = " ".join(command)
        self.db_path = db_path
        self.on_complete = on_complete
        self.timeout = timeout
        self.process = None
        self.process_id = (
            f"{plugin_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(self)}"
        )
        self.logger = logging.getLogger(__name__)
        self._output_buffer = deque(maxlen=self._max_cache_lines)
        self._is_complete = False

    @classmethod
    def get_active_processes(cls) -> Dict[str, "StreamingSubprocess"]:
        """Get all active streaming processes."""
        return cls._active_processes

    @classmethod
    def get_cached_output(cls, process_id: str) -> List[Dict[str, Any]]:
        """Get cached output for a specific process."""
        return list(cls._output_cache.get(process_id, []))

    @classmethod
    def are_all_processes_complete(cls) -> bool:
        """Check if all registered processes have completed."""
        return all(p._is_complete for p in cls._active_processes.values())

    @classmethod
    async def check_all_processes_status(cls) -> None:
        """Check if all processes are complete and notify clients if so."""
        if cls.are_all_processes_complete() and cls._active_processes:
            # All processes are complete, notify state change
            await handler.notify_scanning_complete()
            # Clear the active processes tracking
            cls._active_processes = {}

    async def run(self) -> Dict[str, Any]:
        """
        Run the subprocess command and stream output to the dashboard.

        Returns:
            Dict with status, stdout, stderr, and return_code
        """
        self.logger.info(f"[{self.plugin_name}] Running command: {self.cmd_str}")

        # Register this process in the active processes list
        self._is_complete = False
        StreamingSubprocess._active_processes[self.process_id] = self

        # Create empty cache for this process
        StreamingSubprocess._output_cache[self.process_id] = deque(
            maxlen=self._max_cache_lines
        )

        # Log command to database if db_path is provided
        if self.db_path:
            try:
                from netfang.db.database import add_plugin_log

                add_plugin_log(
                    self.db_path, self.plugin_name, f"Running command: {self.cmd_str}"
                )
            except ImportError:
                self.logger.warning("Could not import add_plugin_log")

        # Start the process
        try:
            # Set the current process info in the dashboard
            await handler.set_current_process(
                self.plugin_name, self.cmd_str, process_id=self.process_id
            )

            # Create process with pipes for stdout and stderr
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Read and stream stdout and stderr concurrently
            stdout_task = asyncio.create_task(
                self._read_stream(self.process.stdout, False)
            )
            stderr_task = asyncio.create_task(
                self._read_stream(self.process.stderr, True)
            )

            # Wait for process to complete with optional timeout
            try:
                return_code = await asyncio.wait_for(self.process.wait(), self.timeout)
                # Process completed successfully
                await asyncio.gather(stdout_task, stderr_task)
                result = {
                    "status": "completed",
                    "stdout": stdout_task.result(),
                    "stderr": stderr_task.result(),
                    "return_code": return_code,
                }

                # Add completion message to output cache
                completion_msg = f"Process completed with return code {return_code}"
                self._cache_output(completion_msg, True)

            except asyncio.TimeoutError:
                # Process timed out
                self.process.terminate()
                await asyncio.gather(stdout_task, stderr_task)
                result = {
                    "status": "timeout",
                    "stdout": stdout_task.result(),
                    "stderr": stderr_task.result(),
                    "return_code": -1,
                }

                timeout_msg = f"Process timed out after {self.timeout} seconds"
                await handler.stream_command_output(
                    self.plugin_name, self.cmd_str, timeout_msg, True, self.process_id
                )

                # Add timeout message to output cache
                self._cache_output(timeout_msg, True)

            # Log completion status
            if self.db_path:
                try:
                    from netfang.db.database import add_plugin_log

                    status_msg = (
                        f"Command completed with return code {result['return_code']}"
                    )
                    if result["status"] == "timeout":
                        status_msg = f"Command timed out after {self.timeout} seconds"
                    add_plugin_log(self.db_path, self.plugin_name, status_msg)
                except ImportError:
                    pass

            # Mark this process as complete
            self._is_complete = True

            # Clear current process info
            await handler.clear_current_process(self.process_id)

            # Check if all processes are complete
            await self.check_all_processes_status()

            # Call completion callback if provided
            if self.on_complete:
                self.on_complete(result["return_code"])

            return result

        except Exception as e:
            # Handle any exceptions
            error_msg = f"Error executing command: {str(e)}"
            self.logger.error(f"[{self.plugin_name}] {error_msg}")

            # Log error to database
            if self.db_path:
                try:
                    from netfang.db.database import add_plugin_log

                    add_plugin_log(self.db_path, self.plugin_name, error_msg)
                except ImportError:
                    pass

            # Stream error message to dashboard
            await handler.stream_command_output(
                self.plugin_name, self.cmd_str, error_msg, True, self.process_id
            )

            # Add error message to output cache
            self._cache_output(error_msg, True)

            # Mark this process as complete
            self._is_complete = True

            # Clear current process info
            await handler.clear_current_process(self.process_id)

            # Check if all processes are complete
            await self.check_all_processes_status()

            # Call completion callback if provided
            if self.on_complete:
                self.on_complete(-1)

            return {
                "status": "error",
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
            }

    def _cache_output(self, line: str, is_complete: bool = False) -> None:
        """
        Cache output line for this process.

        Args:
            line: The line of output to cache
            is_complete: Whether this is a completion message
        """
        output_data = {
            "plugin_name": self.plugin_name,
            "command": self.cmd_str,
            "output": line,
            "is_complete": is_complete,
            "timestamp": datetime.now().isoformat(),
        }

        # Add to process-specific output cache
        if self.process_id in StreamingSubprocess._output_cache:
            StreamingSubprocess._output_cache[self.process_id].append(output_data)

        # Also add to instance buffer for returning complete output
        self._output_buffer.append(line)

    async def _read_stream(self, stream, is_stderr: bool) -> str:
        """
        Read from an async stream and stream output to the dashboard.

        Args:
            stream: The stream to read from
            is_stderr: Whether this is stderr (True) or stdout (False)

        Returns:
            The complete output as a string
        """
        output_lines = []

        while True:
            line = await stream.readline()
            if not line:
                break

            # Decode line and strip whitespace
            line_str = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(line_str)

            # Stream output to dashboard using the async method since we're in an async context
            await handler.stream_command_output(
                self.plugin_name, self.cmd_str, line_str, False, self.process_id
            )

            # Cache the output
            self._cache_output(line_str)

        return "\n".join(output_lines)

    async def stop(self) -> None:
        """Stop the process if it's running."""
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                if self.process.returncode is None:
                    self.process.kill()

                # Log and stream termination message
                message = f"Process {self.cmd_str} was terminated"
                await handler.stream_command_output(
                    self.plugin_name, self.cmd_str, message, True, self.process_id
                )

                # Cache the termination message
                self._cache_output(message, True)

                if self.db_path:
                    try:
                        from netfang.db.database import add_plugin_log

                        add_plugin_log(self.db_path, self.plugin_name, message)
                    except ImportError:
                        pass

                # Mark this process as complete
                self._is_complete = True

                # Clear current process info
                await handler.clear_current_process(self.process_id)

                # Check if all processes are complete
                await self.check_all_processes_status()

            except Exception as e:
                self.logger.error(f"Error stopping process: {str(e)}")

    def get_cached_output(self) -> List[str]:
        """Get all cached output for this process."""
        return list(self._output_buffer)


def run_subprocess_sync(
    plugin_name: str,
    command: List[str],
    db_path: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run a subprocess command synchronously with output streaming.
    This is a convenience wrapper for non-async code.

    Args:
        plugin_name: Name of the plugin running the command
        command: Command to execute as a list of strings
        db_path: Optional database path for logging
        timeout: Optional timeout in seconds

    Returns:
        Dict with status, stdout, stderr, and return_code
    """
    # Create async subprocess runner
    subprocess_runner = StreamingSubprocess(
        plugin_name, command, db_path, timeout=timeout
    )

    # Run the command in the event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create a new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run the async command and return results
    try:
        return loop.run_until_complete(subprocess_runner.run())
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in run_subprocess_sync: {str(e)}")
        return {"status": "error", "stdout": "", "stderr": str(e), "return_code": -1}
