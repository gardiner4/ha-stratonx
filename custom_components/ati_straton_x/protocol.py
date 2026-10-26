"""Strict parsers for firmware-traced read commands. No schedule writes."""
import json
import re


def serial_id(value):
    value = value.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{12}", value):
        raise ValueError("Invalid light identity")
    return value


def header(opcode, tank, passcode=0, subcode=0, target=None):
    if not 0 <= tank <= 65535 or not 0 <= passcode <= 65535:
        raise ValueError("Invalid tank ID or passcode")
    return bytes([opcode, subcode]) + tank.to_bytes(2, "little") + passcode.to_bytes(2, "little") + (bytes.fromhex(serial_id(target)) if target else bytes(6))


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
