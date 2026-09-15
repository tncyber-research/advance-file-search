"""Plain-text extraction with a controlled, fully offline encoding strategy.

Encoding order (handoff §7.4):

1. UTF-8 with BOM
2. UTF-16 / UTF-32 when a BOM indicates it
3. UTF-8
4. Windows-874 / TIS-620 as explicit Thai fallbacks
5. Windows-1252, then a conservative replacement decode after recording a
   warning

No online or heuristic third-party encoding service is used; the decision is
made from the BOM plus strict-decode attempts on the actual bytes.
"""

from __future__ import annotations

import codecs
from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core.models import (
    ContentUnit,
    DocumentMetadata,
    ParseOutcome,
    ParseResult,
)
from advance_file_search.indexing.parsers.base import DocumentParser, clean_text

#: Ordered BOM signatures.  UTF-32 must be tested before UTF-16, because the
#: UTF-32-LE BOM starts with the UTF-16-LE BOM.
#:
#: The BOM-aware codec names ("utf-8-sig", "utf-16", "utf-32") are chosen
#: deliberately: they consume the mark instead of decoding it into a leading
#: U+FEFF that would then appear in the first indexed unit and in snippets.
_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

#: Strict-decode candidates tried in order when there is no BOM.
_FALLBACK_ENCODINGS: tuple[str, ...] = ("utf-8", "cp874", "tis-620", "cp1252")

#: Bytes read to sniff the BOM and detect binary content.
_SNIFF_BYTES = 8192

#: Files larger than this are streamed line by line instead of read whole.
_STREAM_THRESHOLD = 8 * 1024 * 1024


def detect_encoding(sample: bytes) -> tuple[str, bool]:
    """Return ``(encoding, from_bom)`` for a leading byte sample."""
    for bom, encoding in _BOMS:
        if sample.startswith(bom):
            return encoding, True
    return "", False


def looks_binary(sample: bytes) -> bool:
    """Heuristic guard so a mislabelled binary is skipped, not indexed as junk.

    A NUL byte in the first block is the reliable signal; UTF-16 text is
    excluded from this test because the caller only applies it when no BOM was
    found.
    """
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    # A high proportion of non-text control bytes also indicates binary data.
    control = sum(1 for byte in sample if byte < 0x09 or 0x0E <= byte < 0x20)
    return control > max(8, len(sample) // 20)


class TxtParser(DocumentParser):
    """Indexes one :data:`constants.TXT_LINES_PER_BLOCK`-line block per unit."""

    name = "txt"
    supported_extensions = frozenset({".txt", ".md", ".csv", ".log"})

    def _parse(self, path: Path, size_bytes: int) -> ParseResult:
        warnings: list[str] = []
        with open(path, "rb") as handle:
            sample = handle.read(_SNIFF_BYTES)

        encoding, from_bom = detect_encoding(sample)
        if not encoding:
            if looks_binary(sample):
                return ParseResult(
                    ParseOutcome.NO_TEXT,
                    error_code=C.ERR_NO_TEXT,
                    error_message="file appears to contain binary data",
                )
            encoding = self._choose_encoding(path, sample, size_bytes, warnings)

        errors = "strict"
        if encoding.endswith("+replace"):
            encoding = encoding[: -len("+replace")]
            errors = "replace"
            warnings.append(C.ERR_ENCODING)

        units: list[ContentUnit] = []
        line_number = 0
        truncated = False
        total_chars = 0

        try:
            with open(
                path, encoding=encoding, errors=errors, newline=""
            ) as handle:
                block: list[str] = []
                block_start = 1
                for raw_line in handle:
                    line_number += 1
                    if line_number > C.MAX_TXT_LINES:
                        truncated = True
                        break
                    line = raw_line.rstrip("\r\n")
                    if len(line) > C.MAX_TXT_LINE_LENGTH:
                        line = line[: C.MAX_TXT_LINE_LENGTH]
                        truncated = True
                    if not block:
                        block_start = line_number
                    block.append(line)
                    if len(block) >= max(1, C.TXT_LINES_PER_BLOCK):
                        unit = self._make_unit(len(units) + 1, block_start, block)
                        if unit is not None:
                            units.append(unit)
                            total_chars += len(unit.text)
                        block = []
                    if total_chars > C.MAX_DOCUMENT_TEXT_CHARS:
                        truncated = True
                        break
                if block:
                    unit = self._make_unit(len(units) + 1, block_start, block)
                    if unit is not None:
                        units.append(unit)
        except UnicodeDecodeError:
            # Strict decode failed mid-file after succeeding on the sample.
            return self._parse_with_replacement(path, warnings)

        if truncated:
            warnings.append(C.ERR_LIMIT)

        metadata = DocumentMetadata(
            extension=path.suffix.casefold(),
            line_count=line_number,
            encoding=encoding,
            truncated=truncated,
        )
        return self._finish(units, metadata, warnings)

    # -- helpers ----------------------------------------------------------
    def _choose_encoding(
        self, path: Path, sample: bytes, size_bytes: int, warnings: list[str]
    ) -> str:
        """Pick an encoding by strict-decoding real bytes from the file.

        For a small file the whole content is tested, which is decisive.  For a
        large file only a leading window is tested; if a later byte fails the
        caller falls back to a replacement decode.
        """
        probe = sample
        if size_bytes <= _STREAM_THRESHOLD:
            try:
                probe = path.read_bytes()
            except OSError:
                probe = sample
        else:
            # Trim the window to avoid splitting a multi-byte sequence.
            probe = sample[: len(sample) - 4] if len(sample) > 4 else sample

        for encoding in _FALLBACK_ENCODINGS:
            try:
                probe.decode(encoding, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue
            return encoding

        warnings.append(C.ERR_ENCODING)
        return "cp874+replace"

    def _parse_with_replacement(self, path: Path, warnings: list[str]) -> ParseResult:
        """Last-resort decode that never fails, with an encoding warning."""
        if C.ERR_ENCODING not in warnings:
            warnings.append(C.ERR_ENCODING)
        units: list[ContentUnit] = []
        line_number = 0
        with open(path, encoding="cp874", errors="replace", newline="") as handle:
            for raw_line in handle:
                line_number += 1
                if line_number > C.MAX_TXT_LINES:
                    break
                unit = self._make_unit(
                    len(units) + 1, line_number, [raw_line.rstrip("\r\n")]
                )
                if unit is not None:
                    units.append(unit)
        metadata = DocumentMetadata(
            extension=path.suffix.casefold(),
            line_count=line_number,
            encoding="cp874 (replacement)",
            truncated=True,
        )
        return self._finish(units, metadata, warnings)

    def _make_unit(
        self, sequence: int, first_line: int, lines: list[str]
    ) -> ContentUnit | None:
        text = clean_text("\n".join(lines), limit=self.options.max_unit_text_length)
        if not text:
            return None
        return ContentUnit(
            sequence=sequence,
            location_type=C.LOC_LINE,
            location_label=f"Line {first_line}",
            location_data={"line": first_line, "lines": len(lines)},
            text=text,
        )
