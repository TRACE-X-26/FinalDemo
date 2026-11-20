# TRACE-X FinalDemo — Dashboard 0.9.1

TRACE-X uses an STM32 Nucleo-F401RE for motor control and measurements, with a
Python FastAPI backend and React dashboard on a Raspberry Pi 5 or development Mac.

The dashboard has three navigation items:

- **Test Station** — select Motor or Circuit, issue explicit power/test commands,
  and view readings from the two INA219 sensors and the circuit probe.
- **STM32 Sensors** — monitor live STM32 measurements and connection status.
- **Motor Health** — review numbered motor tests, compare saved readings against the provisional T08-01/T08-02 reference, and reopen diagnoses from SQLite history.
  The comparison uses seconds 3–13. A 15-second test gives that window time to complete. Archived RPM scaling is unverified.

## Matching firmware and motor behavior

The only active firmware project is **`ADS/`**. Firmware identity:
**`0.9.0-branch-control`**, using ADS JSON v1 with CRC32 at 115200 baud.

Select Motor or Circuit, confirm its power, then use a separate Start Motor Test
for motor motion. **Reset / All Off** is available across the dashboard and
clears selection while requesting both branches off. Failed communication
shows **Off not confirmed**. Motor power-ready standby expires after 30 seconds.

The current motor test is **50% PWM, forward, for up to 30 seconds**. Firmware
and backend do not gate the motor on voltage/current limits, INA219 validity,
freshness, or electrical calibration. Measurements remain available as telemetry;
invalid values remain invalid rather than becoming zero.

Stop/E-stop, the 2-second communication-loss timeout, bounded test duration,
relay preparation at zero PWM, and motor/circuit branch exclusion remain active.
The controller boots stopped. Relay preparation waits 50 ms and does not verify
that downstream supply voltage is present. These software changes have not been
verified on physical hardware by the coding agent.

Circuit INA219 readings are also telemetry in 0.9.0; missing sensor readings
stay invalid rather than preventing explicit branch-power confirmation.

See [0.9.0 workflow, installation and rollback](docs/RELEASE_0.9.0.md).
The working [v0.8.0 baseline](https://github.com/TRACE-X-26/FinalDemo/tree/v0.8.0) is available on its own branch.

## Run the dashboard manually

Use Python 3.11 or newer and a Node version compatible with the locked Vite 7
frontend (Node 22.12+ or a supported newer release).

```sh
git clone --branch main https://github.com/TRACE-X-26/FinalDemo.git
cd FinalDemo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-backend.txt
cd frontend
npm ci
npm run build
cd ..
ADS_SERVE_DASHBOARD=1 python -m uvicorn api.main:app --host 127.0.0.1 --port 13115
```

Open **http://127.0.0.1:13115/**. This command serves the built dashboard and API
from one process and does not configure browser autostart. Without a configured
STM32, live hardware readings show disconnected/unavailable. Separate legacy
simulation services remain in the backend; the current Test Station does not
substitute simulated values for missing hardware readings.

The repository also includes the prebuilt dashboard. To use it, skip the frontend build and launch from the repository root after installing Python dependencies.

```sh
ADS_SERVE_DASHBOARD=1 ADS_DASHBOARD_DIST=releases/dashboard-0.9.1-dist \
  python -m uvicorn api.main:app --host 127.0.0.1 --port 13115
```

For frontend development, run the backend on port 13115 and `npm run dev` from
`frontend/`; the Vite proxy forwards API and WebSocket traffic to the backend.

## Connect the STM32

1. Import `ADS/` into a new CubeIDE workspace. Debug and Release both select
   `ADS_USE_DIRECT_MOTOR_PROFILE=1`. Clean, build, and flash the Debug image using
   the Trace-X launch. Keep motor supply power off while programming.
2. Copy `deploy/pi/supervised-operator-profile.json` to a local configuration file
   outside Git. Fill its `serial_identity` with the actual ST-LINK USB serial
   number. The repository deliberately does not guess a board identity.
3. Set `ADS_AUTOMATION_HARDWARE_PROFILE` to the absolute path of that local file.
   For shared ADS JSON sensor monitoring, set `ADS_LIVE_PROTOCOL=ads_json` and
   `ADS_LIVE_SERIAL_PORT` to the actual serial device (prefer a persistent
   `/dev/serial/by-id/...` path on the Pi).
4. Restart the backend. Only one process may own the STM32 serial connection.
   The Test Station sends explicit commands; opening it does not start a motor.

The separate circuit power opt-in is `ADS_HARDWARE_CONTROL_ENABLED=true` and
still requires the existing circuit profile approvals. It does not re-enable
motor electrical checks. The `.env.example` file documents available variables;
manual uvicorn execution does not automatically load an `.env` file.

## Measurement wiring

| Measurement | STM32 connection |
|---|---|
| Motor INA219 | I2C1 PB8/PB9, address `0x40` |
| Circuit supply INA219 | Same I2C bus, address `0x41` |
| Circuit probe | ADC1 channel 0, PA0/A0, 30 kΩ / 10 kΩ divider |
| Motor driver | DIR D7/PA8; PWM D6/PB10 |
| Motor / circuit relays | D4/PB5 / D5/PB4, active LOW |
| Encoder A / B | D12/PA6 / D9/PC7 |

Probe voltage is independent of circuit INA219 supply voltage. Initial probe
range is 0–12 V DC. Reference/divider calibration, filtering, raw ADC count,
validity, timestamps and stale/saturation statuses are implemented. Hardware
accuracy requires comparison with reference instruments; an unplugged probe
cannot be distinguished reliably from a grounded probe with this wiring.
See [probe ADC integration](docs/PROBE_ADC_INTEGRATION.md).

## Build and test

```sh
python -m unittest discover -s tests
cd frontend
npm run build
npm run lint
```

Firmware command-line build: `make -C ADS -j4`. Override `TOOLCHAIN` with your
ARM toolchain directory when the bundled Mac CubeIDE path differs. This builds
`ADS/Debug/ADS.elf` and does not flash a board. Host tests use synthetic hardware;
passing tests does not establish motor ratings or physical measurement accuracy.

Local recordings, databases, credentials, generated binaries, IDE workspaces,
recovery archives and duplicate firmware projects are excluded from this
repository. `reference_data/` contains the existing small application fixtures
and derived archive summaries, not the private raw recording folders.
