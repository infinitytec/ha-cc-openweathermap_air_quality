"""Platform for OpenWeatherMap Air Quality sensors."""

from __future__ import annotations
import logging
from datetime import timedelta, datetime, timezone
import json
import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.util import Throttle
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

import owm2json

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

# YAML compatibility (optional)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_LATITUDE): cv.string,
    vol.Required(CONF_LONGITUDE): cv.string
})

SENSOR_PREFIX_ROOT = 'OWM '
SENSOR_PREFIX_POLLUTION = 'Pollution '

SENSOR_TYPES = {
    'co': ['Carbon monoxide (CO)', 'μg/m³', 'mdi:molecule-co'],
    'no': ['Nitrogen monoxide (NO)', 'μg/m³', 'mdi:smog'],
    'no2': ['Nitrogen dioxide (NO2)', 'μg/m³', 'mdi:smog'],
    'o3': ['Ozone (O3)', 'μg/m³', 'mdi:skull-outline'],
    'so2': ['Sulphur dioxide (SO2)', 'μg/m³', 'mdi:smog'],
    'nh3': ['Ammonia (NH3)', 'μg/m³', 'mdi:skull'],
    'pm2_5': ['Fine particles (PM2.5)', 'μg/m³', 'mdi:grain'],
    'pm10': ['Coarse particles (PM10)', 'μg/m³', 'mdi:grain'],
    'aqi': ['Overall Air Quality', '', 'mdi:lungs'],
    'forecast': ['Forecast', '', 'mdi:eye-arrow-right']
}

DOMAIN = "openweathermap_air_quality"


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities: AddEntitiesCallback, discovery_info=None):
    """Legacy YAML setup support."""
    lat = config.get(CONF_LATITUDE)
    lon = config.get(CONF_LONGITUDE)
    api_key = config.get(CONF_API_KEY)
    api_list = ["air_pollution/forecast", "air_pollution", "onecall"]

    try:
        data = OwmPollutionData(api_list, lat, lon, api_key)
    except requests.exceptions.HTTPError as error:
        _LOGGER.error("OWM2JSON initialization failed: %s", error)
        return False

    entities = [OwmPollutionSensor(data, sensor_type) for sensor_type in SENSOR_TYPES]
    async_add_entities(entities, update_before_add=True)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    api_list = ["air_pollution/forecast", "air_pollution", "onecall"]

    data = OwmPollutionData(api_list, lat, lon, api_key)

    sensors = [OwmPollutionSensor(data, sensor_type, entry.entry_id) for sensor_type in SENSOR_TYPES]
    async_add_entities(sensors, update_before_add=True)

    return True


class OwmPollutionData:
    """Fetch and store OWM data for requested endpoints."""

    def __init__(self, api_list, lat, lon, appid):
        self.lat = lat
        self.lon = lon
        self.appid = appid
        self.api_list = api_list
        self.data = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, sensor_type):
        """Call out to the OWM requestor and parse JSON."""
        _LOGGER.debug("Updating OWM pollution sensors for %s,%s", self.lat, self.lon)
        try:
            myOWM = owm2json.owmRequestor(self.api_list, self.lat, self.lon, self.appid)
            self.data = json.loads(myOWM.GetData())
        except requests.exceptions.RequestException as exc:
            _LOGGER.error("Error fetching data: %r", exc)
            self.data = None
            return False


def safe_value(val):
    """Convert to float and clamp to zero to avoid negatives."""
    try:
        return max(float(val), 0.0)
    except (ValueError, TypeError):
        return 0.0


class OwmPollutionSensor(SensorEntity):
    """Representation of a Sensor for one pollutant / forecast value."""

    def __init__(self, data: OwmPollutionData, sensor_type: str, entry_id: str | None = None):
        self.data = data
        self.type = sensor_type
        self._entry_id = entry_id
        self._name = SENSOR_PREFIX_ROOT + SENSOR_PREFIX_POLLUTION + SENSOR_TYPES[self.type][0]
        self._unit = SENSOR_TYPES[self.type][1]
        self._icon = SENSOR_TYPES[self.type][2]
        self._state = None
        self._extra_state_attributes = None
        self._unique_id = f"owm_pollution_{self.type}_{self.data.lat}_{self.data.lon}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return self._icon

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def extra_state_attributes(self):
        return self._extra_state_attributes

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.data.lat}_{self.data.lon}")},
            name=f"OWM Air Quality ({self.data.lat}, {self.data.lon})",
            manufacturer="OpenWeatherMap",
            model="Air Pollution API",
            configuration_url="https://openweathermap.org/api",
        )

    def update(self):
        """Fetch new state data for the sensor."""
        self.data.update(self.type)
        owm_data = self.data.data

        if not owm_data:
            self._state = None
            return

        try:
            if self.type in ["co", "no", "no2", "o3", "so2", "nh3", "pm2_5", "pm10"]:
                self._state = safe_value(owm_data["air_pollution"]["list"][0]["components"][self.type])
            elif self.type == "aqi":
                self._state = safe_value(owm_data["air_pollution"]["list"][0]["main"]["aqi"])
            elif self.type == "forecast":
                forecast_list = owm_data.get("air_pollution/forecast", {}).get("list", [])
                self._state = safe_value(forecast_list[0]["main"]["aqi"] if forecast_list else None)
                # Add extra attributes for forecast
                self._extra_state_attributes = dict(owm_data["air_pollution"]["list"][0]["components"])
                self._extra_state_attributes["forecast"] = []
                for f in forecast_list:
                    fdict = {"datetime": datetime.fromtimestamp(f["dt"], tz=timezone.utc).isoformat()}
                    components = {k: safe_value(v) for k, v in f.get("components", {}).items()}
                    fdict.update(components)
                    fdict.update(f.get("main", {}))
                    self._extra_state_attributes["forecast"].append(fdict)

        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.debug("Error parsing OWM data for %s: %s", self.type, exc)
            self._state = None
