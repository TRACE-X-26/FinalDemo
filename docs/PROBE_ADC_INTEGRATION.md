# Circuit probe ADC integration — November 16, 2026

## Implemented behavior

The existing circuit screens now show four independent live measurements:
circuit supply voltage/current/power from INA219 0x41 and probe voltage from
STM32 A0. The same panel is available in Test station > Circuit and Advanced
tools > Circuit diagnostics > Hardware. Motor controls and the existing capture
and calibration workflows remain in place.

The motor INA219 remains at 0x40; its values describe power entering the MD10C,
not the PWM waveform across the motor. Neither INA219 substitutes for the probe.

No firmware has been flashed, no Pi has been updated, and no physical measurement
accuracy has been established by this implementation.

## Wiring and range

- Red probe -> 30 kohm -> midpoint -> PA0 / A0 / ADC1 channel 0.
- Midpoint -> 10 kohm -> common ground.
- Midpoint -> 100 nF -> common ground.
- Upper BAT54: midpoint anode, 3.3 V cathode.
- Lower BAT54: ground anode, midpoint cathode.
- Black probe -> common ground.

Initial range is 0–12 V DC, with the STM32 powered and common ground connected.
The divider's theoretical 13.2 V full scale is not an approved operating limit.
The clamps do not establish arbitrary overvoltage or negative-input protection;
check the actual diode orientation, resistor tolerances and rail behavior.
Avoid applying a powered probe signal while the STM32 is unpowered.

An unplugged red probe can settle toward zero through the 10 kohm resistor.
This circuit cannot distinguish an unplugged probe from a real grounded point.
Negative voltages also cannot be reliably identified by a unipolar ADC.

## Firmware design

ADC1 is owned only by ads_probe_hw.c. No ADC_HandleTypeDef or MX_ADC1_Init existed
in this checkout, and the HAL ADC source/header dependencies are absent. The
module therefore uses the included CMSIS ADC register definitions and existing
HAL GPIO/clock helpers, rather than introducing missing HAL dependencies or
duplicating initialization. HAL_ADC_MODULE_ENABLED remains unused.

PA0 is analog/no-pull; ADC1 is 12-bit, right-aligned, single-channel and software
triggered. With the current PCLK2 of 84 MHz, ADC prescaler /4 gives 21 MHz. The
480-cycle sampling interval is about 22.9 us, plus 12 conversion cycles. This
long sample interval is appropriate for initial evaluation of the 7.5 kohm
Thevenin source resistance and 100 nF node; bench measurements must establish
actual accuracy and settling. First acquisition waits 100 ms after startup.

Each 100 ms acquisition cycle averages four conversions. Polling never waits in
a conversion loop; a pending conversion times out after 20 ms. Every individual
sample is checked before averaging so saturation cannot be hidden by smoothing.
The ADC code does not switch relays, command PWM, or change motor readiness.
Probe failure is independent of INA219 and encoder validity.

The initial nominal formula is raw/4095 * 3.3 * 4. Fixed-point arithmetic avoids
newlib printf float dependencies. Nominal 12 V endpoint quantization is allowed
one input-referred ADC count; this is not an extension of the 0–12 V operating
range. Raw counts >=4080 flag OUT_OF_RANGE, as do values above the nominal range.
Invalid voltage is serialized as null, never as a valid zero.

Configuration macros in ads_board_config.h (overridable in a build profile):

| Macro | Default | Meaning |
|---|---:|---|
| ADS_PROBE_REFERENCE_MV | 3300 | Measured ADC reference/supply in mV |
| ADS_PROBE_DIVIDER_NUM | 4 | Divider reconstruction numerator |
| ADS_PROBE_DIVIDER_DEN | 1 | Divider reconstruction denominator |
| ADS_PROBE_GAIN_PPM | 1000000 | Additional gain, parts per million |
| ADS_PROBE_OFFSET_MV | 0 | Input-referred offset after gain |
| ADS_PROBE_CALIBRATED | 0 | Keep false until real bench calibration |

The current canonical build selector remains ADS_USE_DIRECT_MOTOR_PROFILE=1,
using bench/downstream.operator.h. The older ADS_USE_OPERATOR_PROFILE selector
is not substituted: motor 50% PWM, 30-second maximum, 10–14 V / 1.5 A protection,
relay polarity, interlocks and watchdog behavior are preserved.

ADC setup lives in the maintained source module, not generated MX_ADC code.
The existing ADS.ioc also predates several custom motor/sensor peripherals;
review generated changes before regenerating CubeMX code over this project.

## Protocol and backend

ADS v1 framing, CRC32 and existing five motor channels are unchanged. A new
optional result.circuit_probe object contains voltage, raw_adc, adc_pin_voltage,
unit, valid, status, calibrated, timestamp_ms and sequence. Older firmware is
shown as NOT_REPORTED; missing probe data never falls back to supply voltage.

Firmware status values include OK, ADC_NOT_INITIALIZED, ADC_TIMEOUT,
ADC_READ_ERROR, OUT_OF_RANGE and STALE. Firmware snapshots expire after 500 ms.
The backend checks MCU sample age when the envelope tick is available and also
expires host data after 3 seconds. Repeated identical acquisition records do not
refresh a frozen probe sample. Malformed/CRC-invalid data and disconnection clear
the displayed voltage. A valid 0 V is displayed numerically.

The existing GET /api/live/status and /ws/live infrastructure exposes the new
object alongside ina219.MOTOR and ina219.CIRCUIT. The UI uses the same read-only
API and shared serial owner; no new serial reader is created by a screen.
The existing ExperimentRecorder CSV gains a PROBE/test_point_voltage row with
raw count and ADC pin voltage. Motor CSV behavior is preserved.

The existing guided capture workflow requires explicit circuit and test-point
identifiers. Live ADC voltage alone does not identify which node the user has
touched, so this change does not invent TP0/TP1 labels or automatic fault claims.

## Build and flash

On the Mac, in /Users/markussanford/Documents/ChatGPT/Capstone:

```sh
make -C ADS -j4
```

The image is ADS/Debug/ADS.elf. In the existing CubeIDE workspace, refresh ADS,
select Debug, clean/build, and use the Trace-X launch configuration for that
image. Disconnect external load power while programming, then resume execution.
Do not import another copy of the project or flash an old installer image.

CubeIDE includes the new Core/Src files through its existing Core source entry.
No additional ADC library download is required.

## Pi update and read-only bring-up

Transfer the matching updated ADS/Python/frontend source tree using your existing
deployment method. Preserve the Pi's database, private profile, runtime settings,
and Python environment; do not transfer the Mac's node_modules or .venv.
No transfer or service restart was performed by this task.

From the Pi project folder containing api/ and frontend/, use its existing Python
environment and install requirements-backend.txt as needed. Rebuild the frontend:

```sh
cd frontend
npm ci
npm run build
cd ..
```

For the existing installed service, configure the verified serial path and
ADS_LIVE_PROTOCOL=ads_json in its runtime.env, then:

```sh
systemctl --user restart trace-x.service
journalctl --user -u trace-x.service -n 40 --no-pager
```

For a manual read-only launch, after stopping any backend/serial reader that owns
the port, activate the Pi's Python environment and run:

```sh
ADS_LIVE_PROTOCOL=ads_json ADS_LIVE_SERIAL_PORT=/dev/ttyACM0 ADS_SERVE_DASHBOARD=1 \
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 13115
```

Replace the example port with the actual ST-LINK port. Open
http://127.0.0.1:13115/ and choose Circuit. Merely viewing readings does not
energize either branch. Physical circuit power still uses its existing separate
profile/permission and supervision rules. Motor USB-identity requirements remain.
The service's existing runtime.env is not loaded by a manual uvicorn command
unless you explicitly export/source those settings.

## Multimeter verification and calibration

No physical rows below have been measured. With the divider/clamps verified,
STM32 powered and the black probe at common ground, compare the red-probe point
against a trusted DMM. Begin with a known low voltage before progressing upward.
Allow the live reading to update after each change.

| Nominal input | Ideal ADC pin | Approx. count | DMM input | Observed count | ADC pin reported | TRACE-X probe | Absolute error | Percent error |
|---|---:|---:|---|---|---|---|---|---|
| 0 V | 0 V | 0 | Pending | Pending | Pending | Pending | Pending | N/A |
| 3 V | 0.75 V | 931 | Pending | Pending | Pending | Pending | Pending | Pending |
| 5 V | 1.25 V | 1551 | Pending | Pending | Pending | Pending | Pending | Pending |
| 9 V | 2.25 V | 2792 | Pending | Pending | Pending | Pending | Pending | Pending |
| 12 V | 3.00 V | 3723 | Pending | Pending | Pending | Pending | Pending | Pending |

Absolute error = abs(TRACE-X - DMM). Percent error = 100 * absolute error /
abs(DMM), only at nonzero reference points. The ADC pin voltage reported by
firmware is derived from the same ADC count, not an independent reference.

First measure the actual ADC reference rail and divider resistors if possible.
Configure those values without marking calibration complete. For a two-point
gain/offset fit, with nominal reconstructed readings x1/x2 and DMM values y1/y2:
gain=(y2-y1)/(x2-x1); offset=y1-gain*x1. Encode gain*1000000 as GAIN_PPM and
offset*1000 as OFFSET_MV, rebuild/flash, then verify all five points independently
and record repeatability and reference equipment before setting CALIBRATED=1.

## Updated files

Firmware:
- ADS/Core/Inc/ads_probe.h (new)
- ADS/Core/Inc/ads_board_config.h
- ADS/Core/Inc/ads_protocol.h
- ADS/Core/Inc/ads_sensors.h
- ADS/Core/Src/ads_probe.c (new)
- ADS/Core/Src/ads_probe_hw.c (new)
- ADS/Core/Src/ads_protocol.c
- ADS/Core/Src/ads_sensors.c
- ADS/Core/Src/main.c

Backend:
- diagnostic_platform/probe.py (new)
- diagnostic_platform/live.py
- diagnostic_platform/automated_engine.py (read-only acquisition metadata only)
- diagnostic_platform/circuit_power.py (acquisition metadata only)
- diagnostic_platform/collector.py

Frontend:
- frontend/src/CircuitMeasurements.tsx (new)
- frontend/src/useCircuitTelemetry.ts (new)
- frontend/src/PhysicalCircuit.tsx
- frontend/src/TestStation.tsx
- frontend/src/types.ts
- frontend/src/api.ts

Tests/documentation:
- tests/probe_harness.c (new)
- tests/test_probe.py (new)
- docs/PROBE_ADC_INTEGRATION.md (new)
- README.md

Other working-tree changes predated this task and are not part of this list.

## Executed validation

- ARM Debug build with the canonical protected operator profile passed:
  text 35,580 bytes; initialized data 92 bytes; BSS 20,292 bytes.
- 244 Python/host-C tests passed, including actual production C protocol frames
  with both INA219 branches and the independent probe object, five conversion
  points, filtering/poll scheduling, timeout/error/saturation/staleness, uint32
  clock wrap, valid zero, API exposure and CSV separation.
- TypeScript project check, Vite production build and ESLint passed. Vite retains
  its existing large-bundle advisory; this does not prevent the build.
- Hardware multimeter comparison, physical ADC behavior, calibration and Pi
  installation remain unverified.
- The actual built circuit panel was inspected in the local browser with no
  controller attached: four separate measurement cards render and show unavailable
  values plus STM32 DISCONNECTED. Headless browser automation was unavailable;
  no claim is made that automated 1024 x 600 layout checks completed.

## Primary references

- ST RM0368, ADC acquisition, timing and register configuration:
  https://www.st.com/resource/en/reference_manual/rm0368-stm32f401xbc-and-stm32f401xde-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
- ST UM1724, Table 16, NUCLEO-F401RE A0/PA0/ADC1_0 mapping:
  https://www.st.com/resource/en/user_manual/dm00105823.pdf
