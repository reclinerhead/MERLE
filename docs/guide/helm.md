# The Helm, rover control (stub)

> Spoke of the [MERLE Technical Guide](../../TechnicalGuide.md). Read the hub
> first for the machine roster, the platform laws, and cross-cutting
> conventions.
>
> **Covers:** the rover cockpit and the service that owns the robot's hardware.
> **Runs on:** `merle` for the hardware service, `robin` for the cockpit.
> **State:** nothing merged yet.

Nothing to document yet. The design record is the epic in the issue tracker and
the [first-draft design document](../design/helm-cockpit-first-draft.md). The
hardware this service will own (the driver board's serial protocol, which
fields it streams, what the Pi can measure about itself, and the vendor stack
it replaces) is recorded in `toddtech-infrastructure/servers/Merle.md` (private).

## The two hard constraints, before anyone touches the rover

**The hardware service replaces the vendor stack rather than joining it.** The
vendor's application continuously reads the robot's serial port and holds the
camera and the lidar exclusively. Two processes reading one serial port split the bytes
between them, and no streaming server can open a camera that another process
already owns. So bringing up our own service is a cutover, and at cutover the
vendor's web interface dies. That interface is currently the only way to drive
the robot. Reaching parity before the switch is a sequencing requirement, not a
preference.

**The dead-man timeout ships before any drive API does.** It is a property of
the hardware service, not of the cockpit, so a crashed browser, a dropped
socket, a killed tab, and a network blip are all identical and all mean stop.
Nothing in the cockpit track starts until the timeout is proven with the robot
up on blocks and its wheels spinning: kill the client, kill it harder, pull the
wireless, and suspend the driving machine. All four stop the robot. A cockpit
that can start a robot it cannot reliably stop is the one outcome this work must
not produce.

## Naming

The actuator-owning service still needs its final name. It is the slot where an
actuator arbiter inserts later without rewriting any mission, and it is the only
thing mission code is allowed to talk to when it wants the robot to move.

## The B0 host sampler (`tools/craft_bench.py`)

The Pi-side half of the bench contract from [#5](https://github.com/reclinerhead/MERLE/issues/5)
lives in `tools/craft_bench.py`. It reads `/proc` and `/sys` only, opens no
serial port, and prints one JSON payload whose `host` sub-map matches the
contract shape (`cpu_pct`, `ram_pct`, `temp_c`, `rssi_dbm`, `ip`) with
explicit units in field names. The ESP32 half (the `T:1001` stream, the
voltage scale, the one-wheel command) is not implemented yet and waits for
the bench session with the rover on blocks.

Conventions the sampler fixes, which B2 inherits:

- **RSSI comes from `/proc/net/wireless`.** Neither `iwconfig` nor `iw` is
  installed on merle, and installing either to read one number is a
  dependency the epic does not need. The parser handles the trailing period
  in the fields and drops the driver's `-256` "not measured" noise sentinel.
- **Unknown is `None`, never `0`.** A failed RSSI or temperature read yields
  `None`; a percentage of `0` would read as a catastrophic value rather than
  as "we did not ask successfully". Downstream panels render `None` as an
  em-dash placeholder, not as zero.
- **CPU% is a two-sample delta sampler** (`CpuSampler`): the first call
  returns `None`, later calls return utilisation since the previous call.
  No sleep anywhere, so it drops into a 10 Hz loop as a plain function call.
  This replaces the vendor `psutil.cpu_percent(interval=2)` blocking read.
- **CPU temperature prefers the zone whose `type` names the SoC** (`cpu`,
  `soc`, `package` markers) instead of trusting `thermal_zone0`; zone order
  is not stable across kernels. Raw millidegrees are scaled by 1000.
- **RAM% is `MemAvailable` over `MemTotal`** from `/proc/meminfo`, which is
  the number the issue's psutil row wants, stdlib-only.

The pure parts are covered by `test_craft_bench.py` (repo root) and enrolled
in `.github/workflows/tests.yml`. Run the script by hand: `python3
tools/craft_bench.py --pretty`.
