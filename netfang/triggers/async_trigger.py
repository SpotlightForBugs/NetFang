import asyncio
from typing import Callable, Union, Awaitable

ConditionFunc = Callable[[], Union[bool, Awaitable[bool]]]
ActionFunc = Callable[[], Union[None, Awaitable[None]]]


class AsyncTrigger:
    """Represents an asynchronous trigger with a condition and an action."""

    def __init__(self, name: str, condition: ConditionFunc, action: ActionFunc) -> None:
        self.name: str = name
        self.condition: ConditionFunc = condition
        self.action: ActionFunc = action

    async def check_and_fire(self) -> None:
        """Checks the condition and fires the action if condition is True."""
        cond_result = self.condition()
        if asyncio.iscoroutine(cond_result):
            cond_result = await cond_result
        if cond_result:
            act_result = self.action()
            if asyncio.iscoroutine(act_result):
                await act_result
