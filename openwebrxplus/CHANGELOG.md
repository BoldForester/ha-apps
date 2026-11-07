# Changelog

## 0.0.1-alpha

- First, untested release. Expect breakage.

## 0.0.2-alpha

- Local bookmarks: Bournemouth and Southampton airband, 2 m / 70 cm calling channels.
- Adds missing local band profiles (airband x3, marine VHF, PMR446) to the RTL-SDR; never edits existing ones. Turn off with `add_local_profiles: false`.
- Frequency scanner plugin (Scan / Skip / Block) loaded from the OpenWebRX+ plugins site.

## 0.0.3-alpha

- MP3 stream helper on port 8074 for Google Cast / Home Assistant:
  `/stream.mp3?freq=119480000&mod=am[&squelch=-55][&force=1]` and `/status`.
- Sharing rules: never changes band while people are listening or another stream
  holds a different band (HTTP 409 "busy") unless `force=1`; a stream stops if a
  person changes the band. Quiet/squelched periods are filled with silence.

## 0.0.4-alpha

- Automatic squelch (default): the stream measures the channel's noise floor for ~2 s
  and sets squelch `margin` dB above the loud end (95th percentile) of the noise (default 2). Use `squelch=-34` for a fixed level.
- /status shows the squelch in use.

## 0.0.5-alpha

- Accept frequencies up to 90% of the half-band from centre (was 85%), so 120.230 MHz is reachable on the 120-122 MHz airband profile.

## 0.0.6-alpha

- Aviation 8.33 kHz channel names are converted to carrier frequencies (e.g. 119.480 -> 119.4750 MHz); bookmarks and profile start frequencies corrected.
- Filter widths follow channel spacing: +/-3.5 kHz for 8.33 kHz channels, +/-6 kHz for 25 kHz airband, +/-7.5 kHz marine NFM, +/-5 kHz PMR446. Override with bw=.

## 0.0.7-alpha

- London Control (Hurn sectors) band profiles 127.5-129.7 and 133.7-135.8 MHz, and bookmarks (frequencies from scanner listings - verify).

## 0.0.8-alpha

- Auto squelch now = 95th percentile of ~3 s of channel noise + margin (default 2 dB), instead of the quietest reading + 7 dB. Keeps noise shut while letting weak calls through. If a call is on air during measurement, the median is used.

## 0.0.9-alpha

- Full-range sweep: `/sweep/start?start=24&stop=1700&step=2&dwell=2&threshold=10`, `/sweep` (progress/results), `/sweep/stop`. Logs every signal above the noise with band name, on-air share and possible receiver spurs (28.8 MHz harmonics). Only starts when nobody is listening; stops if someone connects; restores the band profile afterwards. Results kept in /data/sweep-latest.json.
- Enables OpenWebRX+ free tuning (`allow_center_freq_changes`), needed by the sweep. Option `allow_retune` (default true).

## 0.0.10-alpha

- Admin login follows the app options: on every start the admin user is created if
  missing, or its password is reset to `admin_password` (and the user re-enabled).
  Fixes being locked out after forgetting or changing the password.
