#!/usr/bin/env bash
# Publish both mobile dashboards to your own devices over Tailscale (works from
# any network; nothing is exposed to the public internet).
#
# One-time, needs your sudo password:
#   curl -fsSL https://tailscale.com/install.sh | sh
#   sudo tailscale up --operator=$USER      # sign in; --operator lets this script run without sudo
# Then:
#   bash ~/JOBIRA/mobile/remote_access.sh
set -euo pipefail

command -v tailscale >/dev/null || { echo "Tailscale isn't installed yet (see the top of this file)."; exit 1; }

# HTTPS ports Tailscale Serve allows: 443, 8443, 10000. Separate ports = separate apps.
tailscale serve --bg --https=443  http://127.0.0.1:8430   # JOBIRA Dashboard
tailscale serve --bg --https=8443 http://127.0.0.1:8431   # JOBIRA 2 Dashboard

host=$(tailscale status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")
echo
echo "JOBIRA Dashboard:   https://$host/"
echo "JOBIRA 2 Dashboard: https://$host:8443/"
echo
echo "Passcodes (enter once per device):"
echo "  JOBIRA:   $(cat ~/JOBIRA/mobile/.passcode)"
echo "  JOBIRA 2: $(cat ~/JOBIRA2/mobile/.passcode)"
