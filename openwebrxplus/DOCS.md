# OpenWebRX+ (alpha)

> [!WARNING]
> **EXTREME ALPHA CODE. Use at your own risk.**
> This is a personal, untested wrapper built for one home setup (Raspberry Pi 5, RTL-SDR Blog V3).
> It is not affiliated with OpenWebRX+, its image maintainers or Home Assistant, may break at any time,
> and comes with no support or warranty. Read the files before installing.


Browser-based SDR receiver for the RTL-SDR Blog V3 on this Pi.

- Open `http://<home-assistant-ip>:8073/` from any device on the home network.
- Set **admin_password** in this app's Configuration tab before the first start;
  the admin user is created on first start only. Settings page: `/settings`.
- Only one program can use the SDR at a time: keep the rtl_433 app stopped.
- Settings are stored in the app's /data folder, so they survive updates.
