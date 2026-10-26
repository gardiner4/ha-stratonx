"""Persistent tank-scoped presets, independent of an open dashboard."""
import asyncio
from copy import deepcopy
import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from .const import DOMAIN
from .services import CHANNELS, TANK_SCHEMA, strict_integer, percentage

def preset_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 60:
        raise vol.Invalid("Preset name must contain 1–60 characters")
    return value.strip()

PRESET_SCHEMA = vol.Schema({
    vol.Required("name"): preset_name,
    vol.Required("duration_minutes"): vol.All(strict_integer, vol.Range(min=1, max=60)),
    vol.Required("channels"): vol.All([percentage], vol.Length(min=6, max=6)),
})

def preset_list(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise vol.Invalid("Publish 1–20 presets")
    result = [PRESET_SCHEMA(p) for p in value]
    if len({p["name"].casefold() for p in result}) != len(result):
        raise vol.Invalid("Preset names must be unique")
    return result

PUBLISH_SCHEMA = vol.Schema({**TANK_SCHEMA, vol.Required("presets"): preset_list})
NAMED_SCHEMA = vol.Schema({**TANK_SCHEMA, vol.Required("name"): preset_name})

class PresetLibrary:
    def __init__(self, hass):
        self.store = Store(hass, 1, DOMAIN + ".presets")
        self.lock = asyncio.Lock()
        self.data = None

    async def _load(self):
        if self.data is None:
            raw = await self.store.async_load()
            if raw is not None and not isinstance(raw, dict):
                raise HomeAssistantError("Invalid preset storage")
            self.data = raw or {}

    async def publish(self, tank, presets):
        async with self.lock:
            await self._load()
            updated = deepcopy(self.data)
            group = updated.setdefault(str(tank), {})
            for p in presets:
                group[p["name"].casefold()] = deepcopy(p)
            if len(group) > 100:
                raise HomeAssistantError("A tank can store up to 100 published presets")
            # Do not expose a failed write as successfully published.
            await self.store.async_save(updated)
            self.data = updated

    async def get(self, tank, name=None):
        async with self.lock:
            await self._load()
            group = self.data.get(str(tank), {})
            if name is None:
                return deepcopy(list(group.values()))
            preset = group.get(name.casefold())
            if preset is None:
                raise HomeAssistantError("Preset not found for that tank. Publish it from the card first.")
            return PRESET_SCHEMA(deepcopy(preset))

    async def delete(self, tank, name):
        async with self.lock:
            await self._load()
            updated = deepcopy(self.data)
            group = updated.get(str(tank), {})
            if name.casefold() not in group:
                raise HomeAssistantError("Preset not found for that tank")
            del group[name.casefold()]
            if not group:
                updated.pop(str(tank), None)
            await self.store.async_save(updated)
            self.data = updated

def register_preset_services(hass):
    if hass.services.has_service(DOMAIN, "activate_preset"):
        return
    library = PresetLibrary(hass)
    hass.data.setdefault(DOMAIN, {})["preset_library"] = library

    async def publish(call):
        await library.publish(call.data["tank_id"], call.data["presets"])

    async def listing(call):
        return {"presets": await library.get(call.data["tank_id"])}

    async def delete(call):
        await library.delete(call.data["tank_id"], call.data["name"])

    async def activate(call):
        preset = await library.get(call.data["tank_id"], call.data["name"])
        data = {"tank_id": call.data["tank_id"], "duration_minutes": preset["duration_minutes"]}
        data.update(zip(CHANNELS, preset["channels"]))
        # Reuse group locking, firmware checks, timer verification and rollback.
        await hass.services.async_call(DOMAIN, "set_tank_live", data, blocking=True, context=call.context)

    hass.services.async_register(DOMAIN, "publish_presets", publish, schema=PUBLISH_SCHEMA)
    hass.services.async_register(DOMAIN, "list_presets", listing, schema=vol.Schema(TANK_SCHEMA), supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "delete_preset", delete, schema=NAMED_SCHEMA)
    hass.services.async_register(DOMAIN, "activate_preset", activate, schema=NAMED_SCHEMA)
