#!/bin/bash
# Home Assistant wrapper for the slechev/openwebrxplus image.
# Reads the app options, keeps OpenWebRX+ settings in /data (survives updates),
# then hands over to the image's own s6 init.
set -e

OPTS=/data/options.json
opt() {
  python3 -c "import json; v=json.load(open('$OPTS')).get('$1'); print(v if v else '')"
}

if [ -f "$OPTS" ]; then
  OPENWEBRX_ADMIN_USER="$(opt admin_user)"
  OPENWEBRX_ADMIN_PASSWORD="$(opt admin_password)"
  TZ="$(opt timezone)"
  export OPENWEBRX_ADMIN_USER OPENWEBRX_ADMIN_PASSWORD TZ
fi

# Persistent settings, users and receiver data live in /data/owrx.
mkdir -p /data/owrx /etc/openwebrx/openwebrx.conf.d
if [ -d /owrx-init/var ]; then
  cp -an /owrx-init/var/. /data/owrx/ 2>/dev/null || true
fi
cat > /etc/openwebrx/openwebrx.conf.d/90-home-assistant.conf <<CONF
[core]
data_directory = /data/owrx
CONF

exec /init "$@"
