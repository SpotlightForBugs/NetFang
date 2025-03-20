import asyncio
from typing import Dict, Any, Optional, Callable

from netfang.states.state import State


class StateMachine:
    """
    Handles state transitions and plugin notifications.
    """
    def __init__(
            self,
            state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = None
    ) -> None:
        self.current_state: State = State.WAITING_FOR_NETWORK
        self.state_context: Dict[str, Any] = {}
        self.state_change_callback: Optional[Callable[[State, Dict[str, Any]], None]] = state_change_callback
        self.state_lock: asyncio.Lock = asyncio.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None  # Will be set later

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the event loop for scheduling state update tasks."""
        self.loop = loop

    async def flow_loop(self) -> None:
        """
        Main loop that periodically notifies plugins about the current state.
        """
        while True:
            async with self.state_lock:
                await self.notify_plugins(self.current_state)
            await asyncio.sleep(5)

    async def notify_plugins(self, state: State) -> None:
        """
        Notifies plugins about the current state change.
        """
        if self.state_change_callback:
            self.state_change_callback(self.current_state, self.state_context)

    def update_state(
            self,
            new_state: State,
            mac: str = "",
            ssid: str = "",
            message: str = "",
            alert_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Updates the current state and schedules a task to notify plugins.
        """
        if alert_data is None:
            alert_data = {}

        async def update() -> None:
            async with self.state_lock:
                if self.current_state == new_state:
                    return
                old_state: State = self.current_state
                self.current_state = new_state
                self.state_context = {
                    "mac": mac,
                    "ssid": ssid,
                    "message": message,
                    "alert_data": alert_data,
                }
                print(f"[StateMachine] State transition: {old_state.value} -> {new_state.value}")
                if self.state_change_callback:
                    self.state_change_callback(self.current_state, self.state_context)

        if self.loop is None:
            raise RuntimeError("Event loop for StateMachine is not set!")
        self.loop.create_task(update())
