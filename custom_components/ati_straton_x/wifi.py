"""Read-only, serial-verified HTTP telemetry and explicit bounded LAN discovery."""
import asyncio
import ipaddress
import json
import math
import re
from datetime import datetime, timezone

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .protocol import serial_id

MAX_RESPONSE = 65536
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def normalize_host(value):
    """Accept a bare IPv4 address or DNS hostname, never a URL or credentials."""
    host = value.strip().lower()
    if len(host) > 253 or not host or any(c in host for c in "/:@?#"):
        raise ValueError("Enter an IP address or hostname without a URL or port")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if all(c in "0123456789." for c in host):
            raise ValueError("Invalid IP address") from None
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")):
            raise ValueError("Invalid hostname") from None
    else:
        if address.version != 4 or not any(address in n for n in PRIVATE_NETWORKS):
            raise ValueError("Use a private LAN IPv4 address")
    return host


def scan_network(value):
    network = ipaddress.ip_network(value.strip(), strict=False)
    if network.version != 4 or network.prefixlen < 24 or not any(network.subnet_of(n) for n in PRIVATE_NETWORKS):
        raise ValueError("Choose a private IPv4 subnet of /24 or smaller")
    return network


async def get_json(hass, host, path, timeout=4):
    """Only call known read endpoints. Limit time, body size and redirects."""
    if path not in ("settings_get", "setting_get", "temp_get", "time_get", "schedule.json"):
        raise ValueError("Unsupported read endpoint")
    session = async_get_clientsession(hass)
    async with session.get(
        f"http://{normalize_host(host)}/{path}",
        timeout=aiohttp.ClientTimeout(total=timeout),
        allow_redirects=False,
    ) as response:
        if response.status != 200:
            raise ValueError("HTTP endpoint unavailable")
        body = bytearray()
        async for chunk in response.content.iter_chunked(4096):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE:
                raise ValueError("HTTP response too large")
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            raise ValueError("Invalid JSON response") from None
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value


def parse_identity(raw, expected):
    if not isinstance(raw.get("id"), str):
        raise ValueError("Missing light serial")
    if serial_id(raw["id"]) != serial_id(expected):
        raise ValueError("Wi-Fi address belongs to a different light")
    tank = raw.get("tankId")
    if type(tank) is not int or not 0 <= tank <= 65535:
        raise ValueError("Invalid tank ID")
    if any(not isinstance(raw.get(k), str) or not 1 <= len(raw[k]) <= 32 for k in ("fwVer", "hwVer")):
        raise ValueError("Missing firmware or hardware version")
    # Do not retain passcode, AP password, SSID or other settings.
    return {"serial": serial_id(expected), "tank_id": tank,
            "firmware": raw["fwVer"], "hardware": raw["hwVer"]}


async def verified_identity(hass, host, serial, timeout=4):
    # Firmware strings use settings_get; some versions expose setting_get.
    try:
        raw = await get_json(hass, host, "settings_get", timeout)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        raw = await get_json(hass, host, "setting_get", timeout)
    return parse_identity(raw, serial)


def parse_temperatures(raw):
    result = {}
    for field, key in (("t_1", "temperature_1"), ("t_2", "temperature_2"), ("t_esp", "controller_temperature")):
        value = raw.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or not -40 <= value <= 125:
            raise ValueError("Invalid temperature")
        result[key] = value
    return result


def parse_clocks(raw):
    result = {"rtc_time": None, "local_time": None}
    for prefix, key in (("rtc", "rtc_time"), ("esp", "local_time")):
        values = [raw.get(f"{prefix}_{part}") for part in ("year", "month", "day", "hour", "minute", "second")]
        if any(type(v) is not int for v in values) or not 2026 <= values[0] <= 2099:
            continue
        try:
            stamp = datetime(*values)
        except ValueError:
            continue
        result[key] = stamp.replace(tzinfo=timezone.utc) if key == "rtc_time" else stamp.isoformat(sep=" ")
    return result


def parse_schedule(raw):
    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or len(nodes) > 128:
        raise ValueError("Invalid schedule")
    result, previous = [], -1
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Invalid schedule node")
        stamp, channels = node.get("timestamp"), node.get("channelValues")
        if (type(stamp) is not int or not previous < stamp < 86400 or
                not isinstance(channels, list) or len(channels) != 6 or
                any(type(v) is not int or not 0 <= v <= 1023 for v in channels)):
            raise ValueError("Invalid schedule node")
        result.append({"timestamp": stamp, "channelValues": list(channels)})
        previous = stamp
    return {"nodes": result}


async def read_telemetry(hass, host, serial):
    data = await verified_identity(hass, host, serial)
    data.update(parse_temperatures(await get_json(hass, host, "temp_get")))
    try:
        start = datetime.now(timezone.utc)
        data.update(parse_clocks(await get_json(hass, host, "time_get")))
        end = datetime.now(timezone.utc)
        data["clock_read_at"] = end
        data["clock_read_duration"] = round((end - start).total_seconds(), 2)
        if data.get("rtc_time") is not None:
            data["clock_offset"] = round((data["rtc_time"] - (start + (end-start)/2)).total_seconds(), 1)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        data["clock_error"] = "Wi-Fi clock unavailable"
    # No verified HTTP live timer: never reuse an old BLE timer.
    data["live_timer_error"] = "Live timer requires Bluetooth"
    data["transport"] = "wifi"
    data["wifi_host"] = normalize_host(host)
    data["last_seen"] = datetime.now(timezone.utc)
    return data


async def http_port_open(host):
    """Skip offline hosts quickly, leaving slow JSON servers enough time."""
    writer = None
    try:
        async with asyncio.timeout(0.7):
            _, writer = await asyncio.open_connection(host, 80)
        return True
    except (OSError, TimeoutError):
        return False
    finally:
        if writer is not None:
            writer.close()


async def discover_host(hass, subnet, serial):
    """User-initiated scan only, max 256 addresses and 16 concurrent requests."""
    network = scan_network(subnet)
    semaphore = asyncio.Semaphore(16)
    async def check(address):
        host = str(address)
        async with semaphore:
            try:
                if not await http_port_open(host):
                    return None
                await verified_identity(hass, host, serial, timeout=4)
                return host
            except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, AttributeError):
                return None
    async with asyncio.timeout(110):
        matches = [host for host in await asyncio.gather(*(check(a) for a in network.hosts())) if host]
    if len(matches) != 1:
        raise ValueError("No unique matching light found; enter its IP address manually")
    return matches[0]
