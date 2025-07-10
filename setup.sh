#!/bin/bash

echo "Installing VLC and CIFS utilities..."
sudo apt update && sudo apt install -y vlc cifs-utils

echo "Creating mount directory..."
sudo mkdir -p /mnt/media

echo "Creating Samba credentials file..."
cat <<EOF > /home/media/.smbcredentials
username=pressstartmedia
password=B0ws3rsW!f!
EOF

chmod 600 /home/media/.smbcredentials

echo "Adding entry to /etc/fstab..."
echo "//10.0.5.95/Media /mnt/media cifs credentials=/home/media/.smbcredentials,uid=1000,gid=1000,vers=3.0 0 0" | sudo tee -a /etc/fstab

echo "Enabling network wait service..."
sudo systemctl enable systemd-networkd-wait-online.service

echo "Mounting network drive..."
sudo mount -a

echo "Setting up VLC to autoplay on boot..."
mkdir -p /home/media/.config/autostart

cat <<EOF > /home/media/.config/autostart/vlc.desktop
[Desktop Entry]
Type=Application
Name=VLC Autoplay
Exec=vlc --fullscreen --loop "/home/media/playlist.xspf"
X-GNOME-Autostart-enabled=true
EOF

echo "Setup complete. Please reboot the system to begin playback."
