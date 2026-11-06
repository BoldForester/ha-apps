# BoldForester Home Assistant apps

> [!WARNING]
> **EXTREME ALPHA CODE. Use at your own risk.**
> This is a personal, untested wrapper built for one home setup (Raspberry Pi 5, RTL-SDR Blog V3).
> It is not affiliated with OpenWebRX+, its image maintainers or Home Assistant, may break at any time,
> and comes with no support or warranty. Read the files before installing.


Home Assistant app repository.

| App | What it does |
|---|---|
| [OpenWebRX+](openwebrxplus) | Browser-based SDR receiver for a USB RTL-SDR, wrapping the [slechev/openwebrxplus](https://hub.docker.com/r/slechev/openwebrxplus) image. |

## Install

Settings → Apps → App store → ⋮ → Repositories → add `https://github.com/BoldForester/ha-apps`.

Set `admin_password` in the app's Configuration tab before the first start, then open `http://<home-assistant>:8073/`.
