from __future__ import annotations

import struct
from dataclasses import dataclass, field
from io import BufferedReader, BufferedWriter
from pathlib import Path
from typing import BinaryIO

COPY_CHUNK = 8 * 1024 * 1024


@dataclass
class GpakEntry:
    name: str
    size: int
    offset: int


@dataclass
class Gpak:
    file: BufferedReader
    entries: list[GpakEntry] = field(default_factory=list)

    @staticmethod
    def open(file: BufferedReader) -> Gpak:
        entries: list[GpakEntry] = []

        (entry_count,) = struct.unpack("<I", file.read(4))

        directory: list[tuple[str, int]] = []
        for _ in range(entry_count):
            (name_length,) = struct.unpack("<H", file.read(2))
            name = file.read(name_length).decode("utf-8")
            (file_size,) = struct.unpack("<I", file.read(4))
            directory.append((name, file_size))

        data_start = file.tell()

        offset = data_start
        for name, file_size in directory:
            entries.append(GpakEntry(name=name, size=file_size, offset=offset))
            offset += file_size

        return Gpak(file=file, entries=entries)

    def read_entry(self, entry: GpakEntry) -> bytes:
        self.file.seek(entry.offset)
        return self.file.read(entry.size)

    def find(self, name: str) -> GpakEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def patch(
        self,
        dst: BufferedWriter,
        replacements: dict[str, bytes | Path],
    ) -> list[str]:
        replaced_indices: set[int] = set()
        for i, entry in enumerate(self.entries):
            if entry.name in replacements:
                replaced_indices.add(i)

        kept = [(i, e) for i, e in enumerate(self.entries) if i not in replaced_indices]
        new_names: list[str] = sorted(replacements)

        total = len(kept) + len(new_names)
        dst.write(struct.pack("<I", total))

        # Directory: kept old entries, then all replacements
        for _, entry in kept:
            name_bytes = entry.name.encode("utf-8")
            dst.write(struct.pack("<H", len(name_bytes)))
            dst.write(name_bytes)
            dst.write(struct.pack("<I", entry.size))

        for name in new_names:
            size = _replacement_size(replacements[name])
            name_bytes = name.encode("utf-8")
            dst.write(struct.pack("<H", len(name_bytes)))
            dst.write(name_bytes)
            dst.write(struct.pack("<I", size))

        # Data: kept old entries, then all replacements
        for _, entry in kept:
            self.file.seek(entry.offset)
            _stream_copy(self.file, dst, entry.size)

        for name in new_names:
            _write_replacement(dst, replacements[name])


def _replacement_size(value: bytes | Path) -> int:
    if isinstance(value, Path):
        return value.stat().st_size
    return len(value)


def _write_replacement(dst: BinaryIO, value: bytes | Path) -> None:
    if isinstance(value, Path):
        with value.open("rb") as f:
            _stream_copy(f, dst, value.stat().st_size)
    else:
        dst.write(value)


def _stream_copy(src: BinaryIO, dst: BinaryIO, size: int) -> None:
    remaining = size
    while remaining > 0:
        chunk = src.read(min(remaining, COPY_CHUNK))
        if not chunk:
            break
        dst.write(chunk)
        remaining -= len(chunk)
