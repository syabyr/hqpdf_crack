# hq-pdf-fix

Repair old Chinese PDFs that render but cannot be searched: text is restored as a
real, selectable, copyable text layer without touching the layout.

```bash
pip install hq-pdf-fix
hq_pdf_fix test.pdf          # -> test-1.pdf
```

## The problem

Books produced by 1990s–2000s Chinese typesetting tools (北大方正 / S22PDF and
friends) write their text as raw GB2312/GBK byte pairs straight into the content
stream, while declaring the fonts as simple WinAnsi TrueType fonts or as
non-embedded Type0/CIDFontType2 fonts with `/Encoding /GBK-EUC-H`.

- Chrome (PDFium) guesses the encoding from a hardcoded list of Chinese font names,
  so it draws the right glyphs.
- macOS Preview / Quartz obeys the declared encoding instead: text either comes out
  garbled or — when only `/Encoding` was patched to `/GBK-EUC-H` — renders correctly
  but exposes **zero characters** to selection, search, copy and Spotlight.

Adding `/ToUnicode` alone cannot fix this, because an 8-bit code space cannot carry
the mapping.

## What it does

`hq_pdf_fix` rebuilds the document around an embedded font subset:

| | source | output |
|---|---|---|
| font | `/TrueType` + `/WinAnsiEncoding`, or Type0 + `/GBK-EUC-H`, not embedded | Type0 + `/Identity-H` + `/CIDFontType2` |
| glyph file | absent | embedded TrueType subset (`/FontFile2`), one per typeface for the whole document |
| content | 2-byte GBK codes | the same codes re-encoded to glyph ids |
| text layer | none | GID-keyed `/ToUnicode`, plus a real `/W` widths array and `/CIDToGIDMap /Identity` |

Pages are rebuilt rather than cloned, so no orphaned resource tree is left behind
and the file does not grow to double size. Bookmarks (`/Outlines`), `/PageMode`,
`/PageLayout` and `/Info` are carried over, and bookmark titles written with the
classic byte-swapped UTF-16 are decoded properly. Cover-only pages and Type3 fonts
are left untouched.

Two repairs come along for free. A stray `>>` left by a truncated dictionary —
which makes a tolerant parser paint the page as a black block — is dropped, so the
text underneath becomes visible. Codes are decoded as GB18030 rather than GBK, so
rare characters such as `䴙` and `䴕` survive as themselves instead of becoming
boxes.

A file that is already `/Identity-H` is detected and refused (exit status 1): its
string operands are glyph ids, and re-encoding them would scramble the page.

## Install

```bash
pip install hq-pdf-fix          # or: pipx install hq-pdf-fix
```

Requires Python 3.9+; dependencies are `pypdf` and `fonttools`.

## Fonts

The four CJK faces these documents name (`FangSong`, `KaiTi`, `SimHei`, `SimSun`)
are proprietary and are **not** bundled — you supply a machine that has them, as
Windows and macOS normally do. Lookup order, first hit wins:

1. `--font-dir DIR` (repeatable)
2. `$HQ_PDF_FIX_FONT_DIR` (`:`-separated)
3. `./fonts`
4. a `fonts/` folder shipped next to the package
5. `~/.local/share/hq_pdf_fix/fonts` (or `$XDG_DATA_HOME/…`)
6. the platform font directories (`/System/Library/Fonts`, `/Library/Fonts`,
   `/usr/share/fonts`, `%WINDIR%\Fonts`, …)

Each face is matched by known file names, e.g. `simsun.ttc` / `Songti.ttc` /
`STSong.ttf` for SimSun. When a needed face cannot be found the run stops before
writing anything and lists every directory it searched. To pin a specific file:

```bash
hq_pdf_fix in.pdf --font "宋=fonts/simsun.ttc" --font "黑=fonts/simhei.ttf"
```

A font that cannot be recognised from its `/BaseFont` name is reported and left
as-is, so a wrong guess never corrupts the page.

## Usage

```
hq_pdf_fix SRC [DST] [--pages LIST] [--font FRAGMENT=PATH] [--font-dir DIR]
                [--fallback {box,blank}] [--version] [--help]
```

- `DST` is optional: without it the result is written beside the source as
  `<name>-1<ext>` (bumping to `-2`, `-3` … if that exists), so the original is
  never overwritten and repeat runs never clobber each other.
- `--pages 1-20,25` converts a subset; the rest of the pages are copied through.
- `--fallback box` (default) draws codes with no Unicode mapping — the GBK
  user-defined area — as a hollow box `□`, the convention in these e-books;
  `--fallback blank` uses a space instead.

## Python API

```python
from hq_pdf_fix import convert

written = convert("in.pdf", pages="1-20", font_dir=["/path/to/fonts"])
print(written)          # -> /path/to/in-1.pdf
```

## What it cannot fix

- **User-defined codes.** The GBK private area (`0xA140`–`0xA7A0`, `0xF8`–`0xFE`
  lead bytes, …) has no Unicode meaning; those characters are drawn as `□` and are
  not searchable, because there is nothing to search for.
- **Characters the chosen face lacks.** A rare glyph may exist in SimSun but not in
  KaiTi, for example `鑑` or `砲`. It is drawn as `□` and drops out of the text
  layer; the run names every such character. Pin a face with wider coverage via
  `--font` if it matters.
- **Fonts it does not recognise.** An unknown `/BaseFont` is reported and left
  as-is instead of guessed at.

## Validation

`py/validate_pdfs.py` converts a whole directory tree through the installed
command and measures each result with PDFium — a *different* engine from pypdf —
so that "it exited 0" is never mistaken for success. Per file it records the page
count, the characters PDFium can read back, pages that lost their text, every
warning the converter printed, and (with `--render`) whether the ink still lands
in the same place:

```bash
.venv/bin/python py/validate_pdfs.py --root pdf --out validation_logs --render 3
```

Latest run over this repository's `pdf/` tree: 38 documents / 22,625 pages, zero
failures, page counts and bookmarks intact, sampled layout within 1–2 px, 379
character codes with no Unicode mapping on the private-use pages, and 14 distinct
characters missing from the face that was assigned to them. Four inputs were
already converted and were skipped correctly. Details in
`validation_logs/report.md` and `validation_logs/logs/`.

## Development

The converter lives in `src/hq_pdf_fix/`. Install it into a virtualenv in editable
mode — there is deliberately no `hq_pdf_fix.py` at the repository root, because a
module named like the package shadows it when you work from the checkout:

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/hq_pdf_fix sample.pdf         # the installed command
.venv/bin/python -m hq_pdf_fix sample.pdf
.venv/bin/python -m build               # sdist + wheel into dist/
.venv/bin/python -m twine check dist/*
```

`py/` keeps the earlier converters that produced the already-repaired volumes in
this repository; they are kept for provenance, not for new work.

## 历史笔记

```bash
conda create --name pdf -c conda-forge python=3.14
python3 -m pip install pymupdf pytesseract pillow reportlab pdfminer.six
python3 py/1.py 0.pdf --decode-gb2312
python3 py/1.py 0.pdf --decode-gb2312 --make-pdf --font-path "/System/Library/Fonts/STHeiti Medium.ttc"
```
