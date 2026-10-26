"""Test manual schedule cadence and cached-advertisement diagnostics in HA runtime."""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from homeassistant.exceptions import HomeAssistantError
from custom_components.ati_straton_x import coordinator as cm, bluetooth_sensor as bm, sensor as sm

SCHEDULE = {"nodes":[{"timestamp":0,"channelValues":[0]*6},{"timestamp":43200,"channelValues":[100]*6}]}

@asynccontextmanager
async def connection(*args):
    yield NS()

class PollingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.c = object.__new__(cm.StratonCoordinator)
        self.c.hass = NS()
        self.c.entry = NS(data={"serial":"ABC","address":"AA"},options={})
        self.c.data = None
        self.c.interval = 60
        self.c.failures = 0
        self.c.schedule_requested = True
        self.c.last_update_success = True
        self.info = {"serial":"ABC","tank_id":42,"firmware":"1.4.0.2","hardware":"1"}
        self.reader = AsyncMock(return_value=SCHEDULE)
        for target,value in [("connection",connection),("identity",AsyncMock(side_effect=lambda c:dict(self.info))),
            ("query",AsyncMock(return_value=b"")),("temperatures",Mock(return_value={"temperature_1":40})),
            ("clocks",Mock(return_value={"rtc_time":None})),("live_remaining",Mock(return_value=0)),("read_schedule",self.reader)]:
            p=patch.object(cm,target,value);p.start();self.addCleanup(p.stop)

    async def poll(self):
        self.c.data=await self.c._async_update_data()
        self.c.last_update_success=True

    async def test_startup_then_manual_only(self):
        await self.poll()
        for _ in range(25): await self.poll()
        self.assertEqual(self.reader.await_count,1)
        self.c.async_request_refresh=AsyncMock(side_effect=self.poll)
        await self.c.refresh_schedule()
        self.assertEqual(self.reader.await_count,2)
        self.assertEqual(self.c.data["schedule"],SCHEDULE)

    async def test_group_change_invalidates_schedule(self):
        await self.poll()
        self.info["tank_id"]=43
        self.reader.side_effect=ValueError("bad schedule")
        await self.poll()
        self.assertNotIn("schedule",self.c.data)
        self.assertEqual(self.c.data["tank_id"],43)
        self.assertIn("schedule_error",self.c.data)
        await self.poll()
        self.assertEqual(self.reader.await_count,2)

    async def test_failed_manual_read_keeps_old_schedule_and_telemetry(self):
        await self.poll()
        timestamp=self.c.data["schedule_updated"]
        self.reader.side_effect=ValueError("bad schedule")
        self.c.async_request_refresh=AsyncMock(side_effect=self.poll)
        with self.assertRaises(HomeAssistantError): await self.c.refresh_schedule()
        self.assertEqual(self.c.data["temperature_1"],40)
        self.assertEqual(self.c.data["schedule_updated"],timestamp)
        self.assertEqual(self.c.data["schedule"],SCHEDULE)
        await self.poll()
        self.assertEqual(self.reader.await_count,2)
        self.reader.side_effect=None
        await self.c.refresh_schedule()
        self.assertNotIn("schedule_error",self.c.data)

    async def test_initial_schedule_failure_does_not_fail_telemetry(self):
        self.reader.side_effect=ValueError("bad schedule")
        await self.poll()
        await self.poll()
        self.assertEqual(self.reader.await_count,1)
        self.assertEqual(self.c.data["temperature_1"],40)
        entity=sm.StratonSensor(self.c,"schedule","Schedule")
        self.assertIsNone(entity.native_value)
        self.assertIn("last_refresh_error",entity.extra_state_attributes)
        self.c.last_update_success=False
        last=sm.StratonSensor(self.c,"last_seen","Last successful poll")
        self.assertTrue(last.available)
        self.assertFalse(entity.available)

class AdvertisementTests(unittest.TestCase):
    def setUp(self):
        self.c=NS(entry=NS(data={"serial":"ABC","address":"AA"}),data={"tank_id":42})
        self.info=NS(time=990.0,source="proxy-a",rssi=-65)
        self.now=1000.0
        registry=NS(async_get_device=Mock(return_value=NS(name_by_user="Tank proxy",name="Proxy")))
        for obj,name,value in [(bm.bluetooth,"async_last_service_info",Mock(side_effect=lambda *a,**kw:self.info)),
            (bm,"monotonic",Mock(side_effect=lambda:self.now)),
            (bm.dr,"async_get",Mock(return_value=registry))]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.entities=[bm.AdvertisementSensor(self.c,key,key) for key in ("bluetooth_signal","bluetooth_source","bluetooth_last_seen")]
        for e in self.entities:e.hass=NS()

    def test_fresh_stale_and_recovery(self):
        for e in self.entities:e.sample()
        self.assertEqual([e.native_value for e in self.entities[:2]],[-65,"Tank proxy"])
        seen=self.entities[2].native_value
        self.assertEqual(self.entities[0].extra_state_attributes["source"],"proxy-a")
        self.now=1200
        self.info=None
        for e in self.entities:e.sample()
        self.assertFalse(self.entities[0].available)
        self.assertIsNone(self.entities[0].native_value)
        self.assertTrue(self.entities[2].available)
        self.assertEqual(self.entities[2].native_value,seen)
        self.info=NS(time=1199,source="proxy-b",rssi=-72)
        for e in self.entities:e.sample()
        self.assertTrue(self.entities[0].available)
        self.assertEqual(self.entities[0].native_value,-72)
        self.assertEqual(self.entities[0].extra_state_attributes["source"],"proxy-b")

    def test_mutating_cached_info_and_failed_gatt(self):
        e=self.entities[2];e.sample();seen=e.native_value
        self.info.time=999
        e.sample()
        self.assertNotEqual(e.native_value,seen)
        self.c.last_update_success=False
        self.entities[0].sample()
        self.assertTrue(self.entities[0].available)

    def test_no_advertisement(self):
        self.info=None
        for e in self.entities:
            e.sample()
            self.assertFalse(e.available)
            self.assertIsNone(e.native_value)

if __name__=="__main__":unittest.main()
