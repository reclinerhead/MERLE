# MERLE

**Mission Engine for Robotics & LLM Experiments.**

A mission-running platform for backyard robotics. Experiments plug in as
*missions* with reusable panels, controls, and services, so adding a new
experiment means writing a manifest and some mission code, never a new website.

This is a learning platform first. The point is robotics experience, captured
rigorously enough that the record itself (intent, runs, verdicts, promotions)
becomes the artifact.

## North star

Define a mission in a manifest. Open the Mission Control Center, see the
Go/No-Go Board light green for every system the mission requires, arm it, and
watch the run stream into reusable panels. When the run ends, Gene files a
debrief with suggestions for the next run. When a mission proves out, promote
it to a *skill*, and the next mission composes it off the message bus without
ever seeing its code. If the internet is unplugged, everything above still
works.

## The shape of it

Three control layers, each assuming the ones above it are lying or broken.

| Layer | Where | Rule |
|---|---|---|
| **Reflexes** | Microcontroller and the robot's own Pi | Local, network-independent, always on. Obstacle stop and the dead-man timeout keep working when everything above them is dead. |
| **Supervisor gate** | A daemon | Refuses to start or continue a mission whose required systems are not go. Deterministic code, with no language model anywhere in the path. |
| **UI** | The browser | Renders the truth and hosts the button. Enforces nothing, because a disabled button is theater. |

Three inference tiers, where the tier something runs on decides what it is
allowed to be responsible for.

| Tier | Hardware | Posture | Responsibility |
|---|---|---|---|
| **1, attention** | Coral Edge TPU | Always on, milliseconds, watts-cheap | Continuous watching, and deciding whether anything is worth a closer look. |
| **2, local heavyweight** | A GPU box | Episodic, activated at arm time, released after | Hard perception and local reasoning. A dropped GPU pauses a mission and does nothing worse. |
| **3, frontier** | Hosted language models | Rare, deliberate, asynchronous | Synthesis, second opinions, and debriefs. |

**Tier 3 law:** no cloud call ever sits between a sensor and an actuator. The
absence, slowness, or cost of a frontier model must never change what the robot
physically does. Cutting the internet cable makes the record poorer and the
robot no less safe.

The symmetry is the point. Three tiers of inference mirror three layers of
control: reflexes that never think, thinkers that never actuate directly, and
consultants that never touch the robot at all.

## Gene

Gene is the mission-control persona, named for Gene Kranz. Under one name are
two components, and the split is load-bearing.

The **supervisor daemon** is deterministic code. It runs the preflight check,
gates the arm, watches systems during a run, and aborts. This is the component
with authority and it contains no language model.

The **debrief voice** is Tier 3. After a run it reads the notebook, the stated
intent, the pre-run predictions, the event log, and the observations, then files
a debrief listing anomalies, cross-run patterns, and suggestions for next time.

**Gene proposes, the human disposes.** Suggestions land in the notebook with a
status of proposed, adopted, or rejected. Adopting one means a human edits the
mission and arms the next run through the same preflight as always. The voice
never writes config, never arms anything, and has no path to an actuator.
Rejected suggestions are kept, because "Gene suggested this, rejected for that
reason" is both a judgment record and a calibration record for how much to trust
the consultant.

## Vocabulary

| Term | Meaning |
|---|---|
| **Mission** | A bounded experiment. Stated intent and measurable success criteria written *before* running, append-only observations during, and a mandatory close-out verdict. Mission code may be scrappy. |
| **Run** | One execution of a mission, with its own run id. Predictions and observations attach to runs. The verdict attaches to the mission. |
| **System** | An always-on capability that missions depend on. Publishes go or no-go on a retained topic with a last will. |
| **Core system** | The safety layer: dead-man, containment, collision avoidance. Built deliberately and first, never produced by a mission, and never idle. |
| **Skill** | A capability *earned* through missions. A service with a contract: stable output topic, documented payload schema, health reporting, and regression fixtures. |
| **Supervisor** | The only thing that can start a mission. |
| **Preflight** | The supervisor evaluating a mission's requirements against live system state at the instant of arming, and refusing with a stated reason on any no-go. |
| **Hold** | A non-terminal safe stop. Motion halts, systems stay up, the run stays open. |
| **Resume** | The exit from a hold, which is a re-arm through the full preflight and never a blind continue. |
| **Promotion** | The refactor that turns a proven mission into a skill. |

Lifecycle, end to end: an idea becomes a mission, runs accumulate evidence, the
mission earns a verdict, a proven mission is promoted to a skill with a
contract, and new missions compose that skill off the bus. The platform converts
experiments into capabilities.

## Status

Early and honest about it. The design is settled, the host is online, and the
code starts now.

| Phase | What | State |
|---|---|---|
| 0 | Host online, on the network and on the message bus | Done |
| 1 | The contracts: manifest schema, log envelope, system status, topic grammar | Next |
| 2 | Recorder and the mission notebook | Planned |
| 3 | The supervisor: preflight, arm, refuse with reason, mid-run watch, abort | Planned |
| 4 | Panel types and manifest-driven composition, Go/No-Go Board first | Planned |
| 5 | Mission Zero, end to end | Planned |
| 6 | Gene's voice: the gateway, the cost ledger, the run debrief | Planned |

The issue tracker holds the epic and the per-phase contracts. Design records
live in [`docs/design/`](docs/design/).

## Repo map

| Path | What |
|---|---|
| [`TechnicalGuide.md`](TechnicalGuide.md) | The living guide. Hub, with spokes under `docs/guide/`. Read the relevant section before starting work. |
| [`docs/design/mcc/`](docs/design/mcc/) | The MCC v2 dashboard design reference: palette, layout, information design, and the mapping from screen regions to panel types. |
| [`docs/design/helm-cockpit-first-draft.md`](docs/design/helm-cockpit-first-draft.md) | The first-draft design record for rover control and the actuator-owning service. |
| [`docs/guide/`](docs/guide/) | Component documentation, one spoke per component. |
| [`Servers/`](Servers/) | Ops runbooks and the deploy watcher. |

## Related

This platform was extracted from a larger private home-automation and wildlife
monitoring project, which remains the home of the house services, the message
broker, and the wildlife detection work. MERLE owns the robotics.

## License

MIT. See [LICENSE](LICENSE).
