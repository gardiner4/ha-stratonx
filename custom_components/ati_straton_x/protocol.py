"""Strict parsers for firmware-traced read commands. No schedule writes."""
import json
import re
from datetime import datetime, timezone


def clocks(value):
    """Decode C6: RTC UTC and ESP local calendar, each byte biased by one."""
    if not 16 <= len(value) <= 200 or any(value[16:]) or any(value[i] != 255 for i in (0, 7, 15)):
        raise ValueError("Unexpected clock response")
    result = {"rtc_time": None, "local_time": None}
    for offset, key in ((1, "rtc_time"), (8, "local_time")):
        hour, minute, second, day, month, year = (v - 1 for v in value[offset:offset + 6])
        if not 0 <= year <= 99:
            continue
        try:
            stamp = datetime(2000 + year, month, day, hour, minute, second)
        except ValueError:
            continue  # An unset clock is unknown, never a fabricated valid date.
        result[key] = stamp.replace(tzinfo=timezone.utc) if key == "rtc_time" else stamp.isoformat(sep=" ")
    return result


def serial_id(value):
    value = value.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{12}", value):
        raise ValueError("Invalid light identity")
    return value


def header(opcode, tank, passcode=0, subcode=0, target=None):
    if not 0 <= tank <= 65535 or not 0 <= passcode <= 65535:
        raise ValueError("Invalid tank ID or passcode")
    return bytes([opcode, subcode]) + tank.to_bytes(2, "little") + passcode.to_bytes(2, "little") + (bytes.fromhex(serial_id(target)) if target else bytes(6))


def identify_packet(tank, passcode=0):
    """C1 is connection-local: two 500 ms blinks on channel 5 (white)."""
    return header(0xC1, tank, passcode) + bytes((2, 4))


def live_remaining(value):
    """C2/B2 returns ASCII seconds, optionally NUL padded."""
    text, _, padding = bytes(value).partition(b"\x00")
    if any(padding) or not re.fullmatch(rb"[0-9]{1,5}", text):
        raise ValueError("Unexpected live timer response")
    seconds = int(text)
    if seconds > 65535:
        raise ValueError("Live timer out of range")
    return seconds


def live_timer_packet(tank, seconds, passcode=0):
    """Tank broadcast; zero resumes the saved schedule. No wildcard tanks."""
    if type(tank) is not int or not 1 <= tank <= 65534:
        raise ValueError("Live control requires an explicit tank group")
    if type(seconds) is not int or not 0 <= seconds <= 3600:
        raise ValueError("Live duration must be 0–3600 seconds")
    return header(0xB2, tank, passcode) + seconds.to_bytes(2, "big")


def live_channels_packet(tank, values, passcode=0):
    """Six manual PWM targets, not measured output; temporary group broadcast."""
    live_timer_packet(tank, 0, passcode)
    if not isinstance(values, (list, tuple)) or len(values) != 6 or any(type(v) is not int or not 0 <= v <= 1023 for v in values):
        raise ValueError("Exactly six integer channel targets in 0–1023 are required")
    return header(0xA2, tank, passcode) + b"".join(v.to_bytes(2, "big") for v in values)


def temperatures(value):
    if len(value) != 4 or value[0] != 255:
        raise ValueError("Unexpected temperature response")
    if any(v > 125 for v in value[1:]):
        raise ValueError("Invalid temperature")
    return dict(zip(("temperature_1", "temperature_2", "controller_temperature"), value[1:]))


def schedule_count(value):
    if len(value) < 3 or value[0] != 0xCC:
        raise ValueError("Unexpected schedule count")
    count = int.from_bytes(value[1:3], "little")
    if count > 128:
        raise ValueError("Schedule count out of bounds")
    return count


def schedule_node(value):
    if not value or value[0] != 0xBB:
        raise ValueError("Unexpected schedule node")
    node = json.loads(value[1:].split(b"\x00", 1)[0])
    t, channels = node.get("timestamp"), node.get("channelValues")
    if type(t) is not int or not 0 <= t < 86400:
        raise ValueError("Invalid timestamp")
    if not isinstance(channels, list) or len(channels) != 6 or any(type(v) is not int or not 0 <= v <= 1023 for v in channels):
        raise ValueError("Invalid channel values")
    return {"timestamp": t, "channelValues": channels}
