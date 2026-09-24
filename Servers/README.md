# Servers

This folder holds the deploy watcher (`autodeploy.sh`) that robin and merle
run from their `~/MERLE/Servers/` checkout. It stays here because the boxes
execute it from this path.

The per-host runbooks (`servers/Robin.md`, `servers/Merle.md`) live in the
private infrastructure repo, `reclinerhead/toddtech-infrastructure`, which is
the single source of truth for every box. Read the relevant runbook there
before touching a machine.