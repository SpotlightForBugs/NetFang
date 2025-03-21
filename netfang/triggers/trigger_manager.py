from typing import List
import traceback

from .async_trigger import AsyncTrigger


class TriggerManager:
    """Manages multiple AsyncTriggers."""

    def __init__(self, triggers: List[AsyncTrigger]) -> None:
        self.triggers: List[AsyncTrigger] = triggers

    def add_trigger(self, trigger: AsyncTrigger) -> None:
        """Adds a new trigger to the manager."""
        self.triggers.append(trigger)
        print(f"[TriggerManager] Added trigger: {trigger.name}")

    async def check_triggers(self) -> None:
        """Checks all triggers and fires actions if conditions are met."""
        for trigger in self.triggers:
            try:
                print(f"[TriggerManager] Checking trigger: {trigger.name}")
                await trigger.check_and_fire()
            except Exception as e:
                print(f"[TriggerManager] Error checking trigger {trigger.name}: {e}")
                traceback.print_exc()
