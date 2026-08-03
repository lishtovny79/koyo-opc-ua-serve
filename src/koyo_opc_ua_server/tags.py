"""Kepware CSV import and tag value conversion."""

from __future__ import annotations

import csv
import math
import struct
from dataclasses import dataclass
from pathlib import Path


class TagConfigurationError(ValueError):
    pass


def map_address(address: str) -> tuple[int, int | None]:
    value = address.strip().strip('"').upper()
    if value.startswith("V"):
        parts = value[1:].split(".")
        try:
            return int(parts[0], 8), int(parts[1]) if len(parts) == 2 else None
        except ValueError as exc:
            raise TagConfigurationError(f"invalid V-memory address: {address}") from exc
    prefixes = {"X": (40400, 1), "Y": (40500, 1), "C": (40600, 1), "T": (41100, 1),
                "SP": (41200, 2), "S": (41000, 1)}
    for prefix, (base, prefix_length) in prefixes.items():
        if value.startswith(prefix):
            try:
                index = int(value[prefix_length:], 8)
            except ValueError as exc:
                raise TagConfigurationError(f"invalid {prefix} address: {address}") from exc
            return int(str(base), 8) + index // 16, index % 16
    raise TagConfigurationError(f"unsupported address: {address}")


@dataclass(frozen=True)
class TagDefinition:
    name: str
    address: str
    data_type: str
    client_access: str
    word: int
    bit: int | None

    @property
    def is_boolean(self) -> bool:
        return self.bit is not None or self.data_type == "Boolean"

    @property
    def is_float(self) -> bool:
        return self.data_type == "Float"

    @property
    def is_lbcd(self) -> bool:
        return self.data_type == "LBCD"

    @property
    def is_bcd(self) -> bool:
        return self.data_type == "BCD"

    @property
    def word_count(self) -> int:
        return 2 if self.is_float or self.is_lbcd else 1

    @property
    def writable(self) -> bool:
        return "W" in self.client_access.upper()

    def decode(self, words: dict[int, int]) -> bool | int | float:
        first = words.get(self.word, 0)
        if self.is_boolean:
            return bool((first >> (self.bit if self.bit is not None else 0)) & 1)
        if self.is_float:
            return struct.unpack("<f", struct.pack("<HH", first, words.get(self.word + 1, 0)))[0]
        if self.is_lbcd:
            return int(f"{words.get(self.word + 1, 0):04x}{first:04x}")
        if self.is_bcd:
            return int(f"{first:04x}")
        return first if first <= 32767 else first - 65536

    def encode(self, value: bool | int | float, cached_words: dict[int, int]) -> list[int]:
        if self.is_boolean:
            current = cached_words[self.word]
            mask = 1 << (self.bit if self.bit is not None else 0)
            return [current | mask if bool(value) else current & ~mask]
        if self.is_float:
            if not math.isfinite(float(value)):
                raise ValueError("Float value must be finite")
            return list(struct.unpack("<HH", struct.pack("<f", float(value))))
        if self.is_bcd or self.is_lbcd:
            text = str(int(value))
            if not text.isdigit() or len(text) > (8 if self.is_lbcd else 4):
                raise ValueError("BCD value contains invalid digits or is out of range")
            packed = int(text, 16)
            return [packed & 0xFFFF, packed >> 16] if self.is_lbcd else [packed]
        integer = int(value)
        if not -32768 <= integer <= 65535:
            raise ValueError("Word value must be between -32768 and 65535")
        return [integer & 0xFFFF]


def create_tag(name: str, address: str, data_type: str, client_access: str) -> TagDefinition:
    name, address = name.strip(), address.strip()
    data_type, client_access = data_type.strip(), client_access.strip()
    if not all((name, address, data_type, client_access)):
        raise TagConfigurationError("tag name, address, data type, and client access are required")
    if data_type not in {"Boolean", "Word", "BCD", "LBCD", "Float"}:
        raise TagConfigurationError(f"unsupported type {data_type!r}")
    word, bit = map_address(address)
    return TagDefinition(name, address, data_type, client_access, word, bit)


def load_tags(path: Path) -> list[TagDefinition]:
    required = {"Tag Name", "Address", "Data Type", "Client Access"}
    try:
        file = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise TagConfigurationError(f"tag CSV not found: {path}") from exc
    with file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise TagConfigurationError(f"CSV must contain: {', '.join(sorted(required))}")
        tags: list[TagDefinition] = []
        names: set[str] = set()
        for line, row in enumerate(reader, start=2):
            name = (row.get("Tag Name") or "").strip()
            address = (row.get("Address") or "").strip()
            data_type = (row.get("Data Type") or "").strip()
            access = (row.get("Client Access") or "").strip()
            if name in names:
                raise TagConfigurationError(f"CSV line {line}: duplicate tag name {name!r}")
            try:
                tag = create_tag(name, address, data_type, access)
            except TagConfigurationError as exc:
                raise TagConfigurationError(f"CSV line {line}: {exc}") from exc
            names.add(name)
            tags.append(tag)
    if not tags:
        raise TagConfigurationError("CSV contains no supported tags")
    return tags
