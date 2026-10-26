"""Short BLE sessions through Home Assistant's selected proxy."""
import asyncio
from contextlib import asynccontextmanager
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from .const import DOMAIN, MAIN, TANK, SERIAL, FIRMWARE, HARDWARE, MANUFACTURER
from .protocol import serial_id, header, temperatures, schedule_count, schedule_node


@asynccontextmanager
async def connection(hass, address):
    # Share a single connection slot across every fixture and config flow.
    lock = hass.data.setdefault(DOMAIN, {}).setdefault("lock", asyncio.Lock())
    async with lock:
        device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
        if device is None:
            raise ValueError("Light is not visible to a connectable Bluetooth proxy")
        client = None
        try:
            async with asyncio.timeout(45):
                client = await establish_connection(BleakClientWithServiceCache, device, device.name or address, max_attempts=2)
                yield client
        finally:
            if client is not None and client.is_connected:
                async with asyncio.timeout(10):
                    await client.disconnect()


async def text(client, uuid):
    return bytes(await client.read_gatt_char(uuid)).decode("utf-8").strip("\x00 ")


async def identity(client):
    manufacturer = await text(client, MANUFACTURER)
    if manufacturer != "ATI Aquaristik GmbH":
        raise ValueError("Not an ATI light")
    serial = serial_id(await text(client, SERIAL))
    tank = int(await text(client, TANK))
    if not 0 <= tank <= 65535:
        raise ValueError("Unsupported tank ID")
    return {"serial": serial, "tank_id": tank, "firmware": await text(client, FIRMWARE), "hardware": await text(client, HARDWARE)}


async def query(client, packet):
    await client.write_gatt_char(MAIN, packet, response=True)
    return bytes(await client.read_gatt_char(MAIN))


async def read_schedule(client, tank, passcode):
    prefix = header(0xC7, tank, passcode)
    count = schedule_count(await query(client, prefix + b"\xcc"))
    nodes = [schedule_node(await query(client, prefix + b"\xdd" + i.to_bytes(2, "big"))) for i in range(count)]
    if any(a["timestamp"] >= b["timestamp"] for a, b in zip(nodes, nodes[1:])):
        raise ValueError("Schedule is not ordered")
    # Detect a concurrent schedule edit that changes the node count.
    if schedule_count(await query(client, prefix + b"\xcc")) != count:
        raise ValueError("Schedule changed during read; retry later")
    return {"nodes": nodes}
