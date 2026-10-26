"""Verified telemetry; no schedule estimates presented as channel output."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime, EntityCategory
from .entity import StratonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities([StratonSensor(c, key, name) for key, name in (
        ("temperature_1", "Temperature 1"), ("temperature_2", "Temperature 2"),
        ("controller_temperature", "Controller temperature"), ("tank_id", "Tank group"),
        ("firmware", "Firmware"), ("last_seen", "Last successful poll"),
        ("schedule", "Schedule points"), ("schedule_updated", "Schedule last read"),
        ("local_time", "Light date and time"), ("rtc_time", "Hardware clock"),
        ("clock_offset", "Clock offset"), ("hardware", "Hardware version"),
        ("live_remaining", "Live mode remaining"),
    )])


class StratonSensor(StratonEntity, SensorEntity):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        if "temperature" in key:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key in ("clock_offset", "live_remaining"):
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_icon = "mdi:timer-alert-outline"
        elif key == "local_time":
            self._attr_icon = "mdi:clock-outline"
        elif key in ("last_seen", "schedule_updated", "rtc_time"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif key in ("tank_id", "firmware", "hardware"):
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
        elif self.key == "live_remaining":
            attrs["read_at"] = self.coordinator.data.get("live_read_at")
            attrs["description"] = "Device override timer snapshot; zero means no timed override, not light off"
        elif self.key in ("local_time", "rtc_time", "clock_offset"):
            data = self.coordinator.data
            attrs["read_at"] = data.get("clock_read_at")
            attrs["read_duration_seconds"] = data.get("clock_read_duration")
            if self.key == "local_time":
                attrs["time_basis"] = "Light's configured local time; snapshot at last poll"
            elif self.key == "clock_offset":
                attrs["positive_means"] = "Light hardware clock ahead of Home Assistant (UTC)"
        return attrs
