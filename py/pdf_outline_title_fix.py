#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Fix PDF outline (bookmark) title encoding issues.

Phase 1: repair /Outlines /Title at object level (raw bytes -> Unicode).
Phase 2: rewrite TOC titles via fitz for extra mojibake recovery.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, NameObject, TextStringObject


def _strip_surrogates(text: str) -> str:
    return re.sub(r"[\ud800-\udfff]", "", text)


def _looks_mojibake(text: str) -> bool:
    if not text:
        return False
    bad = sum(1 for ch in text if 0x00C0 <= ord(ch) <= 0x00FF)
    return bad / max(len(text), 1) > 0.25


def _score_text(text: str) -> int:
    if not text:
        return -10**6
    cjk = sum(3 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_good = sum(1 for ch in text if ch.isascii() and (ch.isalnum() or ch in " -_.,:;()[]"))
    moj = sum(2 for ch in text if 0x00C0 <= ord(ch) <= 0x00FF)
    ctrl = sum(3 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    repl = text.count("\ufffd") * 4
    return cjk + ascii_good - moj - ctrl - repl


def _decode_best_effort(raw: bytes) -> str | None:
    if not raw:
        return None

    candidates = []
    if raw.startswith(b"\xff\xfe"):
        candidates.extend(["utf-16le", "utf-16"])
    elif raw.startswith(b"\xfe\xff"):
        candidates.extend(["utf-16be", "utf-16"])
    candidates.extend(["utf-8", "gb18030", "gbk", "big5", "latin-1"])

    best = None
    best_score = -10**9
    for enc in candidates:
        try:
            decoded = raw.decode(enc, errors="ignore")
        except Exception:
            continue
        decoded = _strip_surrogates(decoded).replace("\x00", "").strip()
        if not decoded:
            continue
        score = _score_text(decoded)
        if score > best_score:
            best = decoded
            best_score = score
    return best


def _repair_mojibake_text(text: str) -> str:
    text = _strip_surrogates(text or "")
    best = text
    best_score = _score_text(text)

    for source_enc in ("latin-1", "cp1252"):
        try:
            raw = text.encode(source_enc, errors="ignore")
        except Exception:
            continue
        for target_enc in ("gb18030", "gbk", "utf-8", "utf-16le", "utf-16be"):
            try:
                candidate = raw.decode(target_enc, errors="ignore")
            except Exception:
                continue
            candidate = _strip_surrogates(candidate).replace("\x00", "").strip()
            if not candidate:
                continue
            score = _score_text(candidate)
            if score > best_score:
                best = candidate
                best_score = score
    return best


def _decode_pdf_literal_bytes(literal: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(literal)
    while i < n:
        b = literal[i]
        if b != 0x5C:
            out.append(b)
            i += 1
            continue

        i += 1
        if i >= n:
            break
        esc = literal[i]
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
            out.append(mapping[esc])
            i += 1
            continue

        if 0x30 <= esc <= 0x37:
            oct_digits = [esc]
            i += 1
            for _ in range(2):
                if i < n and 0x30 <= literal[i] <= 0x37:
                    oct_digits.append(literal[i])
                    i += 1
                else:
                    break
            out.append(int(bytes(oct_digits), 8))
            continue

        if esc in (0x0A, 0x0D):
            i += 1
            continue

        out.append(esc)
        i += 1
    return bytes(out)


def _extract_object_title_map(pdf_path: str) -> dict[int, bytes]:
    raw = Path(pdf_path).read_bytes()
    obj_map: dict[int, bytes] = {}

    obj_pattern = re.compile(rb"(\d+)\s+\d+\s+obj(.*?)endobj", re.DOTALL)
    for match in obj_pattern.finditer(raw):
        obj_id = int(match.group(1))
        body = match.group(2)
        pos = body.find(b"/Title")
        if pos < 0:
            continue

        i = pos + len(b"/Title")
        while i < len(body) and body[i] in b" \t\r\n":
            i += 1
        if i >= len(body):
            continue

        if body[i:i+1] == b"(":
            i += 1
            depth = 1
            buf = bytearray()
            while i < len(body) and depth > 0:
                c = body[i]
                if c == 0x5C:
                    if i + 1 < len(body):
                        buf.append(c)
                        i += 1
                        buf.append(body[i])
                    i += 1
                    continue
                if c == 0x28:
                    depth += 1
                    buf.append(c)
                    i += 1
                    continue
                if c == 0x29:
                    depth -= 1
                    if depth > 0:
                        buf.append(c)
                    i += 1
                    continue
                buf.append(c)
                i += 1
            obj_map[obj_id] = _decode_pdf_literal_bytes(bytes(buf))
            continue

        if body[i:i+1] == b"<" and body[i+1:i+2] != b"<":
            j = i + 1
            hex_buf = bytearray()
            while j < len(body) and body[j:j+1] != b">":
                if body[j] not in b" \t\r\n":
                    hex_buf.append(body[j])
                j += 1
            try:
                hex_text = bytes(hex_buf)
                if len(hex_text) % 2 == 1:
                    hex_text += b"0"
                obj_map[obj_id] = bytes.fromhex(hex_text.decode("ascii"))
            except Exception:
                pass

    return obj_map


def _walk_outline_items(first_item_ref):
    stack = [first_item_ref]
    while stack:
        ref = stack.pop()
        if ref is None:
            continue
        item = ref.get_object()
        yield item
        if "/Next" in item:
            stack.append(item["/Next"])
        if "/First" in item:
            stack.append(item["/First"])


def _repair_title(title_obj, fallback_raw: bytes | None = None) -> tuple[str, str, bool]:
    old_text = str(title_obj) if title_obj is not None else ""
    raw = None
    if isinstance(title_obj, ByteStringObject):
        raw = bytes(title_obj)
    else:
        raw = getattr(title_obj, "original_bytes", None)
    if not raw and fallback_raw:
        raw = fallback_raw

    candidate = _decode_best_effort(raw) if raw else None
    old_clean = _strip_surrogates(old_text).strip()
    if not candidate:
        return old_clean, old_clean, False
    candidate = candidate.strip()

    if old_clean and not _looks_mojibake(old_clean) and _score_text(old_clean) >= _score_text(candidate):
        return old_clean, old_clean, False

    return old_clean, candidate, candidate != old_clean


def fix_outline_titles(input_pdf: str, output_pdf: str) -> bool:
    source = Path(input_pdf)
    if not source.exists():
        print(f"Input file not found: {input_pdf}")
        return False

    reader = PdfReader(input_pdf, strict=False)
    object_title_map = _extract_object_title_map(input_pdf)

    root = reader.trailer.get("/Root")
    total = 0
    changed = 0

    if root and "/Outlines" in root:
        outlines = root["/Outlines"].get_object()
        first = outlines.get("/First")
        if first is not None:
            for item in _walk_outline_items(first):
                total += 1
                title_obj = item.get("/Title")
                if title_obj is None:
                    continue
                item_ref = getattr(item, "indirect_reference", None)
                fallback_raw = object_title_map.get(int(item_ref.idnum)) if item_ref else None
                old_text, new_text, is_changed = _repair_title(title_obj, fallback_raw=fallback_raw)
                if is_changed and new_text:
                    item[NameObject("/Title")] = TextStringObject(new_text)
                    changed += 1

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    with Path(output_pdf).open("wb") as fp:
        writer.write(fp)

    # Phase 2 fallback: rewrite TOC titles via fitz.
    toc_changed = 0
    doc = fitz.open(output_pdf)
    toc = doc.get_toc(simple=True)
    if toc:
        fixed_toc = []
        for level, title, page in toc:
            new_title = _repair_mojibake_text(title)
            if new_title != title:
                toc_changed += 1
            fixed_toc.append([level, new_title, page])
        if toc_changed > 0:
            doc.set_toc(fixed_toc)
            tmp_path = output_pdf + ".tmp"
            doc.save(tmp_path, deflate=True, garbage=4)
            doc.close()
            Path(tmp_path).replace(output_pdf)
        else:
            doc.close()
    else:
        doc.close()

    print(f"Outline items scanned: {total}")
    print(f"Titles repaired (phase 1): {changed}")
    print(f"TOC entries rewritten (phase 2): {toc_changed}")
    print(f"Saved: {output_pdf}")
    return True


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "11.pdf"
    dst = sys.argv[2] if len(sys.argv) > 2 else "11-toc-fixed.pdf"
    raise SystemExit(0 if fix_outline_titles(src, dst) else 1)
