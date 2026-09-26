"""Pure-part tests for tools/craft_bench.py, per the test contract in #5.

Covers the parsers and arithmetic that serial and sysfs I/O cannot be
unit-tested for, and that are most likely to be silently wrong: the
/proc/net/wireless trailing period and -256 sentinel, the CPU sampler's
first-sample rule, thermal zone preference, meminfo parsing, and the
documented payload shape.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tools"))

import craft_bench


WIRELESS_SAMPLE = """\
Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   46.  -64.  -256        0      0      0      0      0        0
"""

WIRELESS_MEASURED_NOISE = """\
Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   46.  -64.  -95.        0      0      0      0      0        0
"""


class TestWifiRssiParser:
    def test_trailing_period_parses(self):
        assert craft_bench.parse_wifi_rssi(WIRELESS_SAMPLE) == -64

    def test_missing_interface_returns_none(self):
        assert craft_bench.parse_wifi_rssi(WIRELESS_SAMPLE, interface="wlan1") is None

    def test_empty_text_returns_none(self):
        assert craft_bench.parse_wifi_rssi("") is None

    def test_truncated_line_returns_none(self):
        assert craft_bench.parse_wifi_rssi(" wlan0: 0000   46.\n") is None

    def test_garbage_level_returns_none(self):
        line = " wlan0: 0000   46.  xx.  -256        0      0      0      0      0        0\n"
        assert craft_bench.parse_wifi_rssi(line) is None

    def test_failed_read_is_none_not_zero(self):
        # A host without the proc file must yield None, never 0 dBm.
        assert craft_bench.read_wifi_rssi(interface="doesnotexist0") is None

    def test_measured_noise_still_returns_link_level(self):
        assert craft_bench.parse_wifi_rssi(WIRELESS_MEASURED_NOISE) == -64


class TestCpuSampler:
    def test_first_sample_is_none(self):
        reads = iter([(100, 1000), (120, 1100)])
        sampler = craft_bench.CpuSampler(reader=lambda: next(reads))
        assert sampler.sample() is None

    def test_second_sample_is_percentage(self):
        reads = iter([(100, 1000), (150, 1100)])
        sampler = craft_bench.CpuSampler(reader=lambda: next(reads))
        sampler.sample()
        # busy delta 50 of total delta 100 -> 50.0%
        assert sampler.sample() == 50.0

    def test_failed_read_propagates_as_none(self):
        reads = iter([(100, 1000), None, (130, 1050)])
        sampler = craft_bench.CpuSampler(reader=lambda: next(reads))
        assert sampler.sample() is None
        assert sampler.sample() is None
        # After a failed read the next good read has no comparable previous
        # state retained from before the failure is required; it may return
        # a number or None, but never raises.
        result = sampler.sample()
        assert result is None or 0.0 <= result <= 100.0

    def test_zero_total_delta_returns_none(self):
        reads = iter([(100, 1000), (100, 1000)])
        sampler = craft_bench.CpuSampler(reader=lambda: next(reads))
        sampler.sample()
        assert sampler.sample() is None

    def test_parse_proc_stat_first_line(self):
        text = "cpu  100 20 30 800 10 0 0 0 0 0\ncpu0 50 10 15 400 5 0 0 0 0 0\n"
        idle, total = craft_bench.parse_proc_stat(text)
        assert idle == 810
        assert total == 960


class TestThermalZonePreference:
    def test_prefers_named_soc_zone_over_first_zone(self):
        zones = [("xpwm", "45000"), ("cpu-thermal", "50700")]
        assert craft_bench.pick_soc_zone(zones) == ("cpu-thermal", "50700")

    def test_soc_marker_matches(self):
        zones = [("acpitz", "60000"), ("soc_thermal", "55000")]
        assert craft_bench.pick_soc_zone(zones) == ("soc_thermal", "55000")

    def test_package_marker_matches(self):
        zones = [("pch_compet", "30000"), ("package-thermal", "52000")]
        assert craft_bench.pick_soc_zone(zones) == ("package-thermal", "52000")

    def test_falls_back_to_first_zone_when_unnamed(self):
        zones = [("acpitz", "60000")]
        assert craft_bench.pick_soc_zone(zones) == ("acpitz", "60000")

    def test_empty_zones_returns_none(self):
        assert craft_bench.pick_soc_zone([]) is None

    def test_read_cpu_temp_missing_root_returns_none(self):
        assert craft_bench.read_cpu_temp(thermal_root="/nonexistent-zones") is None


class TestMeminfo:
    def test_parse_totals(self):
        text = "MemTotal:       1000000 kB\nMemFree:         200000 kB\nMemAvailable:    400000 kB\n"
        assert craft_bench.parse_meminfo(text) == (1000000 * 1024, 400000 * 1024)

    def test_memfree_fallback(self):
        text = "MemTotal:       1000000 kB\nMemFree:         200000 kB\n"
        assert craft_bench.parse_meminfo(text) == (1000000 * 1024, 200000 * 1024)

    def test_missing_memtotal_returns_none(self):
        assert craft_bench.parse_meminfo("MemFree: 1 kB\n") is None

    def test_zero_total_returns_none(self):
        assert craft_bench.parse_meminfo("MemTotal: 0 kB\nMemFree: 0 kB\n") is None


class TestPayloadMerge:
    def test_documented_shape(self):
        host = {"cpu_pct": 12.4, "ram_pct": 38.1, "temp_c": 47.2,
                "rssi_dbm": -58, "ip": "192.0.2.103"}
        payload = craft_bench.merge_payload("rover", "rover", 1752940000.123, None, host)
        assert set(payload) == {"craft_id", "kind", "ts", "craft", "host"}
        assert payload["craft_id"] == "rover"
        assert payload["kind"] == "rover"
        assert payload["ts"] == 1752940000.123
        assert payload["craft"] is None
        assert payload["host"] == host

    def test_host_submap_keys(self):
        host = craft_bench.collect_host_payload()
        assert set(host) == {"cpu_pct", "ram_pct", "temp_c", "rssi_dbm", "ip"}
