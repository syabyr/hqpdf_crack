#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Rebuild a PDF with a correct Unicode text layer.

The source PDF uses broken font encoding metadata, so text extraction returns
garbled output even when some renderers can display it. This script renders each
page to an image for faithful visual output, then overlays an invisible text
layer using a proper Chinese font so copy/search works with correct Unicode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz


def _find_font_file() -> str:
    candidates = [
        "fonts/simsun.ttc",
        "/System/Library/Fonts/Songti.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No usable CJK font found")


def _span_text(span: dict) -> str:
    if span.get("text"):
        return span["text"]
    chars = span.get("chars", [])
    return "".join(ch.get("c", "") for ch in chars)


def rebuild_unicode_layer(input_pdf: str, output_pdf: str, zoom: float = 2.0) -> bool:
    source_path = Path(input_pdf)
    if not source_path.exists():
        print(f"Input file not found: {input_pdf}")
        return False

    font_path = _find_font_file()
    source_doc = fitz.open(input_pdf)
    target_doc = fitz.open()

    print(f"Using font: {font_path}")
    print(f"Pages: {source_doc.page_count}")

    for page_index in range(source_doc.page_count):
        source_page = source_doc.load_page(page_index)
        page_rect = source_page.rect
        target_page = target_doc.new_page(width=page_rect.width, height=page_rect.height)

        pixmap = source_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        target_page.insert_image(target_page.rect, pixmap=pixmap, overlay=False)

        raw = source_page.get_text("rawdict")
        span_count = 0
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = _span_text(span)
                    if not text.strip():
                        continue
                    origin = span.get("origin")
                    if not origin:
                        bbox = span.get("bbox")
                        if bbox:
                            origin = (bbox[0], bbox[3])
                        else:
                            continue

                    fontsize = float(span.get("size", 12.0))
                    font_name = span.get("font", "cjk")
                    try:
                        target_page.insert_text(
                            origin,
                            text,
                            fontfile=font_path,
                            fontname=font_name,
                            fontsize=fontsize,
                            render_mode=3,
                            overlay=True,
                        )
                        span_count += 1
                    except Exception as exc:
                        print(f"  skip span on page {page_index + 1}: {exc}")

        print(f"page {page_index + 1}: inserted {span_count} invisible text spans")

    target_doc.save(output_pdf, deflate=True, garbage=4)
    target_doc.close()
    source_doc.close()
    print(f"Saved: {output_pdf}")
    return True


if __name__ == "__main__":
    input_pdf = sys.argv[1] if len(sys.argv) > 1 else "0.pdf"
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else "00.pdf"
    raise SystemExit(0 if rebuild_unicode_layer(input_pdf, output_pdf) else 1)