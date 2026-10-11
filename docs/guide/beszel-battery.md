# The battery bridge (merle)

The house health dashboard (Beszel, run from the private infrastructure repo)
shows a battery column, but its Linux agent only reads batteries from
`/sys/class/power_supply`, which a Raspberry Pi leaves empty. The rover's pack
voltage exists on the box already: the driver board streams it over serial,
and the vendor app that owns that port republishes it on its Socket.IO feed.
`Servers/beszel-battery/` carries it the last step. Nothing here touches the
serial port, the vendor code, or the kernel.

## Shape

Two units, installed from the checkout by `install.sh`:

- **`sys-class-power_supply.mount`** lays a 1 MB tmpfs over
  `/sys/class/power_supply`. The Pi has no power-supply devices, so the mount
  hides an empty directory and nothing else. Its `ConditionDirectoryNotEmpty=!`
  guard makes that permanent: if a real battery or charger ever shows up, the
  mount stands down and the service below, which `Requires` it, stays stopped.
- **`beszel-battery.service`** runs `beszel_battery.py` on system Python with
  Debian's `python3-socketio`. It subscribes to the vendor app's `/ctrl`
  namespace on loopback and reads feedback key `112`, the pack voltage in
  centivolts (the vendor's own page divides by 100). Every 5 s it rewrites
  `BAT0/capacity`, `status`, and `voltage_now`, each write a rename so a reader
  never sees a half-written value. When no reading has arrived for 30 s it
  withdraws `BAT0` entirely: the dashboard then shows nothing, which is the
  truth, rather than the last number before the rover went dark.

Beszel's agent re-enumerates `power_supply` on every stats cycle, so the
battery appears and disappears without touching the agent.

## The percent scale is a readout, not a measurement

The lower anchors come from the field checklist in the private merle runbook
(11.1 V about half, 10.5 V start wrapping up, 10.2 V head home, 9.6 V as
zero), read off this same board on real outings, with straight lines between
the points. The top anchor is **what the board reports with the pack full and
sitting on the charger: 12.20 to 12.25 V**, observed after weeks on the
charger, not the textbook 12.6 V. Whether the board reads a few tenths low or
the pack floats there, the readout is calibrated to the number the board
produces; the default is 12.15 V (`MERLE_BATTERY_FULL_CV=1215`) and a
multimeter against the pack is still the way to settle which it is.

`status` is `Full` at the anchor and above, held with 0.15 V of hysteresis
so a floating pack does not flicker, and `Full` always reads 100. The board
exposes no charger flag, so a charge in progress is inferred: `Charging` on a
0.05 V rise against a minute earlier, otherwise `Discharging`. A pack that
is on the charger but already full therefore reads `Full`, not `Charging`,
which is the truth.

These are cell-chemistry rules of thumb for a pack whose discharge curve
under load has not been measured. The bridge gives the readout and the
history; **no Beszel battery alert is enabled for merle** until a measured
curve replaces the checklist. An invented threshold is an alarm you learn to
ignore.

## Verify

```
systemctl is-active sys-class-power_supply.mount beszel-battery   # active, active
cat /sys/class/power_supply/BAT0/capacity /sys/class/power_supply/BAT0/status
journalctl -u beszel-battery -n 5 --no-pager                      # subscribe, show, withdraw: one line each
```

Stopping `ugv.service` for 40 s should make `BAT0` vanish and the dashboard
cell go blank; starting it brings both back.

## Tests

`test_beszel_battery.py` covers the two pure functions: the voltage-to-percent
curve (anchors, interpolation, rounding, clamping, monotonic across the range)
and the status rule. It is enrolled by name in `.github/workflows/tests.yml`.
The feed and the sysfs writer are I/O and are proven on the box.
