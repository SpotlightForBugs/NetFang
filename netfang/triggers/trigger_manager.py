from typing import List


from .async_trigger import AsyncTrigger


class TriggerManager:
    """Manages multiple AsyncTriggers."""

    def __init__(self, triggers: List[AsyncTrigger]) -> None:
        self.triggers: List[AsyncTrigger] = triggers

    def add_trigger(self, trigger: AsyncTrigger) -> None:
        """Adds a new trigger to the manager."""
        self.triggers.append(trigger)

    async def check_triggers(self) -> None:
        """Checks all triggers and fires actions if conditions are met."""
        for trigger in self.triggers:
            await trigger.check_and_fire()
