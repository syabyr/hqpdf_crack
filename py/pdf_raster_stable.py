#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Render a PDF page-by-page to images and rebuild it as a stable image PDF.

This does not preserve selectable text, but it produces a PDF that should
render consistently across readers because each page is flattened to a bitmap.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def render_pdf_to_stable_pdf(input_pdf: str, output_pdf: str, zoom: float = 2.0) -> bool:
    source_path = Path(input_pdf)
    if not source_path.exists():
        print(f"Input file not found: {input_pdf}")
        return False

    doc = fitz.open(input_pdf)
    if doc.page_count == 0:
        print("Input PDF has no pages")
        return False

    out_canvas = None
    total_pages = doc.page_count

    print(f"Rendering {total_pages} page(s) from {input_pdf} into {output_pdf}")

    for index in range(total_pages):
        page = doc.load_page(index)
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        page_width = page.rect.width
        page_height = page.rect.height
        if out_canvas is None:
            out_canvas = canvas.Canvas(output_pdf, pagesize=(page_width, page_height))

        out_canvas.drawImage(
            ImageReader(buffer),
            0,
            0,
            width=page_width,
            height=page_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        out_canvas.showPage()
        print(f"  page {index + 1}/{total_pages} rendered")

    if out_canvas is not None:
        out_canvas.save()
    print(f"Saved: {output_pdf}")
    return True


if __name__ == "__main__":
    input_pdf = sys.argv[1] if len(sys.argv) > 1 else "0.pdf"
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else "00.pdf"
    sys.exit(0 if render_pdf_to_stable_pdf(input_pdf, output_pdf) else 1)
