#!/usr/bin/env python3
"""Stream one OpenWebRX+ channel as MP3 over HTTP (for Home Assistant / Google Cast).

GET /stream.mp3?freq=119480000&mod=am[&squelch=auto|-55][&margin=2][&bw=7000][&force=1]
    freq may be an aviation channel name (8.33 kHz names are converted to the carrier).
GET /status

The helper joins OpenWebRX+ as an ordinary (hidden) listener.

Sharing rules ("the lock"):
- A frequency inside the band already in use is tuned without disturbing anyone.
- Changing band is refused (HTTP 409) while other people are listening, or while
  another stream holds a different band, unless force=1.
- If a person changes the band while a stream is playing, the stream stops
  (people win over streams).
"""
import json
import math
import logging
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import websocket  # python3-websocket (websocket-client)

OWRX_WS = "ws://127.0.0.1:8073/ws/"
PORT = int(os.environ.get("STREAM_PORT", "8074"))
RATE = 12000                      # audio sample rate requested from OpenWebRX+
CHUNK_S = 0.05                    # pacing interval (s)
SETTINGS = "/data/owrx/settings.json"
DEFAULT_SQUELCH = float(os.environ.get("STREAM_SQUELCH", "-150"))
BAND_FRACTION = 0.9              # usable share of the band either side of centre
BANDWIDTH = {"am": 4000, "nfm": 7500, "usb": 2700, "lsb": 2700, "sam": 4000}


def airband_channel(hz):
    """Aviation channel name -> (carrier Hz, half-bandwidth Hz).

    VHF airband (118-137 MHz) channel names ending .x05/.x10/.x15 (and .x30/.x35/.x40
    etc.) are 8.33 kHz channels: carrier = 25 kHz block + 0 / 8.333 / 16.667 kHz.
    Names on the 25 kHz raster are 25 kHz channels (carrier = name).
    """
    khz = int(round(hz / 1000.0))
    if not 118000 <= khz <= 137000:
        return None
    r = khz % 25
    base = khz - r
    if r == 0:
        return base * 1000, 6000                       # 25 kHz channel
    if r in (5, 10, 15):
        return int(round(base * 1000 + (r // 5 - 1) * 25000 / 3.0)), 3500   # 8.33 kHz channel
    return None


def channel_plan(hz, mod):
    """(tuning Hz, half-bandwidth Hz) for a requested channel/frequency."""
    if mod in ("am", "sam"):
        ab = airband_channel(hz)
        if ab:
            return ab
    if mod == "nfm" and 446000000 <= hz <= 446200000:  # PMR446, 12.5 kHz channels
        return hz, 5000
    return hz, BANDWIDTH.get(mod, 4000)

logging.basicConfig(level=logging.INFO, format="%(asctime)s sdr-stream %(levelname)s %(message)s")
log = logging.getLogger("sdr-stream")


class Busy(Exception):
    pass


# --------------------------------------------------------------------------
# IMA ADPCM with OpenWebRX "SYNC" frames (port of htdocs/lib/AudioEngine.js)
# --------------------------------------------------------------------------
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]
STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
]


class AdpcmDecoder:
    SYNC = b"SYNC"

    def __init__(self):
        self.step_index = 0
        self.predictor = 0
        self.step = 0
        self.synchronized = 0
        self.sync_counter = 0
        self.phase = 0
        self.sync_buf = bytearray()

    def _nibble(self, n):
        self.step_index = min(max(self.step_index + INDEX_TABLE[n], 0), 88)
        diff = self.step >> 3
        if n & 1:
            diff += self.step >> 2
        if n & 2:
            diff += self.step >> 1
        if n & 4:
            diff += self.step
        if n & 8:
            diff = -diff
        self.predictor = min(max(self.predictor + diff, -32768), 32767)
        self.step = STEP_TABLE[self.step_index]
        return self.predictor

    def decode(self, data):
        out = bytearray()
        for b in data:
            if self.phase == 0:
                if b != self.SYNC[self.synchronized]:
                    self.synchronized = 0
                else:
                    self.synchronized += 1
                if self.synchronized == 4:
                    self.sync_buf = bytearray()
                    self.phase = 1
            elif self.phase == 1:
                self.sync_buf.append(b)
                if len(self.sync_buf) == 4:
                    self.step_index = int.from_bytes(self.sync_buf[0:2], "little", signed=True)
                    self.predictor = int.from_bytes(self.sync_buf[2:4], "little", signed=True)
                    self.sync_counter = 1000
                    self.phase = 2
            else:
                for n in (b & 0x0F, b >> 4):
                    out += self._nibble(n).to_bytes(2, "little", signed=True)
                if self.sync_counter == 0:
                    self.synchronized = 0
                    self.phase = 0
                else:
                    self.sync_counter -= 1
        return bytes(out)


# --------------------------------------------------------------------------
# Shared state / lock
# --------------------------------------------------------------------------
STATE_LOCK = threading.Lock()
SESSIONS = []          # active Session objects
LAST = {"event": None, "time": None}


def note(event):
    LAST["event"] = event
    LAST["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log.info(event)


def find_profile(freq):
    """Best RTL-SDR profile containing freq: (sdr_id, profile_id, center, samp_rate)."""
    try:
        with open(SETTINGS) as f:
            settings = json.load(f)
    except Exception:
        return None
    best = None
    for sid, sdr in settings.get("sdrs", {}).items():
        if sdr.get("type") != "rtl_sdr" or sdr.get("enabled") is False:
            continue
        for pid, p in sdr.get("profiles", {}).items():
            c, sr = p.get("center_freq"), p.get("samp_rate")
            if not c or not sr:
                continue
            d = abs(freq - c)
            if d <= sr / 2 * BAND_FRACTION and (best is None or d < best[0]):
                best = (d, sid, pid, c, sr)
    return best[1:] if best else None


class Session:
    def __init__(self, freq, mod, squelch, force, margin=2.0, bw=None):
        # squelch None = automatic: measure the noise floor, then add margin (dB)
        self.channel = freq                          # what was asked for (e.g. 8.33 channel name)
        tune, half_bw = channel_plan(freq, mod)
        self.freq, self.mod, self.squelch, self.force = tune, mod, squelch, force
        self.half_bw = int(bw) if bw else half_bw
        self.margin = margin
        self.smeter = []
        self.ws = None
        self.config = {}
        self.clients = None
        self.buf = bytearray()
        self.buf_lock = threading.Lock()
        self.decoder = AdpcmDecoder()
        self.stop_reason = None
        self.started = time.time()
        self.profile = None

    # ---- OpenWebRX+ side -------------------------------------------------
    def _send(self, obj):
        self.ws.send(obj if isinstance(obj, str) else json.dumps(obj))

    def _handle_text(self, msg):
        if msg.startswith("CLIENT DE SERVER"):
            return
        try:
            j = json.loads(msg)
        except ValueError:
            return
        t = j.get("type")
        if t == "config":
            v = j.get("value", {})
            old_center = self.config.get("center_freq")
            self.config.update(v)
            if (self.profile and "center_freq" in v and old_center is not None
                    and v["center_freq"] != old_center and not self._retuning):
                self.stop_reason = "band changed by another listener"
        elif t == "clients":
            self.clients = j.get("value")
        elif t == "smeter":
            v = j.get("value") or 0
            self.smeter.append(10 * math.log10(v) if v > 0 else -150.0)

    def _in_band(self):
        c, sr = self.config.get("center_freq"), self.config.get("samp_rate")
        return c is not None and sr is not None and abs(self.freq - c) <= sr / 2 * BAND_FRACTION

    def _wait(self, cond, timeout):
        end = time.time() + timeout
        while time.time() < end and not cond():
            self.ws.settimeout(max(0.1, end - time.time()))
            try:
                msg = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            if isinstance(msg, str):
                self._handle_text(msg)
        return cond()

    def open(self):
        self._retuning = False
        self.ws = websocket.create_connection(OWRX_WS, timeout=10)
        self._send("SERVER DE CLIENT client=ha-sdr-stream type=receiver")
        self._send({"type": "connectionproperties", "params": {"output_rate": RATE, "hd_output_rate": 48000}})
        if not self._wait(lambda: "center_freq" in self.config and self.clients is not None, 8):
            if "center_freq" not in self.config:
                raise RuntimeError("OpenWebRX+ did not send its configuration")
        others = max((self.clients or 1) - 1, 0)

        if SWEEP.running:
            if not self.force:
                raise Busy("a frequency sweep is running (%s); use force=1 to stop it" % SWEEP.progress())
            SWEEP.stop("stopped by a forced stream")
            time.sleep(1.5)
        with STATE_LOCK:
            holders = [s for s in SESSIONS if s.profile and not s.stop_reason]
        if not self._in_band():
            target = find_profile(self.freq)
            if target is None:
                raise Busy("no RTL-SDR band profile covers %.4f MHz" % (self.freq / 1e6))
            sid, pid, center, _sr = target
            other_band_holders = [s for s in holders if s.profile != (sid, pid)]
            if not self.force:
                if others > 0:
                    raise Busy("%d other listener(s) on %s; use force=1 to take over"
                               % (others, self.config.get("profile_id", "another band")))
                if other_band_holders:
                    raise Busy("another stream holds %.4f MHz; use force=1"
                               % (other_band_holders[0].freq / 1e6))
            for s in other_band_holders:
                s.stop_reason = "taken over by a forced stream"
            self._retuning = True
            self._send({"type": "selectprofile", "params": {"profile": "%s|%s" % (sid, pid)}})
            if not self._wait(lambda: self.config.get("center_freq") == center, 10):
                raise RuntimeError("band change to %s did not complete" % pid)
            self._retuning = False
            self.profile = (sid, pid)
            note("switched band to %s for %.4f MHz" % (pid, self.freq / 1e6))
        else:
            self.profile = (self.config.get("sdr_id"), self.config.get("profile_id"))

        bw = self.half_bw
        auto = self.squelch is None
        self._send({"type": "dspcontrol", "params": {
            "low_cut": -bw, "high_cut": bw,
            "offset_freq": int(self.freq - self.config["center_freq"]),
            "mod": self.mod, "squelch_level": -150 if auto else self.squelch}})
        self._send({"type": "dspcontrol", "action": "start"})
        if auto:
            # Measure the channel noise (~3 s); squelch = loud end of the noise (95th
            # percentile) + margin, so noise stays shut but weak calls still open it.
            self.smeter = []
            self._wait(lambda: len(self.smeter) >= 12, 4)
            if self.smeter:
                d = sorted(self.smeter)
                median = d[len(d) // 2]
                top = d[min(len(d) - 1, int(0.95 * len(d)))]
                if top - median > 6:      # a call was on air while measuring: trust the median
                    top = median + 2
                self.squelch = round(top + self.margin, 1)
                note("auto squelch %.4f MHz: noise median %.1f / p95 %.1f dB -> squelch %.1f dB"
                     % (self.freq / 1e6, median, top, self.squelch))
            else:
                self.squelch = -150
                note("auto squelch: no S-meter readings, squelch left open")
            self._send({"type": "dspcontrol", "params": {"squelch_level": self.squelch}})
        with STATE_LOCK:
            SESSIONS.append(self)
        note("streaming channel %.3f -> %.5f MHz %s +/-%d Hz (squelch %s)"
             % (self.channel / 1e6, self.freq / 1e6, self.mod, self.half_bw, self.squelch))

    def receive_loop(self):
        self.ws.settimeout(1)
        while not self.stop_reason:
            try:
                msg = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                self.stop_reason = "OpenWebRX+ connection lost (%s)" % e
                break
            if isinstance(msg, str):
                self._handle_text(msg)
            elif msg and msg[0] == 0x02:
                payload = msg[1:]
                if self.config.get("audio_compression") == "adpcm":
                    payload = self.decoder.decode(payload)
                with self.buf_lock:
                    self.buf += payload
                    if len(self.buf) > RATE * 2:      # keep at most ~1 s queued
                        del self.buf[: len(self.buf) - RATE]

    def close(self):
        with STATE_LOCK:
            if self in SESSIONS:
                SESSIONS.remove(self)
        try:
            self.ws.close()
        except Exception:
            pass

    # ---- HTTP side -------------------------------------------------------
    def stream_to(self, wfile):
        lame = subprocess.Popen(
            ["lame", "--quiet", "-r", "-s", str(RATE / 1000), "--bitwidth", "16", "--signed",
             "--little-endian", "-m", "m", "--resample", "44.1", "-b", "64", "-", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)

        def pump():
            try:
                while True:
                    chunk = lame.stdout.read(4096)
                    if not chunk:
                        break
                    wfile.write(chunk)
                    wfile.flush()
            except Exception:
                pass
            if not self.stop_reason:
                self.stop_reason = "speaker disconnected"

        threading.Thread(target=self.receive_loop, daemon=True).start()
        threading.Thread(target=pump, daemon=True).start()
        need = int(RATE * CHUNK_S) * 2
        next_t = time.monotonic()
        try:
            while not self.stop_reason:
                with self.buf_lock:
                    chunk = bytes(self.buf[:need])
                    del self.buf[:need]
                if len(chunk) < need:                     # squelched/quiet: pad with silence
                    chunk += b"\x00" * (need - len(chunk))
                lame.stdin.write(chunk)
                next_t += CHUNK_S
                time.sleep(max(0, next_t - time.monotonic()))
        except Exception as e:
            self.stop_reason = self.stop_reason or "encoder stopped (%s)" % e
        finally:
            for f in (lame.stdin,):
                try:
                    f.close()
                except Exception:
                    pass
            lame.kill()
            note("stream %.4f MHz ended: %s" % (self.freq / 1e6, self.stop_reason))



# --------------------------------------------------------------------------
# Full-range sweep (uses OpenWebRX+ waterfall frames; needs allow_center_freq_changes)
# --------------------------------------------------------------------------
UK_BANDS = [
    (26.965, 27.991, "CB 27 MHz"), (28.0, 29.7, "10 m amateur"), (50.0, 52.0, "6 m amateur"),
    (70.0, 70.5, "4 m amateur"), (87.5, 108.0, "FM broadcast"), (108.0, 117.975, "VOR/ILS navigation"),
    (118.0, 137.0, "VHF airband"), (137.0, 138.0, "weather satellites"), (138.0, 144.0, "military/PMR"),
    (144.0, 146.0, "2 m amateur"), (146.0, 156.0, "PMR/business/paging"), (156.0, 162.05, "marine VHF (incl. AIS 161.975/162.025)"),
    (162.05, 174.0, "business radio"), (174.0, 240.0, "DAB digital radio"), (225.0, 400.0, "military UHF airband"),
    (380.0, 400.0, "TETRA (emergency services, encrypted)"), (400.0, 430.0, "PMR/telemetry"),
    (430.0, 440.0, "70 cm amateur"), (433.05, 434.79, "433 MHz ISM devices"), (440.0, 470.0, "PMR/business (446 = PMR446)"),
    (470.0, 790.0, "digital TV (DVB-T)"), (790.0, 862.0, "4G 800 mobile"), (863.0, 870.0, "868 MHz ISM devices"),
    (870.0, 960.0, "GSM/4G 900 mobile"), (960.0, 1215.0, "aeronautical radionavigation (DME, SSR 1030, ADS-B 1090)"),
    (1215.0, 1300.0, "GNSS L2 / 23 cm"), (1300.0, 1350.0, "radar"), (1525.0, 1559.0, "Inmarsat"),
    (1559.0, 1610.0, "GNSS L1 (GPS/Galileo)"), (1610.0, 1700.0, "satellite / meteorological"),
]


def band_name(mhz):
    names = [n for lo, hi, n in UK_BANDS if lo <= mhz <= hi]
    return names[-1] if names else "other"


class Sweeper:
    RESULT = "/data/sweep-latest.json"

    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_reason = None
        self.params = {}
        self.current = None
        self.started = None
        self.hits = []
        self.steps_done = 0
        self.steps_total = 0

    def progress(self):
        if not self.running:
            return "idle"
        return "%d/%d steps, at %.1f MHz" % (self.steps_done, self.steps_total, (self.current or 0) / 1e6)

    def start(self, start_mhz, stop_mhz, step_mhz, dwell_s, threshold_db):
        if self.running:
            raise Busy("sweep already running (%s)" % self.progress())
        with STATE_LOCK:
            if SESSIONS:
                raise Busy("a stream is playing; stop it first")
        self.params = dict(start_mhz=start_mhz, stop_mhz=stop_mhz, step_mhz=step_mhz,
                           dwell_s=dwell_s, threshold_db=threshold_db)
        self.stop_reason = None
        self.hits = []
        self.steps_done = 0
        self.steps_total = int((stop_mhz - start_mhz) / step_mhz) + 1
        self.running = True
        self.started = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self, reason):
        self.stop_reason = reason

    def _run(self):
        ws = None
        try:
            ws = websocket.create_connection(OWRX_WS, timeout=10)
            ws.send("SERVER DE CLIENT client=ha-sdr-sweep type=receiver")
            ws.send(json.dumps({"type": "connectionproperties", "params": {"output_rate": RATE, "hd_output_rate": 48000}}))
            cfg, clients = {}, [None]

            def pump(timeout, want_fft=False):
                frames = []
                end = time.time() + timeout
                while time.time() < end:
                    ws.settimeout(max(0.05, end - time.time()))
                    try:
                        m = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        break
                    if isinstance(m, str):
                        if m.startswith("{"):
                            j = json.loads(m)
                            if j.get("type") == "config":
                                cfg.update(j.get("value", {}))
                            elif j.get("type") == "clients":
                                clients[0] = j.get("value")
                    elif want_fft and m and m[0] == 0x01:
                        frames.append(m[1:])
                return frames

            pump(3)
            if "center_freq" not in cfg:
                raise RuntimeError("no configuration from OpenWebRX+")
            if (clients[0] or 1) > 1:
                raise Busy("people are listening; sweep not started")
            original = "%s|%s" % (cfg.get("sdr_id"), cfg.get("profile_id"))
            note("sweep started %.1f-%.1f MHz (from profile %s)"
                 % (self.params["start_mhz"], self.params["stop_mhz"], original))
            f = self.params["start_mhz"] * 1e6
            try:
                while f <= self.params["stop_mhz"] * 1e6 and not self.stop_reason:
                    self.current = f
                    ws.send(json.dumps({"type": "setfrequency", "params": {"frequency": int(f), "key": ""}}))
                    end = time.time() + 3
                    while time.time() < end and cfg.get("center_freq") != int(f):
                        pump(0.2)
                    if cfg.get("center_freq") != int(f):
                        raise RuntimeError("radio would not retune to %.1f MHz "
                                           "(allow_center_freq_changes off?)" % (f / 1e6))
                    pump(0.5)                                    # settle
                    raw = pump(self.params["dwell_s"], want_fft=True)
                    if (clients[0] or 1) > 1:
                        self.stop_reason = "someone started listening"
                        break
                    self._analyse(raw, cfg)
                    self.steps_done += 1
                    f += self.params["step_mhz"] * 1e6
            finally:
                try:
                    ws.send(json.dumps({"type": "selectprofile", "params": {"profile": original}}))
                    pump(1)
                except Exception:
                    pass
        except Exception as e:
            self.stop_reason = self.stop_reason or str(e)
        finally:
            try:
                ws and ws.close()
            except Exception:
                pass
            self.running = False
            self._save()
            note("sweep finished: %d steps, %d signals%s" % (
                self.steps_done, len(self.hits), (" (" + self.stop_reason + ")") if self.stop_reason else ""))

    def _analyse(self, raw, cfg):
        if not raw:
            return
        comp = cfg.get("fft_compression", "adpcm") == "adpcm"
        frames = []
        for p in raw:
            if comp:
                d = AdpcmDecoder()
                d.step = 0
                pcm = bytearray()
                for b in p:
                    for n in (b & 0x0F, b >> 4):
                        pcm += d._nibble(n).to_bytes(2, "little", signed=True)
                vals = [int.from_bytes(pcm[i:i + 2], "little", signed=True) / 100.0 for i in range(20, len(pcm), 2)]
            else:
                import struct
                vals = list(struct.unpack("<%df" % (len(p) // 4), p))
            frames.append(vals)
        n = min(len(v) for v in frames)
        c, sr = cfg["center_freq"], cfg["samp_rate"]
        cols = list(zip(*[v[:n] for v in frames]))
        med = [sorted(col)[len(col) // 2] for col in cols]
        mx = [max(col) for col in cols]
        floor = sorted(med)[len(med) // 2]
        thr = self.params["threshold_db"]
        groups = []
        for i in range(n):
            hz = c - sr / 2 + (i + 0.5) * sr / n
            if abs(hz - c) < 8000 or abs(hz - c) > sr / 2 * 0.85:
                continue
            if mx[i] - floor < thr:
                continue
            duty = sum(1 for x in cols[i] if x - floor >= thr) / float(len(cols[i]))
            item = (hz, mx[i] - floor, med[i] - floor, duty)
            if groups and hz - groups[-1][-1][0] < 15000:
                groups[-1].append(item)
            else:
                groups.append([item])
        for g in groups:
            hz, peak, medrel, duty = max(g, key=lambda x: x[1])
            width = (g[-1][0] - g[0][0]) + sr / n
            spur = any(abs(hz - k * 28.8e6) < 5000 for k in range(1, 62))
            self.hits.append({
                "mhz": round(hz / 1e6, 4), "peak_db": round(peak, 1), "typical_db": round(medrel, 1),
                "on_air_pct": round(100 * duty), "width_khz": round(width / 1000, 1),
                "kind": "steady" if duty > 0.8 else ("intermittent" if duty < 0.5 else "frequent"),
                "band": band_name(hz / 1e6), "possible_receiver_spur": spur})

    def _save(self):
        try:
            with open(self.RESULT, "w") as fh:
                json.dump(self.result(), fh, indent=1)
        except Exception as e:
            log.warning("could not save sweep: %s", e)

    def result(self):
        return {"running": self.running, "progress": self.progress(), "params": self.params,
                "started": self.started and time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)),
                "stopped_because": self.stop_reason, "steps_done": self.steps_done,
                "signals": sorted(self.hits, key=lambda h: h["mhz"])}


SWEEP = Sweeper()

class Handler(BaseHTTPRequestHandler):
    server_version = "ha-sdr-stream/0.1"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def _json(self, code, obj):
        body = json.dumps(obj, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if url.path == "/status":
            with STATE_LOCK:
                active = [{"channel": "%.3f" % (s.channel / 1e6), "freq_mhz": round(s.freq / 1e6, 6),
                           "mod": s.mod, "filter_hz": 2 * s.half_bw, "profile": s.profile and s.profile[1],
                           "squelch_db": s.squelch,
                           "since": time.strftime("%H:%M:%S", time.localtime(s.started)),
                           "other_listeners": max((s.clients or 1) - 1, 0)} for s in SESSIONS]
            return self._json(200, {"streaming": bool(active), "streams": active,
                                    "last_event": LAST["event"], "last_event_time": LAST["time"]})
        if url.path == "/sweep/start":
            try:
                SWEEP.start(float(q.get("start", 24)), float(q.get("stop", 1700)), float(q.get("step", 2.0)),
                            float(q.get("dwell", 2.0)), float(q.get("threshold", 10)))
            except Busy as e:
                return self._json(409, {"error": "busy", "reason": str(e)})
            return self._json(200, {"started": True, "steps": SWEEP.steps_total})
        if url.path == "/sweep/stop":
            SWEEP.stop("stopped on request")
            return self._json(200, {"stopping": True})
        if url.path in ("/sweep", "/sweep/status"):
            if not SWEEP.running and not SWEEP.hits:
                try:
                    with open(Sweeper.RESULT) as fh:
                        return self._json(200, json.load(fh))
                except Exception:
                    pass
            return self._json(200, SWEEP.result())
        if url.path not in ("/stream.mp3", "/stream"):
            return self._json(404, {"error": "use /stream.mp3?freq=HZ&mod=am or /status"})
        try:
            freq = int(float(q["freq"]))
        except (KeyError, ValueError):
            return self._json(400, {"error": "freq (Hz) is required"})
        mod = q.get("mod", "am").lower()
        sq = q.get("squelch", "auto").lower()
        try:
            squelch = None if sq == "auto" else float(sq)
            margin = float(q.get("margin", 2))
        except ValueError:
            return self._json(400, {"error": "squelch must be 'auto' or a number (dB)"})
        force = q.get("force", "0") in ("1", "true", "yes")

        bw = q.get("bw")
        session = Session(freq, mod, squelch, force, margin, float(bw) / 2 if bw else None)
        try:
            session.open()
        except Busy as e:
            note("refused %.4f MHz: %s" % (freq / 1e6, e))
            session.close()
            return self._json(409, {"error": "busy", "reason": str(e)})
        except Exception as e:
            note("failed %.4f MHz: %s" % (freq / 1e6, e))
            session.close()
            return self._json(503, {"error": str(e)})

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("icy-name", "SDR %.4f MHz %s" % (freq / 1e6, mod.upper()))
        self.end_headers()
        try:
            session.stream_to(self.wfile)
        finally:
            session.close()



def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    note("listening on port %d" % PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
