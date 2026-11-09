"""
detect_decks.py - list the expansion decks attached to a Crazyflie.

Requirements:
    pip install cflib

Usage:
    python detect_decks.py                       # scans for the Crazyflie automatically
    python detect_decks.py radio://0/80/2M/E7E7E7E7E7   # or give the URI yourself

The drone does NOT take off; it only connects and reads information.
"""

import sys
import time
from threading import Event

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.mem import MemoryElement
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

# Friendly names for the most common deck parameters (deck.<name>).
KNOWN_DECKS = {
    "bcFlow": "Flow deck (v1)",
    "bcFlow2": "Flow deck v2",
    "bcZRanger": "Z-ranger deck (v1)",
    "bcZRanger2": "Z-ranger deck v2",
    "bcMultiranger": "Multi-ranger deck",
    "bcLighthouse4": "Lighthouse positioning deck",
    "bcDWM1000": "Loco positioning deck",
    "bcLedRing": "LED-ring deck",
    "bcBuzzer": "Buzzer deck",
    "bcUSD": "Micro SD card deck",
    "bcAI": "AI deck",
    "bcActiveMarker": "Active marker deck",
    "bcGTGPS": "GPS deck",
    "bcCPPM": "CPPM / RC receiver deck",
    "bcOA": "Obstacle avoidance deck (prototype)",
}


def find_uri():
    """Return the URI given on the command line, or scan for a Crazyflie."""
    if len(sys.argv) > 1:
        return sys.argv[1]

    print("Scanning for Crazyflies...")
    found = cflib.crtp.scan_interfaces()
    if not found:
        print("No Crazyflie found. Is it switched on and is the Crazyradio plugged in?")
        sys.exit(1)

    uri = found[0][0]
    print(f"Found: {uri}")
    return uri


def detected_decks_from_params(cf):
    """Read every parameter in the 'deck' group; value 1 means the deck was detected."""
    toc = cf.param.toc.toc
    if "deck" not in toc:
        return []

    decks = []
    for name in sorted(toc["deck"]):
        value = cf.param.get_value(f"deck.{name}")
        if str(value).strip() not in ("0", ""):
            decks.append(KNOWN_DECKS.get(name, f"Unknown deck (deck.{name})"))
    return decks


def decks_from_onewire_memory(cf):
    """Read the 1-wire memory chip on each deck, which stores its board name."""
    boards = []
    for mem in cf.mem.get_mems(MemoryElement.TYPE_1W):
        done = Event()
        mem.update(lambda _m: done.set())
        if not done.wait(5):
            boards.append("(could not read deck memory)")
            continue
        name = mem.elements.get("Board name", "(no name stored)")
        revision = mem.elements.get("Board revision", "?")
        boards.append(f"{name}  (rev {revision}, VID 0x{mem.vid:02X}, PID 0x{mem.pid:02X})")
    return boards


def main():
    cflib.crtp.init_drivers()
    uri = find_uri()

    print(f"Connecting to {uri} ...")
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache="./cache")) as scf:
        cf = scf.cf
        time.sleep(1.0)  # give the firmware a moment to finish deck detection

        print("\n=== Decks detected by the firmware ===")
        decks = detected_decks_from_params(cf)
        if decks:
            for d in decks:
                print(f"  - {d}")
        else:
            print("  (none)")

        print("\n=== Deck memory chips (raw board names) ===")
        boards = decks_from_onewire_memory(cf)
        if boards:
            for b in boards:
                print(f"  - {b}")
        else:
            print("  (no deck memory found)")

        try:
            vbat = cf.param.get_value("pm.lowVoltage")  # sanity check the link works
            print(f"\nLink OK (pm.lowVoltage threshold = {vbat} V)")
        except Exception:
            pass

    print("\nDone.")


if __name__ == "__main__":
    main()