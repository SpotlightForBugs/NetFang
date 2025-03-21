# actions.py

from netfang.alert_manager import AlertManager, AlertCategory


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
    AlertManager.instance.alert_manager.raise_alert_from_data(alert_data,check_duplicate=True)

async def action_alert_interface_replugged() -> None:
    """Action for interface replugged alert."""
    duplicate = AlertManager.instance.find_unresolved_alert(AlertCategory.INTERFACE, "Interface unplugged!")
    if duplicate is not None:
        AlertManager.instance.resolve_alert(duplicate)


async def action_alert_on_battery() -> None:
    """Action for device running on battery alert."""
    alert_data = {
        "type": "battery",
        "message": "Device is running on battery!"

    }
    AlertManager.instance.alert_manager.raise_alert_from_data(alert_data,check_duplicate=True)

async def action_alert_power_connected() -> None:
    """Resolves the on battery alert."""
    duplicate = AlertManager.instance.find_unresolved_alert(AlertCategory.BATTERY, "Device is running on battery!")
    if duplicate is not None:
        AlertManager.instance.resolve_alert(duplicate)



async def action_alert_cpu_temp() -> None:
    """Action for high CPU temperature alert."""
    alert_data = {
        "type": "temperature",
        "message": "CPU temperature is high!"
    }
    AlertManager.instance.alert_manager.raise_alert_from_data(alert_data)
