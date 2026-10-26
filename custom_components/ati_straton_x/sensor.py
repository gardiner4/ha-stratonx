"""Verified telemetry; no schedule estimates presented as channel output."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, EntityCategory
from .entity import StratonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities([StratonSensor(c, key, name) for key, name in (
        ("temperature_1", "Temperature 1"), ("temperature_2", "Temperature 2"),
        ("controller_temperature", "Controller temperature"), ("tank_id", "Tank group"),
        ("firmware", "Firmware"), ("last_seen", "Last successful poll"),
        ("schedule", "Schedule points"), ("schedule_updated", "Schedule last read"),
    )])


class StratonSensor(StratonEntity, SensorEntity):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        if "temperature" in key:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key in ("last_seen", "schedule_updated"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif key in ("tank_id", "firmware"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        data = self.coordinator.data
        return len(data["schedule"]["nodes"]) if self.key == "schedule" else data.get(self.key)

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self.key == "schedule":
            attrs.update(self.coordinator.data["schedule"])
            attrs["channel_scale"] = "0–1023 (schedule values, not live output)"
        return attrs
