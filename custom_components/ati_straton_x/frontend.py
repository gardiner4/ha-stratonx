"""Serve the bundled read-only dashboard card."""
import asyncio
from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from .const import DOMAIN


async def async_register_card(hass):
    """Register once across concurrent config-entry setup and reloads."""
    data = hass.data.setdefault(DOMAIN, {})
    lock = data.setdefault("frontend_lock", asyncio.Lock())
    async with lock:
        if data.get("frontend_registered"):
            return
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                "/ati_straton_x/stratonx-schedule-card.js",
                str(Path(__file__).parent / "www" / "stratonx-schedule-card.js"),
                False,
            )
        ])
        data["frontend_registered"] = True
