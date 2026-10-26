"""One physical device per serial number, with tank membership attributes."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN


class StratonEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        serial = coordinator.entry.data["serial"]
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)}, manufacturer="ATI Aquaristik GmbH", model="Straton X", name=f"Straton X {serial[-6:]}", serial_number=serial, sw_version=coordinator.data["firmware"], hw_version=coordinator.data["hardware"])

    @property
    def extra_state_attributes(self):
        return {"tank_id": self.coordinator.data["tank_id"], "serial": self.coordinator.entry.data["serial"]}
