"""Platform for sensor integration (OWM -> JSON).

Supports both legacy YAML platform setup (async_setup_platform) and
modern UI config flow setup (async_setup_entry).
"""

import logging
from datetime import timedelta, datetime, timezone
import json
import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE)
from homeassistant.util import Throttle
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo

import owm2json

DOMAIN = "owm2json"

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

# Keep PLATFORM_SCHEMA for YAML compatibility (optional)
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


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """
    Legacy YAML setup support.

    Example YAML:
    sensor:
      - platform: owm2json
        api_key: !secret owm_api_key
        latitude: 52.52
        longitude: 13.41
    """
    lat = config.get(CONF_LATITUDE)
    lon = config.get(CONF_LONGITUDE)
    appid = config.get(CONF_API_KEY)
    api_list = ["air_pollution/forecast", "air_pollution", "onecall"]

    try:
        data = OwmPollutionData(api_list, lat, lon, appid)
    except requests.exceptions.HTTPError as error:
        _LOGGER.error("OWM2JSON initialization failed: %s", error)
        return False

    entities = [OwmPollutionSensor(data, resource.lower()) for resource in SENSOR_TYPES]
    async_add_entities(entities, update_before_add=True)


async def async_setup_entry(hass, entry, async_add_entities):
    """
    UI config flow setup (ConfigEntry).

    Expects entry.data to contain CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE.
    """
    lat = entry.data.get(CONF_LATITUDE)
    lon = entry.data.get(CONF_LONGITUDE)
    appid = entry.data.get(CONF_API_KEY)
    api_list = ["air_pollution/forecast", "air_pollution", "onecall"]

    try:
        data = OwmPollutionData(api_list, lat, lon, appid)
    except requests.exceptions.HTTPError as error:
        _LOGGER.error("OWM2JSON initialization failed: %s", error)
        return False

    entities = [OwmPollutionSensor(data, resource.lower(), entry_id=entry.entry_id) for resource in SENSOR_TYPES]
    async_add_entities(entities, update_before_add=True)


class OwmPollutionData:
    """Fetch and store OWM data for requested endpoints."""

    def __init__(self, api_list, lat, lon, appid):
        self._state = None
        self.lat = lat
        self.lon = lon
        self.appid = appid
        self.data = None
        self.api_list = api_list

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, sensorType):
        """Call out to the owm2json requestor and parse JSON."""
        _LOGGER.debug("Updating OWM pollution sensors for %s,%s", self.lat, self.lon)
        myOWM = owm2json.owmRequestor(self.api_list, self.lat, self.lon, self.appid)
        try:
            self.data = json.loads(myOWM.GetData())
        except requests.exceptions.RequestException as exc:
            _LOGGER.error("Error occurred while fetching data: %r", exc)
            self.data = None
            return False


def safe_value(val):
    """Convert to float and clamp to zero to avoid negatives."""
    try:
        return max(float(val), 0.0)
    except (ValueError, TypeError):
        return 0.0


class OwmPollutionSensor(Entity):
    """Representation of a Sensor for one pollutant / forecast value."""

    def __init__(self, data, sensor_type, entry_id: str | None = None):
        """Initialize the sensor."""
        self.data = data
        self.type = sensor_type
        self._entry_id = entry_id  # optional: used when created via config entry
        if self.type == "uvi" and self.type in SENSOR_TYPES:
            self._name = SENSOR_PREFIX_ROOT + SENSOR_TYPES[self.type][0]
        else:
            self._name = SENSOR_PREFIX_ROOT + SENSOR_PREFIX_POLLUTION + SENSOR_TYPES[self.type][0]
        self._unit = SENSOR_TYPES[self.type][1]
        self._icon = SENSOR_TYPES[self.type][2]
        self._state = None
        self._extra_state_attributes = None

        # Unique id per sensor (type + coordinates)
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
        """Return device information so all sensors are grouped under one device."""
        # Use lat/lon as the device unique identifier so multiple locations are possible.
        identifiers = {(DOMAIN, f"{self.data.lat}_{self.data.lon}")}
        info = DeviceInfo(
            identifiers=identifiers,
            name=f"OWM Air Quality ({self.data.lat}, {self.data.lon})",
            manufacturer="OpenWeatherMap",
            model="Air Pollution API",
            configuration_url="https://openweathermap.org/api",
        )
        # If this entity was created from a config entry, provide the config_entry_id
        # so HA links the device to that entry (useful for UI and removal).
        if getattr(self, "_entry_id", None):
            info = info.__class__(**{**info.__dict__, "via_device": None})  # no-op placeholder for immutability
            # Note: device registry will link device -> config entry automatically when created via async_setup_entry
        return info

    def update(self):
        """Fetch new state data for the sensor."""
        # Trigger throttled data update
        self.data.update(self.type)
        owmData = self.data.data

        try:
            if not owmData:
                self._state = None
                return

            if self.type == 'co':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["co"])

            elif self.type == 'no':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["no"])

            elif self.type == 'no2':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["no2"])

            elif self.type == 'o3':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["o3"])

            elif self.type == 'so2':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["so2"])

            elif self.type == 'nh3':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["nh3"])

            elif self.type == 'pm2_5':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["pm2_5"])

            elif self.type == 'pm10':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["components"]["pm10"])

            elif self.type == 'aqi':
                self._state = safe_value(owmData["air_pollution"]["list"][0]["main"]["aqi"])

            elif self.type == 'forecast':
                # Forecast stored under air_pollution/forecast in the requestor results
                self._state = safe_value(owmData.get("air_pollution/forecast", {}).get("list", [{}])[0].get("main", {}).get("aqi"))
                # copy current components and then add forecast list
                self._extra_state_attributes = dict(owmData["air_pollution"]["list"][0]["components"])
                self._extra_state_attributes["forecast"] = []
                for f in owmData.get("air_pollution/forecast", {}).get("list", []):
                    fdict = {"datetime": datetime.fromtimestamp(f["dt"], tz=timezone.utc).isoformat()}
                    components = {k: safe_value(v) for k, v in f["components"].items()}
                    fdict.update(components)
                    fdict.update(f.get("main", {}))
                    self._extra_state_attributes["forecast"].append(fdict)

        except (ValueError, KeyError, TypeError) as exc:
            _LOGGER.debug("Error parsing OWM data for %s: %s", self.type, exc)
            self._state = None
