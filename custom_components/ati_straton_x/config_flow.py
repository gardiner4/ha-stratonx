"""Bluetooth discovery and manual selection; verify GATT identity on add."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.components import bluetooth
from .const import DOMAIN, DEFAULT_INTERVAL
from .client import connection, identity
from .wifi import normalize_host, verified_identity, discover_host, scan_network


class StratonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _address = None

    async def async_step_bluetooth(self, discovery_info):
        self._address = discovery_info.address.upper()
        self._async_abort_entries_match({"address": self._address})
        self.context["title_placeholders"] = {"name": discovery_info.name or self._address}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                async with connection(self.hass, self._address) as client:
                    info = await identity(client)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured(updates={"address": self._address})
                return self.async_create_entry(title=f"Straton X {info['serial'][-6:]}", data={**info, "address": self._address, "passcode": user_input["passcode"]})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({vol.Required("passcode", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535))}), errors=errors, description_placeholders={"address": self._address})

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._address = user_input["address"].upper()
            self._async_abort_entries_match({"address": self._address})
            return await self.async_step_confirm()
        configured = {entry.data["address"] for entry in self._async_current_entries()}
        devices = {info.address: f"{info.name} ({info.address})" for info in bluetooth.async_discovered_service_info(self.hass, connectable=True) if (info.name or "").startswith("StratonX-") and info.address not in configured}
        if not devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("address"): vol.In(devices)}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return StratonOptionsFlow()


class StratonOptionsFlow(config_entries.OptionsFlow):
    _scan_task = None
    _pending = None
    _scan_error = False
    async def async_step_init(self, user_input=None):
        errors = {"base": "wifi_unverified"} if self._scan_error else {}
        self._scan_error = False
        entry = self.config_entry
        values = dict(self._pending or entry.options)
        if user_input is not None:
            values.update(user_input)
            host = user_input.get("wifi_host", "").strip()
            subnet = user_input.get("wifi_scan_subnet", "").strip()
            try:
                if subnet:
                    scan_network(subnet)
                    self._pending = values
                    self._scan_task = self.hass.async_create_task(self._scan_and_verify(subnet))
                    return await self.async_step_scan()
                if host:
                    host = normalize_host(host)
                    await verified_identity(self.hass, host, entry.data["serial"])
            except Exception:
                errors["base"] = "wifi_unverified"
            else:
                values.pop("wifi_scan_subnet", None)
                values["wifi_host"] = host
                return self.async_create_entry(title="", data=values)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("poll_interval", default=values.get("poll_interval", DEFAULT_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
            vol.Required("passcode", default=values.get("passcode", entry.data.get("passcode", 0))): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
            vol.Optional("wifi_host", description={"suggested_value": values.get("wifi_host", "")}): str,
            vol.Optional("wifi_scan_subnet", default=""): str,
        }), errors=errors)

    async def _scan_and_verify(self, subnet):
        host = await discover_host(self.hass, subnet, self.config_entry.data["serial"])
        await verified_identity(self.hass, host, self.config_entry.data["serial"])
        return host

    async def async_step_scan(self, user_input=None):
        if not self._scan_task.done():
            return self.async_show_progress(step_id="scan", progress_action="wifi_scan", progress_task=self._scan_task)
        return self.async_show_progress_done(next_step_id="scan_finish")

    async def async_step_scan_finish(self, user_input=None):
        try:
            host = self._scan_task.result()
        except Exception:
            self._scan_error = True
            self._scan_task = None
            return await self.async_step_init()
        self._pending.pop("wifi_scan_subnet", None)
        self._pending["wifi_host"] = host
        return self.async_create_entry(title="", data=self._pending)
