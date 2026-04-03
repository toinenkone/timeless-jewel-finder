# Timeless Jewel Finder

A Flask web app for Path of Exile that finds passive tree socket locations with 2+ matching notables for a given timeless jewel seed.

## Production Server Deployment

**Server path:** `/home/cc/code/timeless-jewel-finder`
**Service:** `jewel-finder` (systemd, runs as user `cc`)
**PoB data:** already present on the server at the default path

### First-time setup

```bash
# 1. Clone the repo
git clone https://github.com/toinenkone/timeless-jewel-finder.git /home/cc/code/timeless-jewel-finder

# 2. Install dependencies
pip3 install flask

# 3. Install the systemd service
sudo tee /etc/systemd/system/jewel-finder.service <<'EOF'
[Unit]
Description=Timeless Jewel Finder
After=network.target

[Service]
WorkingDirectory=/home/cc/code/timeless-jewel-finder
ExecStart=/usr/bin/python3 app.py
Restart=on-failure
User=cc
Environment=AUTH_USERNAME=timeless
Environment=AUTH_PASSWORD=iunderstandtherisksofusingaigeneratedcode

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now jewel-finder
```

### Updating to latest code

```bash
cd /home/cc/code/timeless-jewel-finder
git pull
sudo systemctl restart jewel-finder
```

No data migration required — PoB data files are not part of this repo and don't need to change.

### Service management

```bash
sudo systemctl status jewel-finder     # check status
sudo journalctl -u jewel-finder -f     # follow logs
sudo systemctl restart jewel-finder    # restart after update
sudo systemctl stop jewel-finder       # stop
```
