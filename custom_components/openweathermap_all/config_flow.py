import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from . import DOMAIN

class Owm2JsonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OWM2JSON."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # TODO: Optionally test API connectivity here
            return self.async_create_entry(title="OWM Air Quality", data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_LATITUDE): str,
            vol.Required(CONF_LONGITUDE): str,
        })

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)
