# OpenWebRX+ (alpha)

> [!WARNING]
> **EXTREME ALPHA CODE. Use at your own risk.**
> This is a personal, untested wrapper built for one home setup (Raspberry Pi 5, RTL-SDR Blog V3).
> It is not affiliated with OpenWebRX+, its image maintainers or Home Assistant, may break at any time,
> and comes with no support or warranty. Read the files before installing.


Browser-based SDR receiver for the RTL-SDR Blog V3 on this Pi.

- Open `http://<home-assistant-ip>:8073/` from any device on the home network.
- Set **admin_user** and **admin_password** in this app's Configuration tab, then
  restart the app. On every start the admin user is created if missing, or its
  password is reset to the one in the Configuration tab (so a forgotten password
  is fixed by setting a new one there and restarting). Log in at `/login`;
  settings page: `/settings`.
- Only one program can use the SDR at a time: keep the rtl_433 app stopped.
- Settings are stored in the app's /data folder, so they survive updates.

## Speaker stream (port 8074)

`http://<home-assistant-ip>:8074/stream.mp3?freq=119480000&mod=am&squelch=-55`
plays one channel as MP3 (for Google Cast speakers via `media_player.play_media`).
`/status` shows what is streaming. The stream will not change band while people are
listening unless `force=1` is added; it stops if someone changes band in the web UI.
