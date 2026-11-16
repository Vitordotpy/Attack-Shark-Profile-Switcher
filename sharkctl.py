"""Switch the Attack Shark V8's active onboard profile.

Protocol captured from the vendor Hub - see capture/FINDINGS.md.

    17-byte output report on the MI_01 / usage-page 0xFF02 collection:
        08 0F 00 00 00 01 <idx> 00 x9 <cksum>
    <idx> is 0-based (Profile 1 = 0x00), cksum = (0x55 - sum(bytes[0..15])) & 0xFF
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time

from winhid import HidDevice, HidError, HidInfo, enumerate_hid, hid

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
#   0x05 (15 bytes): 3 = light effect (0x60 breathing)  5 = deep sleep minutes
#                    in the high nibble  10 = key response ms / 2
# --------------------------------------------------------------------------

X6_VID = 0x1D57
X6_PIDS = (0xFA60, 0xFA61)          # 2.4 GHz receiver, USB cable

X6_BASE = bytes([
    0x04, 0x38, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x01, 0x0F, 0x17, 0x1F, 0x3F, 0x6F, 0x07, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x02, 0xFF, 0x00, 0x00, 0x00, 0xFF, 0x00, 0x00,
    0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF, 0x40, 0x00, 0xFF, 0xFF,
    0xFF, 0x01, 0x0E, 0x72, 0x00, 0x00, 0x00, 0x00])

X6_DEFAULTS = {
    "dpi_stages": [800, 1200, 1600, 3200, 5600, 400],
    "profiles": [
        {"name": "Desktop", "dpi": 800, "polling": 500, "key_response_ms": 8,
         "deep_sleep_min": 10, "ripple": True, "angle_snap": False},
        {"name": "Gaming", "dpi": 1600, "polling": 1000, "key_response_ms": 4,
         "deep_sleep_min": 15, "ripple": False, "angle_snap": False},
    ],
}

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


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
    return {"dpi_stages": stages, "profiles": profiles}


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
    if resp or sleep:
        resp, sleep = resp or 8, sleep or 10
        p = bytearray([0x05, 0x0F, 0x01, 0x60, 0x03, (sleep << 4) | 0x08,
                       0x00, 0xFF, 0x00, 0x01, resp // 2, 0, 0, 0, 0])
        _x6_sum(p, 10)
        packets.append(bytes(p))
    return packets


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
        raise DeviceNotFound("Attack Shark X6 not found. Is the receiver or cable plugged in?")
    packets = x6_packets(profile, stages)
    with HidDevice(info) as dev:
        for i, pkt in enumerate(packets):
            if i:
                time.sleep(0.15)        # the mouse drops reports sent back to back
            # Sent at the report's own length, exactly as the vendor app does.
            buf = ctypes.create_string_buffer(pkt, len(pkt))
            if not hid.HidD_SetFeature(dev._handle, buf, len(pkt)):
                raise HidError(f"X6 rejected report 0x{pkt[0]:02X}: "
                               f"error {ctypes.get_last_error()}")


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
                return f"Profile {profile} ({profiles[profile - 1]['name']})"
    except (HidError, ValueError):
        pass
    return f"Profile {profile}"


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
