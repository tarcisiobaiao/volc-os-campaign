#!/bin/bash
# uso: probe.sh <nome> "<specs>" "<python -c teste>"
set -u
LAB=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015/experiments/data-intelligence-lab
OUT=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015/research/data-intelligence/probe-b
cd "$LAB"
export UV_CACHE_DIR=$LAB/.uv-cache UV_PYTHON_DOWNLOADS=never
UV=$LAB/.tools/bootstrap/bin/uv
N=$1; SPECS=$2; TEST=$3
V=$LAB/.tools/probe-b/$N
LOG=$OUT/$N.log
: > "$LOG"
echo "## probe $N  specs=[$SPECS]  date=$(date -u +%FT%TZ)" >> "$LOG"
$UV venv -q "$V" --python /usr/local/bin/python3.13 >> "$LOG" 2>&1
t0=$(date +%s)
$UV pip install --python "$V/bin/python" --exclude-newer 2026-10-01T00:00:00Z $SPECS >> "$LOG" 2>&1
rc=$?
t1=$(date +%s)
echo "install_rc=$rc install_s=$((t1-t0))" >> "$LOG"
echo "size=$(du -sh "$V" | cut -f1)" >> "$LOG"
$UV pip freeze --python "$V/bin/python" > "$OUT/$N.freeze.txt" 2>>"$LOG"
echo "n_pkgs=$(wc -l < "$OUT/$N.freeze.txt" | tr -d ' ')" >> "$LOG"
cd /private/tmp/claude-502/-Users-mac-Desktop-VOLC-OS-CAMPAIGN-worktrees-data-intelligence-overnight-20261015/bac85bbe-c90c-49bb-9e5c-e01f6f12373d/scratchpad
HOME=$(mktemp -d) "$V/bin/python" -I -c "$TEST" >> "$LOG" 2>&1
echo "import_rc=$?" >> "$LOG"
tail -12 "$LOG"
