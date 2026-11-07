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
        samp_rate=2400000, start_freq=125600000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-118": dict(
        name="Air: Southampton Tower + Bournemouth Radar (118-120 MHz)", center_freq=int(119.0 * MHZ),
        samp_rate=2400000, start_freq=119475000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-121": dict(
        name="Air: Solent Radar + 121.5 emergency (120-122 MHz)", center_freq=int(121.3 * MHZ),
        samp_rate=2400000, start_freq=121500000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-lon-128": dict(
        name="Air: London Control Hurn (127.5-129.7 MHz)", center_freq=int(128.625 * MHZ),
        samp_rate=2400000, start_freq=129425000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-air-lon-135": dict(
        name="Air: London Control Hurn East + BOH ATIS (133.7-135.8 MHz)", center_freq=int(134.75 * MHZ),
        samp_rate=2400000, start_freq=135050000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-marine": dict(
        name="Marine VHF (ch 16, Poole, Solent)", center_freq=int(156.6 * MHZ),
        samp_rate=2400000, start_freq=156800000, start_mod="nfm", tuning_step="5000", rf_gain=40),
    "local-pmr446": dict(
        name="PMR446 walkie-talkies", center_freq=int(446.1 * MHZ),
        samp_rate=2400000, start_freq=446006250, start_mod="nfm", tuning_step="5000", rf_gain=40),
    # 0.0.11: FM broadcast (wide FM). Each profile covers 2.4 MHz; with free tuning
    # on, typing any 87.5-108 MHz frequency also moves the receiver there.
    "local-fm-88": dict(
        name="FM broadcast 87.8-90.2 MHz", center_freq=int(89.0 * MHZ),
        samp_rate=2400000, start_freq=int(88.5 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    "local-fm-93": dict(
        name="FM broadcast 91.8-94.2 MHz", center_freq=int(93.0 * MHZ),
        samp_rate=2400000, start_freq=int(93.0 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    "local-fm-96": dict(
        name="FM broadcast 95-97.4 MHz (BBC Radio Solent 96.1)", center_freq=int(96.2 * MHZ),
        samp_rate=2400000, start_freq=int(96.1 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    "local-fm-99": dict(
        name="FM broadcast 97.8-100.2 MHz", center_freq=int(99.0 * MHZ),
        samp_rate=2400000, start_freq=int(99.0 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    "local-fm-103": dict(
        name="FM broadcast 102.6-105 MHz (Radio Solent 103.8)", center_freq=int(103.8 * MHZ),
        samp_rate=2400000, start_freq=int(103.8 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    "local-fm-106": dict(
        name="FM broadcast 104.6-107 MHz (Wave 105.2)", center_freq=int(105.8 * MHZ),
        samp_rate=2400000, start_freq=int(105.2 * MHZ), start_mod="wfm", tuning_step="100000", rf_gain=20),
    # DAB national multiplexes (one ensemble per profile, 2.048 MS/s).
    "local-dab-12b": dict(
        name="DAB 12B BBC National", center_freq=225648000,
        samp_rate=2048000, start_freq=225648000, start_mod="dab", tuning_step="1000", rf_gain=30),
    "local-dab-11d": dict(
        name="DAB 11D Digital One", center_freq=222064000,
        samp_rate=2048000, start_freq=222064000, start_mod="dab", tuning_step="1000", rf_gain=30),
    "local-dab-11a": dict(
        name="DAB 11A Sound Digital", center_freq=216928000,
        samp_rate=2048000, start_freq=216928000, start_mod="dab", tuning_step="1000", rf_gain=30),
    # Aviation data and other useful bands.
    "local-air-acars": dict(
        name="Air: ACARS / VDL2 (130.9-133.3 MHz)", center_freq=int(132.1 * MHZ),
        samp_rate=2400000, start_freq=131525000, start_mod="am", tuning_step="5000", rf_gain=40),
    "local-wxsat-137": dict(
        name="Weather satellites (Meteor-M 137 MHz)", center_freq=int(137.5 * MHZ),
        samp_rate=2400000, start_freq=137900000, start_mod="nfm", tuning_step="1000", rf_gain=40),
    "local-ism-433": dict(
        name="433 MHz ISM (sensors, key fobs)", center_freq=int(433.92 * MHZ),
        samp_rate=2400000, start_freq=433920000, start_mod="nfm", tuning_step="1000", rf_gain=30),
    "local-ism-868": dict(
        name="868 MHz ISM (LoRa, alarms, smart devices)", center_freq=int(868.3 * MHZ),
        samp_rate=2400000, start_freq=868300000, start_mod="nfm", tuning_step="1000", rf_gain=40),
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
    # 0.0.6 fix: earlier versions used 8.33 kHz channel names as start frequencies.
    fixed = []
    for pid, wrong, right in (("local-air-bournemouth", 125605000, 125600000),
                              ("local-air-118", 119480000, 119475000)):
        if pid in profiles and profiles[pid].get("start_freq") == wrong:
            profiles[pid]["start_freq"] = right
            fixed.append(pid)
    # 0.0.9: allow free tuning (needed by the sweep; lets the web UI type any frequency).
    retune = False
    if os.environ.get("ALLOW_RETUNE", "True") != "False" and not settings.get("allow_center_freq_changes"):
        settings["allow_center_freq_changes"] = True
        retune = True
    if not added and not fixed and not retune:
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
    print("+++ add-profiles: added %s; fixed start freq %s; free tuning %s"
          % (", ".join(added) or "none", ", ".join(fixed) or "none", "enabled" if retune else "unchanged"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop OpenWebRX+ starting
        print("+++ add-profiles: skipped after error: %r" % (e,))
