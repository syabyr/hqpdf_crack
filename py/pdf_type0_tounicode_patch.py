#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Patch a PDF by wrapping broken TrueType fonts as Type0 GBK fonts.

The source PDF stores Chinese text bytes in GBK-like multibyte sequences but
declares the fonts as WinAnsi simple fonts. This script rewrites the font objects
into Type0 + CIDFontType2 wrappers using GBK-EUC-H and injects a ToUnicode CMap.
The page content is left untouched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz


def _iter_pdf_strings(data: bytes):
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


def _build_mapping_from_content(content: bytes):
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
            if slice_bytes == encoded:
                mapping[encoded] = char
            raw_pos += len(encoded)

    return mapping


def _code_hex(code: bytes) -> str:
    return "<" + code.hex().upper() + ">"


def _unicode_hex(text: str) -> str:
    return "".join(f"{ord(ch):04X}" for ch in text)


def _extract_basefont(font_obj: str, fallback: str) -> str:
    match = re.search(r"/BaseFont\s*/([^\s/>]+)", font_obj)
    if match:
        return match.group(1)
    return fallback


def _extract_fontdescriptor_ref(font_obj: str) -> str | None:
    match = re.search(r"/FontDescriptor\s+(\d+)\s+0\s+R", font_obj)
    if match:
        return f"{match.group(1)} 0 R"
    return None


def _extract_widths(font_obj: str):
    first_char = 0
    match_first = re.search(r"/FirstChar\s+(\d+)", font_obj)
    if match_first:
        first_char = int(match_first.group(1))

    match_widths = re.search(r"/Widths\s*\[([^\]]+)\]", font_obj, re.DOTALL)
    if not match_widths:
        return None, 500

    nums = re.findall(r"-?\d+(?:\.\d+)?", match_widths.group(1))
    widths = []
    for value in nums:
        try:
            widths.append(int(float(value)))
        except Exception:
            continue

    if not widths:
        return None, 500

    # Use the first width as default; many legacy PDFs are monospaced at 500.
    dw = widths[0]
    w_array = f"{first_char} [" + " ".join(str(w) for w in widths) + "]"
    return w_array, dw


def _build_tounicode_cmap(mapping: dict[bytes, str], cmap_name: str) -> str:
    items = sorted(mapping.items(), key=lambda item: (len(item[0]), item[0]))
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        f"/CMapName /{cmap_name} def",
        "/CMapType 2 def",
        "2 begincodespacerange",
        "<20> <7E>",
        "<8100> <FEFF>",
        "endcodespacerange",
    ]

    ascii_items = []
    multibyte_items = []
    for code, char in items:
        if len(code) == 1 and 0x20 <= code[0] <= 0x7E and char == chr(code[0]):
            ascii_items.append((code, char))
        else:
            multibyte_items.append((code, char))

    if ascii_items:
        lines.append(f"{len(ascii_items)} beginbfchar")
        for code, char in ascii_items:
            lines.append(f"{_code_hex(code)} <{_unicode_hex(char)}>")
        lines.append("endbfchar")

    if multibyte_items:
        lines.append(f"{len(multibyte_items)} beginbfchar")
        for code, char in multibyte_items:
            lines.append(f"{_code_hex(code)} <{_unicode_hex(char)}>")
        lines.append("endbfchar")

    lines += [
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ]
    return "\n".join(lines)


def _build_cidfont_dict(
    basefont: str,
    fontdescriptor_ref: str | None,
    w_array: str | None,
    dw: int,
) -> str:
    descriptor_part = (
        f"/FontDescriptor {fontdescriptor_ref} "
        if fontdescriptor_ref
        else (
            f"/FontDescriptor << /Type /FontDescriptor /FontName /{basefont} "
            f"/Flags 4 /Ascent 1000 /Descent -200 /CapHeight 1000 /StemV 100 "
            f"/FontBBox [0 -200 1000 1000] /MissingWidth {dw} /ItalicAngle 0 >> "
        )
    )
    widths_part = f"/W [ {w_array} ] " if w_array else ""
    return (
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{basefont} "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> "
        f"{descriptor_part}"
        f"/DW {dw} {widths_part}>>"
    )


def patch_pdf(input_pdf: str, output_pdf: str) -> bool:
    if not Path(input_pdf).exists():
        print(f"Input file not found: {input_pdf}")
        return False

    doc = fitz.open(input_pdf)

    font_xrefs: set[int] = set()
    font_names: dict[int, str] = {}
    content_xrefs: set[int] = set()

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)

        for entry in page.get_fonts(full=True):
            xref = int(entry[0])
            font_xrefs.add(xref)
            if xref not in font_names:
                font_names[xref] = entry[3] if len(entry) > 3 else f"F{xref}"

        contents = page.get_contents()
        if isinstance(contents, int):
            contents = [contents]
        for xref in contents:
            content_xrefs.add(int(xref))

    mapping = {}
    for xref in sorted(content_xrefs):
        stream = doc.xref_stream(xref)
        if stream:
            mapping.update(_build_mapping_from_content(stream))

    if not mapping:
        print("No usable byte-to-Unicode mappings found")
        return False

    print(f"Pages: {doc.page_count}")
    print(f"Fonts discovered: {len(font_xrefs)}")
    print(f"Content streams scanned: {len(content_xrefs)}")
    print(f"Built {len(mapping)} byte mappings")

    shared_cmap_xref = None
    for font_xref in sorted(font_xrefs):
        font_obj = doc.xref_object(font_xref)
        basefont = _extract_basefont(font_obj, f"F{font_xref}")
        fontdescriptor_ref = _extract_fontdescriptor_ref(font_obj)
        w_array, dw = _extract_widths(font_obj)

        cid_xref = doc.get_new_xref()
        cid_obj = _build_cidfont_dict(basefont, fontdescriptor_ref, w_array, dw)
        doc.update_object(cid_xref, cid_obj)

        if shared_cmap_xref is None:
            shared_cmap_xref = doc.get_new_xref()
            cmap_name = f"{font_names[font_xref]}-GBK-Unicode"
            cmap = _build_tounicode_cmap(mapping, cmap_name)
            doc.update_object(shared_cmap_xref, "<< >>")
            doc.update_stream(shared_cmap_xref, cmap.encode("utf-8"))

        wrapper = (
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{basefont} "
            f"/Encoding /GBK-EUC-H /DescendantFonts [ {cid_xref} 0 R ] "
            f"/ToUnicode {shared_cmap_xref} 0 R >>"
        )
        doc.update_object(font_xref, wrapper)
        print(f"Rewrote font xref {font_xref} as Type0 using descendant {cid_xref}")

    doc.save(output_pdf, deflate=True, garbage=4)
    doc.close()
    print(f"Saved: {output_pdf}")
    return True


if __name__ == "__main__":
    input_pdf = sys.argv[1] if len(sys.argv) > 1 else "0.pdf"
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else "00.pdf"
    raise SystemExit(0 if patch_pdf(input_pdf, output_pdf) else 1)