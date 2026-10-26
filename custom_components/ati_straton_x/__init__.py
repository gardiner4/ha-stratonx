"""ATI Straton X Bluetooth integration."""
from homeassistant.const import Platform
from .coordinator import StratonCoordinator
from .services import register_services
from .frontend import async_register_card

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass, entry):
    coordinator = StratonCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    register_services(hass)
    await async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


async def async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
