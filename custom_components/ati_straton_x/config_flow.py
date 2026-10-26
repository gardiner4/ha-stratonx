"""Bluetooth discovery and manual selection; verify GATT identity on add."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.components import bluetooth
from .const import DOMAIN, DEFAULT_INTERVAL
from .client import connection, identity


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
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        entry = self.config_entry
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("poll_interval", default=entry.options.get("poll_interval", DEFAULT_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
            vol.Required("passcode", default=entry.options.get("passcode", entry.data.get("passcode", 0))): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
        }))
