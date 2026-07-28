#!/bin/bash

set -u

APP_DIRECTORY="/home/media/PressStart/app"
RUNTIME_DIRECTORY="/run/user/$(id -u)"
WAYLAND_SOCKET="${RUNTIME_DIRECTORY}/wayland-0"
MEDIA_MOUNT="/mnt/media"

until [ -S "${WAYLAND_SOCKET}" ]; do
    sleep 1
done

until mountpoint -q "${MEDIA_MOUNT}"; do
    sleep 2
done

export XDG_RUNTIME_DIR="${RUNTIME_DIRECTORY}"
export WAYLAND_DISPLAY="wayland-0"
export XDG_SESSION_TYPE="wayland"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${RUNTIME_DIRECTORY}/bus"
export QT_QPA_PLATFORM="wayland"

unset DISPLAY

cd "${APP_DIRECTORY}" || exit 1

exec /usr/bin/python3 main.py
