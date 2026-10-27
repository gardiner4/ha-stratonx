"""Serialized telemetry polling with startup/manual schedule reads."""
from datetime import datetime, timedelta, timezone
import logging
import asyncio
from bleak.exc import BleakError
from aioesphomeapi.core import APIConnectionError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, DEFAULT_INTERVAL, MAIN
from .client import connection, identity, query, read_schedule
from .protocol import header, temperatures, clocks, identify_packet, live_remaining
from .live import apply_live

_LOGGER = logging.getLogger(__name__)


class StratonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.interval = entry.options.get("poll_interval", DEFAULT_INTERVAL)
        self.schedule_requested = True
        self.failures = 0
        super().__init__(hass, _LOGGER, name=f"Straton {entry.data['serial']}", config_entry=entry, update_interval=timedelta(seconds=self.interval))

    async def _async_update_data(self):
        # Retry read-only telemetry on a NEW connection. Never replay controls.
        for attempt in range(2):
            try:
                data = await self._read_once()
                self.failures = 0
                self.update_interval = timedelta(seconds=self.interval)
                return data
            except (BleakError, APIConnectionError, TimeoutError, OSError) as exc:
                if attempt == 0:
                    _LOGGER.debug("Reconnecting %s after failed telemetry: %s",
                                  self.entry.data["serial"], exc)
                    # connection() has exited: other fixtures can use the slot.
                    await asyncio.sleep(2)
                    continue
                self._record_failure()
                raise UpdateFailed(str(exc)) from exc
            except Exception as exc:
                # Identity/decoder/configuration errors are not transport faults.
                self._record_failure()
                raise UpdateFailed(str(exc)) from exc

    def _record_failure(self):
        self.failures += 1
        # Recover promptly, but bound traffic for a persistently missing light.
        self.update_interval = timedelta(seconds=min(120, 30 * 2 ** min(self.failures - 1, 2)))

    async def _read_once(self):
        async with connection(self.hass, self.entry.data["address"]) as client:
            info = await identity(client)
            if info["serial"] != self.entry.data["serial"]:
                raise ValueError("Light identity changed")
            # Read the actual group on every poll. Do not infer it from a name.
            tank = info["tank_id"]
            passcode = self.entry.options.get("passcode", self.entry.data.get("passcode", 0))
            data = dict(info)
            data.update(temperatures(await query(client, header(0xC3, tank, passcode) + bytes(8))))
            if info["firmware"] == "1.4.0.2":
                timer_packet = await query(client, header(0xC2, tank, passcode, 0xB2))
                try:
                    data["live_remaining"] = live_remaining(timer_packet)
                    data["live_read_at"] = datetime.now(timezone.utc)
                except ValueError:
                    data["live_timer_error"] = "Unsupported live timer response"
                    data["live_timer_response"] = timer_packet.hex()
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
                for key in ("schedule", "schedule_updated", "schedule_error"):
                    if key in previous:
                        data[key] = previous[key]
            # New group invalidates the old group's cached schedule.
            if previous.get("tank_id") is not None and previous.get("tank_id") != tank:
                self.schedule_requested = True
            if self.schedule_requested:
                self.schedule_requested = False
                try:
                    data["schedule"] = await read_schedule(client, tank, passcode)
                    data["schedule_updated"] = datetime.now(timezone.utc)
                    data.pop("schedule_error", None)
                except Exception as exc:
                    # A schedule failure must not discard good telemetry or
                    # trigger another large download on every normal poll.
                    data["schedule_error"] = str(exc)
                    _LOGGER.warning("Schedule read failed for %s: %s", info["serial"], exc)
            data["last_seen"] = datetime.now(timezone.utc)
            return data

    async def refresh_schedule(self):
        self.schedule_requested = True
        # A manual button must await the actual read, not a debounced request.
        await self.async_refresh()
        if not self.last_update_success:
            raise HomeAssistantError("Schedule refresh failed: light could not be read")
        if (self.data or {}).get("schedule_error"):
            raise HomeAssistantError("Schedule refresh failed: " + self.data["schedule_error"])

    async def set_tank_live(self, tank, seconds, channels=None):
        """Explicit group action. A2/B2 can affect undiscovered members too."""
        try:
            async with connection(self.hass, self.entry.data["address"]) as client:
                info = await identity(client)
                if info["serial"] != self.entry.data["serial"] or info["firmware"] != "1.4.0.2" or info["tank_id"] != tank:
                    raise ValueError("Light identity, firmware, or tank group changed; refresh first")
                passcode = self.entry.options.get("passcode", self.entry.data.get("passcode", 0))
                await apply_live(
                    lambda packet: client.write_gatt_char(MAIN, packet, response=True),
                    lambda packet: query(client, packet), tank, passcode, seconds, channels,
                )
        except Exception as exc:
            raise HomeAssistantError(f"Tank live action failed; some members may have received it. The device timer is the fallback: {exc}") from exc

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
