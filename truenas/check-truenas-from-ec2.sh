#!/usr/bin/env bash
# Checks that the CloudHUB EC2 host can reach the home TrueNAS over Tailscale (Phase 5).
#
# Usage:
#   ./check-truenas-from-ec2.sh <truenas-tailscale-ip>
#
# Example:
#   ./check-truenas-from-ec2.sh 100.x.y.z
#
# Exit codes: 0 = all checks passed, 1 = usage error or a check failed.

set -u

NAS_IP="${1:-}"
if [[ -z "$NAS_IP" ]]; then
  echo "Usage: $0 <truenas-tailscale-ip>"
  exit 1
fi

if [[ ! "$NAS_IP" =~ ^100\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
  echo "Warning: '$NAS_IP' doesn't look like a Tailscale 100.x.y.z address. Continuing anyway."
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "FAIL: Tailscale is not installed on this host."
  exit 1
fi

failed=0

echo "== This host's Tailscale status =="
if ! sudo tailscale status 2>/dev/null | head -3; then
  echo "FAIL: could not read Tailscale status. Is tailscaled running?"
  failed=1
fi

echo
echo "== Tailscale ping to TrueNAS ($NAS_IP) =="
if sudo tailscale ping -c 3 "$NAS_IP"; then
  echo "PASS: TrueNAS answers over the tailnet."
else
  echo "FAIL: no reply. Check both machines show Connected in the Tailscale admin console."
  failed=1
fi

echo
echo "== SMB port 445 =="
if command -v nc >/dev/null 2>&1; then
  if nc -zvw5 "$NAS_IP" 445; then
    echo "PASS: port 445 reachable."
  else
    echo "FAIL: port 445 blocked. Check Tailscale ACLs and that SMB is running on TrueNAS."
    failed=1
  fi
else
  if timeout 5 bash -c "echo > /dev/tcp/$NAS_IP/445" 2>/dev/null; then
    echo "PASS: port 445 reachable."
  else
    echo "FAIL: port 445 blocked. Check Tailscale ACLs and that SMB is running on TrueNAS."
    failed=1
  fi
fi

echo
if [[ $failed -eq 0 ]]; then
  echo "All checks passed. Nextcloud can mount the share at $NAS_IP."
else
  echo "One or more checks failed - see above."
fi
exit $failed
