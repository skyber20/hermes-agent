#!/usr/bin/env bash
set -Eeuo pipefail

export DISPLAY="${DISPLAY:-:99}"
DISPLAY_NUM="${DISPLAY#:}"
XVFB_LOG="/tmp/xvfb.log"

VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
CHROME_LOCAL_DEBUG_PORT="${CHROME_LOCAL_DEBUG_PORT:-9223}"
CHROME_PUBLIC_DEBUG_PORT="${CHROME_PUBLIC_DEBUG_PORT:-9222}"
CHROME_PROFILE_DIR="${CHROME_PROFILE_DIR:-/src/browser_data}"

MAX_RESTARTS="${MAX_RESTARTS:-10}"
RESTART_WINDOW_SEC="${RESTART_WINDOW_SEC:-60}"
RESTART_BACKOFF_SEC="${RESTART_BACKOFF_SEC:-2}"

PIDS=()
STOPPING=0
WINDOW_START="$(date +%s)"
RESTART_COUNT=0

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

start_bg() {
  "$@" &
  local pid=$!
  PIDS+=("$pid")
  log "started: $* (pid=$pid)"
}

wait_for_port() {
  local host=$1
  local port=$2
  local timeout_sec=$3
  local end_ts=$(( $(date +%s) + timeout_sec ))

  while [ "$(date +%s)" -lt "$end_ts" ]; do
    if bash -c "</dev/tcp/${host}/${port}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

wait_for_x_display() {
  local timeout_sec=$1
  local end_ts=$(( $(date +%s) + timeout_sec ))

  while [ "$(date +%s)" -lt "$end_ts" ]; do
    if [ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ] && DISPLAY="$DISPLAY" bash -c 'echo >/dev/null' >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

cleanup() {
  if [ "$STOPPING" -eq 1 ]; then
    return
  fi
  STOPPING=1

  log "shutdown signal received, stopping processes..."

  if [ -n "${CHROME_PID:-}" ] && kill -0 "$CHROME_PID" >/dev/null 2>&1; then
    kill "$CHROME_PID" >/dev/null 2>&1 || true
  fi

  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done

  sleep 1

  if [ -n "${CHROME_PID:-}" ] && kill -0 "$CHROME_PID" >/dev/null 2>&1; then
    kill -9 "$CHROME_PID" >/dev/null 2>&1 || true
  fi

  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done

  log "shutdown complete"
}

trap cleanup SIGTERM SIGINT EXIT

mkdir -p /var/run/dbus /var/lib/dbus "$CHROME_PROFILE_DIR"
if [ ! -f /var/lib/dbus/machine-id ]; then
  dbus-uuidgen > /var/lib/dbus/machine-id 2>/dev/null || true
fi

# Удаляем stale lock/socket от прошлых падений Xvfb на том же DISPLAY.
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" || true

log "starting X stack on DISPLAY=${DISPLAY}"
Xvfb "$DISPLAY" -screen 0 1280x720x24 -ac +extension GLX +render -noreset >"$XVFB_LOG" 2>&1 &
XVFB_PID=$!
PIDS+=("$XVFB_PID")
log "started: Xvfb $DISPLAY (pid=$XVFB_PID)"

if ! wait_for_x_display 15; then
  log "fatal: Xvfb did not initialize DISPLAY=${DISPLAY}"
  if [ -f "$XVFB_LOG" ]; then
    log "xvfb log tail:"
    tail -n 40 "$XVFB_LOG" || true
  fi
  exit 1
fi

start_bg fluxbox
start_bg x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -nopw -listen 0.0.0.0 -xkb -forever -shared
start_bg websockify --web=/usr/share/novnc/ "$NOVNC_PORT" "localhost:${VNC_PORT}"
start_bg socat "TCP-LISTEN:${CHROME_PUBLIC_DEBUG_PORT},fork,reuseaddr" "TCP:127.0.0.1:${CHROME_LOCAL_DEBUG_PORT}"

if ! wait_for_port 127.0.0.1 "$VNC_PORT" 20; then
  log "fatal: x11vnc did not open port ${VNC_PORT}"
  exit 1
fi
if ! wait_for_port 127.0.0.1 "$NOVNC_PORT" 20; then
  log "fatal: websockify did not open port ${NOVNC_PORT}"
  exit 1
fi

log "browser infrastructure is ready (noVNC:${NOVNC_PORT}, DevTools proxy:${CHROME_PUBLIC_DEBUG_PORT})"

while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      log "fatal: required background process died (pid=${pid})"
      exit 1
    fi
  done

  rm -f "${CHROME_PROFILE_DIR}/SingletonLock" "${CHROME_PROFILE_DIR}/SingletonCookie" "${CHROME_PROFILE_DIR}/SingletonSocket" 2>/dev/null || true

  log "starting Chromium (local DevTools:${CHROME_LOCAL_DEBUG_PORT})"
  chromium \
    --no-sandbox \
    --disable-dev-shm-usage \
    --ozone-platform=x11 \
    --remote-debugging-port="${CHROME_LOCAL_DEBUG_PORT}" \
    --remote-debugging-address=127.0.0.1 \
    --remote-allow-origins='*' \
    --window-size=1280,720 \
    --user-data-dir="${CHROME_PROFILE_DIR}" \
    --disable-blink-features=AutomationControlled \
    --no-first-run \
    --disable-gpu \
    --mute-audio \
    --no-default-browser-check \
    --disable-software-rasterizer \
    --disable-features=site-per-process \
    --disable-crash-reporter \
    --disable-extensions \
    --disable-sync &

  CHROME_PID=$!
  wait "$CHROME_PID" || CHROME_EXIT=$?
  CHROME_EXIT=${CHROME_EXIT:-0}

  if [ "$STOPPING" -eq 1 ]; then
    break
  fi

  now="$(date +%s)"
  if [ $(( now - WINDOW_START )) -gt "$RESTART_WINDOW_SEC" ]; then
    WINDOW_START="$now"
    RESTART_COUNT=0
  fi

  RESTART_COUNT=$((RESTART_COUNT + 1))
  log "Chromium exited with code=${CHROME_EXIT}; restart ${RESTART_COUNT}/${MAX_RESTARTS} in current window"

  if [ "$RESTART_COUNT" -ge "$MAX_RESTARTS" ]; then
    log "fatal: too many Chromium restarts in ${RESTART_WINDOW_SEC}s"
    exit 1
  fi

  sleep "$RESTART_BACKOFF_SEC"
  unset CHROME_EXIT
  unset CHROME_PID
done

