# PID Thermostat integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

This integration contains a PID regulated thermostat. 

It uses a sensor and a number entity connected to a heater or air conditioning. A typical method to create a number to control a heater or cooler could be to use the [slow_pwm number integration][slow_pwm]. When in heater mode, if the measured temperature is cooler than the target temperature, the heater will be regulated until the required temperature is reached. When in air conditioning mode, if the measured temperature is hotter than the target temperature, the air conditioning will be regulated until the required temperature is reached. One PID Thermostat entity can only control one number output. If you need to activate two numbers (one for a heater and one for an air conditioner), you will need two PID Thermostat entities. The value for the output number entity will be calculated using the [Proportional–Integral–Derivative algorithm (PID)](https://en.wikipedia.org/wiki/PID_controller). The implementation of the PID controller contains bumpless operation, and is prevented against integral windup by clipping of the output value to the minimum and maximum of the corresponding output number entity. Setting up the optimal parameters for a PID controller can be a tough job. Depending on your particular job, you might already know more or less what the parameters should be. If required, you could use [manual tuning](https://en.wikipedia.org/wiki/PID_controller#Manual_tuning) to find optimal parameters. In short, you should make the following steps:
- For kp, start with 100; if your thermostat deviates by 1 °C, you might want the heater to turn on for 100%. If required, gradually make it bigger if you see that the direct reaction of the controller is too low.
- For ki, keep this number to 0 until kp is set. Then, start with a small number (0.1). If you see that the reaction over time is only slowly rising, increase it until the controller regulates to the setpoint in a reasonable amount of time.
- For kd, keep this number to 0 until kp and ki are set. Now you can use the kd to prevent the regulator from overshooting. Only increase in small steps.

The PID thermostat code is shared with the [PID controller][pid_controller]. As an output for the thermostat, the [Slow PWM][slow_pwm] number can be used.

**This integration will set up the following platforms.**

Platform | Description
-- | --
`climate` | This platform can be used to control a number entity output to regulate a temperature to a specific setpoint. The value of the climate entity is the setpoint. As a sensor, any temperature sensor entity can be used.

## Installation

### HACS (Preferred)
1. [Add](http://homeassistant.local:8123/hacs/integrations) the custom integration repository: https://github.com/domectrl/ha-pid_thermostat
2. Select `PID Thermostat` in the Integration tab and click `download`
3. Restart Home Assistant
4. Done!

### Manual
1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `pid_thermostat`.
1. Download _all_ the files from the `custom_components/pid_thermostat/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant

## Configuration via user interface:
* In the user interface go to "Configuration" -> "Integrations" click "+" and search for "PID Thermostat"
* For a description of the configuration parameters, see [Configuration parameters](#configuration-parameters)

## YAML Configuration

Alternatlively, this integration can be configured and set up manually via YAML
instead. To enable the Integration sensor in your installation, add the
following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
climate:
  - platform: pid_thermostat
    name: Kitchen thermostat
    heater: number.floor_heater
    sensor: sensor.kitchen_temperature
```

### Configuration parameters
- name: Name of the PID thermostat.
  > required: true | type: string
- heater: Heater- or cooler device entity. Must be a number device. Typically, the [slow_pwm number entity][slow_pwm] can be used to create a number controlling a binary switch. The output will be limited to the minimum and maximum value of this number.
  > required: true | type: string
- sensor: Temperature sensor entity, used for input signal.
  > required: true | type: string
- kp: Proportional gain factor, directly gaining the error to compensate the fault (Kp).
  > required: false | default: 100.0 | type: float
- ki: Integration factor, reducing the offset fault over time (Ki).
  > required: false | default: 0.1 | type: float
- kd: Differential factor, damping the overshoot (Kd).
  > required: false | default: 0.0 | type: float
- ac_mode: Thermostat mode. Select if the thermostat should be a cooler or a heater.
  > required: false | default: 'heat' | type: string `('heat' or 'cool')`
- min_temp: Minimal temperature setpoint in °C.
  > required: false | default: 7 | type: float
- max_temp: Maximal temperature setpoint in °C.
  > required: false | default: 35 | type: float
- cycle_time: Cycle time for the PID controller loop.
  > required: false | default: "{'seconds': 30}" | type: time_period
- target_temp: Target temperature on startup.
  > required: false | default: 19 | type: float
- initial_hvac_mode: Initial HVAC mode. 
  > required: false | default: 'off' | type: string `('off', 'heat' or 'cool')`
- away_temp: Preset 'Away' temperature. Preset will only be available in the thermostat when set here.
  > required: false | default: not set | type: float
- unique_id: Unique id to be able to configure the entity in the UI.
  > required: false | type: string

### Full configuration example

```yaml
climate:
  - platform: pid_thermostat
    name: Kitchen thermostat
    heater: number.floor_heater
    sensor: sensor.kitchen_temperature
    kp: 100.0
    ki: 0.5
    kd: 0.01
    ac_mode: heat
    min_temp: 10
    max_temp: 25
    cycle_time: {'hours':0, 'minutes':0, 'seconds': 30}
    target_temp: 21
    initial_hvac_mode: heat
    away_temp: 15
    unique_id: "MyUniqueID_1234"
```

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***

[commits-shield]: https://img.shields.io/github/commit-activity/y/domectrl/ha-pid_controller.svg?style=for-the-badge
[commits]: https://github.com/domectrl/ha-pid_controller/commits/main
[hacs]: https://hacs.xyz/
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/domectrl/ha-pid_controller.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-domectrl-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/domectrl/ha-pid_controller.svg?style=for-the-badge
[releases]: https://github.com/domectrl/ha-pid_controller/releases
[slow_pwm]: https://github.com/domectrl/ha-slow_pwm
[pid_controller]: https://github.com/domectrl/ha_pid_controller
