from netfang.states.state import State


async def action_alert_battery_low() -> None:
    """Action for low battery alert."""
    # Import NetworkManager locally to avoid circular imports
    from netfang.network_manager import NetworkManager
    NetworkManager.instance.state_machine.update_state(
        State.ALERTING,
        alert_data={"type": "battery", "message": "Battery level is low!"}
    )


async def action_alert_interface_unplugged() -> None:
    """Action for interface unplugged alert."""
    # Import NetworkManager locally to avoid circular imports
    from netfang.network_manager import NetworkManager
    NetworkManager.instance.state_machine.update_state(
        State.ALERTING,
        alert_data={"type": "interface", "message": "Interface unplugged!"}
    )


async def action_alert_cpu_temp() -> None:
    """Action for high CPU temperature alert."""
    # Import NetworkManager locally to avoid circular imports
    from netfang.network_manager import NetworkManager
    NetworkManager.instance.state_machine.update_state(
        State.ALERTING,
        alert_data={"type": "temperature", "message": "CPU temperature is high!"}
    )
