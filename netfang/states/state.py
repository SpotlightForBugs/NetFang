from enum import Enum


class State(Enum):
    # Connection states:
    WAITING_FOR_NETWORK = "WAITING_FOR_NETWORK"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"

    CONNECTING = "CONNECTING"
    CONNECTED_KNOWN = "CONNECTED_KNOWN"
    CONNECTED_HOME = "CONNECTED_HOME"
    CONNECTED_NEW = "CONNECTED_NEW"
    CONNECTED_BLACKLISTED = "CONNECTED_BLACKLISTED"

    # specific action states:
    SCANNING_IN_PROGRESS = "SCANNING_IN_PROGRESS"
    SCAN_COMPLETED = "SCAN_COMPLETED"

    # generic action state(s):
    PERFORM_ACTION = "PERFORM_ACTION"

    ALERTING = "ALERTING"

    def __str__(self) -> str:
        return self.value


def get_all_states() -> list[str]:
    return [state.value for state in State]
