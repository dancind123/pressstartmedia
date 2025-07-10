#!/bin/bash

echo "Installing required packages..."
sudo apt update && sudo apt install -y vlc cifs-utils fbi

echo "Creating mount and local directories..."
sudo mkdir -p /mnt/media
mkdir -p /home/media/Videos

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

echo "Syncing files from server to local folder (initial sync)..."
rsync -av --delete /mnt/media/ /home/media/Videos/

echo "Creating systemd service to sync files on reboot..."
cat <<EOF | sudo tee /etc/systemd/system/videosync.service
[Unit]
Description=Sync Media Folder on Boot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/rsync -av --delete /mnt/media/ /home/media/Videos/

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable videosync.service

echo "Setting up splash screen..."
sudo cp PSLogo.png /etc
sudo bash -c 'echo -e "[Service]\\nExecStartPre=/usr/bin/fbi -T 1 -noverbose -a /etc/PSLogo.png" >> /lib/systemd/system/display-manager.service'

echo "Configuring VLC to autoplay on boot..."
mkdir -p /home/media/.config/autostart

cat <<EOF > /home/media/.config/autostart/vlc.desktop
[Desktop Entry]
Type=Application
Name=VLC Autoplay
Exec=vlc --no-audio --fullscreen --no-video-title-show --sub-track=-1 --random --loop /home/media/Videos
X-GNOME-Autostart-enabled=true
EOF

echo "Setup complete. Please reboot the system to begin playback."
