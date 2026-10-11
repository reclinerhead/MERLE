"""Pure-logic tests for the Beszel battery bridge: the voltage-to-percent curve and
the status rule. The feed and the sysfs writer are I/O and are proven on the box."""

import beszel_battery as b


def test_anchor_points_match_the_runbook_checklist():
    assert b.percent_from_centivolts(1260) == 100  # 12.6 V full
    assert b.percent_from_centivolts(1110) == 50  # 11.1 V about half
    assert b.percent_from_centivolts(1050) == 20  # 10.5 V start wrapping up
    assert b.percent_from_centivolts(1020) == 10  # 10.2 V head home
    assert b.percent_from_centivolts(960) == 0


def test_between_anchors_is_a_straight_line():
    assert b.percent_from_centivolts(1185) == 75  # midway 11.1..12.6 -> midway 50..100
    assert b.percent_from_centivolts(1035) == 15  # midway 10.2..10.5 -> midway 10..20
    assert b.percent_from_centivolts(1111) == 50  # rounds, never jitters a point per centivolt


def test_clamps_outside_the_curve():
    assert b.percent_from_centivolts(1300) == 100
    assert b.percent_from_centivolts(900) == 0
    assert b.percent_from_centivolts(0) == 0


def test_percent_is_monotonic_across_the_whole_range():
    last = -1
    for cv in range(900, 1300):
        pct = b.percent_from_centivolts(cv)
        assert 0 <= pct <= 100
        assert pct >= last
        last = pct


def test_status_full_wins_over_everything():
    assert b.status_from(1250, None) == "Full"
    assert b.status_from(1262, 1200) == "Full"


def test_status_charging_needs_a_real_rise():
    assert b.status_from(1150, 1145) == "Charging"  # +0.05 V over a minute
    assert b.status_from(1150, 1147) == "Discharging"  # +0.03 V is noise
    assert b.status_from(1150, 1160) == "Discharging"


def test_status_without_history_is_discharging():
    assert b.status_from(1150, None) == "Discharging"
