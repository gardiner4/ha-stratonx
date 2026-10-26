"""Explicit, per-light maintenance buttons."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .entity import StratonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StratonButton(entry.runtime_data, "refresh", "Refresh schedule"), StratonButton(entry.runtime_data, "sync", "Sync clock (UTC)")])


class StratonButton(StratonEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        self._attr_icon = "mdi:refresh" if key == "refresh" else "mdi:clock-check-outline"

    async def async_press(self):
        if self.key == "refresh":
            await self.coordinator.refresh_schedule()
        else:
            await self.coordinator.sync_clock()
