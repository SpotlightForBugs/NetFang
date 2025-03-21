import asyncio

import psutil

from netfang.api.waveshare_ups_hat_c import waveshare_ups_hat_c


async def condition_battery_low() -> bool:
    """Checks if battery is below 20% and not charging."""
    battery_percentage = await asyncio.to_thread(get_battery_percentage)
    is_charging = await asyncio.to_thread(get_charging_status)
    return battery_percentage < 20 and not is_charging


def get_charging_status() -> bool:
    """Returns the charging status."""
    if not globals().get("ups_hat_c"):
        globals()["ups_hat_c"] = waveshare_ups_hat_c()
    return globals()["ups_hat_c"].is_charging()


def get_battery_percentage() -> float:
    """Returns the battery percentage."""
    if not globals().get("ups_hat_c"):
        globals()["ups_hat_c"] = waveshare_ups_hat_c()
    return globals()["ups_hat_c"].get_battery_percentage()

async def condition_on_battery() -> bool:
    return not await asyncio.to_thread(get_charging_status)

async def condition_power_connected() -> bool:
    """Checks if the device is connected to power."""
    return await asyncio.to_thread(get_charging_status)
async def condition_interface_unplugged() -> bool:
    """Checks if any monitored network interface is unplugged."""
    # Import NetworkManager locally to avoid circular import issues.
    from netfang.network_manager import NetworkManager
    monitored = NetworkManager.global_monitored_interfaces
    stats = psutil.net_if_stats()
    return any(iface not in stats or not stats[iface].isup for iface in monitored)

async def condition_interface_replugged() -> bool:
    """Checks if any monitored network interface is replugged."""
    # Import NetworkManager locally to avoid circular import issues.
    from netfang.network_manager import NetworkManager
    monitored = NetworkManager.global_monitored_interfaces
    stats = psutil.net_if_stats()
    return any(iface in stats and stats[iface].isup for iface in monitored)


async def condition_cpu_temp_high() -> bool:
    """Checks if CPU temperature exceeds 70°C."""
    try:
        cpu_temp = await asyncio.to_thread(
            lambda: float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000.0
        )
    except Exception:
        return True # Default to True if we can't read the temperature because of a missing file or permission issue
    return cpu_temp > 70.0
