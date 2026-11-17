# TRACE-X firmware baseline — November 16, 2026

Updated November 18: the canonical project now builds `0.8.0-motor-telemetry`,
with motor electrical gating disabled at the operator's request. The historical
consolidation description below records the preceding protected baseline.
See [current motor policy and installation](MOTOR_TELEMETRY_POLICY.md).

## One project

- Source: `ADS/` (STM32 Nucleo-F401RE).
- Workspace: `Trace-X-Workspace/` (IDE state only; no source copies).
- CubeIDE launch: `Trace-X` (`ADS/Trace-X.launch`).
- Command-line build: `make -C ADS -j4`.
- Image: `ADS/Debug/ADS.elf`; map: `ADS/Debug/ADS.map`.
- Firmware identity: `0.7.0-downstream-protected`, ADS v1/CRC32.
- Active configuration: `ADS/bench/downstream.operator.h`.

In STM32CubeIDE, use File > Switch Workspace > Other and select
`Trace-X-Workspace` within this checkout. Import General > Existing Projects
into Workspace, select the checkout's `ADS` folder, leave Copy projects into
workspace unchecked, and finish. Select Debug and run Project > Clean once.
Use the Trace-X debug configuration for the freshly built Debug image.
The command-line build compiles only; it never flashes the board.
Keep motor power disconnected while programming.

## Why this baseline

The protected motor workspace and the root ADS tree had identical application
C sources. The workspace selected the existing downstream operator profile;
the root CubeIDE settings still selected the disabled example. The canonical
project now uses the protected workspace's profile in both CubeIDE configurations
and in the Makefile. Only its selector was merged; the application protocol,
pins and diagnostic logic were preserved.

The FinalFirmware copy had a wiring header plus globally changed acceptance
defaults. Its header had an empty relay polarity check and did not establish
GPIO port identity. These differences remain in the recovery archive rather
than being adopted as verified hardware facts. Existing operator attestations
remain in the explicit operator profile; fallback defaults remain disabled.
The project remains motor-enabled through that profile, as the former protected
motor workspace was. It boots stopped and waits for dashboard commands.

The current profile retains 50% PWM, a 30-second maximum, 10–14 V bounds and
an absolute-current trip at 1.5 A, plus relay exclusion, the zero-PWM power check,
local deadline, heartbeat shutdown and emergency stop. Temperature/encoder
quality does not replace electrical protection. No new board tests were performed
by consolidating these files.

## Removed from active folders

FinalFirmware, TRACE-X-Protected-Motor-Workspace, the standalone flash folder
and ZIP, the four previous IDE workspaces, generated firmware builds, seven old
launch shortcuts, and STM32/protected/downstream firmware delivery packages.
The dashboard, database, test recordings, other delivery packages and unrelated
local changes were left in place.

Recovery archive: `firmware-archive/trace-x-before-consolidation-2026-11-16.zip`.
Its embedded SHA256_MANIFEST.json records every archived file. Each archive
entry and each original was checked against the manifest before originals
were removed. `firmware-archive/manifest.json` records the removed paths and
the archive hash. Recovery files are local and ignored by Git. Recover individual
files only when needed; do not import the archived projects alongside ADS.

## Finalization sequence

1. Build the canonical project and confirm its reported firmware identity over
   USB with motor power disconnected.
2. Check live motor/circuit INA219 measurements against reference readings;
   confirm the physical board and Pi are running this same baseline.
3. Verify Stop, emergency stop, heartbeat loss and duration shutdown on the bench.
4. Run a bounded motor test, then validate circuit branch switching and measurements.
5. Save actual results and resolve remaining diagnostic/calibration issues in ADS.

A successful build and host regression suite demonstrate software consistency;
they do not prove physical wiring, sensor accuracy or successful flashing.

## Consolidation verification

A fresh ARM-target Makefile build completed successfully. The image uses
33,528 bytes of text, 92 bytes of initialized data and 19,684 bytes of BSS.
All 228 host regression tests passed (`.venv/bin/python -m unittest discover -s tests`).
The existing optional-sensor regression now tests the single ADS tree; the
build-selector regression and motor harness cover the canonical profile.

Initial consolidated ELF SHA-256:
`67acde1364332344015944b8ede8389e976b32d7dbfd25d4fa493fab03170459`.
Rebuilds after source changes will produce a different hash. No firmware was
flashed and no hardware outputs were operated during this cleanup.
