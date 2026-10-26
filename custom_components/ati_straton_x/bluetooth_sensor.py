"""Advertisement diagnostics; never open a Bluetooth connection."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from time import monotonic
from homeassistant.components import bluetooth
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN

STALE_SECONDS = 180

class AdvertisementSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self.key = key
        self.address = coordinator.entry.data["address"]
        self.serial = coordinator.entry.data["serial"]
        self._attr_name = name
        self._attr_unique_id = f"{self.serial}_{key}"
        self._attr_device_info = dr.DeviceInfo(identifiers={(DOMAIN, self.serial)})
        self.info = None
        self.observed_time = None
        self.seen_at = None
        self.age = None
        self.proxy_name = None
        self.fresh = False
        if key == "bluetooth_signal":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = "dBm"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "bluetooth_last_seen":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_icon = "mdi:bluetooth-connect"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.sample()
        self.async_on_remove(async_track_time_interval(self.hass, self._tick, timedelta(seconds=30)))

    @callback
    def _tick(self, _now):
        self.sample()
        self.async_write_ha_state()

    @callback
    def sample(self):
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        if info is not None and isfinite(info.time) and info.time > 0:
            # HA timestamps advertisements using monotonic time, not wall time.
            if self.observed_time is None or info.time >= self.observed_time:
                changed = info.time != self.observed_time
                self.observed_time = info.time
                self.info = info
                if changed:
                    self.seen_at = datetime.now(timezone.utc) - timedelta(seconds=max(0, monotonic() - info.time))
                device = dr.async_get(self.hass).async_get_device(connections={(dr.CONNECTION_NETWORK_MAC, info.source)})
                self.proxy_name = (device.name_by_user or device.name) if device else info.source
        self.age = max(0, monotonic() - self.info.time) if self.info else None
        self.fresh = self.age is not None and self.age <= STALE_SECONDS

    @property
    def available(self):
        # Historical last-seen remains useful even when the lamp stops advertising.
        return self.seen_at is not None if self.key == "bluetooth_last_seen" else self.fresh

    @property
    def native_value(self):
        if self.key == "bluetooth_last_seen":
            return self.seen_at
        if not self.fresh:
            return None
        return self.info.rssi if self.key == "bluetooth_signal" else self.proxy_name

    @property
    def extra_state_attributes(self):
        return {
            "serial": self.serial,
            "tank_id": (self.coordinator.data or {}).get("tank_id"),
            "source": self.info.source if self.info else None,
            "last_advertisement": self.seen_at,
            "advertisement_age_seconds": round(self.age) if self.age is not None else None,
            "stale_after_seconds": STALE_SECONDS,
            "description": "Cached advertisement from a connectable scanner; not active GATT link quality or proxy Wi-Fi signal",
        }
