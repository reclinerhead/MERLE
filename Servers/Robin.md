# Robin

Lenovo ThinkCentre M920x Tiny. Intel Core i5-8500 (6C/6T @ 3.00 GHz), 32 GB
RAM. System disk is a Samsung SSD 840 EVO (931.5 G, SATA, enumerates as
`sda`). Ubuntu Server 26.04 LTS. Hardwired on `eno1`.

| | |
|--|--|
| **Hostname** | `robin` |
| **User** | `todd` |
| **Role** | Dedicated **MCC v2** host and **robotics lab**: missions, experiments, and Coral edge inference |
| **State** | Phase 0 complete. OpenSSH, Tailscale, repo checkout, deploy watcher. Coral A+E seated, gasket/apex live (`/dev/apex_0`). No mission services yet. |

**Why the name:** Robin, the yard bird that shows up while you are working. It
fits the experiments box: not the production house stack, and not the NVR.

BIOS **M1UKT79A**, the flash family that ended this hardware's idle self-reset
errata. Timezone `America/Detroit`, NTP synchronized.

> Addresses, MAC addresses, and the network reservation for this box live in
> the private house repo's copy of this runbook. This public copy is
> deliberately address-free. Reach the box by name.

---

## What runs here today

| Service | Notes |
| ------- | ----- |
| OpenSSH | Desk access. Password authentication is off; per-device ed25519 keys only |
| Tailscale | Joined, untagged, key expiry disabled in the admin console |
| gasket/apex (DKMS) | Coral A+E driver, `/dev/apex_0`. See § Coral below |
| Deploys | `merle-autodeploy`, polling origin/main. See § The deploy watcher |
| CPU governor | `cpu-performance.service`, `performance` rather than `powersave` |

Expected listeners: **22** (ssh). Nothing else is a product door yet.

---

## Names and how to reach it

Prefer the LAN name in anything written down:

```
ssh todd@robin.lan          # local DNS
ssh todd@robin              # MagicDNS, tailnet; only reliable when Tailscale is fully up
```

Bare `robin` is not a short name for the LAN address. On desk machines running
Tailscale DNS, a bare hostname usually resolves to the **tailnet** address.
When Tailscale is logged out or half-joined, bare `robin` times out while
`robin.lan` still works. Write `.lan`.

---

## Storage

The installer used the full 840 EVO:

```
/dev/mapper/ubuntu--vg-ubuntu--lv  ~914G usable on the 931.5G Samsung 840 EVO (sda)
/dev/sda2                          2.0G  /boot
/dev/sda1                          1.1G  /boot/efi
```

No extra data drive. Scratch space goes on this disk, never `/tmp`, which is
tmpfs here.

---

## Repo checkout

This repo is public, so the checkout is plain https and needs no deploy key:

```
https://github.com/reclinerhead/MERLE.git
```

Checkout path:

```
/home/todd/MERLE
```

Robin also carries a checkout of the private house repo from its Phase 0
bring-up. That checkout predates this repo and its watcher deploys nothing.
Retiring it is a cleanup task, not a blocker.

---

## Phase 0 record

Done, in order:

- BIOS: restore-AC-after-power-loss, turbo on, secure boot off, **M1UKT79A**.
- Ubuntu Server 26.04 LTS (full, not minimized), hostname `robin`, user `todd`.
- Timezone `America/Detroit`, NTP synchronized. The installer defaults to
  `Etc/UTC` and nothing downstream ever fixes it. Set it at install.
- Root logical volume extended to the whole disk. The installer leaves most of
  the volume group unallocated on this hardware:
  `sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv`.
- Per-device ed25519 keys in `~/.ssh/authorized_keys`, one per machine plus an
  offline recovery key. Keys are generated on the machine that uses them and
  never copied. Password ssh is **off**.
- DHCP reservation and a local DNS record for `robin.lan`.
- Tailscale joined, **not** tagged, so the box can reach outbound. Key expiry
  disabled in the admin console. Untagged nodes expire in about 180 days,
  silently, and the tag does not do this for you.
- No power saving: `performance` governor and energy performance preference.
  C-states are left at the kernel default; capping them at C1 was the
  pre-flash workaround for the idle errata and is no longer needed. Never
  `idle=poll`, and never disable EIST.
- Repo cloned, `git pull --ff-only` succeeds.
- Message bus reachability proven with `mosquitto_sub` against a retained
  topic. No unit consumes the broker address yet. The name is the contract
  when the first one lands.
- `merle-autodeploy` armed with an empty unit list. The watcher's job at this
  stage is keeping the checkout current, nothing more.

The Coral was seated and its driver brought live separately. It was never a
Phase 0 gate. Userspace belongs to Mission Zero.

---

## The deploy watcher

Unit: `/etc/systemd/system/merle-autodeploy.service`
Code: `Servers/autodeploy.sh`, inside the checkout it deploys.

Its job is keeping the checkout on origin/main. Install it at bring-up rather
than when the first service lands. A box running without its watcher looks
exactly like a box running with one, right up until you notice the checkout is
weeks stale.

```ini
[Unit]
Description=MERLE deploy watcher -- merges to main deploy themselves
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/todd/MERLE/Servers/autodeploy.sh
Restart=on-failure
RestartSec=10
Environment=MERLE_REPO=/home/todd/MERLE
Environment="MERLE_DEPLOY_UNITS="
Environment=MERLE_DEPLOY_MCC=0

[Install]
WantedBy=multi-user.target
```

The empty unit list is load-bearing rather than a placeholder. Adding a unit
later means a drop-in that sets the **full** list, because a later
`Environment=` replaces the earlier one wholesale rather than appending to it.

It runs as root so future restarts need no sudo password, but every git step is
demoted to `todd` via `setpriv`. Quiet polls log nothing, so
`journalctl -u merle-autodeploy` reads as a deploy history.

```
sudo systemctl enable --now merle-autodeploy
systemctl is-active merle-autodeploy
journalctl -u merle-autodeploy -n 50 --no-pager
```

---

## Coral M.2 A+E

`lspci` shows `1ac1:089a` at `0000:01:00.0`, PCIe x1 at 5.0 GT/s, which is full
speed for this card. Bound to the `apex` driver. `/dev/apex_0` is
`crw-rw---- root:apex`, major 120.

Driver install, with no new patches:

- `apt install dkms`, then a patched `/usr/src/gasket-1.0` tree.
- `dkms add / build / install -m gasket -v 1.0` for the running kernel.
- `/etc/udev/rules.d/65-apex.rules` containing
  `SUBSYSTEM=="apex", MODE="0660", GROUP="apex"`, an `apex` group, and `todd`
  as a member.
- `AUTOINSTALL=YES` armed for kernel bumps. Patch `/usr/src/gasket-1.0` when
  the kernel API rots.

**Trap:** keep `/usr/src/gasket-1.0` at mode **755**. A 700 tree makes
*non-root* `dkms status` print a false "dkms.conf does not exist" error, while
root and AUTOINSTALL are unaffected. The error is a lie about permissions
wearing the costume of a missing file.

Rebuild after a kernel that does not autoinstall:

```
sudo dkms build -m gasket -v 1.0 && sudo dkms install -m gasket -v 1.0
sudo modprobe apex && ls -l /dev/apex_0    # expect crw-rw---- root:apex
```

`libedgetpu` and `pycoral` are **not** installed. The mission stack that talks
to `/dev/apex_0` decides which userspace it wants, and that decision belongs to
Mission Zero.

---

## What this box is for

- **MCC v2**, developed and served here.
- **Robotics missions and experiments.** Inference that wants the Coral stays
  on this box, where it cannot stall anything the household depends on.
- **Not** the NVR, not DNS, not the message broker.

Still open:

- `libedgetpu` and `pycoral` userspace, owned by Mission Zero.
- Mission services. Grow the deploy watcher's unit list when the first one
  lands.
- Retire the leftover private-repo checkout from Phase 0.
