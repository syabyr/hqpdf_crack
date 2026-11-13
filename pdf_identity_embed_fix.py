#!/usr/bin/env python3
"""Rewrite a GBK-passthrough PDF so that macOS Preview can both render AND select text.

Source shape (0.pdf, 1.pdf, 00.pdf, I30.pdf ...): text is written as raw GB2312/GBK
byte pairs inside the content stream, while the fonts are either simple WinAnsi
TrueType fonts or non-embedded Type0/CIDFontType2 fonts with /Encoding /GBK-EUC-H.

Target shape: Type0 + /Identity-H + embedded TrueType subset (/FontFile2), where the
2-byte codes in the content stream are re-encoded to glyph IDs, /CIDToGIDMap is
/Identity, a real /W array is emitted, and /ToUnicode maps glyph ID -> Unicode.

Quartz then draws from the embedded file and extracts text through /ToUnicode, so
Preview gets a real, searchable text layer. One subset per typeface is shared by
every page of the document.

Pages are rebuilt from scratch instead of cloned, so no orphaned copy of the old
resource tree survives (that waste used to nearly double the file size), and the
outline, /PageMode and /Info are carried over from the source.

usage:
  python pdf_identity_embed_fix.py 1.pdf 111.pdf
  python pdf_identity_embed_fix.py 1.pdf out.pdf --pages 1-20
  python pdf_identity_embed_fix.py in.pdf out.pdf --font "仿宋=sample/simfang.ttf"
"""
import argparse
import io
import re
import sys
import unicodedata

from fontTools import subset
from fontTools.ttLib import TTFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    TextStringObject,
)

# (name fragment, font file, face index) -- matched against /BaseFont, first hit wins.
# Order matters: 仿宋 contains 宋, so it must be tested first.
FONT_LIBRARY = [
    ("仿宋", "sample/simfang.ttf", 0, "FangSong", "MNOPQR"),
    ("楷", "sample/simkai.ttf", 0, "KaiTi", "STUVWX"),
    ("黑", "sample/simhei.ttf", 0, "SimHei", "GHIJKL"),
    ("宋", "sample/simsun.ttc", 0, "SimSun", "ABCDEF"),
]

# Codes in the GBK user-defined area (A590, AEEC, FEBD ...) carry no standard Unicode and
# no glyph in any normal font. They are drawn as a hollow box so the hole stays visible,
# the usual convention in Chinese e-books; --fallback blank replaces them with a space.
FALLBACK_CHAR = "\u25a1"
FALLBACK_UNICODE = 0x25A1

TEXT_TOKEN = re.compile(
    rb"/([A-Za-z0-9#_.\-]+)\s+[-+]?[\d.]+\s+Tf"          # 1: font selection
    rb"|(\[(?:[^\[\]\\]|\\.)*\])\s*TJ"                    # 2: TJ array
    rb"|(\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]*>)\s*(?:Tj|'|\")"  # 3: Tj / ' / "
)
STRING_IN_ARRAY = re.compile(rb"\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]*>")


# ---------------------------------------------------------------- PDF strings

def decode_string(token: bytes) -> bytes:
    """Turn a PDF literal `(..)` or hex `<..>` string token into raw bytes."""
    if token.startswith(b"<"):
        digits = re.sub(rb"[^0-9A-Fa-f]", b"", token[1:-1])
        if len(digits) % 2:
            digits += b"0"
        return bytes.fromhex(digits.decode("ascii"))

    body = token[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == 0x5C and i + 1 < len(body):
            nxt = body[i + 1]
            if 0x30 <= nxt <= 0x37:
                digits = re.match(rb"[0-7]{1,3}", body[i + 1:]).group(0)
                out.append(int(digits, 8) & 0xFF)
                i += 1 + len(digits)
                continue
            out.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return bytes(out)


def code_to_unicode(code: bytes):
    """2-byte GBK code -> code point, or None when the code is not valid GBK."""
    try:
        char = code.decode("gbk")
    except UnicodeDecodeError:
        return None
    return ord(char) if len(char) == 1 else None


def needs_fallback(uni):
    """True when the code point cannot be drawn from a normal CJK font."""
    return uni is None or 0xE000 <= uni <= 0xF8FF


def split_codes(raw: bytes):
    """Split a text operand into characters the way a GBK reader does.

    Bytes below 0x80 are single ASCII characters (producers mix them in with the
    double-byte codes); 0x81-0xFE start a two-byte code. One trailing separator byte
    is dropped, since these writers emit `<code><space>` per glyph.

    Returns a list of code points, None marking a byte pair that is not valid GBK.
    """
    if raw and raw[-1] in (0x20, 0x0D, 0x0A):
        raw = raw[:-1]
    out = []
    index = 0
    while index < len(raw):
        byte = raw[index]
        if byte < 0x80:
            out.append(byte)
            index += 1
            continue
        out.append(code_to_unicode(raw[index:index + 2]))
        index += 2
    return out


def iter_strings(content: bytes):
    """Yield (start, end, font_resource_name, raw_bytes) for every shown string."""
    current = None
    for m in TEXT_TOKEN.finditer(content):
        if m.group(1):
            current = m.group(1).decode("latin-1")
            continue
        if m.group(2) is not None:
            base = m.start(2)
            for sm in STRING_IN_ARRAY.finditer(m.group(2)):
                yield base + sm.start(), base + sm.end(), current, decode_string(sm.group(0))
            continue
        yield m.start(3), m.end(3), current, decode_string(m.group(3))


def strip_stray_dict_ends(data: bytes) -> bytes:
    """Drop `>>` tokens that close no dictionary.

    Some producers emit a truncated `<< ... >>` pair, leaving a bare `>>` at top level.
    Viewers ignore it but strict content parsers reject the whole page.
    """
    out = bytearray()
    index = 0
    depth = 0
    changed = False
    while index < len(data):
        byte = data[index]
        if byte == 0x28:  # literal string: copy verbatim, honouring escapes and nesting
            end = index + 1
            nesting = 1
            while end < len(data) and nesting:
                if data[end] == 0x5C:
                    end += 2
                    continue
                if data[end] == 0x28:
                    nesting += 1
                elif data[end] == 0x29:
                    nesting -= 1
                end += 1
            out += data[index:end]
            index = end
            continue
        if data[index:index + 2] == b"<<":
            depth += 1
            out += b"<<"
            index += 2
            continue
        if data[index:index + 2] == b">>":
            if depth:
                depth -= 1
                out += b">>"
            else:
                changed = True
            index += 2
            continue
        out.append(byte)
        index += 1
    return bytes(out) if changed else data


# ---------------------------------------------------------------- font mapping

def base_font_name(font_dict) -> str:
    name = str(font_dict.get("/BaseFont", "")).lstrip("/")
    if any(ch in name for ch in "宋黑楷仿"):
        return name
    try:  # pypdf may hand back a latin-1 view of GBK bytes
        return name.encode("latin-1", "ignore").decode("gbk", "ignore")
    except Exception:
        return name


def classify(font_dict, overrides: dict):
    """Typeface key for one font dictionary, or None when it must be left alone.

    Type3 fonts draw their glyphs from embedded procedures, so they already work and
    rewriting them would destroy them. An unrecognised /BaseFont is left untouched too:
    guessing a typeface for unknown text would corrupt whatever it really is.
    """
    if str(font_dict.get("/Subtype")) == "/Type3":
        return None
    name = base_font_name(font_dict)
    for fragment, key in overrides.items():
        if fragment and fragment in name:
            return key
    for fragment, _path, _idx, key, _tag in FONT_LIBRARY:
        if fragment in name:
            return key
    return None


def page_resources(page):
    node = page
    for _ in range(16):  # walk the page tree for an inherited /Resources
        if "/Resources" in node:
            return node["/Resources"]
        parent = node.get("/Parent")
        if parent is None:
            break
        node = parent.get_object()
    return None


def page_alias(page, overrides, unknown=None):
    """Map /Font resource name -> typeface key for one page."""
    resources = page_resources(page)
    if not resources:
        return {}
    fonts = resources.get("/Font")
    if not fonts:
        return {}
    alias = {}
    for res_name, ref in fonts.items():
        try:
            font_dict = ref.get_object()
            key = classify(font_dict, overrides)
        except Exception:
            continue
        name = str(res_name).lstrip("/")
        if key is None:
            if unknown is not None and str(font_dict.get("/Subtype")) != "/Type3":
                unknown.add((name, base_font_name(font_dict) or "<no /BaseFont>"))
            continue
        alias[name] = key
    return alias


# ---------------------------------------------------------------- font building

def subset_font(path, face_index, unicodes):
    font = TTFont(path, fontNumber=face_index) if path.lower().endswith(".ttc") else TTFont(path)
    options = subset.Options()
    options.recalc_bounds = True
    options.notdef_outline = True
    options.drop_tables += ["DSIG"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    data = buf.getvalue()
    return data, TTFont(io.BytesIO(data))


def to_unicode_cmap(gid_to_unicode: dict) -> bytes:
    items = sorted(gid_to_unicode.items())
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    for start in range(0, len(items), 100):
        chunk = items[start:start + 100]
        lines.append("%d beginbfchar" % len(chunk))
        lines += ["<%04X> <%04X>" % (gid, uni) for gid, uni in chunk]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end", ""]
    return "\n".join(lines).encode("ascii")


def make_stream(writer, data: bytes):
    stream = DecodedStreamObject()
    stream.set_data(data)
    try:
        return writer._add_object(stream.flate_encode())
    except AttributeError:
        return writer._add_object(stream)


# ------------------------------------------------------- document level copying

def _text_score(text: str) -> int:
    """How much does this look like real text? Used to pick between UTF-16 orders."""
    score = 0
    for char in text:
        code = ord(char)
        if code == 0xFFFD or 0xE000 <= code <= 0xF8FF:
            score -= 3
        elif code < 0x80 or 0x3000 <= code <= 0x303F or 0xFF01 <= code <= 0xFF5E:
            score += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            score += 2
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            score -= 2      # Hangul is the classic symptom of byte-swapped UTF-16
        elif unicodedata.category(char)[0] in "LNPS":
            score += 1
        else:
            score -= 1
    return score


def decode_text(value) -> str:
    """Decode a PDF text string the way these producers actually meant it.

    S22PDF-era files store two broken shapes: bare GBK bytes (no BOM), and UTF-16
    whose payload is big-endian while the BOM claims little-endian. Trusting book
    metadata or outline titles to pypdf's fallback yields garbage, so decode both
    shapes here and keep the reading that scores better.
    """
    if value is None:
        return ""
    try:
        raw = value.original_bytes
    except AttributeError:
        return str(value)
    if raw[:2] in (b"\xfe\xff", b"\xff\xfe"):
        body = raw[2:]
        if len(body) % 2:
            body = body[:-1]
        readings = []
        for codec in ("utf-16-be", "utf-16-le"):
            try:
                readings.append(body.decode(codec))
            except UnicodeDecodeError:
                readings.append(body.decode(codec, "replace"))
        return max(readings, key=_text_score)
    for codec in ("gbk", "utf-8"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def import_object(writer, value):
    """Bring one source object into the writer, reusing pypdf's per-document dedupe."""
    if isinstance(value, IndirectObject):
        value = value.get_object()
    if isinstance(value, (NumberObject, FloatObject, BooleanObject, NullObject, NameObject)):
        return value
    if not hasattr(value, "clone"):
        return value
    clone = value.clone(writer)
    if getattr(clone, "indirect_reference", None) is not None:
        return clone.indirect_reference
    return writer._add_object(clone)


def _is_open(node) -> bool:
    count = node.get("/Count")
    return True if count is None else int(count) > 0


_DROP_CHARS = set(" \u3000、，。：；！？（）()《》“”‘’—―-·,.:;!?/|")
_DROP_CHARS.update(("\r", "\n", "\t"))


def _normalize(text: str) -> str:
    """Squash a heading so line breaks and punctuation stop mattering."""
    return "".join(ch for ch in text if ch not in _DROP_CHARS)


def _resembles(needle: str, text: str, slack: int = 6) -> bool:
    """Is `needle` printed somewhere in `text`?

    A stray particle or two is tolerated, because the composed bookmark and the
    printed heading do not always agree: a bookmark reading 顺生录一 sits above a
    heading printed 顺生录之一（别录一）.  The characters still have to appear in
    order inside one short stretch of text, which keeps unrelated pages out.
    """
    if needle in text:
        return True
    if len(needle) < 4:
        return False
    span = len(needle) + slack
    for start in range(len(text) - 3):
        window = text[start:start + span]
        position = matched = 0
        for char in needle:
            found = window.find(char, position)
            if found < 0:
                break
            matched += 1
            position = found + 1
        if matched * 10 >= len(needle) * 9:
            return True
    return False


def _page_head(reader, index, limit=90) -> str:
    """First few characters drawn on a page, used to confirm a bookmark target."""
    try:
        content = reader.pages[index].get_contents()
    except Exception:
        return ""
    if content is None:
        return ""
    chars = []
    for _start, _end, _font, raw in iter_strings(content.get_data()):
        for code in split_codes(raw):
            if code is None or needs_fallback(code):
                continue
            chars.append(chr(code))
            if len(chars) >= limit:
                return "".join(chars)
    return "".join(chars)


def _raw_item(array, index):
    """Read an array element without resolving a page reference to a page object."""
    try:
        return list.__getitem__(array, index)
    except (IndexError, TypeError):
        return None


def _outline_dest(reader, node):
    """Destination array of an outline node, resolving /A /GoTo and named targets."""
    dest = node.get("/Dest")
    if dest is None:
        action = node.get("/A")
        if action is None:
            return None
        action = action.get_object()
        if str(action.get("/S")) != "/GoTo":
            return None
        dest = action.get("/D")
    if isinstance(dest, IndirectObject):
        dest = dest.get_object()
    if isinstance(dest, (str, NameObject)):
        named = reader.named_destinations.get(str(dest))
        if isinstance(named, ArrayObject):
            return named
        if isinstance(named, DictionaryObject):
            page = named.get("/Page")
            return ArrayObject([page, named.get("/Type") or NameObject("/Fit")]) if page is not None else None
    return dest if isinstance(dest, ArrayObject) and dest else None


def copy_outline(reader, writer, page_refs):
    """Rebuild /Outlines on the new document.

    These books carry a navigation shell: entries are /GoToR actions into sibling
    volumes plus /Named viewer commands, so they start out as copies of those
    actions.  Jumps that really point into this volume are re-pointed at the local
    pages afterwards, otherwise the bookmark opens nothing.  Titles go through
    decode_text(), so the byte-swapped ones become readable.
    """
    root_ref = reader.trailer["/Root"].get("/Outlines")
    if root_ref is None:
        return 0
    try:
        root_node = root_ref.get_object()
    except Exception:
        return 0

    page_index = {}
    for position, page in enumerate(reader.pages):
        ref = getattr(page, "indirect_reference", None)
        if ref is not None:
            page_index[ref.idnum] = position

    new_root = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Outlines"),
    }))
    copied = 0
    seen = set()
    pending = []

    def build(parent_ref, parent_node, depth=0):
        """Copy parent_node's /First chain; return (first, last, count, visible)."""
        nonlocal copied
        if depth > 32:
            return None, None, 0, 0
        nodes = []
        ref = parent_node.get("/First")
        while ref is not None:
            node = ref.get_object() if hasattr(ref, "get_object") else ref
            if id(node) in seen:
                break
            seen.add(id(node))
            nodes.append(node)
            ref = node.get("/Next")
        if not nodes:
            return None, None, 0, 0

        made, opened = [], []
        for node in nodes:
            title = decode_text(node.get("/Title"))
            item = DictionaryObject({
                NameObject("/Title"): TextStringObject(title or " "),
                NameObject("/Parent"): parent_ref,
            })
            color = node.get("/C")
            if color:
                item[NameObject("/C")] = ArrayObject([import_object(writer, c) for c in color])
            flags = node.get("/F")
            if flags:
                item[NameObject("/F")] = NumberObject(int(flags))

            dest = _outline_dest(reader, node)
            target = None
            if dest is not None:
                anchor = _raw_item(dest, 0)
                position = None
                if isinstance(anchor, IndirectObject):
                    position = page_index.get(anchor.idnum)
                elif isinstance(anchor, int):
                    position = anchor
                if position is not None and 0 <= position < len(page_refs):
                    target = ArrayObject([page_refs[position]] +
                                         [import_object(writer, v) for v in list(dest)[1:]])
            remote_index, remote_file = None, None
            if target is not None:
                item[NameObject("/Dest")] = target
            elif "/A" in node:
                item[NameObject("/A")] = import_object(writer, node.get("/A"))
                # a cross-file jump may actually be a page of this very book
                action = node.get("/A")
                action = action.get_object() if hasattr(action, "get_object") else action
                jump = action.get("/D")
                if str(action.get("/S")) == "/GoToR" and isinstance(jump, ArrayObject) and jump:
                    anchor = _raw_item(jump, 0)
                    if isinstance(anchor, int) and not isinstance(anchor, bool):
                        remote_index = int(anchor)
                        remote_file = str(action.get("/F") or "")

            item_ref = writer._add_object(item)
            if remote_index is not None:
                pending.append((item_ref, title, remote_index, remote_file))
            made.append(item_ref)
            opened.append(_is_open(node))
            copied += 1

        below = []
        for index, item_ref in enumerate(made):
            item = item_ref.get_object()
            if index:
                item[NameObject("/Prev")] = made[index - 1]
            if index + 1 < len(made):
                item[NameObject("/Next")] = made[index + 1]
            child_first, child_last, child_total, child_visible = build(
                item_ref, nodes[index], depth + 1)
            if child_first is not None:
                item[NameObject("/First")] = child_first
                item[NameObject("/Last")] = child_last
                item[NameObject("/Count")] = NumberObject(
                    child_total if opened[index] else -child_total)
                below.append((child_total, child_visible if opened[index] else 0))
            else:
                below.append((0, 0))

        total = sum(1 + child[0] for child in below)
        visible = sum(1 + child[1] for child in below)
        return made[0], made[-1], total, visible

    first, last, total, visible = build(new_root, root_node)
    if first is None:
        return 0, 0

    # Nearly every entry is a /GoToR jump into the volume this file was cut from,
    # with 0-based page numbers and no scroll offset.  Detect that volume (the file
    # most links point at), confirm that its page numbers really do land on the
    # bookmarks' own headings, and then re-point those links at the local pages so
    # they navigate instead of asking for a sibling file.  Links into any other
    # file (the "return to volume contents" jump) are left exactly as they were.
    volume, seen_files = None, {}
    for _ref, _title, _index, remote_file in pending:
        seen_files[remote_file] = seen_files.get(remote_file, 0) + 1
    if seen_files:
        volume = max(seen_files, key=lambda name: seen_files[name])

    usable = [entry for entry in pending
              if entry[3] == volume and 0 <= entry[2] < len(page_refs)]
    heads, hits = {}, 0
    for _ref, title, index, _file in usable:
        if index not in heads:
            heads[index] = _normalize(_page_head(reader, index, 100000))
        needle = _normalize(title)[:10]
        if len(needle) < 4 or len(heads[index]) < 8:
            continue          # too short to judge, or nothing drawn (cover, scan)
        if _resembles(needle, heads[index]):
            hits += 1
    verified = sum(1 for entry in usable
                   if len(_normalize(entry[1])[:10]) >= 4
                   and len(heads.get(entry[2]) or "") >= 8)

    rebound = 0
    if verified >= 3 and hits * 5 >= verified * 2:      # at least 40 % line up
        for item_ref, _title, index, _file in usable:
            item = item_ref.get_object()
            item[NameObject("/Dest")] = ArrayObject([page_refs[index], NameObject("/Fit")])
            if NameObject("/A") in item:
                del item[NameObject("/A")]
            rebound += 1

    outline = new_root.get_object()
    outline[NameObject("/First")] = first
    outline[NameObject("/Last")] = last
    outline[NameObject("/Count")] = NumberObject(visible)
    writer._root_object[NameObject("/Outlines")] = new_root
    return total, rebound


def copy_info(reader, writer):
    """Carry /Title /Author ... over, decoded from GBK where needed."""
    info = reader.trailer.get("/Info")
    if info is None:
        return 0
    try:
        source = info.get_object()
    except Exception:
        return 0
    metadata = {}
    for key, value in source.items():
        text = decode_text(value)
        if text:
            metadata[str(key)] = text
    if metadata:
        writer.add_metadata(metadata)
    return len(metadata)


def build_type0_font(writer, base_font, tag, font_data, ttfont, gid_to_unicode):
    scale = 1000.0 / ttfont["head"].unitsPerEm
    head, hhea = ttfont["head"], ttfont["hhea"]
    os2 = ttfont.get("OS/2")

    def s(value):
        return round(value * scale)

    font_file = DecodedStreamObject()
    font_file.set_data(font_data)
    font_file = font_file.flate_encode()
    font_file[NameObject("/Length1")] = NumberObject(len(font_data))
    font_file = writer._add_object(font_file)

    descriptor = DictionaryObject({
        NameObject("/Type"): NameObject("/FontDescriptor"),
        NameObject("/FontName"): NameObject("/%s+%s" % (tag, base_font)),
        NameObject("/Flags"): NumberObject(4),
        NameObject("/FontBBox"): ArrayObject([NumberObject(s(v)) for v in
                                              (head.xMin, head.yMin, head.xMax, head.yMax)]),
        NameObject("/ItalicAngle"): NumberObject(0),
        NameObject("/Ascent"): NumberObject(s(hhea.ascent)),
        NameObject("/Descent"): NumberObject(s(hhea.descent)),
        NameObject("/CapHeight"): NumberObject(s(getattr(os2, "sCapHeight", 0) or hhea.ascent)),
        NameObject("/StemV"): NumberObject(80),
        NameObject("/MissingWidth"): NumberObject(1000),
        NameObject("/FontFile2"): font_file,
    })

    hmtx = ttfont["hmtx"]
    widths = [NumberObject(round(hmtx[ttfont.getGlyphName(gid)][0] * scale))
              for gid in range(1, max(gid_to_unicode) + 1)]

    descendant = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/CIDFontType2"),
        NameObject("/BaseFont"): NameObject("/%s+%s" % (tag, base_font)),
        NameObject("/CIDSystemInfo"): DictionaryObject({
            NameObject("/Registry"): TextStringObject("Adobe"),
            NameObject("/Ordering"): TextStringObject("Identity"),
            NameObject("/Supplement"): NumberObject(0),
        }),
        NameObject("/FontDescriptor"): writer._add_object(descriptor),
        NameObject("/DW"): NumberObject(1000),
        NameObject("/W"): ArrayObject([NumberObject(1), ArrayObject(widths)]),
        NameObject("/CIDToGIDMap"): NameObject("/Identity"),
    })

    return writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type0"),
        NameObject("/BaseFont"): NameObject("/%s+%s" % (tag, base_font)),
        NameObject("/Encoding"): NameObject("/Identity-H"),
        NameObject("/DescendantFonts"): ArrayObject([writer._add_object(descendant)]),
        NameObject("/ToUnicode"): make_stream(writer, to_unicode_cmap(gid_to_unicode)),
    }))


# ---------------------------------------------------------------- main

def parse_pages(spec, total):
    if not spec:
        return list(range(total))
    chosen = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            chosen += list(range(int(a) - 1, min(int(b), total)))
        else:
            chosen.append(int(part) - 1)
    return [p for p in chosen if 0 <= p < total]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--pages", help="1-based page list, e.g. 1-20,25 (default: all)")
    ap.add_argument("--font", action="append", default=[],
                    help="override mapping, e.g. --font 仿宋=sample/simfang.ttf")
    ap.add_argument("--fallback", choices=["box", "blank"], default="box",
                    help="glyph for codes with no Unicode mapping (default: box)")
    args = ap.parse_args()

    global FALLBACK_CHAR, FALLBACK_UNICODE
    if args.fallback == "blank":
        FALLBACK_CHAR, FALLBACK_UNICODE = "\u3000", 0x3000

    overrides = {}
    for item in args.font:
        fragment, _, path = item.partition("=")
        overrides[fragment] = path

    reader = PdfReader(args.src)
    total = len(reader.pages)
    targets = parse_pages(args.pages, total)
    print("source: %s (%d pages), converting %d page(s)" % (args.src, total, len(targets)))

    # ---- pass 1: collect the code points each typeface needs
    used, empty_pages = {}, []
    aliases = {}
    fallback_count = 0
    unknown = set()
    for index in targets:
        page = reader.pages[index]
        alias = page_alias(page, overrides, unknown)
        aliases[index] = alias
        content = page.get_contents()
        content = content.get_data() if content is not None else b""
        found = 0
        for _s, _e, font, raw in iter_strings(content):
            key = alias.get(font)
            if key is None:
                continue
            codes = split_codes(raw)
            if not codes:
                continue
            for uni in codes:
                if needs_fallback(uni):
                    uni = FALLBACK_UNICODE
                    fallback_count += 1
                used.setdefault(key, set()).add(uni)
                found += 1
        if not found:
            empty_pages.append(index)

    if not used:
        sys.exit("no GBK text found on the selected pages")
    for chars in used.values():
        chars.add(FALLBACK_UNICODE)
    print("typefaces needed: %s" % {k: len(v) for k, v in used.items()})
    if fallback_count:
        print("codes with no Unicode mapping, drawn as %r: %d" % (FALLBACK_CHAR, fallback_count))
    if empty_pages:
        print("pages without text (left untouched): %d" % len(empty_pages))
    if unknown:
        print("fonts left as-is (add --font NAME=path to convert them): %s"
              % ", ".join("/%s(%s)" % (n, f) for n, f in sorted(unknown)))

    # ---- pass 2: build one subset per typeface
    writer = PdfWriter()
    shared = {}
    for fragment, path, face_index, key, tag in FONT_LIBRARY:
        if key not in used:
            continue
        if fragment in overrides:
            path = overrides[fragment]
        data, ttfont = subset_font(path, face_index, used[key])
        cmap = ttfont.getBestCmap()
        char_to_gid, gid_to_uni, missing = {}, {}, []
        for uni in sorted(used[key]):
            glyph = cmap.get(uni)
            if glyph is None:
                missing.append(chr(uni))
                continue
            gid = ttfont.getGlyphID(glyph)
            char_to_gid[chr(uni)] = gid
            gid_to_uni.setdefault(gid, uni)
        if missing:
            print("  warning: %s lacks %d glyph(s): %s"
                  % (path, len(missing), "".join(missing[:20])))
        shared[key] = (char_to_gid, build_type0_font(writer, key, tag, data, ttfont, gid_to_uni))
        print("  %-9s %-24s %5d glyphs  subset %6.1f KB"
              % (key, path, len(gid_to_uni), len(data) / 1024.0))

    # ---- pass 3: rewrite and emit
    # Pages are assembled by hand: writer.add_page() deep-clones the source resource
    # tree, and the content streams it replaces stay behind as unreachable objects
    # (that alone nearly doubled the file size).
    rewritten = 0
    page_refs = []
    pages_node = DictionaryObject({
        NameObject("/Type"): NameObject("/Pages"),
        NameObject("/Kids"): ArrayObject([]),
        NameObject("/Count"): NumberObject(0),
    })
    pages_ref = writer._add_object(pages_node)
    writer._root_object[NameObject("/Pages")] = pages_ref

    for count, index in enumerate(targets, 1):
        page = reader.pages[index]
        alias = aliases[index]

        content = page.get_contents()
        content = content.get_data() if content is not None else b""
        replacements, cursor, output = [], 0, bytearray()
        for start, end, font, raw in iter_strings(content):
            table = shared.get(alias.get(font))
            if table is None:
                continue
            codes = split_codes(raw)
            if not codes:
                continue
            encoded = bytearray()
            for uni in codes:
                if needs_fallback(uni):
                    uni = FALLBACK_UNICODE
                gid = table[0].get(chr(uni))
                if gid is None:
                    gid = table[0].get(chr(FALLBACK_UNICODE))
                if gid is None:
                    break
                encoded += gid.to_bytes(2, "big")
            else:
                replacements.append((start, end, b"<" + encoded.hex().encode() + b">"))

        for start, end, token in replacements:
            output += content[cursor:start]
            output += token
            cursor = end
        output += content[cursor:]
        output = strip_stray_dict_ends(bytes(output))

        new_page = DictionaryObject({
            NameObject("/Type"): NameObject("/Page"),
            NameObject("/Parent"): pages_ref,
        })
        for key in ("/MediaBox", "/CropBox", "/Rotate", "/BleedBox", "/TrimBox",
                    "/ArtBox", "/UserUnit", "/Annots", "/Group", "/Tabs"):
            if key in page:
                value = page.raw_get(key)
                new_page[NameObject(key)] = import_object(writer, value)

        # keep every untouched font (Type3, Latin faces ...) and override only the
        # resources whose text we actually re-encoded
        source_res = page.get("/Resources")
        source_res = source_res if source_res is not None else DictionaryObject()
        resources = DictionaryObject()
        for key, value in source_res.items():
            if str(key) != "/Font":
                resources[NameObject(str(key))] = import_object(writer, value)
                continue
            fonts = DictionaryObject()
            for res_name, ref in (value.get_object() or {}).items():
                table = shared.get(alias.get(str(res_name).lstrip("/")))
                fonts[NameObject(str(res_name))] = table[1] if table else import_object(writer, ref)
            resources[NameObject("/Font")] = fonts
        new_page[NameObject("/Resources")] = writer._add_object(resources)

        if output != content:
            new_page[NameObject("/Contents")] = make_stream(writer, output)
            rewritten += 1
        else:
            new_page[NameObject("/Contents")] = import_object(writer, page.raw_get("/Contents"))

        ref = writer._add_object(new_page)
        page_refs.append(ref)
        pages_node[NameObject("/Kids")].append(ref)

        if count % 100 == 0:
            print("  ... %d/%d pages" % (count, len(targets)))

    pages_node[NameObject("/Count")] = NumberObject(len(page_refs))

    # ---- document level extras the source carried and a bare writer would drop
    catalog = reader.trailer["/Root"]
    for key in ("/PageMode", "/PageLayout"):
        if key in catalog:
            writer._root_object[NameObject(key)] = NameObject(str(catalog[key]))
    bookmarks, rebound = copy_outline(reader, writer, page_refs)
    if bookmarks:
        print("restored %d bookmark(s)%s" % (
            bookmarks, ", %d of them re-bound to pages in this file" % rebound if rebound else ""))
    info_fields = copy_info(reader, writer)
    if info_fields:
        print("restored document information (%d field(s))" % info_fields)

    with open(args.dst, "wb") as fh:
        writer.write(fh)
    print("rewrote text on %d page(s); wrote %s" % (rewritten, args.dst))


if __name__ == "__main__":
    main()
