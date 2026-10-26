"""Serialized polling with slower schedule refresh and failure backoff."""
from datetime import datetime, timedelta, timezone
import logging
from time import monotonic
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, DEFAULT_INTERVAL, SCHEDULE_INTERVAL, MAIN
from .client import connection, identity, query, read_schedule
from .protocol import header, temperatures, clocks, identify_packet

_LOGGER = logging.getLogger(__name__)


class StratonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.interval = entry.options.get("poll_interval", DEFAULT_INTERVAL)
        self.last_schedule = 0
        self.failures = 0
        super().__init__(hass, _LOGGER, name=f"Straton {entry.data['serial']}", config_entry=entry, update_interval=timedelta(seconds=self.interval))

    async def _async_update_data(self):
        try:
            async with connection(self.hass, self.entry.data["address"]) as client:
                info = await identity(client)
                if info["serial"] != self.entry.data["serial"]:
                    raise ValueError("Light identity changed")
                # Read the actual group on every poll. Do not infer it from a name.
                tank = info["tank_id"]
                passcode = self.entry.options.get("passcode", self.entry.data.get("passcode", 0))
                data = dict(info)
                data.update(temperatures(await query(client, header(0xC3, tank, passcode) + bytes(8))))
                # Clock decode failures must not discard otherwise valid telemetry.
                clock_start = datetime.now(timezone.utc)
                clock_packet = await query(client, header(0xC6, tank, passcode) + bytes(8))
                clock_end = datetime.now(timezone.utc)
                try:
                    data.update(clocks(clock_packet))
                    data["clock_read_at"] = clock_end
                    data["clock_response"] = clock_packet.hex()
                    if data["rtc_time"] is not None:
                        midpoint = clock_start + (clock_end - clock_start) / 2
                        data["clock_offset"] = round((data["rtc_time"] - midpoint).total_seconds(), 1)
                    data["clock_read_duration"] = round((clock_end - clock_start).total_seconds(), 2)
                except ValueError:
                    data["clock_error"] = "Unsupported clock response"
                previous = self.data or {}
                if previous.get("tank_id") == tank:
                    for key in ("schedule", "schedule_updated"):
                        if key in previous:
                            data[key] = previous[key]
                if "schedule" not in data or monotonic() - self.last_schedule >= SCHEDULE_INTERVAL:
                    data["schedule"] = await read_schedule(client, tank, passcode)
                    data["schedule_updated"] = datetime.now(timezone.utc)
                    self.last_schedule = monotonic()
                data["last_seen"] = datetime.now(timezone.utc)
                self.failures = 0
                self.update_interval = timedelta(seconds=self.interval)
                return data
        except Exception as exc:
            self.failures += 1
            self.update_interval = timedelta(seconds=min(900, self.interval * 2 ** min(self.failures, 4)))
            raise UpdateFailed(str(exc)) from exc

    async def refresh_schedule(self):
        self.last_schedule = 0
        await self.async_request_refresh()

    async def identify(self):
        """Blink only the connected fixture; never use the broadcast wrapper."""
        try:
            async with connection(self.hass, self.entry.data["address"]) as client:
                info = await identity(client)
                if info["serial"] != self.entry.data["serial"] or info["firmware"] != "1.4.0.2":
                    raise ValueError("Identify requires the verified identity and firmware 1.4.0.2")
                passcode = self.entry.options.get("passcode", self.entry.data.get("passcode", 0))
                await client.write_gatt_char(MAIN, identify_packet(info["tank_id"], passcode), response=True)
        except Exception as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def sync_clock(self):
        # Explicit button only; no automatic writes. Only the tested firmware.
        try:
            async with connection(self.hass, self.entry.data["address"]) as client:
                info = await identity(client)
                if info["serial"] != self.entry.data["serial"] or info["firmware"] != "1.4.0.2":
                    raise ValueError("Clock sync requires the verified identity and firmware 1.4.0.2")
                if not self.data or info["tank_id"] != self.data["tank_id"]:
                    raise ValueError("Tank group changed; refresh first")
                now = datetime.now(timezone.utc)
                if not 2026 <= now.year <= 2099:
                    raise ValueError("Host clock is outside supported range")
                prefix = header(0xD1, info["tank_id"], self.entry.options.get("passcode", self.entry.data.get("passcode", 0)), 0xB1, info["serial"])
                await client.write_gatt_char(MAIN, prefix + bytes((now.hour, now.minute, now.second, now.day, now.month, now.year - 2000, 0, 0)), response=True)
        except Exception as exc:
            raise HomeAssistantError(str(exc)) from exc
