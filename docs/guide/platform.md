# The mission platform (stub)

> Spoke of the [MERLE Technical Guide](../../TechnicalGuide.md). Read the hub
> first for the machine roster, the platform laws, and cross-cutting
> conventions.
>
> **Covers:** the contracts, the supervisor, the recorder and notebook, panel
> types, and skill runtime posture.
> **Runs on:** `robin`.
> **State:** nothing merged yet. Phase 1 is the first code.

Nothing to document yet. The design record is the epic in the issue tracker,
and the per-phase contracts are its sub-issues. As each phase lands, its
section accumulates here.

## Planned sections

**Contracts.** A `contracts/` directory at the repo root holding canonical JSON
Schema documents plus golden example payloads. Both language test suites load
the same examples and validate them against the same schemas, so the examples
are the drift alarm: a schema change that breaks an example turns both suites
red in the same pull request. Four artifacts: the mission manifest, the log
envelope, the system status payload, and the topic grammar.

**Recorder and notebook.** A service subscribing to the mission namespace,
writing runs, observations, verdicts, and debriefs into a database on `robin`.
The notebook is a database rather than a pile of issues, specifically so a
synthesis pass can read it.

**Supervisor.** The only thing that can start a mission. Preflight against live
system state at the instant of arming, refuse with a stated reason, watch during
the run, and hold or abort on a required system flipping no-go. Deterministic
code. The pure core is tested against an injected clock.

**Panels.** Panel types are code: event log, time series, key-value card, video
tile, two-dimensional spatial view, notebook view, and the Go/No-Go Board. Panel
instances are manifest entries. The design reference in
[`docs/design/mcc/`](../design/mcc/) is the visual target and the region-to-type
mapping.

**Skills.** One skill is one service unit in its own virtual environment, on the
host its manifest declares. Systemd owns stopped and running. Inside a running
skill, idle and active are gated behind a control topic. There is deliberately
no third paused state, because deactivate covers it and fewer states means fewer
bugs. Core systems never idle.
