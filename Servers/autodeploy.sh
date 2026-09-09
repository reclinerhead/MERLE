#!/usr/bin/env bash
# =============================================================================
# MERLE -- Servers/autodeploy.sh
#
# The deploy watcher: a long-lived loop that checks the configured deploy
# branch (MERLE_DEPLOY_BRANCH) every MERLE_DEPLOY_INTERVAL_S and brings this
# box current when it moves. On a change it fast-forwards the checkout,
# restarts the units named in MERLE_DEPLOY_UNITS, and (where
# MERLE_DEPLOY_MCC=1) rebuilds and restarts the dashboard.
#
# This repo is PUBLIC, so origin is a plain https URL and no credential or
# deploy key lives on any box. That is a deliberate difference from the
# private repo this script was written for, where every box authenticated
# its pull with a per-box read-only deploy key. If this repo is ever made
# private, an https remote freezes the watcher SILENTLY -- it keeps polling
# and never reports that it cannot fetch -- so the remote must be switched
# to ssh in the same change.
#
# A LOOP SERVICE, not a systemd timer: a timer firing a oneshot every minute
# writes start and finish journal lines forever, thousands a day saying
# "nothing happened". This loop logs ONLY when it acts or when something
# breaks, so `journalctl -u merle-autodeploy` reads as a deploy history.
#
# Remote-failure posture: deploys touch exactly two things, the checkout and
# `systemctl restart`. Never a database, never an env file (they live outside
# the repo or untracked, so a pull cannot reach them), and never sshd or
# tailscaled (never name them in MERLE_DEPLOY_UNITS). A deploy that breaks a
# service therefore leaves the box reachable and the failure in the journal.
# The restart loop below logs and continues rather than dying with the unit
# it just restarted.
#
# Root/user split: the unit runs as ROOT, because the whole point is
# restarting units without a sudo password, but every git and pnpm step is
# demoted to MERLE_DEPLOY_USER. Root-owned files in the checkout or in
# .next/ would silently break the next manual deploy. Demotion is setpriv,
# NOT runuser or sudo: those open a PAM session per call, and at roughly
# three calls per quiet tick that is thousands of "session opened/closed"
# journal lines a day, which is the same spam disease the loop-not-timer
# choice exists to avoid. setpriv drops uid and gid with no PAM at all, and
# --reset-env gives the demoted step the owner's HOME, so `bash -l` finds
# the right profile and pnpm the right PATH.
#
# Config, all via Environment= lines in the unit:
#   MERLE_DEPLOY_UNITS       space-separated units to restart on any change
#                            to the deploy branch. Empty = restart nothing,
#                            which is the correct setting for a box whose
#                            job is only to keep its checkout current.
#                            NOTE: a later Environment= line REPLACES an
#                            earlier one wholesale rather than appending, so
#                            a drop-in that adds a unit must restate the
#                            full list.
#   MERLE_DEPLOY_MCC         "1" where this box serves the MCC: when the
#                            pulled range touches mcc/, run install, then
#                            build, then restart. A failed build never
#                            restarts, so old code keeps serving.
#   MERLE_DEPLOY_INTERVAL_S  poll cadence, default 60
#   MERLE_DEPLOY_BRANCH      the branch this box deploys from, default main.
#                            The checkout must sit ON the configured branch;
#                            anywhere else reads as pinned and the branch
#                            guard below refuses to move it.
#   MERLE_DEPLOY_USER        checkout owner, default todd
#   MERLE_REPO               checkout path, default /home/todd/MERLE
#
# Manual escape hatches: `systemctl stop <the watcher unit>` pauses it, and
# checking the checkout out to any other branch pins the box until it is put
# back on the deploy branch.
#
# TRAP, learned the hard way: an uncommitted emergency edit in the checkout
# makes `git pull` abort, and when its output is piped the abort is SILENT.
# After any deploy-box pull, verify with `git log -1` rather than trusting
# the absence of an error.
# =============================================================================
set -uo pipefail

REPO="${MERLE_REPO:-/home/todd/MERLE}"
SELF="$REPO/Servers/autodeploy.sh"
UNITS="${MERLE_DEPLOY_UNITS:-}"
DEPLOY_MCC="${MERLE_DEPLOY_MCC:-0}"
INTERVAL="${MERLE_DEPLOY_INTERVAL_S:-60}"
OWNER="${MERLE_DEPLOY_USER:-todd}"
BRANCH="${MERLE_DEPLOY_BRANCH:-main}"

fetch_down=0    # fetch failures are transition-logged, not logged per tick
off_channel=0   # off-branch checkouts too -- one line entering, one leaving
self_changed=0  # set by tick(); the loop hands over to the new copy

log() { echo "[autodeploy] $*"; }

as_owner() {
    setpriv --reuid="$OWNER" --regid="$OWNER" --init-groups --reset-env "$@"
}

repo_git() { as_owner git -C "$REPO" "$@"; }

# One Next app's gated deploy, in order: install, build, restart.
# Build as the owner through a login shell -- pnpm lives on the owner's
# PATH, and a root-owned .next/ would break the next manual deploy. A failed
# build never restarts: old code keeps serving, and the log says fix forward.
deploy_next_app() {
    local dir="$1" unit="$2"
    log "$dir/ changed -- install + build, then restart"
    local build_out
    if build_out=$(as_owner bash -lc \
            "cd '$REPO/$dir' && pnpm install --frozen-lockfile && pnpm build" 2>&1); then
        if systemctl restart "$unit"; then
            log "restarted $unit"
        else
            log "restart FAILED for $unit -- check: systemctl status $unit"
        fi
    else
        log "$dir build FAILED -- old build keeps serving; fix forward and merge again"
        printf '%s\n' "$build_out" | tail -n 30
    fi
}

tick() {
    self_changed=0

    # THE BRANCH GUARD (issue #392): a checkout off the configured deploy
    # branch is a box someone deliberately pinned -- field-testing unmerged
    # work is the sanctioned use. Without this guard the loop below is a
    # disaster there: HEAD never equals the deploy branch's tip, `pull
    # --ff-only` "succeeds" against the checkout's own upstream, and every
    # watched unit restarts every tick, forever. Measured on merle
    # 2026-08-02: fieldmode killed every ~60s, three park recording sessions
    # dead at 6min/0s/60s -- and paused only while the network was down, so
    # recording worked precisely when the internet didn't. Before the fetch
    # on purpose: a pinned box generates no deploy traffic at all. Checking
    # the deploy branch back out resumes deploys by itself. "Pinned" means
    # off the CONFIGURED branch: a station checkout sitting on main is a
    # half-finished channel flip, and it pauses the same way (#354).
    local branch
    branch=$(repo_git rev-parse --abbrev-ref HEAD) || return 0
    if [ "$branch" != "$BRANCH" ]; then
        if [ "$off_channel" -eq 0 ]; then
            off_channel=1
            log "checkout is on '$branch', not $BRANCH -- deploys paused until it returns"
        fi
        return 0
    fi
    if [ "$off_channel" -eq 1 ]; then
        off_channel=0
        log "back on $BRANCH -- deploys resume"
    fi

    if ! repo_git fetch --quiet origin "$BRANCH"; then
        # One line when the fetch starts failing, one when it recovers --
        # never one per quiet minute of an outage.
        if [ "$fetch_down" -eq 0 ]; then
            fetch_down=1
            log "can't fetch origin (network/GitHub down?) -- retrying quietly"
        fi
        return 0
    fi
    if [ "$fetch_down" -eq 1 ]; then
        fetch_down=0
        log "fetch recovered"
    fi

    local head remote
    head=$(repo_git rev-parse HEAD) || return 0
    remote=$(repo_git rev-parse "origin/$BRANCH") || return 0
    [ "$head" = "$remote" ] && return 0   # the quiet path: no news, no log

    # Never act on a checkout someone's mid-something in -- but only TRACKED
    # changes count. Untracked files can't be harmed by a --ff-only pull (git
    # refuses a path collision on its own), and the services' runtime state
    # (journal windows, weather history) lives beside the code as untracked
    # or ignored files -- counting those blocked pearl's deploys forever.
    # Skipping is safe: the tick retries, so cleaning the tree resumes.
    if [ -n "$(repo_git status --porcelain --untracked-files=no)" ]; then
        log "origin/$BRANCH moved to ${remote:0:9} but the checkout is dirty -- not touching it"
        return 0
    fi

    log "deploying ${head:0:9} -> ${remote:0:9} from origin/$BRANCH"
    if ! repo_git pull --ff-only --quiet; then
        log "pull --ff-only refused (diverged history?) -- needs a human"
        return 0
    fi

    local changed
    changed=$(repo_git diff --name-only "$head" "$remote")

    local unit
    for unit in $UNITS; do
        if systemctl restart "$unit"; then
            log "restarted $unit"
        else
            log "restart FAILED for $unit -- check: systemctl status $unit"
        fi
    done

    # The gated expensive path: a docs-only merge never costs a Next build, so
    # the MCC rebuilds only when mcc/ itself changed.
    if [ "$DEPLOY_MCC" = "1" ] && grep -q "^mcc/" <<<"$changed"; then
        deploy_next_app mcc mcc-dashboard
    fi

    # The self-update guard: this script deploys the repo it lives in. The
    # body runs entirely from functions parsed at startup, so the pulled copy
    # can't corrupt this run -- the loop exec's the new file before sleeping.
    if grep -q "^Servers/autodeploy.sh$" <<<"$changed"; then
        self_changed=1
    fi
    log "deploy complete at ${remote:0:9}"
}

main() {
    if [ "${1:-}" = "--once" ]; then
        tick   # a single hand-run tick: desk-testing, no loop, no self-exec
        return
    fi
    # Branch in the startup line so `journalctl -u <watcher> | head` answers
    # "why is this box not deploying" in one read (issue #392).
    log "watching origin/$BRANCH every ${INTERVAL}s -- units: [${UNITS:-none}]" \
        "mcc: $DEPLOY_MCC repo: $REPO" \
        "branch: $(repo_git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
    while true; do
        tick
        if [ "$self_changed" -eq 1 ]; then
            log "autodeploy.sh itself changed -- handing over to the new copy"
            exec "$SELF"
        fi
        sleep "$INTERVAL"
    done
}

main "$@"
