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
