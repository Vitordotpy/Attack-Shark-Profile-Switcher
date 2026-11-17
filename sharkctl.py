"""Switch the Attack Shark V8's active onboard profile.

Protocol captured from the vendor Hub - see capture/FINDINGS.md.

    17-byte output report on the MI_01 / usage-page 0xFF02 collection:
        08 0F 00 00 00 01 <idx> 00 x9 <cksum>
    <idx> is 0-based (Profile 1 = 0x00), cksum = (0x55 - sum(bytes[0..15])) & 0xFF
"""

from __future__ import annotations

import json
import os
import sys
import time

if sys.platform == "win32":
    from winhid import HidDevice, HidError, HidInfo, enumerate_hid
else:
    from linhid import HidDevice, HidError, HidInfo, enumerate_hid

VID = 0x3554
PID = 0xF517

VENDOR_USAGE_PAGE = 0xFF02
VENDOR_USAGE = 0x02
REPORT_LEN = 17

REPORT_ID = 0x08
CMD_SET_PROFILE = 0x0F
CMD_GET_PROFILE = 0x0E

PROFILE_COUNT = 4


class DeviceNotFound(HidError):
    """The dongle is not plugged in, or the config collection is missing."""


def checksum(data: bytes) -> int:
    return (0x55 - sum(data)) & 0xFF


def build_frame(command: int, args: bytes = b"") -> bytes:
    """Build a 17-byte report: ID, command, arguments, trailing checksum."""
    frame = bytearray(REPORT_LEN)
    frame[0] = REPORT_ID
    frame[1] = command
    frame[2:2 + len(args)] = args
    frame[REPORT_LEN - 1] = checksum(frame[:REPORT_LEN - 1])
    return bytes(frame)


def find_device() -> HidInfo:
    """Locate the config channel of a V8 or, failing that, an X6."""
    try:
        return find_v8()
    except DeviceNotFound as v8_error:
        x6 = find_x6()
        if x6 is not None:
            return x6
        raise v8_error


def find_v8() -> HidInfo:
    """Locate the vendor config collection.

    Selected by usage page rather than by 'col05' in the path: the collection
    index is assigned by Windows and the instance part of the path changes with
    the USB port, but the usage page comes from the device's report descriptor.
    """
    candidates = enumerate_hid(VID, PID)
    if not candidates:
        raise DeviceNotFound(
            f"No VID_{VID:04X}/PID_{PID:04X} device. Is the dongle plugged in?")

    for info in candidates:
        if (info.usage_page == VENDOR_USAGE_PAGE
                and info.usage == VENDOR_USAGE
                and info.output_len == REPORT_LEN):
            return info

    raise DeviceNotFound(
        f"Dongle found but no usage-page 0x{VENDOR_USAGE_PAGE:04X} collection "
        f"with {REPORT_LEN}-byte output reports. Firmware may have changed - "
        "re-run capture/capture.py.")


def set_profile(profile: int, info: HidInfo | None = None) -> None:
    """Select profile 1..4 (as numbered in the Hub UI)."""
    info = info or find_device()
    if info.vendor_id == X6_VID:
        x6_set_profile(profile, info)
        return
    if not 1 <= profile <= PROFILE_COUNT:
        raise ValueError(f"profile must be 1..{PROFILE_COUNT}, got {profile}")
    frame = build_frame(CMD_SET_PROFILE,
                        bytes([0x00, 0x00, 0x00, 0x01, profile - 1]))
    with HidDevice(info, overlapped=True) as dev:
        dev.write_output(frame)


def get_profile(info: HidInfo | None = None, attempts: int = 3) -> int | None:
    """Best-effort read of the active profile; None if the device doesn't answer.

    Only answers while the mouse is awake - a sleeping V8 leaves the query
    unacknowledged even though the dongle still accepts writes. The query is
    therefore re-sent a few times before giving up, and callers must treat None
    as "unknown" rather than as an error. Nothing in the switcher depends on it;
    it exists for manual checks and the tray display.

    Reads on this collection also see unrelated traffic, because Windows
    delivers every input report to all open handles - the Hub's ~1 Hz status
    poll shows up here too, hence the explicit command-byte match.
    """
    info = info or find_device()
    if info.vendor_id == X6_VID:
        return None                     # the X6 cannot be read back
    query = build_frame(CMD_GET_PROFILE)
    try:
        with HidDevice(info, overlapped=True) as dev:
            for _ in range(attempts):
                dev.write_output(query)
                for _ in range(6):
                    try:
                        reply = dev.read_input(timeout_ms=250)
                    except HidError:
                        break               # nothing pending; re-send the query
                    if len(reply) >= 7 and reply[1] == CMD_GET_PROFILE:
                        return reply[6] + 1
    except HidError:
        return None
    return None


# --------------------------------------------------------------------------
# Attack Shark X6
#
# The X6 has no onboard profiles: it holds a single configuration. A "profile"
# here is therefore a full set of settings (DPI, polling rate, ...) defined in
# config.json under "x6", and switching re-sends that whole set as feature
# reports - the same reports the vendor app (X6.exe) sends, captured from its
# hiddriver_*.dll calls. Every report ends in a 16-bit big-endian sum of the
# data bytes starting at byte 3.
#
#   0x04 (56 bytes): 3,6 = angle snap  4 = ripple  7 = motion sync (left on)
#                    8-13 = DPI stages (dpi/50 - 1)  24 = active stage (1-based)
#   0x06 (9 bytes):  06 09 01 c FF-c 00 00 00 00, c = 1000 / polling_hz
#   0x05 (15 bytes): 3 = light effect << 4 (see X6_LED_MODES)
#                    4 = effect speed, 5 slowest .. 1 fastest
#                    5 = deep sleep minutes << 4 | brightness (1-8)
#                    6-8 = colour R, G, B   9 = 01   10 = key response ms / 2
# --------------------------------------------------------------------------

X6_VID = 0x1D57
X6_PIDS = (0xFA60, 0xFA61)          # 2.4 GHz receiver, USB cable

X6_BASE = bytes([
    0x04, 0x38, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x01, 0x0F, 0x17, 0x1F, 0x3F, 0x6F, 0x07, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x02, 0xFF, 0x00, 0x00, 0x00, 0xFF, 0x00, 0x00,
    0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF, 0x40, 0x00, 0xFF, 0xFF,
    0xFF, 0x01, 0x0E, 0x72, 0x00, 0x00, 0x00, 0x00])

# Light effects of the X6, in the vendor app's order (their value is the index).
X6_LED_MODES = ["off", "static", "breathing", "neon", "color_breathing",
                "static_dpi", "breathing_dpi"]
X6_LED_DEFAULT = {"mode": "breathing_dpi", "color": "#00ff00", "brightness": 8, "speed": 3}
# Effects where the colour / speed setting does something.
X6_LED_USES_COLOR = {"static", "breathing"}
X6_LED_USES_SPEED = {"breathing", "neon", "color_breathing", "breathing_dpi"}

X6_DEFAULTS = {
    "dpi_stages": [800, 1200, 1600, 3200, 5600, 400],
    "profiles": [
        {"name": "Desktop", "dpi": 800, "polling": 500, "key_response_ms": 8,
         "deep_sleep_min": 10, "ripple": True, "angle_snap": False},
        {"name": "Gaming", "dpi": 1600, "polling": 1000, "key_response_ms": 4,
         "deep_sleep_min": 15, "ripple": False, "angle_snap": False},
    ],
}

import app_paths  # noqa: E402
from i18n import _  # noqa: E402

_CONFIG_PATH = app_paths.CONFIG_PATH


def set_config_path(path: str) -> None:
    """Point the X6 profile lookup at another config.json (switcher --config)."""
    global _CONFIG_PATH
    _CONFIG_PATH = path


def x6_config(path: str | None = None) -> dict:
    """The "x6" section of config.json, validated, with defaults filled in."""
    cfg = dict(X6_DEFAULTS)
    try:
        with open(path or _CONFIG_PATH, encoding="utf-8-sig") as handle:
            cfg.update(json.load(handle).get("x6") or {})
    except (OSError, ValueError):
        pass
    return validate_x6(cfg)


def validate_x6(cfg: dict) -> dict:
    """Check an "x6" section; raises ValueError naming the first problem."""
    stages = [int(d) for d in cfg["dpi_stages"]]
    if len(stages) != 6:
        raise ValueError("x6.dpi_stages must list exactly 6 values")
    profiles = cfg["profiles"]
    if not profiles:
        raise ValueError("x6.profiles must define at least one profile")
    for n, p in enumerate(profiles, 1):
        for d in [p["dpi"]] + (stages if n == 1 else []):
            if not (50 <= int(d) <= 12800 and int(d) % 50 == 0):
                raise ValueError(f"invalid DPI {d}: use multiples of 50, 50-12800")
        if p.get("polling") not in (None, 125, 250, 500, 1000):
            raise ValueError(f"x6 profile {n}: polling must be 125, 250, 500 or 1000")
        resp = p.get("key_response_ms")
        if resp is not None and not (2 <= resp <= 20 and resp % 2 == 0):
            raise ValueError(f"x6 profile {n}: key_response_ms must be even, 2-20")
        sleep = p.get("deep_sleep_min")
        if sleep is not None and not 1 <= sleep <= 15:
            raise ValueError(f"x6 profile {n}: deep_sleep_min must be 1-15")
        led = p.get("led")
        if led is not None:
            led = led_settings(led)         # raises ValueError when wrong
    return {"dpi_stages": stages, "profiles": profiles}


def led_settings(led: dict | None) -> dict:
    """A profile's "led" block with defaults filled in, validated."""
    out = dict(X6_LED_DEFAULT)
    out.update(led or {})
    if out["mode"] not in X6_LED_MODES:
        raise ValueError(f"led.mode must be one of {', '.join(X6_LED_MODES)}")
    color = str(out["color"]).lstrip("#")
    if len(color) != 6 or any(c not in "0123456789abcdefABCDEF" for c in color):
        raise ValueError("led.color must look like #RRGGBB")
    out["color"] = "#" + color.lower()
    if not 1 <= int(out["brightness"]) <= 8:
        raise ValueError("led.brightness must be 1-8")
    if not 1 <= int(out["speed"]) <= 5:
        raise ValueError("led.speed must be 1-5")
    return out


def _x6_sum(buf: bytearray, last: int) -> None:
    total = sum(buf[3:last + 1])
    buf[last + 1] = (total >> 8) & 0xFF
    buf[last + 2] = total & 0xFF


def x6_packets(profile: dict, stages: list[int]) -> list[bytes]:
    """Feature reports that put the mouse in the given profile's settings."""
    stages = list(stages)
    dpi = int(profile["dpi"])
    if dpi in stages:
        stage = stages.index(dpi) + 1
    else:
        stages[0], stage = dpi, 1       # not a stage: take over stage 1

    angle = 1 if profile.get("angle_snap") else 0
    b = bytearray(X6_BASE)
    for k, d in enumerate(stages):
        b[8 + k] = d // 50 - 1
    b[3] = b[6] = angle
    b[4] = 1 if profile.get("ripple") else 0
    b[24] = stage
    _x6_sum(b, 49)
    packets = [bytes(b)]

    polling = profile.get("polling")
    if polling:
        c = 1000 // polling
        packets.append(bytes([0x06, 0x09, 0x01, c, 0xFF - c, 0, 0, 0, 0]))

    resp, sleep = profile.get("key_response_ms"), profile.get("deep_sleep_min")
    if resp or sleep or profile.get("led"):
        # Light, click response and deep sleep share one report, so all three
        # always travel together; missing ones get the factory defaults.
        resp, sleep = int(resp or 8), int(sleep or 10)
        led = led_settings(profile.get("led"))
        rgb = bytes.fromhex(led["color"][1:])
        p = bytearray([0x05, 0x0F, 0x01, X6_LED_MODES.index(led["mode"]) << 4,
                       6 - int(led["speed"]), (sleep << 4) | int(led["brightness"]),
                       rgb[0], rgb[1], rgb[2], 0x01, resp // 2, 0, 0, 0, 0])
        _x6_sum(p, 10)
        packets.append(bytes(p))
    return packets


# -- X6 macros ----------------------------------------------------------------
#
#   0x08 (59 bytes): button map, 18 slots of 3 bytes from byte 3, 16-bit sum at
#                    57-58. A slot holds the button's function; "12 00 <slot>"
#                    makes it play the macro stored under that slot number.
#   0x09:            one macro, a 128-byte block sent as 3 reports
#                    (09 40 <slot> 00 + 60 bytes, 09 40 <slot> 01 + 60 bytes,
#                    09 0C <slot> 02 + 8 bytes). In the block: byte 4 = times
#                    to play, byte 25 = number of events, then 2 bytes per event
#                    (bit 7 = release, bits 0-6 = delay after it in 10 ms units;
#                    then the USB HID key code), and a 16-bit sum at 126-127.

X6_BUTTON_DEFAULTS = [bytes.fromhex(h) for h in (
    "020000", "030000", "040000", "0d0000", "0e0000", "0f0000", "060000", "050000",
    "3c0000", "010000", "010000", "010000", "010000", "010000", "010000", "010000",
    "0a0000", "090000")]
# Buttons that can hold a macro, and their slot (1-based) in the button map.
X6_MACRO_SLOTS = {"forward": 7, "backward": 8}
X6_MACRO_MAX_EVENTS = 50
X6_MACRO_MAX_DELAY_MS = 1270

# USB HID keyboard usage codes, by the names stored in config.json.
HID_KEYS = {chr(ord("A") + i): 0x04 + i for i in range(26)}
HID_KEYS.update({str((i + 1) % 10): 0x1E + i for i in range(10)})
HID_KEYS.update({f"F{i}": 0x39 + i for i in range(1, 13)})
HID_KEYS.update({
    "ENTER": 0x28, "ESC": 0x29, "BACKSPACE": 0x2A, "TAB": 0x2B, "SPACE": 0x2C,
    "MINUS": 0x2D, "EQUAL": 0x2E, "LBRACKET": 0x2F, "RBRACKET": 0x30, "BACKSLASH": 0x31,
    "SEMICOLON": 0x33, "QUOTE": 0x34, "GRAVE": 0x35, "COMMA": 0x36, "PERIOD": 0x37,
    "SLASH": 0x38, "CAPSLOCK": 0x39, "PRINTSCREEN": 0x46, "SCROLLLOCK": 0x47,
    "PAUSE": 0x48, "INSERT": 0x49, "HOME": 0x4A, "PAGEUP": 0x4B, "DELETE": 0x4C,
    "END": 0x4D, "PAGEDOWN": 0x4E, "RIGHT": 0x4F, "LEFT": 0x50, "DOWN": 0x51, "UP": 0x52,
    "LCTRL": 0xE0, "LSHIFT": 0xE1, "LALT": 0xE2, "LWIN": 0xE3,
    "RCTRL": 0xE4, "RSHIFT": 0xE5, "RALT": 0xE6, "RWIN": 0xE7,
})


def _sum16(data: bytes) -> bytes:
    total = sum(data)
    return bytes([(total >> 8) & 0xFF, total & 0xFF])


def validate_macro(macro: dict) -> dict:
    """{"loops": 1-255, "events": [{"key", "action": press|release, "delay"}]}."""
    loops = int(macro.get("loops", 1))
    if not 1 <= loops <= 255:
        raise ValueError("macro loops must be 1-255")
    events = macro.get("events") or []
    if not events:
        raise ValueError("macro has no steps")
    if len(events) > X6_MACRO_MAX_EVENTS:
        raise ValueError(f"macro has more than {X6_MACRO_MAX_EVENTS} steps")
    clean = []
    for ev in events:
        key = str(ev.get("key", "")).upper()
        if key not in HID_KEYS:
            raise ValueError(f"unknown key in macro: {ev.get('key')}")
        if ev.get("action") not in ("press", "release"):
            raise ValueError("macro step action must be press or release")
        delay = int(ev.get("delay", 10))
        clean.append({"key": key, "action": ev["action"],
                      "delay": max(10, min(X6_MACRO_MAX_DELAY_MS, delay))})
    return {"loops": loops, "events": clean}


def x6_macro_packets(slot: int, macro: dict) -> list[bytes]:
    macro = validate_macro(macro)
    block = bytearray(128)
    block[4] = macro["loops"]
    block[25] = len(macro["events"])
    for i, ev in enumerate(macro["events"]):
        units = max(1, min(127, round(ev["delay"] / 10)))
        block[26 + 2 * i] = (0x80 if ev["action"] == "release" else 0) | units
        block[27 + 2 * i] = HID_KEYS[ev["key"]]
    block[126:128] = _sum16(block[:126])
    return [bytes([0x09, 0x40, slot, 0]) + bytes(block[0:60]),
            bytes([0x09, 0x40, slot, 1]) + bytes(block[60:120]),
            bytes([0x09, 0x0C, slot, 2]) + bytes(block[120:128]) + bytes(52)]


def x6_button_map(macro_slots: set[int]) -> bytes:
    """The button map with factory functions, except slots that play a macro."""
    body = bytearray()
    for slot, default in enumerate(X6_BUTTON_DEFAULTS, 1):
        body += bytes([0x12, 0x00, slot]) if slot in macro_slots else default
    return bytes([0x08, 0x3B, 0x01]) + bytes(body) + _sum16(body)


def x6_apply_macros(macros: dict, info: HidInfo | None = None) -> None:
    """Send {"forward": macro | None, "backward": macro | None} to the X6.

    A button without a macro goes back to its normal function.
    """
    info = info or find_x6()
    if info is None:
        raise DeviceNotFound(_("Attack Shark X6 nao encontrado. O receptor ou o cabo esta conectado?"))
    active = {X6_MACRO_SLOTS[b]: m for b, m in (macros or {}).items()
              if b in X6_MACRO_SLOTS and m and m.get("enabled", True)}
    packets = [x6_button_map(set(active))]
    for slot, macro in sorted(active.items()):
        packets += x6_macro_packets(slot, macro)
    with HidDevice(info) as dev:
        for i, pkt in enumerate(packets):
            if i:
                time.sleep(0.3)         # the mouse stores macros in flash
            dev.send_feature(pkt)


def find_x6() -> HidInfo | None:
    """The X6 collection that takes the config feature reports (col04)."""
    for pid in X6_PIDS:
        for info in enumerate_hid(X6_VID, pid):
            if info.feature_len >= len(X6_BASE):
                return info
    return None


def x6_set_profile(profile: int, info: HidInfo) -> None:
    cfg = x6_config()
    count = len(cfg["profiles"])
    if not 1 <= profile <= count:
        raise ValueError(f"profile must be 1..{count}, got {profile}")
    x6_apply(cfg["profiles"][profile - 1], cfg["dpi_stages"], info)


def x6_apply(profile: dict, stages: list[int], info: HidInfo | None = None) -> None:
    """Send one profile's settings to the X6 right now."""
    info = info or find_x6()
    if info is None:
        raise DeviceNotFound(_("Attack Shark X6 nao encontrado. O receptor ou o cabo esta conectado?"))
    packets = x6_packets(profile, stages)
    with HidDevice(info) as dev:
        for i, pkt in enumerate(packets):
            if i:
                time.sleep(0.15)        # the mouse drops reports sent back to back
            # Sent at the report's own length, exactly as the vendor app does.
            dev.send_feature(pkt)


def profile_count() -> int:
    """4 on a V8; the number of profiles in config.json on an X6."""
    try:
        find_v8()
        return PROFILE_COUNT
    except HidError:
        pass
    try:
        if find_x6() is not None:
            return len(x6_config()["profiles"])
    except (HidError, ValueError):
        pass
    return PROFILE_COUNT


def profile_label(profile: int) -> str:
    """'Profile 2', plus the profile's name when it comes from config.json."""
    try:
        if find_x6() is not None:
            profiles = x6_config()["profiles"]
            if 1 <= profile <= len(profiles) and profiles[profile - 1].get("name"):
                return _("Perfil {n} ({name})", n=profile, name=profiles[profile - 1]['name'])
    except (HidError, ValueError):
        pass
    return _("Perfil {n}", n=profile)


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("Usage:\n"
              "  python sharkctl.py <1-4>   select a profile\n"
              "  python sharkctl.py get     read the active profile\n"
              "  python sharkctl.py list    show matching HID collections")
        return 0

    try:
        if args[0] == "list":
            for info in enumerate_hid(VID, PID):
                mark = ""
                if (info.usage_page == VENDOR_USAGE_PAGE
                        and info.usage == VENDOR_USAGE
                        and info.output_len == REPORT_LEN):
                    mark = "  <-- config channel"
                print(info.describe() + mark)
            x6 = find_x6()
            for pid in X6_PIDS:
                for info in enumerate_hid(X6_VID, pid):
                    mark = "  <-- config channel" if info == x6 else ""
                    print(info.describe() + mark)
            return 0

        if args[0] == "get":
            current = get_profile()
            print(f"active profile: {current}" if current
                  else "active profile: unknown (device did not answer)")
            return 0

        profile = int(args[0])
        set_profile(profile)
        print(f"switched to Profile {profile}")
        return 0

    except (HidError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
