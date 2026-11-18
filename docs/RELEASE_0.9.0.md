# TRACE-X 0.9.0 — confirmed branch control

Firmware identity: `0.9.0-branch-control`. Dashboard/backend release: `0.9.0`.
The preceding working motor version, `0.8.0-motor-telemetry`, is available on the
[v0.8.0 branch](https://github.com/TRACE-X-26/FinalDemo/tree/v0.8.0).
Operator-confirmed motor operation is the baseline. That confirmation does not
establish sensor accuracy.

## Workflow

1. STM32 boots with both relays commanded OFF and PWM at zero. Backend selection
   starts empty; a browser reconnect does not automatically energize a branch.
2. Select Motor or Circuit. Selection changes software state only.
3. Check the branch/supply/cutoff confirmation, then Confirm & Power On. The
   backend first requests both outputs off and requires acknowledgment. It then
   enables the selected branch, using the existing relay drivers and command
   ownership lock. An active branch must be reset before another is selected.
4. Motor confirmation powers the driver at zero PWM. It enters POWER_READY after
   50 ms relay settling. Start Motor Test is a separate action using the existing
   50% forward start, event, recording and stop sequence. The duration can be
   edited before Start. Starting the motor twice is rejected.
5. Reset / All Off cancels any pending/active session, waits for the existing
   serial owner to finish its stop exchange, sends RESET_ALL, and requires both
   relay-off flags plus zero PWM in the acknowledgment. Selection clears even
   if USB is disconnected. Missing acknowledgment displays Off not confirmed.

Reset is a stop operation, not an STM32 reboot, and does not re-arm anything.
The button is available on both Test Station and STM32 Sensors. It is idempotent
and remains accepted during lockout or for an old request sequence. The MCU still
requires fresh explicit arm/confirmation before another power operation.

Motor power-ready standby expires after 30 seconds, even with heartbeats. A
started motor test has its own maximum of 30 seconds; standby plus run can
therefore approach 60 seconds of branch power. Circuit supply sessions remain
bounded to 30 seconds. Both controllers retain the 2-second heartbeat shutdown.
No simultaneous motor/circuit enable or automatic restart is added.

## Measurement policy

Motor voltage/current cutoffs remain disabled as in 0.8.0. The circuit branch
also uses readings as telemetry in this operator-selected release: missing,
stale or invalid INA219 samples do not prevent power confirmation. This is
advertised by `circuit_sensor_gating_enabled=false`. The generic/legacy profiles
retain their previous sensor policy. Calibration flags and invalid/null values
are preserved; powering a branch does not assert a valid measurement or a
healthy circuit. ADC probe acquisition and conversion are unchanged.

## Protocol and implementation

ADS JSON v1/CRC32 framing is unchanged. Added commands: RESET_ALL and
GET_STATION_STATUS. Added capabilities: station_control, motor_power_hold_ms and
circuit_sensor_gating_enabled. PREPARE_TEST_POWER requires an explicit branch
confirmation in the 0.9 operator profile. Circuit ARM retains its explicit
supervision confirmation. The existing mutual-exclusion callbacks remain.

Python `StationService` serializes branch confirmation and reset. Existing
`AutomatedTestEngine` owns the motor connection through POWER_READY and RUNNING;
the existing circuit service owns circuit sessions. A reset prevents new starts
while waiting for either owner. Read-only polling uses the same owner lock.
Selection waits for a short read-only poll instead of mistaking it for a powered
test. No second serial reader is created for the new controls.

## Installation and rollback

Use the matching firmware and dashboard together. Import the extracted firmware
ADS directory into a fresh CubeIDE workspace, Clean, build Debug and flash using
Trace-X. A successful build produces ADS/Debug/ADS.elf. The existing .ioc
must not be regenerated without reviewing custom GPIO, timer, I2C and ADC code.

The repository contains dashboard and backend source. The prebuilt frontend is
in `releases/dashboard-0.9.0-dist`. Create its Python virtual environment and install requirements-backend.txt.
Follow the root README to serve a fresh build or the prebuilt frontend on port 13115. Preserve the
actual USB serial identity in a local copy of the new supervised operator profile;
its firmware_version must be 0.9.0-branch-control. Use ADS_AUTOMATION_HARDWARE_PROFILE
to point to that copy. The circuit opt-in remains ADS_HARDWARE_CONTROL_ENABLED=true.
ADS_LIVE_PROTOCOL=ads_json and ADS_LIVE_SERIAL_PORT configure shared sensor polling.
Only one backend may own the real STM32 serial port.

For rollback, restore the whole 0.8.0 baseline and flash its saved image; use its
matching backend/profile. Do not combine only selected old/new files. Nothing in
this implementation flashes a board, restarts the live backend, or operates the
connected hardware automatically. A separate hardware-disabled 0.9 preview may
run on port 13116; the existing port 13115 service is left running.

## Verification and physical limits

Regression tests use synthetic hardware, actual production C protocol/state
machines, fake GPIO, and the Python API. New tests cover explicit confirmation,
zero PWM during preparation, single start, active reset, repeated reset, missing
reset acknowledgment, invalid circuit telemetry, cross-branch exclusion, standby
expiry and heartbeat loss. The real ARM image and frontend build separately.

GPIO inactive levels are preloaded before output configuration. However, relay
behavior before STM32 initialization, relay supply preceding MCU supply, floating
inputs, mechanical contact release and welded contacts require physical
verification. Relay-off acknowledgment confirms software output commands, not
measured contact disconnection. Hardware pull-ups/interfaces may be necessary
after checking the specific relay module's input circuit.

## Main files changed

- Firmware: ADS/Core/Inc/ads_board_config.h, ads_test.h;
  ADS/Core/Src/ads_motor.c, ads_protocol.c, ads_test.c, main.c;
  ADS/bench/downstream.operator.h and ADS/Makefile.
- Backend: diagnostic_platform/station.py, automated_engine.py,
  automated_storage.py, circuit_power.py, protocol.py, stm32.py;
  api/main.py, api/schemas.py and deploy/pi/supervised-operator-profile.json.
- Dashboard: frontend/src/App.tsx, TestStation.tsx, HardwareMotorControls.tsx,
  api.ts, types.ts and package version files.
- Tests: test_station_control.py; extended firmware/GPIO/contract fixtures.
