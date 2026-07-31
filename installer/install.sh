#!/bin/bash

set -euo pipefail

INSTALL_USER="media"
INSTALL_HOME="/home/${INSTALL_USER}"
INSTALL_ROOT="${INSTALL_HOME}/PressStart"

SERVICE_USERNAME="pressstartmedia"

MEDIA_SERVER="10.0.5.95"
MEDIA_SHARE="Media"
MEDIA_MOUNT="/mnt/media"

MEDIA_CREDENTIALS="${INSTALL_ROOT}/config/media-credentials"
MQTT_CREDENTIALS="${INSTALL_ROOT}/config/mqtt-credentials"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo
echo "Press Start Media Installer"
echo "==========================="
echo

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this installer with sudo."
    echo
    echo "Example:"
    echo "  sudo ./installer/install.sh"
    exit 1
fi

if ! id "${INSTALL_USER}" >/dev/null 2>&1; then
    echo "ERROR: Required user does not exist: ${INSTALL_USER}"
    echo "Create the Raspberry Pi OS account as 'media' before installing."
    exit 1
fi

echo "This installer will use one shared password for:"
echo "  - Samba media access"
echo "  - MQTT access"
echo
echo "Username for both services: ${SERVICE_USERNAME}"
echo

while true; do
    read -r -s -p "Enter the shared Press Start service password: " SERVICE_PASSWORD
    echo

    if [ -z "${SERVICE_PASSWORD}" ]; then
        echo "ERROR: The password cannot be empty."
        echo
        continue
    fi

    read -r -s -p "Confirm the shared Press Start service password: " SERVICE_PASSWORD_CONFIRM
    echo

    if [ "${SERVICE_PASSWORD}" != "${SERVICE_PASSWORD_CONFIRM}" ]; then
        echo "ERROR: The passwords did not match."
        echo
        continue
    fi

    break
done

echo
echo "[1/11] Installing system packages..."

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cifs-utils \
    fonts-dejavu-core \
    python3 \
    python3-paho-mqtt \
    python3-pil \
    swayimg \
    vlc \
    wtype

echo "[2/11] Creating Press Start directories..."

mkdir -p \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin" \
    "${INSTALL_ROOT}/config" \
    "${INSTALL_ROOT}/logs" \
    "${INSTALL_ROOT}/runtime" \
    "${INSTALL_ROOT}/scripts" \
    "${INSTALL_HOME}/.config/systemd/user" \
    "${INSTALL_HOME}/.config/labwc" \
    "${MEDIA_MOUNT}"

echo "[3/11] Installing application files..."

rm -rf "${INSTALL_ROOT}/app/pressstart_media"

cp -a \
    "${REPOSITORY_ROOT}/src/pressstart_media" \
    "${INSTALL_ROOT}/app/pressstart_media"

cp \
    "${REPOSITORY_ROOT}/src/main.py" \
    "${INSTALL_ROOT}/app/main.py"

if [ "$(readlink -f "${REPOSITORY_ROOT}/assets")" != "$(readlink -f "${INSTALL_ROOT}/assets")" ]; then
    cp -a \
        "${REPOSITORY_ROOT}/assets/." \
        "${INSTALL_ROOT}/assets/"
fi

echo "[4/11] Installing runtime scripts..."

cp \
    "${REPOSITORY_ROOT}/scripts/start-media.sh" \
    "${INSTALL_ROOT}/bin/start-media.sh"

if [ "$(readlink -f "${REPOSITORY_ROOT}/scripts/generate-playlist.py")" != "$(readlink -f "${INSTALL_ROOT}/scripts/generate-playlist.py")" ]; then
    cp \
        "${REPOSITORY_ROOT}/scripts/generate-playlist.py" \
        "${INSTALL_ROOT}/scripts/generate-playlist.py"
fi

chmod +x \
    "${INSTALL_ROOT}/bin/start-media.sh" \
    "${INSTALL_ROOT}/scripts/generate-playlist.py"

echo "[5/11] Installing platform configuration..."

if [ ! -f "${INSTALL_ROOT}/config/media.conf" ]; then
    cp \
        "${REPOSITORY_ROOT}/config/templates/media.conf.template" \
        "${INSTALL_ROOT}/config/media.conf"
fi

cp \
    "${REPOSITORY_ROOT}/config/templates/labwc-rc.xml" \
    "${INSTALL_HOME}/.config/labwc/rc.xml"

cp \
    "${REPOSITORY_ROOT}/config/templates/labwc-autostart" \
    "${INSTALL_HOME}/.config/labwc/autostart"

# player.conf is intentionally not created here. A new player remains
# unprovisioned until Home Assistant supplies its name and profile.

echo "[6/11] Creating service credential files..."

umask 077

printf 'username=%s\npassword=%s\n' \
    "${SERVICE_USERNAME}" \
    "${SERVICE_PASSWORD}" \
    > "${MEDIA_CREDENTIALS}"

printf 'USERNAME=%s\nPASSWORD=%s\n' \
    "${SERVICE_USERNAME}" \
    "${SERVICE_PASSWORD}" \
    > "${MQTT_CREDENTIALS}"

unset SERVICE_PASSWORD
unset SERVICE_PASSWORD_CONFIRM

echo "[7/11] Configuring the media-server mount..."

FSTAB_ENTRY="//${MEDIA_SERVER}/${MEDIA_SHARE} ${MEDIA_MOUNT} cifs credentials=${MEDIA_CREDENTIALS},uid=${INSTALL_USER},gid=${INSTALL_USER},iocharset=utf8,file_mode=0644,dir_mode=0755,nofail,x-systemd.automount,_netdev 0 0"

FSTAB_TEMP="$(mktemp)"

awk -v mount_point="${MEDIA_MOUNT}" '
    $2 != mount_point {
        print
    }
' /etc/fstab > "${FSTAB_TEMP}"

printf '%s\n' "${FSTAB_ENTRY}" >> "${FSTAB_TEMP}"

install -o root -g root -m 644 "${FSTAB_TEMP}" /etc/fstab
rm -f "${FSTAB_TEMP}"

systemctl daemon-reload

echo "[8/11] Installing systemd user service..."

cp \
    "${REPOSITORY_ROOT}/systemd/pressstart-media.service" \
    "${INSTALL_HOME}/.config/systemd/user/pressstart-media.service"

echo "[9/11] Setting ownership and permissions..."

chown -R "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_ROOT}" \
    "${INSTALL_HOME}/.config/systemd" \
    "${INSTALL_HOME}/.config/labwc"

chmod 755 \
    "${INSTALL_ROOT}" \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin" \
    "${INSTALL_ROOT}/runtime" \
    "${INSTALL_ROOT}/scripts"

chmod 600 \
    "${MEDIA_CREDENTIALS}" \
    "${MQTT_CREDENTIALS}"

echo "[10/11] Enabling the user service..."

loginctl enable-linger "${INSTALL_USER}"

USER_ID="$(id -u "${INSTALL_USER}")"
USER_RUNTIME_DIR="/run/user/${USER_ID}"

mkdir -p "${USER_RUNTIME_DIR}"
chown "${INSTALL_USER}:${INSTALL_USER}" "${USER_RUNTIME_DIR}"
chmod 700 "${USER_RUNTIME_DIR}"

sudo -u "${INSTALL_USER}" \
    XDG_RUNTIME_DIR="${USER_RUNTIME_DIR}" \
    systemctl --user daemon-reload

sudo -u "${INSTALL_USER}" \
    XDG_RUNTIME_DIR="${USER_RUNTIME_DIR}" \
    systemctl --user enable pressstart-media.service

echo "[11/11] Checking the media-server mount..."

if mountpoint -q "${MEDIA_MOUNT}"; then
    echo "Media server is already mounted."
elif timeout 20 mount "${MEDIA_MOUNT}" >/dev/null 2>&1; then
    echo "Media server mounted successfully."
else
    echo "WARNING: The media server could not be mounted during installation."
    echo "The configured systemd automount will retry when the path is accessed."
    echo "Verify the network connection and shared password if it remains unavailable."
fi

echo
echo "Press Start Media installation completed."
echo
echo "Configured automatically:"
echo "  - Application files"
echo "  - Runtime scripts"
echo "  - Platform configuration"
echo "  - Labwc cursor hiding"
echo "  - Samba credentials"
echo "  - MQTT credentials"
echo "  - /mnt/media automount"
echo "  - systemd user service"
echo
echo "The service has been enabled but not started."
echo
echo "The player will remain unprovisioned until Home Assistant"
echo "supplies its player name and profile through MQTT."
echo
echo "Next step:"
echo "  Reboot the Raspberry Pi."
echo
