"""Linux HID access through /dev/hidraw - same interface as winhid.py.

Windows exposes one device path per top-level HID collection, with the
collection's usage page and report lengths; sharkctl picks its channel from
those. Linux exposes one hidraw node per USB interface instead, so this module
reads each node's report descriptor from sysfs (no root needed for that) and
splits it back into per-collection HidInfo entries with the same meaning.
Report lengths include the report ID byte, as on Windows.

Opening /dev/hidraw* for writing needs permission: install.sh adds a udev rule
for the supported mice.
"""

from __future__ import annotations

import fcntl
import glob
import os
import select
from typing import NamedTuple


class HidError(RuntimeError):
    """Raised when a HID device cannot be opened or a report fails."""


class HidInfo(NamedTuple):
    path: str
    vendor_id: int
    product_id: int
    usage_page: int
    usage: int
    feature_len: int
    input_len: int
    output_len: int
    product: str

    def describe(self) -> str:
        return (
            f"VID_{self.vendor_id:04X}&PID_{self.product_id:04X} "
            f"usage_page=0x{self.usage_page:04X} usage=0x{self.usage:02X} "
            f"feature={self.feature_len} input={self.input_len} "
            f"output={self.output_len}  {self.product}  ({self.path})"
        )


# -- report descriptor parsing -----------------------------------------------

def parse_collections(desc: bytes) -> list[dict]:
    """Split a report descriptor into its top-level collections.

    Returns [{"usage_page", "usage", "input", "output", "feature"}], the last
    three being the longest report of that kind in bytes (report ID included
    when the device uses IDs), mirroring HIDP_CAPS on Windows.
    """
    collections: list[dict] = []
    globals_ = {"page": 0, "size": 0, "count": 0, "id": 0}
    stack: list[dict] = []
    local_usage: int | None = None
    local_usage_size = 0
    depth = 0
    current: dict | None = None
    uses_ids = False
    i = 0
    while i < len(desc):
        prefix = desc[i]
        if prefix == 0xFE:                          # long item: skip
            i += 3 + (desc[i + 1] if i + 1 < len(desc) else 0)
            continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        kind = (prefix >> 2) & 0x03                 # 0 main, 1 global, 2 local
        tag = prefix >> 4
        data = desc[i + 1:i + 1 + size]
        value = int.from_bytes(data, "little") if data else 0
        i += 1 + size

        if kind == 1:                               # global
            if tag == 0x0:
                globals_["page"] = value
            elif tag == 0x7:
                globals_["size"] = value
            elif tag == 0x8:
                globals_["id"] = value
                uses_ids = True
            elif tag == 0x9:
                globals_["count"] = value
            elif tag == 0xA:
                stack.append(dict(globals_))
            elif tag == 0xB and stack:
                globals_ = stack.pop()
        elif kind == 2:                             # local
            if tag == 0x0 and local_usage is None:
                # 4-byte usages carry their own page in the high half.
                local_usage, local_usage_size = value, size
        elif kind == 0:                             # main
            if tag == 0xA:                          # Collection
                if depth == 0:
                    usage = local_usage or 0
                    page = (usage >> 16) if local_usage_size == 4 else globals_["page"]
                    current = {"usage_page": page, "usage": usage & 0xFFFF,
                               "bits": {"input": {}, "output": {}, "feature": {}}}
                    collections.append(current)
                depth += 1
            elif tag == 0xC:                        # End Collection
                depth = max(0, depth - 1)
            elif tag in (0x8, 0x9, 0xB) and current is not None:
                which = {0x8: "input", 0x9: "output", 0xB: "feature"}[tag]
                rid = globals_["id"]
                bits = current["bits"][which]
                bits[rid] = bits.get(rid, 0) + globals_["size"] * globals_["count"]
            local_usage = None

    result = []
    for c in collections:
        entry = {"usage_page": c["usage_page"], "usage": c["usage"]}
        for which in ("input", "output", "feature"):
            sizes = [(b + 7) // 8 for b in c["bits"][which].values()]
            entry[which] = (max(sizes) + (1 if uses_ids else 0)) if sizes else 0
        result.append(entry)
    return result


# -- enumeration ---------------------------------------------------------------

def _uevent(node_dir: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(os.path.join(node_dir, "device", "uevent"), encoding="utf-8",
                  errors="replace") as handle:
            for line in handle:
                key, _, val = line.strip().partition("=")
                values[key] = val
    except OSError:
        pass
    return values


def enumerate_hid(vendor_id: int | None = None,
                  product_id: int | None = None) -> list[HidInfo]:
    """Every hidraw collection, optionally filtered by VID/PID."""
    found: list[HidInfo] = []
    for node_dir in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        ev = _uevent(node_dir)
        hid_id = ev.get("HID_ID", "")               # e.g. 0003:00001D57:0000FA60
        try:
            _bus, vid, pid = (int(x, 16) for x in hid_id.split(":"))
        except ValueError:
            continue
        if vendor_id is not None and vid != vendor_id:
            continue
        if product_id is not None and pid != product_id:
            continue
        try:
            with open(os.path.join(node_dir, "device", "report_descriptor"), "rb") as handle:
                desc = handle.read()
        except OSError:
            continue
        path = "/dev/" + os.path.basename(node_dir)
        for c in parse_collections(desc):
            found.append(HidInfo(path, vid, pid, c["usage_page"], c["usage"],
                                 c["feature"], c["input"], c["output"],
                                 ev.get("HID_NAME", "")))
    return found


# -- device I/O ----------------------------------------------------------------

def _ioc(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | number


def HIDIOCSFEATURE(size: int) -> int:   # noqa: N802 - kernel macro name
    return _ioc(3, 0x06, size)


def HIDIOCGFEATURE(size: int) -> int:   # noqa: N802
    return _ioc(3, 0x07, size)


class HidDevice:
    """An open hidraw node. `overlapped` is accepted for winhid compatibility."""

    def __init__(self, info: HidInfo, overlapped: bool = False):
        self.info = info
        try:
            self._fd = os.open(info.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            from i18n import _
            raise HidError(_(
                "Sem permissao para abrir {path}. Rode o install.sh (ele instala "
                "a regra udev do mouse) e reconecte o receptor.", path=info.path)) from None
        except OSError as exc:
            raise HidError(f"Nao consegui abrir {info.path}: {exc}") from None

    def write_output(self, payload: bytes, timeout_ms: int = 1000) -> None:
        size = self.info.output_len or len(payload)
        buf = bytes(payload).ljust(size, b"\0")
        _, ready, _ = select.select([], [self._fd], [], timeout_ms / 1000)
        if not ready:
            raise HidError(f"timed out after {timeout_ms} ms (mouse asleep or dongle unplugged?)")
        try:
            os.write(self._fd, buf)
        except OSError as exc:
            raise HidError(f"write failed: {exc}") from None

    def read_input(self, timeout_ms: int = 1000) -> bytes:
        ready, _, _ = select.select([self._fd], [], [], timeout_ms / 1000)
        if not ready:
            raise HidError(f"timed out after {timeout_ms} ms")
        try:
            return os.read(self._fd, max(self.info.input_len, 64))
        except OSError as exc:
            raise HidError(f"read failed: {exc}") from None

    def send_feature(self, report: bytes) -> None:
        """Send a feature report exactly as given (byte 0 = report ID)."""
        buf = bytearray(report)
        try:
            fcntl.ioctl(self._fd, HIDIOCSFEATURE(len(buf)), buf)
        except OSError as exc:
            raise HidError(f"feature report 0x{report[0]:02X} rejected: {exc}") from None

    def set_feature(self, payload: bytes, report_id: int = 0) -> None:
        size = self.info.feature_len or (len(payload) + 1)
        self.send_feature(bytes([report_id]) + bytes(payload[:size - 1]).ljust(size - 1, b"\0"))

    def get_feature(self, report_id: int = 0) -> bytes:
        buf = bytearray(self.info.feature_len or 64)
        buf[0] = report_id
        try:
            n = fcntl.ioctl(self._fd, HIDIOCGFEATURE(len(buf)), buf, True)
        except OSError as exc:
            raise HidError(f"get feature failed: {exc}") from None
        return bytes(buf[1:n if isinstance(n, int) and n > 0 else len(buf)])

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "HidDevice":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
