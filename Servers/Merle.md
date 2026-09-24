# Merle

Raspberry Pi 5 (8 GB) riding a Waveshare UGV rover chassis. Raspberry Pi OS
Lite (64-bit, Bookworm), Python 3.11. Wireless only, on `wlan0`.

| | |
|--|--|
| **Hostname** | `merle` |
| **User** | `todd` |
| **Role** | **The rover.** Tier 0 reflexes and on-robot perception, and eventually the actuator-owning service |
| **State** | Driving under its own power since the July 2026 reflash, controlled only by the vendor web UI. Lidar and pan-tilt fitted and live. No MERLE code runs here yet. |

A rover that is **off, out of range, or charging elsewhere is a normal state,
not a fault.** Expect `ssh` to time out sometimes. Everything below is dated
where it could only be verified with the box up, and marked unverified where it
could not be re-checked.

> Addresses, network reservations, Wi-Fi network names, tailnet addresses, and
> home coordinates live in the private house repo's copy of this runbook. This
> public copy is deliberately free of them. Reach the box by name. Wi-Fi
> network names are left out on purpose: a network name is geolocatable
> through public wardriving databases.

**Where this came from.** Merle was built and first documented inside the
private house project, which still owns three services on this box (see
§ House-repo tenants). The robotics now belongs here. The house copy of this
runbook remains the record for those tenants.

---

## Hardware

| Component | What | State |
|---|---|---|
| Compute | Raspberry Pi 5 Model B, 8 GB | Installed |
| Chassis | Waveshare UGV rover (the `ugv_rpi` platform): all-aluminum shell, four encoder gearmotors under closed-loop PID | Installed |
| Driver board | ESP32 sub-controller: motors, encoders, 9-axis IMU, battery voltage. Talks to the Pi over UART | Installed |
| Power | 3S lithium pack of 18650 cells on the chassis UPS module | Installed, one pack |
| Camera | USB camera (enumerates as `0abd:8050` "Xitech USB Camera"), 640×480 native, served as MJPEG at about 30 fps. `/dev/video0` | Installed |
| Pan-tilt | Two-axis camera gimbal, driven by the ESP32 over the same serial link as the motors | Installed |
| Microphone | Built into the USB camera. ALSA `plughw:0,0` | Installed |
| Speaker | USB audio adapter (`0c76:1229` JMTek "USB PnP Audio Device") | Installed |
| Display | Small OLED on the chassis, written by the vendor app | Installed |
| Lidar | LDROBOT LD19 (10 Hz scan, 4,500 points per second, 12 m range) on a CH343 USB serial adapter (`1a86:55d3`). `/dev/ttyACM0` at 230400 baud | Installed, read by the vendor app |

The JMTek adapter's microphone input is silent; it serves as the speaker only.
The camera's mic is the one that works. A USB hub (`1a40:0101`) sits between
the Pi and the lidar and audio adapters.

The MCC design reference once listed pan-tilt as aspirational set-dressing.
That note predates the gimbal; the rover has one.

### The layered-control split comes pre-built

The ESP32/Pi split is the platform's reflex layer sold as hardware. The ESP32
owns the motors and the IMU and keeps running no matter what the Pi is doing.
The Pi is the removable brain above it. That is why the chassis was chosen over
a from-scratch build: it skips the wiring phase and lands directly on the
architecture MERLE wants.

### Battery

Pack voltage, from the field checklist the house project used on real outings:

| Voltage | Meaning |
|---|---|
| 12.6 V | Full |
| 11.1 V | About half |
| 10.5 V | Start wrapping up |
| 10.2 V | Head home now |

These are cell-chemistry rules of thumb, not a measured discharge curve for this
pack under this load. No low-battery alarm should be built on them until that
curve exists, because an invented threshold is an alarm you learn to ignore.
With the charger plugged in, the reading should visibly rise; around 12.5 V and
up means full.

### Pi-side hardware configuration

Applied per SD card, already done on the current card:

- `uart0=on`, Bluetooth disabled, serial console removed from the kernel
  command line. The Pi 5 serial port is `/dev/ttyAMA0`.
- `todd` is in `dialout` (verified 2026-07-19), so opening the port needs no
  sudo. `/dev/ttyAMA0` is `crw-rw---- root:dialout`.
- No real-time clock. Away from a network the clock is wrong until something
  sets it.

### The lidar

The LD19 is a 2D spinning lidar, connected by USB through a CH343 serial
adapter and stable at `/dev/serial/by-id/usb-1a86_USB_Single_Serial_*-if00`
(currently `/dev/ttyACM0`). MERLE's plans lean on it: the MCC design reference
has a polar lidar panel sized to its real spec, and the Red Ball, Green Ball
mission names a Pi-local obstacle-stop reflex on lidar as the thing that
outranks every game behavior.

Today the **vendor app owns it** (verified 2026-09-24 with `fuser`: the `ugv`
process holds `/dev/ttyACM0`, `/dev/ttyAMA0`, and `/dev/video0`). It is enabled
by `use_lidar: true` in `~/ugv_rpi/config.yaml`, and read in `base_ctrl.py`:

- It opens the first `/dev/ttyACM*` it finds, at 230400 baud. With a second
  USB serial device plugged in, that glob picks whichever enumerates first.
- It reads 47-byte frames (a `0x54` header plus 46 bytes), each carrying 12
  points, and assumes a fixed 0.833° step between points, rotated 180° to the
  chassis frame.
- **The data goes nowhere but the video overlay.** With `add_osd: true` the
  points are drawn as dots on the camera stream. Nothing is published over
  Socket.IO or anywhere else, so no other process can get lidar data before
  cutover.

So the lidar joins the serial port and the camera on the list of devices
MERLE's hardware service takes over at cutover.

### The gimbal and `module_type`

The vendor config says `module_type: 0`, which the vendor code documents as
"0: None, 1: RoArm-M2-S, 2: Gimbal". At startup `app.py` sends that value to the
ESP32 (`{"T":4,"cmd":0}`) along with `{"T":900,"main":2,"module":0}`. With the
gimbal fitted, the expected value is `2`. The pan-tilt commands themselves are
`T:133` (position, speed, acceleration), `T:141` (base control), and `T:137`
(steady mode). If pan-tilt misbehaves in the vendor UI, check this setting
first. It has not been changed, and this runbook does not record whether it
matters in practice.

**The vendor clone carries local edits.** `config.yaml` differs from upstream
(`use_lidar` and `add_osd` switched on). A `git pull` in `~/ugv_rpi` can
conflict on it. Stash and reapply, never discard.

---

## What the hardware reports

Measured on the rover, 2026-07-19, while planning the Helm. These are the
facts the actuator-owning service inherits.

**The driver board, over serial** (`/dev/ttyAMA0` at 115200 baud). It streams
`T:1001` feedback at about 10 Hz without being asked:

| Field | Wire | Notes |
|---|---|---|
| Battery voltage | `v` | **Scale unverified.** The board sent `"v":1089` at about 10.9 V (centivolts). The vendor's code comment shows whole volts. Confirm against a multimeter before trusting either |
| Motor speeds | `L`, `R` | |
| Wheel odometry | `odl`, `odr` | Present on the wire, missing from the vendor's documentation. Free dead-reckoning input |
| Raw accelerometer | `ax`, `ay`, `az` | Live. `az` reads about 8526 at rest |
| Raw gyro | `gx`, `gy`, `gz` | Live |
| Raw magnetometer | `mx`, `my`, `mz` | Live |
| Fused attitude | `T:1002`: `r`, `p`, `y`, `q0`..`q3` | **All zeros on the bench**, including an all-zero quaternion, which is not a valid orientation |

Attitude is the hard field. Pitch and roll from the raw accelerometer are simple
arithmetic. Heading is not: a tilt-compensated magnetic heading needs hard and
soft iron calibration, on an aluminum chassis with four motor currents swinging
around the magnetometer. Treat heading as its own project.

**The Pi itself:**

| Field | Mechanism | Notes |
|---|---|---|
| CPU temperature | `/sys/class/thermal/thermal_zone0/temp`, divide by 1000 | 50.7 °C idle. No need for the vendor's `vcgencmd` shell-out |
| Wi-Fi signal | `/proc/net/wireless` | Neither `iwconfig` nor `iw` is installed on Lite. Fields carry a **trailing period** (`-64.`), which breaks a naive `int()`. The `noise` column reads `-256`, meaning "not measured"; never surface it |
| CPU load | `psutil.cpu_percent()` | The vendor calls it with `interval=2`, a blocking two-second sleep. Sample it on its own thread |
| Memory | `psutil.virtual_memory()` | |

Wi-Fi signal is the one Pi-side number that matters operationally. The link is
the tether, so falling signal is the leading indicator of the dead-man timeout
firing. A failed read renders `—`, never `0 dBm`.

**Known-benign noise.** `[base_ctrl.feedback_data] error: Expecting value: line
1 column 1 (char 0)` in the vendor app's journal is a vendor bug: it drains the
serial buffer, then reads an empty line and parses it as JSON. Do not chase it.

---

## Measured compute and power

From a 2026-07-24 benchmark on this rover, parked outside with the vendor app
running. The workload was the house project's bird-sound classifier
(TensorFlow, about 1.1 s of compute per 3 s audio window), which makes it a
useful yardstick for what a Tier 0 model costs here.

| Measure | Result |
|---|---|
| Sustained 15-minute inference loop | No slowdown. Median and max within 5% of each other |
| CPU temperature under that load, outdoors | 48.3 °C rising to a 53.8 °C plateau. Never throttled, about 26 °C of margin |
| Peak memory of a loaded TensorFlow stack | 861 MB, comfortable on 8 GB beside the vendor app |
| SoC power, idle with the vendor app running | 1.80 W |
| SoC power, idle with the vendor app stopped | 1.76 W |
| SoC power, sustained inference | 2.34 W |

Two takeaways for MERLE. A continuously running model costs about half a watt,
so battery life is set by the motors and the base platform, not by on-robot
inference. And an unwatched camera is already nearly free (stopping the whole
vendor app saved 0.05 W), so quiescing video to save power is not worth
building. The power rails measured exclude USB bus power, so the camera's own
draw is not in these numbers. The driver board reports voltage but not current,
so whole-system watts are not measurable today.

A Pi 5 does not serve large language models. Anything heavier than an edge
model belongs on Tier 2.

---

## What runs here today

| Service | Unit | Port | Owner | Purpose |
|---|---|---|---|---|
| Rover | `ugv` | `5000` | Vendor | Waveshare web UI and driver-board bridge: drive, lights, speed modes, camera stream. **The only control path today** |
| Field Mode | `fieldmode` | `8080` | House repo | **Retired**, still installed. Standalone audio recording sessions at a park, with a phone viewfinder |
| Jim | `narrator-jim` | none | House repo | A narration persona that talks only to the message broker |
| Deploys | `merle-autodeploy` | none | House repo | The **house** deploy watcher, restarting the two units above |

Nothing from this repo is deployed here yet. The house-repo rows are being
phased out entirely (see § House-repo tenants), which also clears the unit name
collision in the last row.

---

## The vendor stack (`ugv.service`)

Drive the rover at `http://merle:5000`. The unit as installed (2026-07-15,
observed running since):

```ini
[Unit]
Description=Waveshare UGV rover -- web UI + driver board bridge
After=network-online.target
Wants=network-online.target

[Service]
User=todd
WorkingDirectory=/home/todd/ugv_rpi
ExecStart=/home/todd/ugv_rpi/ugv-env/bin/python /home/todd/ugv_rpi/app.py
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Load-bearing facts the unit file does not show:

- **`~/ugv_rpi` is a separate clone of the vendor's repository** with its own
  venv, `ugv-env`, owned by `todd`. It never autodeploys. Update it by hand:
  `cd ~/ugv_rpi && git pull && sudo systemctl restart ugv`.
- **`app.py` owns `/dev/ttyAMA0`, the lidar, and the USB camera exclusively.** Two processes
  reading the serial port split the bytes between them, and that breaks
  driving, not just telemetry. Nothing else can open the camera while `app.py`
  holds it. This is the reason MERLE's hardware service replaces `ugv` at
  cutover rather than running beside it (see
  [`docs/guide/helm.md`](../docs/guide/helm.md)).
- **Anything that needs rover data before cutover reads it from `app.py`, not
  from the port.** The vendor app re-broadcasts driver-board feedback as a
  Socket.IO `update` event every 5 s on namespace `/ctrl`. Its payload keys are
  opaque integers defined in the vendor's `config.yaml` under `fb:` (battery
  voltage is `fb.base_voltage`, currently `112`). Read the key from the config;
  it is the vendor's value and nothing stops it moving.
- **The camera stream** is MJPEG at `http://merle:5000/video_feed`, 640×480 at
  about 30 fps.
- **The OLED** shows the Wi-Fi address on its first line (`W:<address>`),
  refreshed every 5 s by `app.py`.

### Installing it: the vendor's instructions do not work on Pi OS Lite

Recorded from the actual 2026-07-15 install so the box is rebuildable. This was
the single most expensive thing to work out. **Do not run `sudo ./setup.sh` or
`./autorun.sh`:**

- `requirements.txt` is a roughly 350-package `pip freeze` of the vendor's
  **desktop** image (Thonny, PyQt5, torch, about 130 `types-*` stubs, all three
  OpenCV variants), not a dependency list. `python-apt==2.6.0` cannot install
  from pip at all, so the all-or-nothing install hard-fails, after PyQt5 spends
  hours compiling.
- `sudo ./setup.sh` creates a **root-owned venv** that `./autorun.sh`, running
  as `todd`, then cannot write to. Lite also lacks `python3-picamera2`, which
  the script never installs.
- `./autorun.sh` needs Jupyter and configures it with an empty token and
  password: **unauthenticated remote code execution on the LAN**. The systemd
  unit above replaces it.

What the code actually imports is about eleven third-party packages: flask,
flask_socketio, werkzeug, picamera2, aiortc, mediapipe, depthai, imageio,
imutils, pygame, and pyttsx3, plus cv2, numpy, yaml, serial, psutil, and
netifaces from apt. `depthai` is a hard top-level import in `cv_ctrl.py`,
required even with no OAK camera attached.

The recipe that works (a 481 MB venv; piwheels is already in `/etc/pip.conf`, so
ARM wheels come prebuilt):

```
# apt for everything Debian packages:
sudo apt install -y python3-picamera2 python3-pygame python3-flask \
    python3-werkzeug python3-opencv python3-numpy python3-serial \
    python3-yaml python3-psutil python3-netifaces \
    libcamera-dev portaudio19-dev espeak ffmpeg

# venv AS TODD (not sudo), inheriting the apt packages:
cd ~/ugv_rpi && python3 -m venv --system-site-packages ugv-env

# pip only for what apt cannot provide, then re-pin numpy:
ugv-env/bin/pip install Flask-SocketIO aiortc imageio imutils pyttsx3 \
    mediapipe depthai
ugv-env/bin/pip install 'numpy<2' 'matplotlib<3.9'
ugv-env/bin/pip uninstall -y opencv-contrib-python   # let apt's cv2 win
```

Two traps that cost the most time:

- A `--system-site-packages` venv **also inherits `~/.local`**, so a stale
  `~/.local/lib/python3.11/site-packages` silently shadows both apt and the
  venv. Fixes never stick until it is deleted. The failed vendor installs left
  1.5 GB there.
- Letting pip resolve mediapipe drags in numpy 2.x and a second OpenCV, which
  breaks apt's numpy 1.x extensions (`numpy.dtype size changed, Expected 96 …
  got 88`). Hence the explicit `numpy<2` pin and the uninstall.

### Audio out

The vendor's `asound.conf` hardcodes `card 3`, which on merle is an unplugged
HDMI port. `pygame.mixer.init()` dies with ALSA error 524, and `audio_ctrl.py`
swallows it into a silent "audio usb not connected". Card indexes also shuffle
across boots, so `/etc/asound.conf` now targets the speaker **by id**
(`type plug` with `slave.pcm "hw:Device,0"`, where "Device" is the USB PnP Audio
Device). The original is saved as `/etc/asound.conf.waveshare-orig`. A healthy
start logs `mixer OK -> (44100, -16, 2)`.

---

## Wi-Fi and networking

### NetworkManager, and the priority trap

Since the reflash, Wi-Fi is managed by NetworkManager (`nmcli`), not
`wpa_supplicant`. The known profiles, highest priority first:

| Profile | Priority | What |
|---|---|---|
| Outdoor access point | 10 | The yard AP. The rover's normal home network |
| Phone hotspot | 5 | For outings |
| `preconfigured` | 0 | The house 2.4 GHz network, created by Pi OS imaging. The deliberate fallback |

Real profile names are in the private copy.

NetworkManager does **not** roam between different networks on its own. Once
connected, it stays until that network drops. At equal priority, any blip (the
rover booting before the yard AP is up, a weak moment, the AP rebooting) makes
merle grab `preconfigured` and stay there, which looks exactly like a failing
yard AP when the AP is fine. That cost an hour of AP troubleshooting on
2026-07-21. The fix is the priority column above:

```
sudo nmcli connection modify <outdoor-ap-profile> connection.autoconnect-priority 10
nmcli -f NAME,AUTOCONNECT-PRIORITY connection show
```

Check what it is actually on, and force a switch:

```
nmcli -f NAME,DEVICE connection show --active
iwgetid -r                                        # the live network name
sudo nmcli connection up <outdoor-ap-profile>
```

Adding a network later: `sudo nmcli device wifi connect "<name>" password
"<password>"`, then set its priority. **Never delete `preconfigured`.** A rover
with zero known networks is a rover you plug a keyboard into.

### The rover's own access point: not working

The vendor installer left `AccessPopup` under `~/ugv_rpi`, whose job is to raise
the Pi's own access point when no known network is in range. Observed state:
`AccessPopup` inactive, `hostapd` masked, `dnsmasq` enabled. On the first real
outing (2026-08-02) it did not come up, and it has not been verified working
since. AccessPopup's default AP address is `192.168.50.5`; that is unverified on
this box.

What that outing taught, because it will bite any mission that leaves the yard:

- **A phone hotspot gives no name resolution for devices on it.** `merle` then
  resolves through Tailscale MagicDNS to its tailnet address, so two devices a
  few feet apart route through the tailnet, which needs working internet at
  both ends. Every cellular wobble breaks the path.
- **The tailnet follows the rover.** Anything at home that reaches merle by
  name keeps reaching it over cellular at a park. "Away from home" does not
  mean "unreachable from home."
- **The Wi-Fi network named `UGV` is the ESP32's**, not the Pi's. It can never
  reach anything the Pi serves.
- The Pi has one radio. Serving an access point and staying a client at the
  same time is not reliable on this hardware; it is one or the other.
- The rover must always rejoin known networks when they are in range. An
  AP-only rover has no `ssh`, no `git pull`, and no Tailscale.

### Tailscale

Merle is an ordinary tailnet member, not a confined station. It can reach the
house over the mesh, including from a phone hotspot. Use that for liveness and
debugging, never as a control path: teleoperation latency over cellular is not
LAN latency, and nothing that must work at a park may depend on it.

---

## House-repo tenants

Three services from the private house project still run here. **The rover is
being phased out of the house project completely**, so all three are on their
way off the box and MERLE should not build on any of them. Until they are gone,
they share the hardware.

**Field Mode is retired.** It was an early experiment in carrying the rover to
a park and recording birdsong with a live phone viewfinder. The house project's
permanent remote field stations surpassed it: they listen at the places worth
hearing all the time, instead of for an hour on a picnic table. The unit is
still installed and holds the microphone only during a session, which no one
starts anymore.

Listening on the rover may come back as a learned listening *skill* on this
platform. If it does, it gets built fresh against MERLE's contracts rather than
ported. What Field Mode taught is worth carrying into that design:

- **The recorder must survive everything else dying.** Capture depended on
  ALSA and a file writer alone. The model ran in a separate process fed by a
  bounded, drop-oldest queue, so a crashed or slow model never cost audio.
- **The microphone is single-open.** Whoever listens has to own it outright or
  arbitrate for it; two readers do not share.
- **Nothing downloads at a park.** First model use pulls about 100 MB, so
  models are warmed at home, and any cache path must survive a reboot (`/tmp`
  does not).
- **The Pi has no clock away from a network.** Field Mode took the time from the
  phone at session start and recorded the offset, so the timestamps stayed
  honest.
- **Battery voltage came from `app.py`'s Socket.IO feed**, never the serial
  port. That is still the only safe way to read it before cutover.
- **Measured on this rover**, a bird-sound model classified every 3 s window in
  about 1.1 s at roughly half a watt (see § Measured compute and power).

The house deploy watcher runs `/home/todd/project-squirrel/Servers/autodeploy.sh`
with `MERLE_DEPLOY_UNITS="narrator-jim fieldmode"`. The vendor stack is
deliberately outside its reach. The house checkout uses a read-only deploy key,
because the house repo is private.

Three virtual environments on the box, three jobs, zero shared imports:
`~/ugv_rpi/ugv-env` (vendor), `~/field-venv` (Field Mode), and
`~/project-squirrel/venv` (Jim). A leftover `~/spike-venv` from the benchmark is
safe to delete.

Left behind by Field Mode, to remove with it: 14 recorded sessions (about
589 MB, never imported anywhere) under `~/field-sessions/`, and a sudoers entry
at `/etc/sudoers.d/fieldmode-clock` that lets `todd` run `/usr/bin/date -s @*`
without a password. Decide what happens to the recordings before deleting
anything.

---

## Day-to-day

`ssh todd@merle`. Never bare `ssh merle`, which tries the wrong user and hangs.
If it times out, check whether the rover is on the charger or out past the yard
AP before suspecting software. If it is up but on the wrong network, see
§ Wi-Fi and networking.

```
systemctl status ugv                  # green dot = rover is drivable
journalctl -u ugv -f                  # watch live
journalctl -u ugv -n 100              # recent history
sudo systemctl restart ugv            # UI wedged, or driver board unresponsive
```

Liveness from the couch: `http://merle:5000` loads, or it does not.

**Never touch `/dev/ttyAMA0` while `ugv` is running.** For bench work that
needs the port, stop the service by hand and start it again when done. Do not
disable or mask it: it is the only way to drive the rover until the Helm
reaches parity.

```
sudo systemctl stop ugv
# ... bench work ...
sudo systemctl start ugv
```

---

## Access and hardening

Per-device ed25519 keys from the desk machines, generated on the machine that
uses them and never copied.

Two fleet-wide changes landed on 2026-09-06 while merle was powered off, and
**neither has been applied here yet**:

- The **offline recovery key** is missing from `~/.ssh/authorized_keys`.
- **Password ssh is still on.** The rest of the fleet is key-only. Apply the
  same `sshd_config.d` hardening drop-in the other boxes use, then verify with
  a no-key probe that password authentication is refused.

Do both on the next visit when the rover is up.

---

## Still open

- **Phase the house project off the box.** Remove `fieldmode`,
  `narrator-jim`, and the house `merle-autodeploy`; the Field Mode recordings
  and sudoers entry; the house checkout and its deploy key; and the house
  venvs (`~/field-venv`, `~/spike-venv`, and the one inside the checkout).
  `~/ugv_rpi/ugv-env` stays. Removing the house watcher frees the `merle-autodeploy` name,
  which this repo's watcher takes when MERLE code first lands here.
- **Password ssh off, recovery key on.** See § Access and hardening.
- **Battery voltage scale**, cross-checked against a multimeter.
- **`T:1002` attitude**, re-checked. The board's fusion works, or pitch and
  roll are derived on the Pi, or attitude is deferred.
- **`module_type`**: decide whether the vendor config should say `2` (gimbal).
- **The rover's own access point**, made to work and verified, or replaced.
- **The lidar's measured behavior**: actual scan rate and point spacing on
  this unit, versus the vendor code's fixed 0.833° assumption.
- **A measured discharge curve** for the pack, before any low-battery alarm.
- **The cutover** from `ugv` to MERLE's hardware service, tracked in the issue
  tracker.
