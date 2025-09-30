import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE

from .const import DOMAIN

class OpenWeatherMapAQConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Here you could validate the API key by hitting OpenWeatherMap
            return self.async_create_entry(
                title="OpenWeatherMap Air Quality",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): float,
            vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): float,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
