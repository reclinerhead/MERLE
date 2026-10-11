"""Pure-logic tests for the Beszel battery bridge: the voltage-to-percent curve, the
status rule with its hysteresis, and the combined readout. The feed and the sysfs
writer are I/O and are proven on the box."""

import beszel_battery as b

FULL = 1215  # the default anchor: what the board reads with the pack full on the charger


def test_default_full_anchor_is_the_boards_on_charger_reading():
    assert b.DEFAULT_FULL_CV == FULL
    assert b.percent_from_centivolts(1220) == 100  # 12.20 V, weeks on the charger
    assert b.percent_from_centivolts(1225) == 100


def test_lower_anchors_match_the_runbook_checklist():
    assert b.percent_from_centivolts(1110) == 50  # 11.1 V about half
    assert b.percent_from_centivolts(1050) == 20  # 10.5 V start wrapping up
    assert b.percent_from_centivolts(1020) == 10  # 10.2 V head home
    assert b.percent_from_centivolts(960) == 0


def test_between_anchors_is_a_straight_line():
    mid = (1110 + FULL) // 2  # midway 11.1 V .. full -> midway 50 .. 100
    assert b.percent_from_centivolts(mid) in (74, 75)
    assert b.percent_from_centivolts(1035) == 15  # midway 10.2..10.5 -> midway 10..20
    assert b.percent_from_centivolts(1111) == 50  # rounds, never jitters a point per centivolt


def test_full_anchor_is_configurable():
    assert b.percent_from_centivolts(1260, full_cv=1260) == 100
    assert b.percent_from_centivolts(1220, full_cv=1260) < 100
    assert b.status_from(1220, None, full_cv=1260) == "Discharging"


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


def test_status_full_at_and_above_the_anchor():
    assert b.status_from(FULL, None) == "Full"
    assert b.status_from(1225, 1150) == "Full"  # rising, but Full wins


def test_status_full_has_hysteresis():
    assert b.status_from(FULL - 1, None, was_full=False) == "Discharging"
    assert b.status_from(FULL - 1, None, was_full=True) == "Full"  # a floating pack does not flicker
    assert b.status_from(FULL - b.FULL_HYSTERESIS_CV, None, was_full=True) == "Full"
    assert b.status_from(FULL - b.FULL_HYSTERESIS_CV - 1, None, was_full=True) == "Discharging"


def test_status_charging_needs_a_real_rise():
    assert b.status_from(1150, 1145) == "Charging"  # +0.05 V over a minute
    assert b.status_from(1150, 1147) == "Discharging"  # +0.03 V is noise
    assert b.status_from(1150, 1160) == "Discharging"


def test_status_without_history_is_discharging():
    assert b.status_from(1150, None) == "Discharging"


def test_readout_full_always_means_100():
    assert b.readout(1220, None) == ("Full", 100)
    assert b.readout(FULL - 5, None, was_full=True) == ("Full", 100)  # held by hysteresis
    assert b.readout(FULL - 5, None, was_full=False) == ("Discharging", b.percent_from_centivolts(FULL - 5))
    assert b.readout(1150, 1140) == ("Charging", b.percent_from_centivolts(1150))
