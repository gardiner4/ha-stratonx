"""Run with Home Assistant's Python dependencies installed."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from custom_components.ati_straton_x import presets as mod

PHOTO = {"name": "Photo", "duration_minutes": 10, "channels": [0,100,100,0,0,0]}

class FakeStore:
    saved = None
    fail = False
    def __init__(self, *args): pass
    async def async_load(self): return deepcopy(self.saved)
    async def async_save(self, data):
        if self.fail: raise OSError("disk error")
        FakeStore.saved = deepcopy(data)

class PresetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeStore.saved = None
        FakeStore.fail = False
        self.patch = patch.object(mod, "Store", FakeStore)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.lib = mod.PresetLibrary(NS())

    async def test_restart_and_tank_isolation(self):
        await self.lib.publish(42, [PHOTO])
        other = dict(PHOTO, duration_minutes=30)
        await self.lib.publish(43, [other])
        restarted = mod.PresetLibrary(NS())
        self.assertEqual((await restarted.get(42, "pHoTo"))["duration_minutes"], 10)
        self.assertEqual((await restarted.get(43, "Photo"))["duration_minutes"], 30)
        with self.assertRaises(HomeAssistantError): await restarted.get(44, "Photo")

    async def test_update_delete_and_copy(self):
        await self.lib.publish(42, [PHOTO])
        await self.lib.publish(42, [dict(PHOTO, name="Maintenance")])
        await self.lib.publish(42, [dict(PHOTO, name="PHOTO", duration_minutes=7)])
        self.assertEqual(len(await self.lib.get(42)), 2)
        value = await self.lib.get(42, "photo")
        value["channels"][1] = 0
        self.assertEqual((await self.lib.get(42, "photo"))["channels"][1], 100)
        await self.lib.delete(42, "photo")
        with self.assertRaises(HomeAssistantError): await self.lib.get(42, "photo")
        self.assertEqual(len(await self.lib.get(42)), 1)

    async def test_failure_does_not_publish(self):
        await self.lib.publish(42, [PHOTO])
        FakeStore.fail = True
        with self.assertRaises(OSError):
            await self.lib.publish(42, [dict(PHOTO, duration_minutes=5)])
        self.assertEqual((await self.lib.get(42, "Photo"))["duration_minutes"], 10)

    async def test_concurrent_updates(self):
        await asyncio.gather(self.lib.publish(42,[PHOTO]),self.lib.publish(43,[PHOTO]))
        self.assertEqual(len(await self.lib.get(42)),1)
        self.assertEqual(len(await self.lib.get(43)),1)

    async def test_validation(self):
        for bad in [dict(PHOTO,duration_minutes=True),dict(PHOTO,duration_minutes=61),
                    dict(PHOTO,channels=[0]*5),dict(PHOTO,channels=[float("nan")]*6),
                    dict(PHOTO,channels=[101]*6),dict(PHOTO,name=" ")]:
            with self.assertRaises(vol.Invalid): mod.PRESET_SCHEMA(bad)
        with self.assertRaises(vol.Invalid): mod.preset_list([PHOTO,dict(PHOTO,name=" photo ")])
        with self.assertRaises(vol.Invalid): mod.PUBLISH_SCHEMA({"tank_id":True,"presets":[PHOTO]})

    async def test_service_dispatch_context_and_failures(self):
        registered = {}
        services = NS(has_service=lambda d,s:s in registered,
            async_register=lambda d,s,fn,**kw:registered.update({s:(fn,kw)}),
            async_call=AsyncMock())
        hass = NS(data={},services=services)
        mod.register_preset_services(hass)
        mod.register_preset_services(hass)
        self.assertEqual(len(registered),4)
        context = object()
        await registered["publish_presets"][0](NS(data={"tank_id":42,"presets":[PHOTO]}))
        services.async_call.assert_not_awaited()
        result = await registered["list_presets"][0](NS(data={"tank_id":42}))
        self.assertEqual(result["presets"],[PHOTO])
        await registered["activate_preset"][0](NS(data={"tank_id":42,"name":"Photo"},context=context))
        services.async_call.assert_awaited_once_with("ati_straton_x","set_tank_live",
            {"tank_id":42,"duration_minutes":10,"uv_violet":0,"royal_blue":100,"blue":100,"horti_white":0,"white":0,"red":0},
            blocking=True,context=context)
        services.async_call.reset_mock()
        with self.assertRaises(HomeAssistantError):
            await registered["activate_preset"][0](NS(data={"tank_id":43,"name":"Photo"},context=context))
        services.async_call.assert_not_awaited()
        services.async_call.side_effect=HomeAssistantError("Unavailable group")
        with self.assertRaises(HomeAssistantError):
            await registered["activate_preset"][0](NS(data={"tank_id":42,"name":"Photo"},context=context))

if __name__ == "__main__":
    unittest.main()
