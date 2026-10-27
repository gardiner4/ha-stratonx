"""Explicit tank-group actions; never infer a target group from entity names."""
import voluptuous as vol
import math
import asyncio
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN

CHANNELS = ("uv_violet", "royal_blue", "blue", "horti_white", "white", "red")


def strict_integer(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value != int(value):
        raise vol.Invalid("An integer is required")
    return int(value)


def percentage(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise vol.Invalid("A channel percentage from 0 to 100 is required")
    return value


TANK_SCHEMA = {vol.Required("tank_id"): vol.All(strict_integer, vol.Range(min=1, max=65534))}
LIVE_SCHEMA = vol.Schema({
    **TANK_SCHEMA,
    vol.Required("duration_minutes", default=10): vol.All(strict_integer, vol.Range(min=1, max=60)),
    **{vol.Required(channel): percentage for channel in CHANNELS},
})


def register_services(hass):
    if hass.services.has_service(DOMAIN, "set_tank_live"):
        return

    action_lock = hass.data.setdefault(DOMAIN, {}).setdefault("live_action_lock", asyncio.Lock())

    async def handle(call):
        async with action_lock:
            await execute(call)

    async def execute(call):
        tank = call.data["tank_id"]
        candidates = []
        missing = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state.value != "loaded":
                previous = getattr(getattr(entry, "runtime_data", None), "data", None) or entry.data
                if previous.get("tank_id") == tank:
                    missing.append(entry.entry_id)
                continue
            coordinator = entry.runtime_data
            if coordinator.data and coordinator.data.get("tank_id") == tank:
                candidates.append(coordinator)
        if not candidates:
            raise HomeAssistantError("No loaded light belongs to that tank; refresh its tank information first")
        if any(c.data.get("firmware") != "1.4.0.2" for c in candidates):
            raise HomeAssistantError("Group live mode currently requires firmware 1.4.0.2")
        if len({c.entry.options.get("passcode", c.entry.data.get("passcode", 0)) for c in candidates}) != 1:
            raise HomeAssistantError("Configured lights in this tank have different passcodes; correct their options first")
        if call.service == "set_tank_live":
            if missing or any(not c.last_update_success or c.data.get("transport", "bluetooth") != "bluetooth" for c in candidates):
                raise HomeAssistantError("A configured light in this tank has no verified Bluetooth telemetry; live mode was not started")
        seconds = call.data["duration_minutes"] * 60 if call.service == "set_tank_live" else 0
        channels = [round(call.data[key] * 1023 / 100) for key in CHANNELS] if seconds else None
        # Firmware broadcasts are lossy. Contact every configured member so that
        # each receives and confirms its own timer instead of trusting one relay.
        try:
            for coordinator in candidates:
                await coordinator.set_tank_live(tank, seconds, channels)
            for coordinator in candidates:
                await coordinator.async_request_refresh()
                remaining = (coordinator.data or {}).get("live_remaining")
                if not coordinator.last_update_success or remaining is None or (seconds and remaining <= 0) or (not seconds and remaining != 0):
                    raise HomeAssistantError("A tank member did not confirm the requested timer state")
            if missing:
                raise HomeAssistantError("Some tank members are not loaded and could not be verified")
        except Exception as exc:
            # A partial group change is not success. Best-effort resume on every
            # configured member; unreachable members retain the bounded timer.
            for coordinator in candidates:
                try:
                    await coordinator.set_tank_live(tank, 0)
                except Exception:
                    pass
            raise HomeAssistantError("Tank action was incomplete; resume was attempted for all configured members. Check their timers.") from exc

    hass.services.async_register(DOMAIN, "set_tank_live", handle, schema=LIVE_SCHEMA)
    hass.services.async_register(DOMAIN, "resume_tank_schedule", handle, schema=vol.Schema(TANK_SCHEMA))
