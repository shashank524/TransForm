#!/usr/bin/env sh
set -eu

# When this file is sourced (e.g. from run_bird_network_e2e.sh), some shells do not pass
# dot-command arguments as $1 reliably. Prefer $1, else NET_PROFILE from the environment.
PROFILE="${1:-${NET_PROFILE:-WAN}}"
DEV="${TC_DEV:-eth0}"

# Clear existing qdisc (ignore errors)
tc qdisc del dev "$DEV" root 2>/dev/null || true

case "$PROFILE" in
  LAN)
    # ~1ms RTT, effectively unlimited rate
    DELAY="1ms"
    RATE="1000mbit"
    LOSS="0%"
    ;;
  WAN)
    DELAY="40ms"
    RATE="50mbit"
    LOSS="0%"
    ;;
  Cellular)
    DELAY="80ms"
    RATE="10mbit"
    LOSS="0.1%"
    ;;
  BadWifi)
    DELAY="30ms"
    RATE="5mbit"
    LOSS="1%"
    ;;
  *)
    echo "Unknown NET_PROFILE=$PROFILE. Use LAN|WAN|Cellular|BadWifi." >&2
    exit 2
    ;;
esac

# Export for child processes (e.g. Python JSONL headers via bench_* scripts)
export TC_DEV="$DEV"
export TC_DELAY="$DELAY"
export TC_RATE="$RATE"
export TC_LOSS="$LOSS"
export NET_PROFILE="$PROFILE"

# Use TBF for rate limiting + netem for delay/loss
tc qdisc add dev "$DEV" root handle 1: tbf rate "$RATE" burst 32kbit latency 400ms
tc qdisc add dev "$DEV" parent 1:1 handle 10: netem delay "$DELAY" loss "$LOSS"

echo "Applied tc profile=$PROFILE dev=$DEV delay=$DELAY rate=$RATE loss=$LOSS"
tc qdisc show dev "$DEV" || true

