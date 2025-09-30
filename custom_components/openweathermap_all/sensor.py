"""Platform for OpenWeatherMap Air Quality sensors with EPA AQI calculation."""

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

SCAN_INTERVAL = timedelta(minutes=30)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)

# YAML compatibility
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
    entities.append(OwmEpaAqiSensor(data))  # Add EPA AQI sensor
    async_add_entities(entities, update_before_add=True)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    api_list = ["air_pollution/forecast", "air_pollution", "onecall"]

    data = OwmPollutionData(api_list, lat, lon, api_key)

    sensors = [OwmPollutionSensor(data, sensor_type, entry.entry_id) for sensor_type in SENSOR_TYPES]
    sensors.append(OwmEpaAqiSensor(data, entry.entry_id))  # Add EPA AQI sensor
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


# ---------- EPA AQI SENSOR ----------

# Breakpoints in μg/m³ (converted from ppm where necessary)
EPA_BREAKPOINTS = {
    "pm2_5": [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ],
    "pm10": [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 504, 301, 400),
        (505, 604, 401, 500),
    ],
    "co": [
        (0.0, 242, 0, 50),
        (245, 516, 51, 100),
        (522, 611, 101, 150),
        (617, 837, 151, 200),
        (854, 1858, 201, 300),
        (1870, 2487, 301, 400),
        (2502, 4119, 401, 500),
    ],
    "so2": [
        (0, 44, 0, 50),
        (45, 89, 51, 100),
        (90, 185, 101, 150),
        (186, 304, 151, 200),
        (305, 604, 201, 300),
        (605, 804, 301, 400),
        (805, 1004, 401, 500),
    ],
    "no2": [
        (0, 53, 0, 50),
        (54, 100, 51, 100),
        (101, 360, 101, 150),
        (361, 649, 151, 200),
        (650, 1249, 201, 300),
        (1250, 1649, 301, 400),
        (1650, 2049, 401, 500),
    ],
    "o3": [
        (0.0, 70, 0, 50),
        (71, 85, 51, 100),
        (86, 105, 101, 150),
        (106, 200, 151, 200),
        (201, 300, 201, 300),
        (301, 400, 301, 400),
        (401, 500, 401, 500),
    ],
}

def calculate_aqi(pollutant, concentration):
    """Calculate EPA AQI for a single pollutant using μg/m³."""
    if concentration is None:
        return None
    for c_low, c_high, i_low, i_high in EPA_BREAKPOINTS[pollutant]:
        if c_low <= concentration <= c_high:
            return round((i_high - i_low) / (c_high - c_low) * (concentration - c_low) + i_low)
    return None


class OwmEpaAqiSensor(SensorEntity):
    """Sensor for estimated EPA AQI based on OWM components."""

    def __init__(self, data: OwmPollutionData, entry_id: str | None = None):
        self.data = data
        self._entry_id = entry_id
        self._name = "OWM EPA AQI"
        self._unit = "AQI"
        self._icon = "mdi:air-filter"
        self._state = None
        self._extra_state_attributes = None
        self._unique_id = f"owm_epa_aqi_{self.data.lat}_{self.data.lon}"

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
            name=f"OWM EPA AQI ({self.data.lat}, {self.data.lon})",
            manufacturer="OpenWeatherMap",
            model="Air Pollution API",
            configuration_url="https://openweathermap.org/api",
        )

    def update(self):
        self.data.update(None)
        owm_data = self.data.data
        if not owm_data:
            self._state = None
            return

        try:
            components = owm_data["air_pollution"]["list"][0]["components"]
            aqi_values = []
            for p in ["pm2_5", "pm10", "co", "so2", "no2", "o3"]:
                aqi = calculate_aqi(p, safe_value(components.get(p)))
                if aqi is not None:
                    aqi_values.append(aqi)
            self._state = max(aqi_values) if aqi_values else None
            self._extra_state_attributes = components
        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.debug("Error calculating EPA AQI: %s", exc)
            self._state = None
