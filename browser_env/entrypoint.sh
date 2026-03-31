#!/bin/bash

export DISPLAY=:99

mkdir -p /var/run/dbus
dbus-uuidgen > /var/lib/dbus/machine-id
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address &

Xvfb :99 -screen 0 1280x720x16 -ac +extension GLX +render -noreset &
sleep 2

fluxbox &
x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb -forever -shared &
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

socat TCP-LISTEN:9222,fork,reuseaddr TCP:127.0.0.1:9223 &

echo "--- Запуск Chromium в режиме Local-Only (Port 9223) ---"

while true; do
  rm -f /src/browser_data/SingletonLock
  
  chromium \
    --no-sandbox \
    --disable-dev-shm-usage \
    --remote-debugging-port=9223 \
    --remote-debugging-address=127.0.0.1 \
    --remote-allow-origins=* \
    --window-size=1280,720 \
    --user-data-dir=/src/browser_data \
    --disable-blink-features=AutomationControlled \
    --no-first-run \
    --disable-gpu \
    --mute-audio \
    --no-default-browser-check \
    --disable-software-rasterizer \
    --disable-features=site-per-process

  echo "Chromium упал или был закрыт агентом, рестарт через 2 секунды..."
  sleep 2
done