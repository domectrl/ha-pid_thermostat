"""The tests for the PID_thermostat climate component."""

import asyncio
import logging

import pytest
import voluptuous as vol
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.input_number import CONF_MAX, CONF_MIN, CONF_STEP
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_PLATFORM,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import METRIC_SYSTEM

from custom_components.pid_thermostat.const import (
    AC_MODE_COOL,
    AC_MODE_HEAT,
    CONF_AC_MODE,
    CONF_CYCLE_TIME,
    CONF_HEATER,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_SENSOR,
    DEFAULT_NAME,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
)

LOGGER = logging.getLogger(__name__)


ENTITY_CLIMATE = "climate.pid_thermostat"
ENTITY_SENSOR = "sensor.temperature"
ENTITY_HEATER = "input_number.heater"
CYCLE_TIME = 0.01


DEFAULT_SENSOR_TEMPERATURE = 10.0


CLIMATE_CONFIG = {
    Platform.CLIMATE: {
        CONF_PLATFORM: DOMAIN,
        CONF_NAME: DEFAULT_NAME,
        CONF_SENSOR: ENTITY_SENSOR,
        CONF_HEATER: ENTITY_HEATER,
        CONF_CYCLE_TIME: {"seconds": CYCLE_TIME},
    }
}
NUMBER_CONFIG = {
    "input_number": {
        "heater": {
            CONF_NAME: "Floor heater",
            CONF_MIN: 0,
            CONF_MAX: 100,
            CONF_STEP: 1,
        }
    }
}


@pytest.fixture(autouse=True)
async def fixture_setup_helpers(hass: HomeAssistant) -> None:
    """Initialize hass and helper components."""
    hass.config.units = METRIC_SYSTEM
    hass.states.async_set(ENTITY_SENSOR, 10.0)
    # Create a number, required by the climate component first
    assert await async_setup_component(hass, "input_number", NUMBER_CONFIG)


async def _setup_pid_climate(hass: HomeAssistant, config: ConfigType) -> None:
    """Setupfunctions for the pid thermostat."""
    assert await async_setup_component(hass, Platform.CLIMATE, config)
    await hass.async_block_till_done()


async def test_setup_params(hass: HomeAssistant) -> None:
    """Test the initial parameters."""
    await _setup_pid_climate(hass, CLIMATE_CONFIG)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == DEFAULT_SENSOR_TEMPERATURE
    assert state.attributes.get(ATTR_HVAC_MODES) == [
        HVACMode.OFF,
        HVACMode.HEAT,
    ]


async def test_default_setup_params(hass: HomeAssistant) -> None:
    """Test the setup with default parameters."""
    await _setup_pid_climate(hass, CLIMATE_CONFIG)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.attributes.get(ATTR_MIN_TEMP) == DEFAULT_MIN_TEMP
    assert state.attributes.get(ATTR_MAX_TEMP) == DEFAULT_MAX_TEMP


async def test_set_only_target_temp_bad_attr(hass: HomeAssistant) -> None:
    """Test setting the target temperature without required attribute."""
    await _setup_pid_climate(hass, CLIMATE_CONFIG)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            Platform.CLIMATE,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_TEMPERATURE: None},
            blocking=True,
        )

    state = hass.states.get(ENTITY_CLIMATE)
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE


async def test_set_only_target_temp(hass: HomeAssistant) -> None:
    """Test the setting of the target temperature."""
    await _setup_pid_climate(hass, CLIMATE_CONFIG)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE

    target_temperature = 30.0
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_TEMPERATURE: target_temperature},
        blocking=True,
    )
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.attributes.get(ATTR_TEMPERATURE) == target_temperature
    # Range is not supported as we regulate to a temperature, should be None
    assert state.attributes.get(ATTR_TARGET_TEMP_LOW) is None
    assert state.attributes.get(ATTR_TARGET_TEMP_HIGH) is None


async def test_turn_on_and_off(hass: HomeAssistant) -> None:
    """Test turn on- and off device."""
    await _setup_pid_climate(hass, CLIMATE_CONFIG)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF

    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF

    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE},
        blocking=True,
    )
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.HEAT

    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Sleep some cyles. Set all off and to 0 to prevent from lingering errors.
    await asyncio.sleep(CYCLE_TIME * 10)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF


async def test_enable_heater_kp(hass: HomeAssistant) -> None:
    """Test if enabling the thermostat enables the heater (kp-setting)."""
    cl = CLIMATE_CONFIG.copy()
    # Inject PID values
    cl[Platform.CLIMATE][CONF_PID_KP] = 1.0
    cl[Platform.CLIMATE][CONF_PID_KI] = 0.0
    cl[Platform.CLIMATE][CONF_PID_KD] = 0.0

    await _setup_pid_climate(hass, cl)
    state = hass.states.get(ENTITY_CLIMATE)
    # Make sure input sensor is at 10 degC,
    # target temperature is at 19 degC,
    # so output should be 9 when Kp is 1.
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == DEFAULT_SENSOR_TEMPERATURE
    assert state.state == HVACMode.OFF

    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.HEAT

    # Sleep some cyles.
    await asyncio.sleep(CYCLE_TIME * 3)
    assert hass.states.get(ENTITY_HEATER).state == "9.0"

    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Sleep some cyles. Set all off and to 0 to prevent from lingering errors.
    await asyncio.sleep(CYCLE_TIME * 10)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF
    assert hass.states.get(ENTITY_HEATER).state == "0.0"


async def test_enable_cooler_kp(hass: HomeAssistant) -> None:
    """Test if enabling the thermostat enables the cooler (kp-setting)."""
    cl = CLIMATE_CONFIG.copy()
    # Inject PID values
    cl[Platform.CLIMATE][CONF_PID_KP] = 2.0
    cl[Platform.CLIMATE][CONF_PID_KI] = 0.0
    cl[Platform.CLIMATE][CONF_PID_KD] = 0.0
    cl[Platform.CLIMATE][CONF_AC_MODE] = AC_MODE_COOL

    await _setup_pid_climate(hass, cl)
    state = hass.states.get(ENTITY_CLIMATE)
    # Set input sensor to 25 degC,
    # target temperature is 19 degC,
    # so output should be 12 when Kp is 2.
    sensor_temperature = 25.0
    hass.states.async_set(ENTITY_SENSOR, sensor_temperature)

    assert state.state == HVACMode.OFF
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Sleep some cyles.
    await asyncio.sleep(CYCLE_TIME * 3)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.HEAT
    assert hass.states.get(ENTITY_HEATER).state == "12.0"
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == sensor_temperature
    # Switch to off again to disable the internal timers
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    # Sleep some cyles. Set all off and to 0 to prevent from lingering errors.
    await asyncio.sleep(CYCLE_TIME * 10)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF
    assert hass.states.get(ENTITY_HEATER).state == "0.0"


async def test_enable_heater_ki(hass: HomeAssistant) -> None:
    """Test if enabling the thermostat enables the heater (ki-setting)."""
    cl = CLIMATE_CONFIG.copy()
    # Inject PID values
    cl[Platform.CLIMATE][CONF_PID_KP] = 0.0
    cl[Platform.CLIMATE][CONF_PID_KI] = 100.0
    cl[Platform.CLIMATE][CONF_PID_KD] = 0.0
    cl[Platform.CLIMATE][CONF_AC_MODE] = AC_MODE_HEAT

    await _setup_pid_climate(hass, cl)
    state = hass.states.get(ENTITY_CLIMATE)
    # Input sensor is 10 degC,
    # target temperature is 19 degC,
    # so output should clip to 100 when Kp is 2.

    assert state.state == HVACMode.OFF
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Sleep some cyles.
    await asyncio.sleep(CYCLE_TIME * 30)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == DEFAULT_SENSOR_TEMPERATURE
    assert hass.states.get(ENTITY_HEATER).state == "100.0"
    # Switch to off again to disable the internal timers
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    # Sleep some cyles. Set all off and to 0 to prevent from lingering errors.
    await asyncio.sleep(CYCLE_TIME * 10)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF
    assert hass.states.get(ENTITY_HEATER).state == "0.0"


async def test_enable_heater_kd(hass: HomeAssistant) -> None:
    """Test if enabling the thermostat enables the heater (kd-setting)."""
    cl = CLIMATE_CONFIG.copy()
    # Inject PID values
    cl[Platform.CLIMATE][CONF_PID_KP] = 0.0
    cl[Platform.CLIMATE][CONF_PID_KI] = 0.0
    cl[Platform.CLIMATE][CONF_PID_KD] = 100.0
    cl[Platform.CLIMATE][CONF_AC_MODE] = AC_MODE_HEAT

    await _setup_pid_climate(hass, cl)
    state = hass.states.get(ENTITY_CLIMATE)
    # Input sensor is 10 degC,
    # target temperature is 19 degC,
    # so output should clip to 100 when Kp is 2.

    assert state.state == HVACMode.OFF
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Sleep some cyles.
    await asyncio.sleep(CYCLE_TIME * 30)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes.get(ATTR_TEMPERATURE) == DEFAULT_TARGET_TEMPERATURE
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == DEFAULT_SENSOR_TEMPERATURE
    # Check if output is equal to 0, as we only have a Kd100
    # and  input remains always 10.0
    assert hass.states.get(ENTITY_HEATER).state == "0.0"
    # Switch to off again to disable the internal timers
    await hass.services.async_call(
        Platform.CLIMATE,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    # Sleep some cyles. Set all off and to 0 to prevent from lingering errors.
    await asyncio.sleep(CYCLE_TIME * 10)
    state = hass.states.get(ENTITY_CLIMATE)
    assert state.state == HVACMode.OFF
    assert hass.states.get(ENTITY_HEATER).state == "0.0"
