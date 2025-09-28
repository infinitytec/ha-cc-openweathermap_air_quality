from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "owm2json"

async def async_setup(hass: HomeAssistant, config: dict):
    """YAML setup is ignored — only config flow supported."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up owm2json from a config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload owm2json config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
