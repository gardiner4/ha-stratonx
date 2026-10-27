"""Wi-Fi fallback tests in Home Assistant's runtime; no real device writes."""
import asyncio
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, PropertyMock, patch
from bleak.exc import BleakError
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.ati_straton_x import wifi as wm, coordinator as cm, button as bm, config_flow as fm, services as sv
from custom_components.ati_straton_x.estimates import estimate_channels

SERIAL="AABBCCDDEEFF"
RAW={"id":SERIAL,"tankId":42,"fwVer":"1.4.0.2","hwVer":"1.5","apPw":"secret","passcode":1234}
SCHEDULE={"nodes":[{"timestamp":0,"channelValues":[0]*6},{"timestamp":43200,"channelValues":[100]*6}]}
INFO={"serial":SERIAL,"tank_id":42,"firmware":"1.4.0.2","hardware":"1.5"}
DATA={**INFO,"transport":"wifi","temperature_1":40,"last_seen":datetime.now(timezone.utc)}

class ParserTests(unittest.TestCase):
 def test_identity_and_secret_exclusion(self):
  result=wm.parse_identity(RAW,SERIAL)
  self.assertEqual(result,INFO)
  for raw in ({**RAW,"id":"112233445566"},{**RAW,"id":None},{**RAW,"tankId":True},{**RAW,"fwVer":None}):
   with self.assertRaises(ValueError):wm.parse_identity(raw,SERIAL)
 def test_temperatures(self):
  self.assertEqual(wm.parse_temperatures({"t":99,"t_1":40,"t_2":41,"t_esp":45})["temperature_1"],40)
  for bad in (None,True,126,float("nan")):
   with self.assertRaises(ValueError):wm.parse_temperatures({"t_1":bad,"t_2":41,"t_esp":45})
 def test_clock_dates(self):
  values=dict(zip(("year","month","day","hour","minute","second"),(2026,10,26,20,5,6)))
  raw={f"{p}_{k}":v for p in ("rtc","esp") for k,v in values.items()}
  self.assertEqual(wm.parse_clocks(raw)["local_time"],"2026-10-26 20:05:06")
  self.assertIsNotNone(wm.parse_clocks(raw)["rtc_time"].tzinfo)
  for bad in ({**raw,"rtc_month":0},{**raw,"rtc_year":2000},{**raw,"rtc_day":32}):
   self.assertIsNone(wm.parse_clocks(bad)["rtc_time"])
   self.assertIsNotNone(wm.parse_clocks(bad)["local_time"])
 def test_schedule_validation(self):
  self.assertEqual(wm.parse_schedule(SCHEDULE),SCHEDULE)
  for raw in ({"nodes":[{"timestamp":1,"channelValues":[0]*5}]},{"nodes":[SCHEDULE["nodes"][0]]*2},{"nodes":[{"timestamp":True,"channelValues":[0]*6}]}):
   with self.assertRaises(ValueError):wm.parse_schedule(raw)
 def test_hosts_and_scan_boundaries(self):
  self.assertEqual(wm.normalize_host(" ATI-Light.local "),"ati-light.local")
  for host in ("http://192.168.1.1","a@b","8.8.8.8","127.0.0.1","169.254.169.254","a/b","192.168.1.999"):
   with self.assertRaises(ValueError):wm.normalize_host(host)
  self.assertEqual(wm.scan_network("192.168.2.1/24").num_addresses,256)
  for subnet in ("192.168.0.0/16","8.8.8.0/24","::/120","127.0.0.0/24"):
   with self.assertRaises(ValueError):wm.scan_network(subnet)

class HttpTests(unittest.IsolatedAsyncioTestCase):
 async def test_reads_and_no_stale_timer(self):
  replies={"temp_get":{"t_1":40,"t_2":41,"t_esp":45},"time_get":{}}
  with patch.object(wm,"verified_identity",AsyncMock(return_value=dict(INFO))),patch.object(wm,"get_json",AsyncMock(side_effect=lambda h,host,path:replies[path])):
   data=await wm.read_telemetry(NS(),"192.168.1.2",SERIAL)
  self.assertNotIn("live_remaining",data)
  self.assertEqual(data["transport"],"wifi")
  self.assertIsNone(estimate_channels(data)[0])
 async def test_identity_alias(self):
  with patch.object(wm,"get_json",AsyncMock(side_effect=[ValueError("404"),RAW])) as read:
   self.assertEqual(await wm.verified_identity(NS(),"192.168.1.2",SERIAL),INFO)
   self.assertEqual([call.args[2] for call in read.await_args_list],["settings_get","setting_get"])
 async def test_bounded_scan_unique_match(self):
  active=peak=0
  async def check(hass,host,serial,timeout):
   nonlocal active,peak
   active+=1;peak=max(peak,active)
   try:
    await asyncio.sleep(0)
    if host!="192.168.1.24":raise ValueError("other device")
    return INFO
   finally:active-=1
  with patch.object(wm,"http_port_open",AsyncMock(return_value=True)),patch.object(wm,"verified_identity",AsyncMock(side_effect=check)) as read:
   self.assertEqual(await wm.discover_host(NS(),"192.168.1.0/24",SERIAL),"192.168.1.24")
   self.assertEqual(read.await_count,254)
   self.assertLessEqual(peak,16)
 async def test_scan_duplicate_and_none(self):
  for side in (None,ValueError("none")):
   with patch.object(wm,"http_port_open",AsyncMock(return_value=True)),patch.object(wm,"verified_identity",AsyncMock(side_effect=side,return_value=INFO)):
    with self.assertRaises(ValueError):await wm.discover_host(NS(),"192.168.1.0/30",SERIAL)
 async def test_http_bounds_and_no_redirect(self):
  class Response:
   status=200
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   @property
   def content(self):return self
   async def iter_chunked(self,size):
    yield self.body
  response=Response()
  session=NS(get=Mock(return_value=response))
  with patch.object(wm,"async_get_clientsession",Mock(return_value=session)):
   response.body=b'{"ok":true}'
   self.assertEqual(await wm.get_json(NS(),"light.local","temp_get"),{"ok":True})
   self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
   for body in (b"x"*(wm.MAX_RESPONSE+1),b"[]",b"bad"):
    response.body=body
    with self.assertRaises(ValueError):await wm.get_json(NS(),"light.local","temp_get")
   response.status=302
   with self.assertRaises(ValueError):await wm.get_json(NS(),"light.local","temp_get")
   with self.assertRaises(ValueError):await wm.get_json(NS(),"light.local","time_set")

class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.c=object.__new__(cm.StratonCoordinator)
  self.c.hass=NS()
  self.c.entry=NS(data={"serial":SERIAL,"address":"AA"},options={"wifi_host":"192.168.1.2"})
  self.c.interval=60;self.c.failures=0;self.c.schedule_requested=False
  self.c.data={**INFO,"schedule":SCHEDULE,"schedule_updated":"old","live_remaining":0,"local_time":"2026-10-26 12:00:00"}
  self.c.last_update_success=True
 async def test_fallback_then_ble_recovery(self):
  with patch.object(self.c,"_read_once",AsyncMock(side_effect=BleakError("GATT"))),patch.object(cm.asyncio,"sleep",AsyncMock()),patch.object(cm,"read_telemetry",AsyncMock(return_value=dict(DATA))) as http:
   self.c.data=await self.c._async_update_data()
   http.assert_awaited_once()
  self.assertEqual(self.c.data["schedule"],SCHEDULE)
  self.assertNotIn("live_remaining",self.c.data)
  self.assertNotIn("local_time",self.c.data)
  self.assertEqual(self.c.update_interval.total_seconds(),30)
  self.assertFalse(bm.StratonButton(self.c,"identify","Identify").available)
  self.assertTrue(bm.StratonButton(self.c,"refresh","Refresh").available)
  with patch.object(self.c,"_read_once",AsyncMock(return_value={**INFO,"transport":"bluetooth"})):
   self.c.data=await self.c._async_update_data()
  self.assertEqual(self.c.failures,0)
  self.assertEqual(self.c.update_interval.total_seconds(),60)
  self.assertTrue(bm.StratonButton(self.c,"identify","Identify").available)
 async def test_disabled_and_wrong_device_rejected(self):
  for host in ("","192.168.1.2"):
   self.c.entry.options["wifi_host"]=host
   with patch.object(cm,"read_telemetry",AsyncMock(side_effect=ValueError("wrong serial"))) as read:
    with self.assertRaises(UpdateFailed):await self.c._wifi_or_fail(BleakError("GATT"))
    self.assertEqual(read.await_count, int(bool(host)))
 async def test_manual_schedule_only_and_group_invalidation(self):
  with patch.object(cm,"read_telemetry",AsyncMock(side_effect=lambda *a:{**DATA,"tank_id":43})),patch.object(cm,"get_json",AsyncMock(return_value=SCHEDULE)) as read:
   self.c.data=await self.c._wifi_or_fail(BleakError("GATT"))
   self.assertEqual(self.c.data["tank_id"],43)
   self.assertEqual(self.c.data["schedule_source"],"wifi")
   self.c.data=await self.c._wifi_or_fail(BleakError("GATT"))
   self.assertEqual(read.await_count,1)
   self.c.schedule_requested=True
   await self.c._wifi_or_fail(BleakError("GATT"))
   self.assertEqual(read.await_count,2)
 async def test_failed_schedule_preserves_cached_snapshot(self):
  self.c.schedule_requested=True
  with patch.object(cm,"read_telemetry",AsyncMock(return_value=dict(DATA))),patch.object(cm,"get_json",AsyncMock(side_effect=TimeoutError())):
   result=await self.c._wifi_or_fail(BleakError("GATT"))
  self.assertEqual(result["schedule_updated"],"old")
  self.assertIn("schedule_error",result)
 async def test_requested_schedule_http_identity_guard(self):
  data={**INFO,"schedule_error":"GATT"}
  with patch.object(cm,"verified_identity",AsyncMock(side_effect=ValueError("wrong light"))),patch.object(cm,"get_json",AsyncMock()) as read:
   await self.c._wifi_schedule(data)
   read.assert_not_awaited()
   self.assertNotIn("schedule",data)
  with patch.object(cm,"verified_identity",AsyncMock(return_value=INFO)),patch.object(cm,"get_json",AsyncMock(return_value=SCHEDULE)):
   await self.c._wifi_schedule(data)
  self.assertEqual(data["schedule"],SCHEDULE)
  self.assertNotIn("schedule_error",data)

class OptionsTests(unittest.IsolatedAsyncioTestCase):
 async def test_save_verify_disable_and_preserve(self):
  entry=NS(data={"serial":SERIAL,"passcode":0},options={"poll_interval":90,"passcode":7,"other":"preserved"})
  with patch.object(fm.StratonOptionsFlow,"config_entry",new_callable=PropertyMock,return_value=entry):
   flow=fm.StratonOptionsFlow();flow.hass=NS(async_create_task=asyncio.create_task);flow.handler='test-entry'
   with patch.object(fm,"verified_identity",AsyncMock(return_value=INFO)) as verify:
    result=await flow.async_step_init({"poll_interval":90,"passcode":7,"wifi_host":"192.168.1.2"})
    verify.assert_awaited_once()
    self.assertEqual(result["data"]["other"],"preserved")
    self.assertEqual(result["data"]["wifi_host"],"192.168.1.2")
   with patch.object(fm,"verified_identity",AsyncMock()) as verify:
    result=await flow.async_step_init({"poll_interval":90,"passcode":7,"wifi_host":""})
    verify.assert_not_awaited()
    self.assertEqual(result["data"]["wifi_host"],"")
 async def test_scan_and_failed_verification(self):
  entry=NS(data={"serial":SERIAL,"passcode":0},options={})
  with patch.object(fm.StratonOptionsFlow,"config_entry",new_callable=PropertyMock,return_value=entry):
   flow=fm.StratonOptionsFlow();flow.hass=NS(async_create_task=asyncio.create_task);flow.handler='test-entry'
   with patch.object(fm,"discover_host",AsyncMock(return_value="192.168.1.24")),patch.object(fm,"verified_identity",AsyncMock(return_value=INFO)):
    result=await flow.async_step_init({"wifi_scan_subnet":"192.168.1.0/24"})
    self.assertEqual(result["type"], "progress")
    await flow._scan_task
    self.assertEqual((await flow.async_step_scan())["type"], "progress_done")
    result=await flow.async_step_scan_finish()
    self.assertEqual(result["data"]["wifi_host"],"192.168.1.24")
    self.assertNotIn("wifi_scan_subnet",result["data"])
   with patch.object(fm,"verified_identity",AsyncMock(side_effect=ValueError("wrong light"))):
    result=await flow.async_step_init({"wifi_host":"192.168.1.2"})
    self.assertEqual(result["errors"]["base"],"wifi_unverified")


class ControlTests(unittest.IsolatedAsyncioTestCase):
 async def test_wifi_member_blocks_group_writes(self):
  handlers={}
  c=NS(data={**DATA},last_update_success=True,entry=NS(options={},data={}),set_tank_live=AsyncMock())
  entry=NS(state=NS(value="loaded"),runtime_data=c)
  hass=NS(data={},services=NS(has_service=lambda *a:False,async_register=lambda d,s,fn,**kw:handlers.update({s:fn})),config_entries=NS(async_entries=lambda d:[entry]))
  sv.register_services(hass)
  with self.assertRaisesRegex(Exception,"no verified Bluetooth"):
   await handlers["set_tank_live"](NS(data={"tank_id":42},service="set_tank_live"))
  c.set_tank_live.assert_not_awaited()

if __name__=="__main__":unittest.main()

