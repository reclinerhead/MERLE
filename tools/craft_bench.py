#!/usr/bin/env python3
"""B0 bench sampler for the Pi-side half of the rover telemetry contract.

Run by hand on merle, per reclinerhead/MERLE#5. This file is deliberately
only the host half: it reads /proc and /sys, never opens a serial port, and
prints one JSON object to stdout. The ESP32 half (T:1001 stream, voltage
scale, the one-wheel command) needs the rover on blocks with ugv.service
stopped, and stays with the bench session.

Conventions inherited from the issue contract:

- Unknown is a first-class output. A failed read yields None, never 0.
- CPU% comes from a two-sample delta sampler, never a blocking read.
- CPU temperature prefers the zone whose type names the SoC instead of
  trusting thermal_zone0; zone order is not stable across kernels.
- RSSI comes from /proc/net/wireless (neither iwconfig nor iw is installed
  on merle). The driver reports "not measured" as -256; that sentinel is
  never surfaced.
- Field names carry explicit units (cpu_pct, ram_pct, temp_c, rssi_dbm).

The payload shape matches the contract in issue #5 so B2 can inherit it:

    {"craft_id": "rover", "kind": "rover", "ts": <epoch float>,
     "craft": null, "host": {"cpu_pct": ..., "ram_pct": ...,
                             "temp_c": ..., "rssi_dbm": ..., "ip": "..."}}

craft is null here because the ESP32 half is not wired yet; that is the
honest value, and the bench session fills it in.
"""

import argparse
import json
import socket
import time
from pathlib import Path

PROC_NET_WIRELESS = "/proc/net/wireless"
THERMAL_ROOT = "/sys/class/thermal"
MEMINFO = "/proc/meminfo"
PROC_STAT = "/proc/stat"

RSSI_NOT_MEASURED = -256

PREFERRED_ZONE_MARKERS = ("cpu", "soc", "package")


# ---------------------------------------------------------------------------
# WiFi RSSI
# ---------------------------------------------------------------------------

def parse_wifi_rssi(text, interface="wlan0"):
    """Return the RSSI in dBm for interface, or None.

    The fields in /proc/net/wireless carry a trailing period ("46.", "-64."),
    so a naive int() raises. The noise column reads -256 when the driver does
    not measure it; this function never returns the noise value, only the
    link level.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(interface + ":"):
            continue
        fields = line.split()
        # fields[0] is "wlan0:", then status, then link, level, noise.
        if len(fields) < 4:
            return None
        try:
            rssi = float(fields[3].rstrip("."))
        except ValueError:
            return None
        return int(rssi)
    return None


def read_wifi_rssi(interface="wlan0"):
    """Read /proc/net/wireless and return RSSI in dBm, or None on any failure."""
    try:
        text = Path(PROC_NET_WIRELESS).read_text()
    except OSError:
        return None
    rssi = parse_wifi_rssi(text, interface=interface)
    if rssi is not None and rssi == RSSI_NOT_MEASURED:
        return None
    return rssi


# ---------------------------------------------------------------------------
# CPU sampler
# ---------------------------------------------------------------------------

def parse_proc_stat(text):
    """Return (idle, total) CPU counters from the first line of /proc/stat."""
    parts = text.splitlines()[0].split()
    values = [int(v) for v in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def read_proc_stat():
    try:
        return parse_proc_stat(Path(PROC_STAT).read_text())
    except (OSError, ValueError, IndexError):
        return None


class CpuSampler:
    """Non-blocking CPU% sampler.

    The first call returns None (there is no interval to measure over yet).
    Every later call returns utilisation since the previous call, as a
    percentage, or None if the underlying read failed. There is no sleep
    anywhere, so it drops into a 10 Hz loop as a plain function call.
    """

    def __init__(self, reader=None):
        self._reader = reader or read_proc_stat
        self._previous = None

    def sample(self):
        current = self._reader()
        if current is None:
            return None
        previous = self._previous
        self._previous = current
        if previous is None:
            return None
        idle_delta = current[0] - previous[0]
        total_delta = current[1] - previous[1]
        if total_delta <= 0:
            return None
        pct = 100.0 * (total_delta - idle_delta) / total_delta
        if pct < 0.0:
            return 0.0
        return pct


# ---------------------------------------------------------------------------
# CPU temperature
# ---------------------------------------------------------------------------

def pick_soc_zone(zones):
    """Return the (type, raw) pair whose type names the SoC, or None.

    zones is an iterable of (type_string, raw_temp_string) pairs. Zone
    ordering is not stable across kernels; on one host thermal_zone0 is the
    WiFi chip. Preferring a type that names cpu/soc/package stops the radio's
    temperature being reported as the SoC's.
    """
    fallback = None
    for zone_type, raw in zones:
        if zone_type and any(marker in zone_type.lower() for marker in PREFERRED_ZONE_MARKERS):
            return zone_type, raw
        if fallback is None:
            fallback = (zone_type, raw)
    return fallback


def read_cpu_temp(thermal_root=THERMAL_ROOT):
    """Return the SoC temperature in degrees Celsius, or None.

    Reads every thermal zone's type and temp, prefers the SoC zone, and
    applies the kernel's millidegree scaling (50700 -> 50.7).
    """
    root = Path(thermal_root)
    try:
        zone_dirs = sorted(root.glob("thermal_zone*"))
    except OSError:
        return None
    zones = []
    for zone_dir in zone_dirs:
        try:
            zone_type = (zone_dir / "type").read_text().strip()
            raw = (zone_dir / "temp").read_text().strip()
        except OSError:
            continue
        zones.append((zone_type, raw))
    picked = pick_soc_zone(zones)
    if picked is None:
        return None
    try:
        return int(picked[1]) / 1000.0
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def parse_meminfo(text):
    """Return (total_bytes, available_bytes) from /proc/meminfo."""
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            values[parts[0].rstrip(":")] = int(parts[1])
    total = values.get("MemTotal")
    available = values.get("MemAvailable", values.get("MemFree"))
    if total is None or available is None or total <= 0:
        return None
    return total * 1024, available * 1024


def read_ram_pct():
    """Return RAM utilisation as a percentage, or None.

    The issue table names psutil, but MemAvailable over MemTotal is the same
    number stdlib-only, and this file adds no dependencies.
    """
    try:
        text = Path(MEMINFO).read_text()
    except OSError:
        return None
    parsed = parse_meminfo(text)
    if parsed is None:
        return None
    total, available = parsed
    return round(100.0 * (total - available) / total, 1)


# ---------------------------------------------------------------------------
# IP
# ---------------------------------------------------------------------------

def read_local_ip():
    """Return the primary outbound IPv4 address, or None.

    A UDP connect to a discard-range address routes the socket without
    sending a packet; getsockname then reports the interface address the
    kernel would use. No external service is contacted.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Payload merge
# ---------------------------------------------------------------------------

def merge_payload(craft_id, kind, ts, craft, host):
    """Merge the craft and host maps into the documented payload shape."""
    return {
        "craft_id": craft_id,
        "kind": kind,
        "ts": ts,
        "craft": craft,
        "host": host,
    }


def collect_host_payload(cpu_sampler=None, interface="wlan0"):
    """Collect the host sub-map exactly as it rides the payload."""
    sampler = cpu_sampler or CpuSampler()
    return {
        "cpu_pct": sampler.sample(),
        "ram_pct": read_ram_pct(),
        "temp_c": read_cpu_temp(),
        "rssi_dbm": read_wifi_rssi(interface),
        "ip": read_local_ip(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sample merle's own OS for the Pi-side bench fields and "
                    "print one JSON payload. Reads no serial port.")
    parser.add_argument("--interface", default="wlan0",
                        help="wireless interface to read RSSI for (default: wlan0)")
    parser.add_argument("--pretty", action="store_true",
                        help="indent the JSON output")
    args = parser.parse_args()

    host = collect_host_payload(interface=args.interface)
    payload = merge_payload(
        craft_id="rover",
        kind="rover",
        ts=time.time(),
        craft=None,
        host=host,
    )
    print(json.dumps(payload, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
