#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Patch a PDF by injecting ToUnicode CMaps into its original font objects.

This keeps the source PDF page content intact and only repairs the font
metadata needed for text extraction/search/copy to work correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz


def _iter_pdf_strings(data: bytes):
    """Yield raw byte strings from PDF literal strings and hex strings."""
    i = 0
    n = len(data)
    while i < n:
        ch = data[i]
        if ch == ord("("):
            i += 1
            depth = 1
            buf = bytearray()
            while i < n and depth > 0:
                b = data[i]
                if b == ord("\\"):
                    i += 1
                    if i >= n:
                        break
                    esc = data[i]
                    if esc in b"nrtbf()\\":
                        mapping = {
                            ord("n"): 0x0A,
                            ord("r"): 0x0D,
                            ord("t"): 0x09,
                            ord("b"): 0x08,
                            ord("f"): 0x0C,
                            ord("("): ord("("),
                            ord(")"): ord(")"),
                            ord("\\"): ord("\\"),
                        }
                        buf.append(mapping[esc])
                    elif 48 <= esc <= 55:
                        oct_digits = [esc]
                        for _ in range(2):
                            if i + 1 < n and 48 <= data[i + 1] <= 55:
                                i += 1
                                oct_digits.append(data[i])
                            else:
                                break
                        buf.append(int(bytes(oct_digits), 8))
                    elif esc in (10, 13):
                        pass
                    else:
                        buf.append(esc)
                elif b == ord("("):
                    depth += 1
                    buf.append(b)
                elif b == ord(")"):
                    depth -= 1
                    if depth > 0:
                        buf.append(b)
                else:
                    buf.append(b)
                i += 1
            yield bytes(buf)
            continue

        if ch == ord("<") and i + 1 < n and data[i + 1] != ord("<"):
            j = i + 1
            hex_bytes = bytearray()
            while j < n and data[j] != ord(">"):
                if chr(data[j]).isspace():
                    j += 1
                    continue
                hex_bytes.append(data[j])
                j += 1
            if hex_bytes:
                hex_text = bytes(hex_bytes)
                if len(hex_text) % 2 == 1:
                    hex_text += b"0"
                try:
                    yield bytes.fromhex(hex_text.decode("ascii"))
                except Exception:
                    pass
            i = j + 1
            continue

        i += 1


def _build_mapping_from_stream(content: bytes):
    """Build byte-sequence to Unicode mapping from GBK-decoded text chunks."""
    mapping = {}
    for raw in _iter_pdf_strings(content):
        if not raw:
            continue
        try:
            decoded = raw.decode("gbk")
        except Exception:
            try:
                decoded = raw.decode("gb2312")
            except Exception:
                continue

        raw_pos = 0
        for char in decoded:
            try:
                encoded = char.encode("gbk")
            except Exception:
                try:
                    encoded = char.encode("gb2312")
                except Exception:
                    continue

            slice_bytes = raw[raw_pos : raw_pos + len(encoded)]
            if slice_bytes != encoded:
                # Skip mismatches; the PDF may mix in non-text bytes.
                raw_pos += len(encoded)
                continue

            mapping[encoded] = char
            raw_pos += len(encoded)

    return mapping


def _hex_code(data: bytes) -> str:
    return "<" + data.hex().upper() + ">"


def _unicode_hex(text: str) -> str:
    return "".join(f"{ord(ch):04X}" for ch in text)


def _build_tounicode_cmap(mapping: dict[bytes, str], font_name: str) -> str:
    ascii_items = []
    multi_items = []
    for code, char in sorted(mapping.items(), key=lambda item: (len(item[0]), item[0])):
        if len(code) == 1 and 0x20 <= code[0] <= 0x7E and char == chr(code[0]):
            ascii_items.append((code, char))
        else:
            multi_items.append((code, char))

    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        f"/CMapName /{font_name}-Unicode def",
        "/CMapType 2 def",
    ]

    # Cover printable ASCII and the GBK two-byte range we observed.
    lines += [
        "2 begincodespacerange",
        "<20> <7E>",
        "<8100> <FEFF>",
        "endcodespacerange",
    ]

    if ascii_items:
        lines.append(f"{len(ascii_items)} beginbfchar")
        for code, char in ascii_items:
            lines.append(f"{_hex_code(code)} <{_unicode_hex(char)}>" )
        lines.append("endbfchar")

    if multi_items:
        # Use bfchar entries; a few hundred mappings are still small.
        lines.append(f"{len(multi_items)} beginbfchar")
        for code, char in multi_items:
            lines.append(f"{_hex_code(code)} <{_unicode_hex(char)}>" )
        lines.append("endbfchar")

    lines += [
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ]
    return "\n".join(lines)


def patch_pdf(input_pdf: str, output_pdf: str) -> bool:
    source = Path(input_pdf)
    if not source.exists():
        print(f"Input file not found: {input_pdf}")
        return False

    doc = fitz.open(input_pdf)
    page = doc.load_page(0)
    font_entries = page.get_fonts(full=True)
    font_xrefs = []
    for entry in font_entries:
        xref = int(entry[0])
        if xref not in font_xrefs:
            font_xrefs.append(xref)

    contents = page.get_contents()
    if isinstance(contents, int):
        contents = [contents]

    stream_mapping = {}
    for xref in contents:
        stream = doc.xref_stream(xref)
        if stream:
            stream_mapping.update(_build_mapping_from_stream(stream))

    if not stream_mapping:
        print("No byte-to-Unicode mapping could be built")
        return False

    print(f"Built {len(stream_mapping)} code mappings")
    print(f"Font xrefs: {font_xrefs}")

    for font_xref in font_xrefs:
        font_obj = doc.xref_object(font_xref)
        font_name = f"F{font_xref}"
        for token in ["/TT0", "/TT1", "/F1", "/F2", "/FontName"]:
            if token in font_obj:
                font_name = token.strip("/")
                break

        cmap = _build_tounicode_cmap(stream_mapping, font_name)
        cmap_xref = doc.get_new_xref()
        doc.update_object(cmap_xref, "<< >>")
        doc.update_stream(cmap_xref, cmap.encode("utf-8"))
        doc.xref_set_key(font_xref, "ToUnicode", f"{cmap_xref} 0 R")
        print(f"Injected ToUnicode into font xref {font_xref} using stream {cmap_xref}")

    doc.save(output_pdf, deflate=True, garbage=4)
    doc.close()
    print(f"Saved: {output_pdf}")
    return True


if __name__ == "__main__":
    input_pdf = sys.argv[1] if len(sys.argv) > 1 else "0.pdf"
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else "00.pdf"
    raise SystemExit(0 if patch_pdf(input_pdf, output_pdf) else 1)