# actions.py

from netfang.alert_manager import  AlertManager


async def action_alert_battery_low() -> None:
    """Action for low battery alert."""
    alert_data = {
        "type": "battery",
        "message": "Battery level is low!"
    }
    AlertManager.instance.raise_alert_from_data(alert_data)


async def action_alert_interface_unplugged() -> None:
    """Action for interface unplugged alert."""
    alert_data = {
        "type": "interface",
        "message": "Interface unplugged!"
    }
    AlertManager.instance.alert_manager.raise_alert_from_data(alert_data)


async def action_alert_cpu_temp() -> None:
    """Action for high CPU temperature alert."""
    alert_data = {
        "type": "temperature",
        "message": "CPU temperature is high!"
    }
    AlertManager.instance.alert_manager.raise_alert_from_data(alert_data)
