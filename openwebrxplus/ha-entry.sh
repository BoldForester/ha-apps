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
  ADD_LOCAL_PROFILES="$(python3 -c "import json; print(json.load(open('$OPTS')).get('add_local_profiles', True))")"
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

# Local bookmarks (Bournemouth/Southampton airband, calling channels).
mkdir -p /etc/openwebrx/bookmarks.d
cp /ha/local-bookmarks.json /etc/openwebrx/bookmarks.d/zz-local.json

# Add local band profiles (only ones that are missing; never edits others).
if [ "${ADD_LOCAL_PROFILES:-True}" != "False" ]; then
  python3 /ha/add-profiles.py || true
fi

exec /init "$@"
