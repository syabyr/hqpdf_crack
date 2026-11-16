#!/usr/bin/env python3
"""Convert every PDF under a directory tree with ``hq_pdf_fix`` and report problems.

For each file the converter is run as a real subprocess (exactly the installed
command), its stdout/stderr are captured to a log, and the result is measured with
PDFium -- the second engine -- so that "it exited 0" is never taken as success:

  * page count preserved, bookmarks and /Info restored
  * characters PDFium can read back from the output, per sampled page and in total
  * how many pages still carry no text at all
  * every warning the converter emitted (unrecognised fonts, missing glyphs,
    user-defined codes, pages left alone)

usage:
  python py/validate_pdfs.py                     # pdf/ -> validation_logs/
  python py/validate_pdfs.py --root pdf --out /tmp/v
  python py/validate_pdfs.py --root pdf --only 毛泽东
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pypdfium2 as pdfium

TEXT_NEEDED = re.compile(r"typefaces needed: \{(.*)\}")
NO_GBK = "no GBK text found on the selected pages"
LEFT_AS_IS = re.compile(r"fonts left as-is[^:]*: (.*)")
MISSING_GLYPHS = re.compile(r"warning: (\S+) lacks (\d+) glyph")
NO_UNICODE = re.compile(r"codes with no Unicode mapping.*: (\d+)")
PAGES_NO_TEXT = re.compile(r"pages without text \(left untouched\): (\d+)")
REWROTE = re.compile(r"rewrote text on (\d+) page\(s\)")
BOOKMARKS = re.compile(r"restored (\d+) bookmark")
INFO_FIELDS = re.compile(r"restored document information \((\d+) field")


def pdf_pages(path):
    """Page count, or None when the file will not open."""
    try:
        with pdfium.PdfDocument(str(path)) as doc:
            return len(doc)
    except Exception:
        return None


def text_stats(path, sample_limit=0):
    """(total chars, empty pages, per-page char list for the sampled pages)."""
    total = empty = 0
    sample = []
    with pdfium.PdfDocument(str(path)) as doc:
        count = len(doc)
        for index in range(count):
            try:
                page = doc[index]
                text = page.get_textpage().get_text_range()
                page.close()
            except Exception:
                text = ""
            length = len(text.strip())
            total += length
            if length == 0:
                empty += 1
            if sample_limit and index in sample_pages(count, sample_limit):
                sample.append((index + 1, length))
        return total, empty, sample


def sample_pages(count, limit):
    """First two, last two and a couple from the middle."""
    if count <= limit:
        return set(range(count))
    picks = {0, 1, count - 2, count - 1}
    step = max(count // limit, 1)
    index = 2
    while len(picks) < limit and index < count - 2:
        picks.add(index)
        index += step
    return picks


def run_converter(src, dst, timeout):
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "hq_pdf_fix", str(src), str(dst)],
        capture_output=True, text=True, timeout=timeout,
    )
    return proc, time.time() - started


def parse_log(text):
    found = {
        "faces": "", "left_as_is": [], "missing_glyphs": 0,
        "no_unicode": 0, "pages_untouched": 0, "rewrote": 0,
        "bookmarks": 0, "info_fields": 0, "no_gbk": NO_GBK in text,
    }
    match = TEXT_NEEDED.search(text)
    if match:
        found["faces"] = match.group(1).strip()
    match = LEFT_AS_IS.search(text)
    if match:
        found["left_as_is"] = [part for part in match.group(1).split(",") if part.strip()]
    match = MISSING_GLYPHS.search(text)
    if match:
        found["missing_glyphs"] = int(match.group(2))
    for key, pattern in (("no_unicode", NO_UNICODE), ("pages_untouched", PAGES_NO_TEXT),
                         ("rewrote", REWROTE), ("bookmarks", BOOKMARKS),
                         ("info_fields", INFO_FIELDS)):
        match = pattern.search(text)
        if match:
            found[key] = int(match.group(1))
    return found


def audit(src, dst):
    """Compare source and output with PDFium."""
    result = {"src_pages": pdf_pages(src), "dst_pages": pdf_pages(dst) if dst.exists() else None}
    if result["dst_pages"] is None:
        return result
    result["dst_chars"], result["dst_empty"], result["dst_sample"] = text_stats(dst)
    result["src_chars"], result["src_empty"], _ = text_stats(src)
    result["src_mb"] = src.stat().st_size / 1048576.0
    result["dst_mb"] = dst.stat().st_size / 1048576.0
    return result


def verdict(proc, log, metrics):
    if log["no_gbk"]:
        return "SKIP", "no GBK text found"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return "FAIL", tail[-1] if tail else "exit %d" % proc.returncode
    if metrics.get("dst_pages") != metrics.get("src_pages"):
        return "FAIL", "page count %s -> %s" % (metrics.get("src_pages"), metrics.get("dst_pages"))
    if not metrics.get("dst_chars"):
        return "FAIL", "output has no readable text"
    notes = []
    if log["left_as_is"]:
        notes.append("%d font(s) left as-is" % len(log["left_as_is"]))
    if log["missing_glyphs"]:
        notes.append("%d glyph(s) missing from font" % log["missing_glyphs"])
    if log["no_unicode"]:
        notes.append("%d code(s) drawn as fallback" % log["no_unicode"])
    if metrics.get("dst_empty"):
        notes.append("%d page(s) without text" % metrics["dst_empty"])
    return ("WARN" if notes else "PASS"), "; ".join(notes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="pdf")
    ap.add_argument("--out", default="validation_logs")
    ap.add_argument("--only", default="", help="substring filter on the path")
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    logs.mkdir(exist_ok=True)

    files = sorted(p for p in root.rglob("*")
                   if p.is_file() and p.suffix.lower() == ".pdf" and args.only in str(p))
    print("%d files under %s" % (len(files), root), flush=True)

    rows = []
    for number, src in enumerate(files, 1):
        label = str(src.relative_to(root))
        safe = re.sub(r"[^\w.\-]+", "_", str(src.relative_to(root)))
        dst = out / ("converted_" + safe)
        print("[%2d/%2d] %s" % (number, len(files), label), flush=True)
        proc, elapsed = run_converter(src, dst, args.timeout)
        text = (proc.stdout or "") + (("" if not proc.stderr else "\n[stderr]\n" + proc.stderr))
        (logs / (safe + ".log")).write_text(text, encoding="utf-8")

        log = parse_log(text)
        metrics = audit(src, dst)
        status, note = verdict(proc, log, metrics)
        rows.append({"file": label, "status": status, "note": note, "seconds": elapsed,
                     "log": log, **metrics})
        print("        %-4s %5.1fs  %s" % (status, elapsed, note), flush=True)

    write_report(out / "report.md", rows)
    print("\nreport: %s" % (out / "report.md"))
    for status in ("FAIL", "WARN", "SKIP"):
        count = sum(1 for row in rows if row["status"] == status)
        print("  %-4s %d" % (status, count))


def write_report(path, rows):
    lines = ["# hq_pdf_fix validation", ""]
    lines.append("| status | file | pages | chars (pdfium) | empty pages | mb | s | note |")
    lines.append("|---|---|---|---|---|---|---|---|")
    order = {"FAIL": 0, "WARN": 1, "SKIP": 2, "PASS": 3}
    for row in sorted(rows, key=lambda item: (order[item["status"]], item["file"])):
        pages = "%s->%s" % (row.get("src_pages"), row.get("dst_pages"))
        chars = "%s->%s" % (row.get("src_chars"), row.get("dst_chars"))
        empty = "%s->%s" % (row.get("src_empty"), row.get("dst_empty"))
        mb = "%.1f->%.1f" % (row.get("src_mb", 0), row.get("dst_mb", 0))
        lines.append("| %s | `%s` | %s | %s | %s | %s | %.1f | %s |"
                     % (row["status"], row["file"], pages, chars, empty, mb,
                        row["seconds"], row["note"]))
    lines.append("")
    lines.append("## details")
    for row in rows:
        if row["status"] == "PASS":
            continue
        log = row["log"]
        lines.append("")
        lines.append("### %s (%s)" % (row["file"], row["status"]))
        lines.append("- faces rebuilt: %s" % (log["faces"] or "none"))
        if log["left_as_is"]:
            lines.append("- left as-is: %s" % ", ".join(log["left_as_is"]))
        lines.append("- fallback codes: %d, missing glyphs: %d, pages rewritten: %d"
                     % (log["no_unicode"], log["missing_glyphs"], log["rewrote"]))
        lines.append("- bookmarks: %d, info fields: %d" % (log["bookmarks"], log["info_fields"]))
        if row.get("dst_sample"):
            lines.append("- sampled pages (page: chars): %s"
                         % ", ".join("%d:%d" % pair for pair in row["dst_sample"]))
        lines.append("- log: logs/%s.log" % re.sub(r"[^\w.\-]+", "_", row["file"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
