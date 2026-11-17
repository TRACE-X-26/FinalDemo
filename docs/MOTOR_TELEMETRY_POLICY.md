# Motor measurements and control — November 18, 2026

Canonical firmware: ADS, version `0.8.0-motor-telemetry`, Nucleo-F401RE.
The operator requested removal of motor voltage/current and INA219 readiness
gates. `ADS/bench/downstream.operator.h` selects
`ADS_ELECTRICAL_LIMITS_ENABLED=0`; generic and protected profiles retain their
previous enabled default. This flag now controls actual behavior.

In this build, motor overcurrent/voltage software cutoffs are disabled, and
INA219 validity, age, calibration, acquisition matching and off-state voltage
do not gate motor control. INA219 acquisition continues and invalid readings
remain invalid/null. A0 probe acquisition and circuit relay controls are unchanged.
The existing configured numeric thresholds are informational while disabled.

Relay preparation still uses PREPARE_TEST_POWER, POWER_CHECK and POWER_READY
states, so old command sequencing is retained. With electrical checks disabled,
the state becomes ready after 50 ms of relay settling without verifying supply
voltage. The 1500 ms preparation deadline remains. Capabilities explicitly report:

```json
{
  "firmware_version": "0.8.0-motor-telemetry",
  "electrical_limits_enabled": false,
  "motor_sensor_gating_enabled": false,
  "supply_sensing": "TELEMETRY_ONLY",
  "power_check_mode": "RELAY_SETTLE_ONLY",
  "power_check_required": true,
  "protection_limits_verified": false
}
```

`power_check_required` now denotes mandatory relay preparation; the explicit
mode distinguishes it from electrical verification. JSON v1 and CRC32 are
unchanged. The updated backend recognizes both complete telemetry-only and
protected policies. Missing/inconsistent policy fields remain a protocol error.
Malformed serial frames are still rejected; a correctly framed invalid sensor
reading is recorded as a quality warning rather than preventing motor operation.

Retained: boot stopped, explicit ARM/Start, Stop/E-stop, 2-second heartbeat
shutdown, 30-second maximum, fixed 50% forward PWM, motor/circuit exclusion,
relay polarity, and existing non-electrical operating-mode acceptance. No
automatic restart is added. The optional calibrated encoder stationary check
is unchanged; encoder calibration remains disabled in the current profile.

## CubeIDE installation

Extract `TRACE-X-Firmware-0.8.0-Motor-Telemetry.zip`. Choose a new empty CubeIDE
workspace. File > Import > General > Existing Projects into Workspace, then
select the extracted ADS folder. Check Copy projects into workspace if desired.
Clean and build Debug, then use the Trace-X launch. The archive includes a
prebuilt ADS/Debug/ADS.elf and all project sources/drivers/settings. It excludes
IDE workspace state and unrelated application bundles. Do not regenerate from
the old ADS.ioc without reviewing custom peripheral owners.

## Pi update

Use the matching updated Python backend and rebuilt frontend. The repository's
`deploy/pi/supervised-operator-profile.json` now describes this firmware and
RELAY_SETTLE_ONLY policy. Preserve the real ST-LINK USB serial identity when
updating an existing deployed profile; its blank repository value is deliberate.
If `ADS_AUTOMATION_HARDWARE_PROFILE` points to a different deployed file, update
that file's firmware_version, electrical_limits_enabled, motor_sensor_gating_enabled
and power_check_mode to match. Restart the existing backend after deployment;
do not start a second process that also owns the serial port. The older backend
requires electrical protections and will reject this firmware.

The motor screen distinguishes configured Pi policy from a fresh STM32 snapshot.
It shows electrical checks OFF only when that policy was reported by the MCU.
Circuit ADC/INA219 measurements remain separate and unchanged.

## Verification and limitations

Host tests cover operation with missing supply, supply present while idle,
high voltage/current, invalid and stale electrical telemetry; retained shutdown
and branch logic; actual C JSON/CRC exchanges with the Python backend; and probe
conversion/validity. The ARM image and frontend are built separately. These
checks use synthetic hardware and do not establish physical operating limits.
No board was flashed and no real motor/probe test was performed.

## Changed files for this update

- ADS/bench/downstream.operator.h
- ADS/Core/Inc/ads_board_config.h
- ADS/Core/Src/ads_protection.c
- ADS/Core/Src/ads_sensors.c
- ADS/Core/Src/ads_motor.c
- ADS/Core/Src/ads_protocol.c
- diagnostic_platform/hardware_runtime.py
- diagnostic_platform/automated_engine.py
- deploy/pi/supervised-operator-profile.json
- frontend/src/HardwareMotorControls.tsx
- api/main.py (corrected an existing startup indentation error found by tests)
- tests/telemetry_motor_sensors_harness.c
- tests/test_motor_telemetry_policy.py
- tests/backend_firmware_harness.c
- tests/test_backend_firmware_contract.py
- tests/test_hardware_runtime.py
- tests/test_branch_power.py
- tests/test_operator_motor_build.py
- README.md, docs/FIRMWARE_BASELINE.md, docs/MOTOR_TELEMETRY_POLICY.md

The firmware ZIP contains only the firmware project and import guide; Pi/backend
and frontend changes live in the existing repository.
