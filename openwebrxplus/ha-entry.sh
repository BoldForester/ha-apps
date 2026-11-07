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
  ALLOW_RETUNE="$(python3 -c "import json; print(json.load(open('$OPTS')).get('allow_retune', True))")"
  export OPENWEBRX_ADMIN_USER OPENWEBRX_ADMIN_PASSWORD TZ ALLOW_RETUNE
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

# Admin login: the app options are the source of truth. The image only
# creates the admin user when it doesn't exist, so a changed or forgotten
# password would never take effect. Create the user if missing, otherwise
# reset its password to the one in the app options, on every start.
if [ -n "${OPENWEBRX_ADMIN_USER:-}" ] && [ -n "${OPENWEBRX_ADMIN_PASSWORD:-}" ]; then
  if openwebrx admin --silent hasuser "$OPENWEBRX_ADMIN_USER" 2>/dev/null; then
    if OWRX_PASSWORD="$OPENWEBRX_ADMIN_PASSWORD" openwebrx admin --noninteractive resetpassword "$OPENWEBRX_ADMIN_USER"; then
      openwebrx admin --silent enableuser "$OPENWEBRX_ADMIN_USER" || true
      echo "[ha] Admin password for '$OPENWEBRX_ADMIN_USER' set from the app options."
    else
      echo "[ha] WARNING: could not reset the admin password."
    fi
  else
    if OWRX_PASSWORD="$OPENWEBRX_ADMIN_PASSWORD" openwebrx admin --noninteractive adduser "$OPENWEBRX_ADMIN_USER"; then
      echo "[ha] Admin user '$OPENWEBRX_ADMIN_USER' created from the app options."
    else
      echo "[ha] WARNING: could not create the admin user."
    fi
  fi
fi

# Local bookmarks (Bournemouth/Southampton airband, calling channels).
mkdir -p /etc/openwebrx/bookmarks.d
cp /ha/local-bookmarks.json /etc/openwebrx/bookmarks.d/zz-local.json

# Add local band profiles (only ones that are missing; never edits others).
if [ "${ADD_LOCAL_PROFILES:-True}" != "False" ]; then
  python3 /ha/add-profiles.py || true
fi

exec /init "$@"
