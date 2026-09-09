# MERLE Technical Guide

The living documentation of how MERLE is built and why. It describes current
state. Chronology lives in `git log` and pull request descriptions, not here.

**Read the relevant section before starting work.** That is a standing
precondition, whether or not the task mentions it. Any change that introduces
or modifies a feature, integration, data flow, schema, or architectural
decision updates the matching section in the same commit set.

This guide is a **hub with spokes**. The hub carries the machine roster, the
cross-cutting conventions, and the map. Each component gets one spoke under
[`docs/guide/`](docs/guide/). Read the hub, then the spoke you are touching,
and update the spoke your change lands in.

## Project context

A mission-running platform for backyard robotics, built as a learning vehicle.
Missions are bounded experiments with stated intent, measurable success
criteria, and a mandatory verdict. Proven missions are promoted to skills that
later missions compose off the message bus. See [`README.md`](README.md) for the
north star, the vocabulary, and the platform laws.

MERLE was extracted from a larger private home-automation and wildlife
monitoring project. That project keeps the house services, the message broker,
the wildlife detection stack, and the production dashboard that MERLE's MCC v2
eventually succeeds. MERLE owns the robotics.

## Platform laws

These are settled and are not relitigated per pull request. A change that
appears to require breaking one is a design conversation, not an
implementation detail.

1. **Gate enforcement is daemon-side.** The supervisor refuses the arm. A
   disabled button is theater.
2. **No language model in a control loop.** Tier 3 absence, slowness, or cost
   must never change what the robot physically does.
3. **Panels are config, not code.** Panel *types* are code. Panel *instances*
   are manifest entries. A bespoke component per mission is the failure this
   platform exists to prevent.
4. **Missions never touch hardware directly.** Mission code is a client of the
   service that owns an actuator, never of the serial port.
5. **Core systems are never produced by missions.** Safety is built
   deliberately, not experimented into existence.
6. **Unknown is a first-class output.** Contracts preserve uncertainty rather
   than guessing. Downstream consumers can trust a stream precisely because it
   admits ignorance.
7. **Gene proposes, the human disposes.** The debrief voice has no path to an
   actuator and no ability to write config.

## Machine roster

| Host | Role | Runbook |
|---|---|---|
| `robin` | MCC v2 host and robotics lab. Supervisor, recorder, notebook, Tier 3 gateway, Tier 1 Coral inference | [`Servers/Robin.md`](Servers/Robin.md) |
| `merle` | The rover. Tier 0 reflexes, rover-local skills, the actuator-owning service | Private house repo |
| `bluejay` | Tier 2. GPU skills and local language models | Private house repo |

The message broker, DNS, the NVR, and the household services live on other
boxes documented in the private house repo. MERLE reaches the broker by name
and depends on nothing else from that side.

## Cross-cutting conventions

**The message bus is the integration surface.** Everything meets on MQTT and
tolerates everything else being absent. The broker address comes from the
`MERLE_MQTT` environment variable, which is required and has no default, so a
misconfigured service fails loudly at startup rather than silently connecting
somewhere unintended.

**Status topics are retained and carry a last will.** Every system publishes
`system/<id>/status`, retained so late subscribers get current state instantly,
with a broker-published last will so an uncleanly dead service flips itself to
no-go. Silence becomes a signal instead of an ambiguity.

**Refusals state their reason and never flip state.** A refused arm publishes
why it refused, and the UI snaps back rather than optimistically showing a state
the system did not enter.

**Deploys are pull-based.** Each box runs `Servers/autodeploy.sh` as
`merle-autodeploy`, polling origin/main and bringing itself current. A box's
role is expressed entirely through environment variables. The script is never
edited per box.

**Tests are selective.** Pure logic with non-obvious behavior gets covered:
ranking, thresholds, fusion, parsing, normalization, timeout arithmetic against
an injected clock. Input and output bound code does not. The continuous
integration workflow enumerates test files **by hand**, so a test file that is
not named there silently never runs. Add new files to the list in the same pull
request that creates them.

**No layout shift.** Empty and error states reserve the same space as populated
ones. A reason line is rendered under every status block so a go to no-go flip
moves nothing on screen.

## Component spokes

| Spoke | Covers |
|---|---|
| [`docs/guide/platform.md`](docs/guide/platform.md) | Contracts, supervisor, recorder, notebook, panels |
| [`docs/guide/helm.md`](docs/guide/helm.md) | Rover control and the actuator-owning service |

## Design records

| Document | What |
|---|---|
| [`docs/design/mcc/`](docs/design/mcc/) | The MCC v2 dashboard design reference. Palette, layout, information design, and the mapping from screen regions to panel types |
| [`docs/design/helm-cockpit-first-draft.md`](docs/design/helm-cockpit-first-draft.md) | First-draft design record for rover control, superseded in places by the issue tracker |

Design records are historical artifacts, captured at a moment. This guide is
the current state. Where the two disagree, the guide wins, and where the guide
and an issue disagree, surface the conflict rather than silently picking one.
