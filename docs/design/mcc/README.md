# MCC v2 dashboard — design reference

`rover-mission-control-mockup.standalone.html` is a Claude Design export (2026-08-28) of a mission-control dashboard concept for the Mission Platform (epic #485). Open it in any browser — it is fully self-contained (the runtime unpacks itself; the React inside is Claude Design's canvas runtime, not app code).

**This is a design reference, not a code foundation.** The dashboard is one static HTML/CSS artboard with hand-plotted SVG data: no state, no timers, every number hardcoded. Its value is the layout system, the palette, and the information design. When Phase 4 (panels) is built, the panel components should reproduce this look, driven by manifest declarations and live bus data — do not lift the markup.

## Design language (treat as rules when building Phase 4)

- **Palette:** near-black ground `#201e1d`, panel fill `#2d2b2b`, off-white ink `#f3f2f2`/`#d7d3d3`, muted labels `#9b9797`. **One accent: `#ec3013`, reserved for alarm / live / abort semantics — never decorative.** The single-accent discipline is what makes the screen readable at a glance. Deep-alarm variant `#ae1800`, tint `#fff2ef`.
- **Type:** Archivo (woff2s embedded in the export), caps-and-tracking for labels, big numerals for readings.
- **Honesty idioms rendered as UI:** every GO block carries a confirmed-at timestamp (must be bus-truth time, not render time); a NO GO block states its reason ("GUST 14.2 m/s > LIMIT 12.0") and its HELD timestamp; the reason line reserves space under every block so a GO→NO GO flip causes zero layout shift.
- **Degraded-but-go:** "1 CAM DEGRADED" under a green perception block — degradation is displayed without flipping the gate. Cousin of the unknown-is-first-class law.
- **Flight-controller callsigns** (EECOM, SENSE, SAFETY, WX) as display groupings on the Go/No-Go Board. Groupings only — the board renders whatever the mission's `requires:` list declares.

## Region → #485 panel-type mapping

The mock decomposes cleanly into the epic's locked panel taxonomy, which is the main evidence it fits the platform:

| Mock region | Panel type | Data source |
|---|---|---|
| Left GO/NO-GO column | Go/No-Go Board | `system/<id>/status` retained+LWT (Phase 1 contract, Phase 3 supervisor) |
| Consumables bars | Key-value card | Rover base telemetry (voltage today; SOC/watts derived) |
| Geofence + waypoint map | 2D spatial view | Localization — a skill to be earned; earliest runs get cruder position |
| Speed / cross-track / gust strips | Time-series (with limit lines) | Rover telemetry; Ecowitt GW2000B for wind/lux/rain; cross-track needs localization |
| Onboard cam + SEC-2 overhead | Video tile ×2 | Merle cam stream; Amcrest/Frigate restream for overhead containment view |
| Lidar LD19 polar panel | 2D spatial (polar) | LD19 on Merle (10 Hz / 4500 pts/s / 12 m — real spec) |
| Task success table | Notebook view | `missions.db` runs/trials (Phase 2 recorder) |
| Event & anomaly log | Event log | `mission/<id>/log/#` envelope (Phase 1) |
| ABORT TO SAFE HOLD / RE-POLL | Supervisor commands | UI hosts the button, enforces nothing (platform law) |

## Known deltas from the platform design

- No mission identity on screen (name, `run_id`, phase, verdict) — this is the *during-a-run* view only; MCC v2 wraps it in the manifest → preflight → arm → run → debrief lifecycle. The arm/preflight interaction has no UI here yet.
- No Gene surface (debrief/commentary panel).
- Some instrumentation is aspirational set-dressing (4/4 e-stops, stereo cam, pan/tilt, battery pack B, 240×110 m geofence). Merle has one cam, one lidar, one battery.
- "ABORT TO SAFE HOLD" prompted the **Hold/Resume** vocabulary added to #485 on 2026-08-28: hold = non-terminal safe stop (run stays open), resume = re-arm through full preflight.

## How to use this artifact

1. **Phase 1 (contracts):** walk every datum on the screen and ask "which topic and field feeds this?" Anything unanswerable either earns a field in the manifest/status/log schemas or is consciously cut.
2. **Phase 4 (panels):** visual north star. Build the panel *types* to this look; this exact screen then becomes one mission's panel config in a manifest.
