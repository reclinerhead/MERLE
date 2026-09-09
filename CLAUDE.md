# CLAUDE.md

Working agreement for this repository. General workflow conventions (issues as
contracts, feature branches, pull requests, when to write tests) live in the
author's global configuration and are not repeated here. This file carries what
is specific to MERLE.

## Read before writing code

1. [`TechnicalGuide.md`](TechnicalGuide.md), the hub: machine roster, platform
   laws, cross-cutting conventions.
2. The [`docs/guide/`](docs/guide/) spoke for the component you are touching.
3. The issue you are implementing. It is the contract. Its do-not-change list
   and acceptance criteria are load-bearing.

Any pull request that introduces or modifies a feature, integration, data flow,
schema, or architectural decision updates the matching guide spoke in the same
commit set. A pull request that ships code without its guide update is
incomplete.

## The platform laws are not negotiable per pull request

They are listed in the hub. The two that get accidentally violated most easily:

**Gate enforcement is daemon-side.** If you find yourself disabling a button to
prevent an unsafe action, stop. The supervisor refuses the arm. The UI renders
the truth and hosts the button, and it enforces nothing. A disabled button is
theater, because the process that takes the action is the only place a gate can
actually live.

**Panels are config, not code.** Adding a mission must never mean adding a React
component. If a mission needs something the existing panel types cannot express,
the answer is a new panel *type* used by many missions, not a bespoke component
for this one. Writing a per-mission dashboard component is rebuilding the
website, which is the exact failure this platform exists to prevent.

## Repository-specific traps

**The continuous integration test list is manual.** `.github/workflows/tests.yml`
enumerates test files by name. There is no directory walk and no fallback. A
test file that is not listed there never runs, and the job goes green having
tested nothing. Add the file to the list in the pull request that creates it.

**Contracts are the source of truth for two languages.** Python services and
TypeScript panels both consume the schemas in `contracts/`. Both test suites
load the *same* golden example payloads. A schema change that breaks an example
must break both suites in the same pull request. That is the design, not an
inconvenience to work around by regenerating the examples.

**The deploy script is shared and role-neutral.** `Servers/autodeploy.sh` is
configured entirely through environment variables. A box's role is expressed in
its unit file, never by editing the script. Note that a later `Environment=`
line replaces an earlier one wholesale rather than appending, so a drop-in that
adds a unit must restate the full list.

**This repo is public.** Do not commit addresses, MAC addresses, network
reservations, personal names, or anything that identifies a physical location.
Machine hostnames are fine. When a runbook needs private detail, it lives in the
private house repo and the public copy says so.

## House style for public prose

README, guide, and runbook prose avoids em-dashes. Recast with a colon, a comma,
a parenthetical, or a second sentence. En-dash numeric ranges are fine. This
applies to new prose, not to imported design records, which are historical
artifacts and stay as written.

## Avoid the usual generated-code failure modes

**No premature abstraction.** No wrapper components, custom hooks, or utility
functions until there are at least two concrete callers. Inline it at the call
site until duplication justifies extraction.

**No generic AI aesthetics.** The dashboard design reference in
[`docs/design/mcc/`](docs/design/mcc/) is the visual target: near-black ground,
one accent color reserved for alarm and live semantics and never used
decoratively, caps-and-tracking labels, big numerals. No purposeless gradients,
no decorative icons, no card-grid-as-default.

**No hallucinated APIs.** Verify a method exists in the codebase or the current
library documentation before calling it.

**No unsolicited scope.** Implement what the issue says. A worthwhile
improvement noticed during implementation becomes a follow-up issue, not an
extra commit on this branch.
