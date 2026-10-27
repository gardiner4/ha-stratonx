"""Explicit, per-light maintenance buttons."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .entity import StratonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StratonButton(entry.runtime_data, "refresh", "Refresh schedule"), StratonButton(entry.runtime_data, "sync", "Sync clock (UTC)"), StratonButton(entry.runtime_data, "identify", "Identify light")])


class StratonButton(StratonEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        self._attr_icon = {"refresh": "mdi:refresh", "sync": "mdi:clock-check-outline", "identify": "mdi:lightbulb-on-outline"}[key]

    @property
    def available(self):
        return super().available and (self.key == "refresh" or (self.coordinator.data or {}).get("transport", "bluetooth") == "bluetooth")

    async def async_press(self):
        if self.key == "refresh":
            await self.coordinator.refresh_schedule()
        elif self.key == "identify":
            await self.coordinator.identify()
        else:
            await self.coordinator.sync_clock()
