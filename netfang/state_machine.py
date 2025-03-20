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
        self.state_change_callback: Optional[
            Callable[[State, Dict[str, Any]], None]
        ] = state_change_callback
        self.state_lock: asyncio.Lock = asyncio.Lock()

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
        If a state_change_callback is provided, it is invoked.
        """
        if self.state_change_callback:
            self.state_change_callback(self.current_state, self.state_context)

    def update_state(
            self,
            new_state: State,
            mac: str = "",
            message: str = "",
            alert_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Updates the current state and notifies plugins.
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
                    "message": message,
                    "alert_data": alert_data,
                }
                print(
                    f"[StateMachine] State transition: {old_state.value} -> {new_state.value}"
                )
                if self.state_change_callback:
                    self.state_change_callback(self.current_state, self.state_context)

        # Schedule the asynchronous state update.
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        loop.create_task(update())
