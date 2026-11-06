#!/usr/bin/env python3
"""Add local band profiles to the RTL-SDR in OpenWebRX+ settings.

Runs before OpenWebRX+ starts. Only ADDS profiles whose id is missing;
never changes or removes anything already there. Keeps a one-off backup.
"""
import json
import os
import shutil

from owrx.config.defaults import defaultConfig
from owrx.config.migration import Migrator
from owrx.jsons import Encoder

SETTINGS = "/data/owrx/settings.json"
MHZ = 1_000_000

LOCAL_PROFILES = {
    "local-air-bournemouth": dict(
        name="Air: Bournemouth Tower (124-126 MHz)", center_freq=int(125.0 * MHZ),
        samp_rate=2400000, start_freq=125605000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-118": dict(
        name="Air: Southampton Tower + Bournemouth Radar (118-120 MHz)", center_freq=int(119.0 * MHZ),
        samp_rate=2400000, start_freq=119480000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-121": dict(
        name="Air: Solent Radar + 121.5 emergency (120-122 MHz)", center_freq=int(121.3 * MHZ),
        samp_rate=2400000, start_freq=121500000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-marine": dict(
        name="Marine VHF (ch 16, Poole, Solent)", center_freq=int(156.6 * MHZ),
        samp_rate=2400000, start_freq=156800000, start_mod="nfm", tuning_step="5000", rf_gain=40),
    "local-pmr446": dict(
        name="PMR446 walkie-talkies", center_freq=int(446.1 * MHZ),
        samp_rate=2400000, start_freq=446006250, start_mod="nfm", tuning_step="5000", rf_gain=40),
}


def main():
    settings = {}
    if os.path.exists(SETTINGS):
        with open(SETTINGS) as f:
            settings = json.load(f)
    settings.setdefault("version", Migrator.currentVersion)
    if "sdrs" not in settings:
        settings["sdrs"] = json.loads(json.dumps(defaultConfig["sdrs"], cls=Encoder))

    rtl = next((s for s in settings["sdrs"].values() if s.get("type") == "rtl_sdr"), None)
    if rtl is None:
        print("+++ add-profiles: no RTL-SDR device in settings, nothing added")
        return
    profiles = rtl.setdefault("profiles", {})
    added = [pid for pid in LOCAL_PROFILES if pid not in profiles]
    if not added:
        print("+++ add-profiles: local profiles already present")
        return
    for pid in added:
        profiles[pid] = LOCAL_PROFILES[pid]

    if os.path.exists(SETTINGS) and not os.path.exists(SETTINGS + ".before-local-profiles"):
        shutil.copy2(SETTINGS, SETTINGS + ".before-local-profiles")
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=4)
    os.replace(tmp, SETTINGS)
    print("+++ add-profiles: added " + ", ".join(added))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop OpenWebRX+ starting
        print("+++ add-profiles: skipped after error: %r" % (e,))
