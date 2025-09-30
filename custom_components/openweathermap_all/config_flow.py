"""Config flow for OpenWeatherMap Air Quality integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE

from .const import DOMAIN


class OpenWeatherMapAQConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenWeatherMap Air Quality."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title="OpenWeatherMap Air Quality",
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): float,
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): float,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
