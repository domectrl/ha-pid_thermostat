"""Adds support for generic thermostat units."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from dvg_pid_controller import Constants as PIDConst
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    PLATFORM_SCHEMA,
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
    PRECISION_TENTHS,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    AC_MODE_COOL,
    CONF_AC_MODE,
    CONF_AWAY_TEMP,
    CONF_CYCLE_TIME,
    CONF_HEATER,
    CONF_INITIAL_HVAC_MODE,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    DEFAULT_AC_MODE,
    DEFAULT_CYCLE_TIME,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
    PLATFORMS,
    SUPPORT_FLAGS,
)
from .pid_shared import PidBaseClass

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HEATER): cv.entity_id,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_CYCLE_TIME, default=DEFAULT_CYCLE_TIME): cv.time_period_dict,
        vol.Optional(CONF_PID_KP, default=DEFAULT_PID_KP): vol.Coerce(float),
        vol.Optional(CONF_PID_KI, default=DEFAULT_PID_KI): vol.Coerce(float),
        vol.Optional(CONF_PID_KD, default=DEFAULT_PID_KD): vol.Coerce(float),
        vol.Optional(CONF_AC_MODE, default=DEFAULT_AC_MODE): cv.string,
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TARGET_TEMP, default=DEFAULT_TARGET_TEMPERATURE): vol.Coerce(
            float
        ),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize PID Controller config entry."""
    async_add_entities(
        [PidThermostat(hass, config_entry.options, config_entry.entry_id)]
    )


# pylint: disable=unused-argument
async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,  # noqa: ARG001
) -> None:
    """Set up the generic thermostat platform."""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    async_add_entities([PidThermostat(hass, config, config.get(CONF_UNIQUE_ID))])


class PidThermostat(ClimateEntity, RestoreEntity, PidBaseClass):
    """Representation of a PID Thermostat device."""

    # pylint: disable=too-many-instance-attributes
    # thermostat already contains a lot of attributes...
    def __init__(
        self,
        hass: HomeAssistant,  # noqa: ARG002
        config: ConfigType,
        unique_id: str,
    ) -> None:
        """Initialize the thermostat."""
        self._config = config
        self.heater_entity_id = config[CONF_HEATER]
        self.sensor_entity_id = config[CONF_SENSOR]
        self.ac_mode = config.get(CONF_AC_MODE, DEFAULT_AC_MODE) == AC_MODE_COOL
        super().__init__(
            config.get(CONF_PID_KP, DEFAULT_PID_KP),
            config.get(CONF_PID_KI, DEFAULT_PID_KI),
            config.get(CONF_PID_KD, DEFAULT_PID_KD),
            PIDConst.DIRECT if not self.ac_mode else PIDConst.REVERSE,
            config.get(CONF_CYCLE_TIME, DEFAULT_CYCLE_TIME),
        )
        self._pid.setpoint = config.get(CONF_TARGET_TEMP)
        self._hvac_list = [
            HVACMode.OFF,
            HVACMode.COOL if self.ac_mode else HVACMode.HEAT,
        ]
        self._hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
        self._min_temp = config.get(CONF_MIN_TEMP)
        self._max_temp = config.get(CONF_MAX_TEMP)
        self._away_temp = config.get(CONF_AWAY_TEMP)
        self._saved_target_temp = config.get(CONF_TARGET_TEMP) or config.get(
            CONF_AWAY_TEMP
        )
        self._attr_preset_mode = PRESET_NONE
        self._unique_id = unique_id
        self._support_flags = SUPPORT_FLAGS
        if config.get(CONF_AWAY_TEMP):
            self._support_flags = SUPPORT_FLAGS | ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
        else:
            self._attr_preset_modes = [PRESET_NONE]
        self._cur_temp = None
        self._output_step = 0.01
        self._attr_last_cycle_start = dt_util.utcnow().replace(microsecond=0)
        self._attr_extra_state_attributes = super().pid_state_attributes

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.sensor_entity_id, self._async_sensor_changed
            )
        )

        # Recover state
        await self._async_recover_state()

        @callback
        async def _async_startup(*_) -> None:  # noqa: ANN002
            """Init on startup."""
            sensor_state = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                await self._async_set_curr_temp(sensor_state)
            heater_state = self.hass.states.get(self.heater_entity_id)
            if heater_state and heater_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                # Get knowledge about the limits of our outputs
                attr_min = heater_state.attributes.get("min", 0.0)
                attr_max = heater_state.attributes.get("max", 100.0)
                self._output_step = heater_state.attributes.get("step", 0.01)
                # Set min/max for output
                self._pid.set_output_limits(attr_min, attr_max)
                # Set to initial state
                self.hass.create_task(self._check_switch_initial_state())

            # If hvac_state is not off, start the PID regulator
            await self.async_set_hvac_mode(self._hvac_mode)
            # Start PID regulator loop
            await self._async_start_pid_cycle()
            # ---- _async_startup ----

        if self.hass.state == CoreState.running:
            await _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

    async def _async_recover_state(self) -> None:
        """Recover state."""
        # Check If we have an old state
        if (old_state := await self.async_get_last_state()) is not None:
            # If we have a previously saved temperature
            if old_state.attributes.get(ATTR_TEMPERATURE):
                self._pid.setpoint = float(old_state.attributes[ATTR_TEMPERATURE])
            else:
                if self.ac_mode:
                    self._pid.setpoint = self.max_temp
                else:
                    self._pid.setpoint = self.min_temp
                _LOGGER.warning(
                    "Undefined target temperature, falling back to %s",
                    self._pid.setpoint,
                )
            if old_state.attributes.get(ATTR_PRESET_MODE) in self._attr_preset_modes:
                self._attr_preset_mode = old_state.attributes.get(ATTR_PRESET_MODE)
            if not self._hvac_mode and old_state.state:
                self._hvac_mode = old_state.state
        else:
            # No previous state, try and restore defaults
            if self._pid.setpoint is None:
                if self.ac_mode:
                    self._pid.setpoint = self.max_temp
                else:
                    self._pid.setpoint = self.min_temp
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._pid.setpoint
            )
        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVACMode.OFF

    @property
    def should_poll(self) -> bool:
        """Return the polling state."""
        return False

    @property
    def name(self) -> str:
        """Return the name of the thermostat."""
        return self._config[CONF_NAME]

    @property
    def unique_id(self) -> str:
        """Return the unique id of this thermostat."""
        return self._unique_id

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        return PRECISION_TENTHS

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        # Since this integration does not yet have a step size parameter
        # we have to re-use the precision as the step size for now.
        return self.precision

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return self.hass.config.units.temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def hvac_mode(self) -> str:
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> str:
        """
        Return the current running hvac operation if supported.

        Need to be one of HVACAction.*.
        """
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not self._is_device_active:
            return HVACAction.IDLE
        if self.ac_mode:
            return HVACAction.COOLING
        return HVACAction.HEATING

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._pid.setpoint

    @property
    def hvac_modes(self) -> list[str]:
        """List of available operation modes."""
        return self._hvac_list

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set hvac mode."""
        if hvac_mode not in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF):
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return

        input_sensor = self._cur_temp
        output_sensor = None
        try:
            output_sensor = float(self.hass.states.get(self.heater_entity_id).state)
        except (ValueError, TypeError, AttributeError) as ex:
            _LOGGER.warning("Could not read state of output for %s: %s", self.name, ex)

        mode = PIDConst.MANUAL
        if hvac_mode != HVACMode.OFF:
            mode = PIDConst.AUTOMATIC

        if None not in (input_sensor, output_sensor):
            self._pid.set_mode(mode, input_sensor, output_sensor)

        # Switch off output if device was switched off
        if hvac_mode == HVACMode.OFF:
            await self._async_heater_turn_off()

        # All is done, set value
        self._hvac_mode = hvac_mode
        self._attr_extra_state_attributes.update(self.pid_state_attributes)
        self.schedule_update_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._pid.setpoint = temperature
        self.schedule_update_ha_state()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp

    @callback
    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle temperature changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        await self._async_set_curr_temp(new_state)

    async def _async_set_curr_temp(self, new_state: State) -> None:
        """Set the current temperature on change."""

        def _check_value(state: str) -> float:
            state_f = float(state)
            if math.isnan(state_f) or math.isinf(state_f):
                msg = f"Sensor has illegal state: {state}"
                raise ValueError(msg)
            return state_f

        try:
            self._cur_temp = _check_value(new_state.state)
        except ValueError:
            _LOGGER.exception("Unable to update from sensor.")
        self.schedule_update_ha_state()

    async def _check_switch_initial_state(self) -> None:
        """Prevent the device from keep running if HVAC_MODE_OFF."""
        if self._hvac_mode == HVACMode.OFF and self._is_device_active:
            _LOGGER.warning(
                "The climate mode is OFF, device is ON. Turning off device %s",
                self.heater_entity_id,
            )
            await self._async_heater_turn_off()

    async def _async_pid_cycle(self, *_: Any) -> None:
        """PID controller cycle."""
        if not self._cur_temp:
            _LOGGER.warning("Could not read actual temperature for %s", self.name)
            return
        if not self._pid.setpoint:
            _LOGGER.warning("Could not read actual setpoint for %s", self.name)
            return

        if self._hvac_mode == HVACMode.OFF:
            return

        if not self._pid.compute(self._cur_temp) and self._pid.in_auto:
            _LOGGER.warning("PID regulator fails for thermostat %s!", self.name)
        await self._async_heater_set_value(self._pid.output)
        self._attr_last_cycle_start = dt_util.utcnow().replace(microsecond=0)
        self._attr_extra_state_attributes.update(self.pid_state_attributes)
        self.schedule_update_ha_state()

    @property
    def _is_device_active(self) -> bool:
        """If the toggleable device is currently active."""
        output_state = self.hass.states.get(self.heater_entity_id)
        if not output_state:
            _LOGGER.warning("PID thermostat cannot detect output state")
            return None
        if (
            self._pid.output_limit_min is None
        ):  # During startup pid controller returns None
            _LOGGER.warning(
                "PID thermostat pid controller not yet started: no output limit"
            )
            return None
        # check if output state is minimal
        output = float(output_state.state)
        return output > self._pid.output_limit_min

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return self._support_flags

    async def _async_heater_set_value(self, value: float) -> None:
        """Turn heater toggleable device on."""
        output_value = (
            round(value / self._output_step) * self._output_step
        )  # Round off to step
        # Make output as type-agnostic as possible by picking the
        # domain and calling set_value service
        state = self.hass.states.get(self.heater_entity_id)
        if state:
            output_domain = state.domain
            await self.hass.services.async_call(
                output_domain,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: self.heater_entity_id, ATTR_VALUE: output_value},
                blocking=False,
            )
        # Next line does not work; it only switches the state in HA but does
        # not activate set_value within the numbers....
        # self.hass.states.async_set(
        #           self.heater_entity_id,output_value, attr)

    async def _async_heater_turn_off(self) -> None:
        """Turn heater toggleable device off."""
        await self._async_heater_set_value(self._pid.output_limit_min)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in (self._attr_preset_modes or []):
            msg = (
                f"Got unsupported preset_mode {preset_mode} "
                f"Must be one of {self._attr_preset_modes}"
            )
            raise ValueError(msg)
        if preset_mode == self._attr_preset_mode:
            # I don't think we need to call async_write_ha_state
            # if we didn't change the state
            return
        if preset_mode == PRESET_AWAY:
            self._attr_preset_mode = PRESET_AWAY
            self._saved_target_temp = self._pid.setpoint
            self._pid.setpoint = self._away_temp
        elif preset_mode == PRESET_NONE:
            self._attr_preset_mode = PRESET_NONE
            self._pid.setpoint = self._saved_target_temp
