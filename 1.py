from __future__ import annotations

import argparse
from pathlib import Path


def extract_with_pypdf(pdf_path: Path) -> tuple[str, object | None]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", None

    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts), reader


def extract_with_pdfminer(pdf_path: Path) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(str(pdf_path)) or ""


def decode_gb2312_latin1(text: str) -> str:
    try:
        return text.encode("latin1", errors="ignore").decode("gb2312", errors="ignore")
    except Exception:
        return text


def inspect_fonts(reader: object) -> None:
    try:
        pages = reader.pages
    except Exception:
        print("[inspect] pypdf reader not available.")
        return

    for page_index, page in enumerate(pages, start=1):
        resources = page.get("/Resources", {})
        fonts = resources.get("/Font", {})
        print(f"[inspect] page {page_index}: {len(fonts)} font(s)")
        for name, font_ref in fonts.items():
            try:
                font = font_ref.get_object()
            except Exception:
                font = font_ref
            subtype = font.get("/Subtype")
            encoding = font.get("/Encoding")
            has_tounicode = "/ToUnicode" in font
            print(
                f"  {name}: subtype={subtype} encoding={encoding} ToUnicode={has_tounicode}"
            )


def write_text(txt_path: Path, text: str) -> None:
    txt_path.write_text(text, encoding="utf-8")


def write_pdf_from_text(out_pdf: Path, text: str, font_path: str) -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("CNFont", font_path))
    c = canvas.Canvas(str(out_pdf))
    c.setFont("CNFont", 12)

    x, y = 40, 800
    line_height = 16
    for line in text.splitlines():
        if y < 40:
            c.showPage()
            c.setFont("CNFont", 12)
            y = 800
        c.drawString(x, y, line)
        y -= line_height

    c.save()


def decode_gb2312_textline(text: str) -> str:
    try:
        return text.encode("latin1", errors="ignore").decode("gb2312", errors="ignore")
    except Exception:
        return text


def write_pdf_preserve_layout(
    pdf_path: Path,
    out_pdf: Path,
    font_path: str,
    decode_gb2312: bool,
    draw_background: bool,
    bg_zoom: float,
) -> None:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer, LTTextLine
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    if draw_background:
        try:
            import fitz
            from reportlab.lib.utils import ImageReader
        except Exception:
            print("[background] PyMuPDF not available, skip background.")
            draw_background = False

    pdfmetrics.registerFont(TTFont("CNFont", font_path))
    laparams = LAParams()

    page_iter = extract_pages(str(pdf_path), laparams=laparams)
    c = None
    doc = None
    if draw_background:
        doc = fitz.open(str(pdf_path))

    for page_index, page_layout in enumerate(page_iter):
        page_x0, page_y0, page_x1, page_y1 = page_layout.bbox
        page_width = page_x1 - page_x0
        page_height = page_y1 - page_y0
        if c is None:
            c = canvas.Canvas(str(out_pdf), pagesize=(page_width, page_height))
        else:
            c.setPageSize((page_width, page_height))

        if draw_background and doc is not None:
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(bg_zoom, bg_zoom), alpha=False)
            img = ImageReader(pix.tobytes("png"))
            c.drawImage(img, 0, 0, width=page_width, height=page_height)

        c.setFont("CNFont", 12)
        c.saveState()
        c.translate(-page_x0, -page_y0)
        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                text = line.get_text().rstrip("\n")
                if decode_gb2312:
                    text = decode_gb2312_textline(text)
                if text:
                    c.drawString(line.x0, line.y0, text)

        c.restoreState()

        c.showPage()

    if c is not None:
        c.save()


def draw_invisible_text(canvas_obj, text: str, x: float, y: float, size: float) -> None:
    canvas_obj.saveState()
    try:
        canvas_obj.setFillAlpha(0)
    except Exception:
        pass
    canvas_obj.setFont("CNFont", size)
    canvas_obj.drawString(x, y, text)
    canvas_obj.restoreState()


def write_pdf_with_ocr(
    pdf_path: Path,
    out_pdf: Path,
    font_path: str,
    ocr_lang: str,
    ocr_zoom: float,
    draw_background: bool,
) -> None:
    try:
        import fitz
        import pytesseract
        from PIL import Image
        from reportlab.lib.utils import ImageReader
    except Exception as exc:
        print(f"[ocr] missing dependency: {exc}")
        return

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("CNFont", font_path))
    doc = fitz.open(str(pdf_path))

    c = None
    for page_index, page in enumerate(doc, start=1):
        rect = page.rect
        page_width, page_height = rect.width, rect.height
        if c is None:
            c = canvas.Canvas(str(out_pdf), pagesize=(page_width, page_height))
        else:
            c.setPageSize((page_width, page_height))

        pix = page.get_pixmap(matrix=fitz.Matrix(ocr_zoom, ocr_zoom), alpha=False)
        if draw_background:
            img = ImageReader(pix.tobytes("png"))
            c.drawImage(img, 0, 0, width=page_width, height=page_height)

        img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        data = pytesseract.image_to_data(img_pil, lang=ocr_lang, output_type=pytesseract.Output.DICT)

        scale = pix.width / page_width if page_width else 1.0
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue
            left = data["left"][i]
            top = data["top"][i]
            width = data["width"][i]
            height = data["height"][i]

            x = left / scale
            y = page_height - (top + height) / scale
            font_size = max(6, (height / scale) * 0.8)
            draw_invisible_text(c, text, x, y, font_size)

        c.showPage()

    if c is not None:
        c.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?", default="0.pdf")
    parser.add_argument("--txt", default="0.utf8.txt")
    parser.add_argument("--pdf-out", default="0.utf8.pdf")
    parser.add_argument("--decode-gb2312", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--make-pdf", action="store_true")
    parser.add_argument("--preserve-layout", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--bg-zoom", type=float, default=2.0)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--ocr-lang", default="chi_sim+eng")
    parser.add_argument("--ocr-zoom", type=float, default=2.0)
    parser.add_argument(
        "--font-path",
        default="/System/Library/Fonts/STHeiti Medium.ttc",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    txt_path = Path(args.txt)

    text, reader = extract_with_pypdf(pdf_path)
    if not text:
        text = extract_with_pdfminer(pdf_path)

    if args.inspect and reader is not None:
        inspect_fonts(reader)

    if args.decode_gb2312:
        text = decode_gb2312_latin1(text)

    write_text(txt_path, text)

    if args.preserve_layout:
        write_pdf_preserve_layout(
            pdf_path,
            Path(args.pdf_out),
            args.font_path,
            args.decode_gb2312,
            args.background,
            args.bg_zoom,
        )
    elif args.ocr:
        write_pdf_with_ocr(
            pdf_path,
            Path(args.pdf_out),
            args.font_path,
            args.ocr_lang,
            args.ocr_zoom,
            args.background,
        )
    elif args.make_pdf:
        write_pdf_from_text(Path(args.pdf_out), text, args.font_path)


if __name__ == "__main__":
    main()