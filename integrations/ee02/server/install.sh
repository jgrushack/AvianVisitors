#!/bin/sh
set -eu
install -d -m 755 /etc/bird-renderer /var/lib/bird-renderer /opt/bird-renderer/avian-visitors/avian/assets/illustrations
if [ ! -e /etc/bird-renderer/config.json ]; then
    install -m 644 /opt/bird-renderer/config.json /etc/bird-renderer/config.json
fi
chown -R birdframe:birdframe /var/lib/bird-renderer
install -m 644 /opt/bird-renderer/bird-history.service /opt/bird-renderer/bird-history.timer /opt/bird-renderer/bird-image.service /opt/bird-renderer/bird-render.service /opt/bird-renderer/bird-render.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bird-image.service bird-render.timer bird-history.timer
# Successful history sync triggers rendering after the HTTP server is available.
systemctl start --no-block bird-history.service
