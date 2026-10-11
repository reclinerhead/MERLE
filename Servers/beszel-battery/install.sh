#!/bin/sh
# merle: install or update the Beszel battery bridge. Run as root on the box:
#   sudo sh /home/todd/MERLE/Servers/beszel-battery/install.sh
# Idempotent. Pulls nothing; update the checkout first (git -C ~/MERLE pull --ff-only).
set -eu
D=/home/todd/MERLE/Servers/beszel-battery
for f in beszel_battery.py beszel-battery.service sys-class-power_supply.mount; do
  [ -s "$D/$f" ] || { echo "missing $D/$f" >&2; exit 1; }
done
# the Socket.IO client comes from Debian, on system Python; no venv, nothing from the vendor's
python3 -c "import socketio" 2>/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-socketio python3-requests
# The unit drops every capability, so root is subject to plain file permissions and
# must be able to traverse todd's home to reach the script. 701 = traverse, no list
# (the same posture orchid uses for its Caddy). Pi OS creates the home as 700.
chmod o+x /home/todd
install -m 644 -o root -g root "$D/sys-class-power_supply.mount" /etc/systemd/system/sys-class-power_supply.mount
install -m 644 -o root -g root "$D/beszel-battery.service" /etc/systemd/system/beszel-battery.service
systemctl daemon-reload
systemctl enable --now sys-class-power_supply.mount
systemctl enable beszel-battery.service
systemctl restart beszel-battery.service
sleep 8
echo "--- units"
systemctl is-active sys-class-power_supply.mount beszel-battery.service
echo "--- what the agent will read"
cat /sys/class/power_supply/BAT0/capacity /sys/class/power_supply/BAT0/status 2>/dev/null || echo "no reading yet (is ugv.service up?)"
# no agent restart needed: Beszel's agent re-reads power_supply on every stats cycle
journalctl -u beszel-battery -n 3 --no-pager -o cat
