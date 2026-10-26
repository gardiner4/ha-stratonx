"""Verified telemetry and explicitly labeled schedule estimates."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime, EntityCategory
from .entity import StratonEntity
from .bluetooth_sensor import AdvertisementSensor
from .estimates import CHANNELS, LIMITATIONS, estimate_channels

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
    async_add_entities([AdvertisementSensor(c, key, name) for key, name in (
        ("bluetooth_signal", "Bluetooth signal"),
        ("bluetooth_source", "Bluetooth reporting proxy"),
        ("bluetooth_last_seen", "Last Bluetooth advertisement"),
    )])
    async_add_entities([EstimatedChannelSensor(c, index, key, name)
                        for index, (key, name) in enumerate(CHANNELS)])


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
    def available(self):
        if self.key == "last_seen":
            return bool((self.coordinator.data or {}).get("last_seen"))
        return super().available

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.key == "schedule":
            schedule = data.get("schedule")
            return len(schedule["nodes"]) if schedule else None
        return data.get(self.key)

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self.key == "schedule":
            attrs.update(self.coordinator.data.get("schedule") or {})
            attrs["refresh_policy"] = "Startup or manual; refresh after edits in the ATI app"
            attrs["last_refresh_error"] = self.coordinator.data.get("schedule_error")
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


class EstimatedChannelSensor(StratonEntity, SensorEntity):
    """A schedule snapshot, not measured PWM or optical output."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:brightness-percent"

    def __init__(self, coordinator, index, key, name):
        super().__init__(coordinator, f"estimated_{key}", f"Estimated {name} output")
        self.index = index

    @property
    def native_value(self):
        values, _ = estimate_channels(self.coordinator.data or {})
        return values[self.index] if values is not None else None

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        data = self.coordinator.data or {}
        _, reason = estimate_channels(data)
        attrs.update({
            "source": "Saved schedule with linear interpolation",
            "estimate_status": reason,
            "light_local_time": data.get("local_time"),
            "read_at": data.get("clock_read_at"),
            "schedule_last_read": data.get("schedule_updated"),
            "limitations": LIMITATIONS,
        })
        return attrs
