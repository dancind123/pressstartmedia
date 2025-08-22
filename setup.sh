#!/bin/bash
set -e

echo "=== Installing dependencies ==="
sudo apt update
sudo apt install -y vlc cifs-utils

echo "=== Creating mount point ==="
sudo mkdir -p /mnt/media

echo "=== Adding Samba share to fstab ==="
if ! grep -q "//10.0.5.95/Media" /etc/fstab; then
  echo "//10.0.5.95/Media /mnt/media cifs username=pressstartmedia,password=B0ws3rsW!f!,vers=3.0 0 0" | sudo tee -a /etc/fstab
fi

echo "=== Mounting share ==="
sudo mount -a

echo "=== Creating startup script ==="
cat << 'EOF' > ~/startmedia.sh
#!/bin/bash
# Mount Samba share
mount -t cifs //10.0.5.95/Media /mnt/media -o username=pressstartmedia,password=YOURPASSWORD,vers=3.0

# Run VLC with playlist (loop forever, no scanning)
cvlc --loop /mnt/media/playlist.xspf
EOF

chmod +x ~/startmedia.sh

echo "=== Creating systemd service ==="
SERVICE_FILE=/etc/systemd/system/mediadisplay.service
sudo bash -c "cat > \$SERVICE_FILE" << 'EOF'
[Unit]
Description=Media Display Service
After=network-online.target
Wants=network-online.target

[Service]
User=media
ExecStart=/home/media/startmedia.sh
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "=== Enabling service ==="
sudo systemctl daemon-reexec
sudo systemctl enable mediadisplay.service
sudo systemctl start mediadisplay.service

echo "=== Setup complete! ==="
