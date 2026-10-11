# Servers

This folder holds what the boxes execute from their `~/MERLE/Servers/`
checkout. It stays here because the boxes run it from this path.

- `autodeploy.sh`: the deploy watcher robin and merle run as `merle-autodeploy`.
- `beszel-battery/`: merle only. Bridges the rover's pack voltage from the
  vendor app's feed to the Beszel health agent as a Linux battery. See
  [`docs/guide/beszel-battery.md`](../docs/guide/beszel-battery.md).

The per-host runbooks (`servers/Robin.md`, `servers/Merle.md`) live in the
private infrastructure repo, `reclinerhead/toddtech-infrastructure`, which is
the single source of truth for every box. Read the relevant runbook there
before touching a machine.
