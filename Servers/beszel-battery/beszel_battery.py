#!/usr/bin/env python3
"""Report the rover's pack voltage to the Beszel agent as a Linux battery.

The Waveshare driver board streams the pack voltage over serial, and the vendor
app (ugv.service), which owns that port, republishes it on its Socket.IO feed as
feedback key 112, in centivolts. Beszel's agent reads batteries from
/sys/class/power_supply, which is empty on a Raspberry Pi. This service bridges
the two: it subscribes to the vendor feed and keeps BAT0/capacity and
BAT0/status current under the tmpfs that sys-class-power_supply.mount lays
over that directory. When the feed goes quiet (vendor app down, rover off) it
withdraws BAT0 so the dashboard shows nothing rather than a stale number.

The percent scale is the field checklist in the merle runbook (12.6 V full,
11.1 V about half, 10.5 V start wrapping up, 10.2 V head home), joined by
straight lines. It is a readout, not a measured discharge curve: do not build
an alarm on it.

Configuration, all optional, from the environment:
  MERLE_UGV_URL           vendor app base URL         default http://127.0.0.1:5000
  MERLE_UGV_VOLTAGE_KEY   feedback key for voltage    default 112
  MERLE_BATTERY_DIR       the fake battery directory  default /sys/class/power_supply/BAT0
  MERLE_BATTERY_STALE_S   seconds without a reading before BAT0 is withdrawn, default 30
  MERLE_BATTERY_FULL_CV   the board's reading, in centivolts, that means full, default 1215
"""

import collections
import logging
import os
import signal
import time

# centivolts -> percent. The lower anchors are the runbook's field checklist, read off
# this same board on real outings. The top anchor is what the board reports with the
# pack full and sitting on the charger (12.20 to 12.25 V, observed 2026-10-11 after
# weeks on the charger), not the textbook 12.6 V. Whether the board reads low or the
# pack floats there, the readout has to be calibrated to the number the board produces.
CHECKLIST = ((960, 0), (1020, 10), (1050, 20), (1110, 50))
DEFAULT_FULL_CV = int(os.environ.get("MERLE_BATTERY_FULL_CV", "1215"))
FULL_HYSTERESIS_CV = 15  # once Full, stay Full until the reading falls 0.15 V below the anchor
RISE_CV = 5  # a 0.05 V rise against a minute ago reads as charging


def percent_from_centivolts(cv, full_cv=None):
    """Map pack voltage in centivolts to 0..100 along the checklist, clamped at both ends."""
    full_cv = DEFAULT_FULL_CV if full_cv is None else full_cv
    curve = CHECKLIST + ((full_cv, 100),)
    if cv <= curve[0][0]:
        return 0
    if cv >= curve[-1][0]:
        return 100
    for (lo_cv, lo_pct), (hi_cv, hi_pct) in zip(curve, curve[1:]):
        if lo_cv <= cv <= hi_cv:
            return round(lo_pct + (hi_pct - lo_pct) * (cv - lo_cv) / (hi_cv - lo_cv))
    return 0


def status_from(cv, cv_a_minute_ago, was_full=False, full_cv=None):
    """One of the sysfs status strings Beszel understands: Full, Charging, Discharging.

    The board exposes no charger flag, so Full is inferred from voltage, with hysteresis
    so a pack floating at the anchor does not flicker between Full and Discharging."""
    full_cv = DEFAULT_FULL_CV if full_cv is None else full_cv
    if cv >= full_cv or (was_full and cv >= full_cv - FULL_HYSTERESIS_CV):
        return "Full"
    if cv_a_minute_ago is not None and cv - cv_a_minute_ago >= RISE_CV:
        return "Charging"
    return "Discharging"


def readout(cv, cv_a_minute_ago, was_full=False, full_cv=None):
    """(status, percent) for one reading. Full always means 100."""
    status = status_from(cv, cv_a_minute_ago, was_full, full_cv)
    percent = 100 if status == "Full" else percent_from_centivolts(cv, full_cv)
    return status, percent


def write_battery(bat_dir, cv, status, percent):
    """Lay down the files Beszel's Linux reader looks for. Each write is a rename, so a
    reader never sees a half-written value."""
    os.makedirs(bat_dir, exist_ok=True)
    values = {
        "type": "Battery",
        "present": "1",
        "model_name": "UGV pack",
        "status": status,
        "capacity": str(percent),
        "voltage_now": str(cv * 10000),  # sysfs convention is microvolts
    }
    for name, value in values.items():
        tmp = os.path.join(bat_dir, "." + name)
        with open(tmp, "w") as f:
            f.write(value + "\n")
        os.replace(tmp, os.path.join(bat_dir, name))


def withdraw_battery(bat_dir):
    """Remove BAT0 entirely. No battery is better than a stale one."""
    if not os.path.isdir(bat_dir):
        return
    for name in os.listdir(bat_dir):
        os.unlink(os.path.join(bat_dir, name))
    os.rmdir(bat_dir)


def main():
    import socketio  # lazy: the functions above import without it (tests, CI)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("beszel-battery")

    url = os.environ.get("MERLE_UGV_URL", "http://127.0.0.1:5000")
    key = os.environ.get("MERLE_UGV_VOLTAGE_KEY", "112")
    bat_dir = os.environ.get("MERLE_BATTERY_DIR", "/sys/class/power_supply/BAT0")
    stale_s = float(os.environ.get("MERLE_BATTERY_STALE_S", "30"))

    latest = {"t": 0.0, "cv": None}
    history = collections.deque()  # (monotonic time, cv) over the last ~90 s, one per cycle

    sio = socketio.Client(reconnection=True, reconnection_delay=5, reconnection_delay_max=30)

    @sio.on("update", namespace="/ctrl")
    def on_update(data):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            latest["t"] = time.monotonic()
            latest["cv"] = int(v)

    stopping = {"now": False}

    def stop(*_):
        stopping["now"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    shown = False
    was_full = False
    unavailable_logged = False  # one line per outage, not one per retry
    while not stopping["now"]:
        if not sio.connected:
            try:
                sio.connect(url, namespaces=["/ctrl"], transports=["polling"])
                log.info("subscribed to the vendor feed at %s", url)
                unavailable_logged = False
            except Exception as e:  # noqa: BLE001 - any failure here just means "try again later"
                if not unavailable_logged:
                    log.warning("vendor feed unavailable at %s (%s); retrying every 5 s", url, type(e).__name__)
                    unavailable_logged = True

        now = time.monotonic()
        if latest["cv"] is not None and now - latest["t"] <= stale_s:
            history.append((now, latest["cv"]))
            while history and now - history[0][0] > 90:
                history.popleft()
            minute_ago = next((cv for t, cv in history if now - t >= 55), None)
            status, percent = readout(latest["cv"], minute_ago, was_full)
            was_full = status == "Full"
            write_battery(bat_dir, latest["cv"], status, percent)
            if not shown:
                log.info("battery shown: %.2f V, %s, %d%%", latest["cv"] / 100, status, percent)
                shown = True
        elif shown or os.path.isdir(bat_dir):
            withdraw_battery(bat_dir)
            history.clear()
            was_full = False
            log.info("no reading for %.0f s, battery withdrawn", stale_s)
            shown = False

        for _ in range(50):  # a 5 s cycle that still notices SIGTERM promptly
            if stopping["now"]:
                break
            time.sleep(0.1)

    withdraw_battery(bat_dir)
    if sio.connected:
        sio.disconnect()
    log.info("stopped, battery withdrawn")


if __name__ == "__main__":
    main()
