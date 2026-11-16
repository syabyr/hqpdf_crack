"""Locate the CJK typefaces these documents name but never embed.

The Sim* faces cannot ship inside the wheel -- they are proprietary (Microsoft /
Zhongyi) and would add ~29 MB -- so they are resolved at run time instead.  A face
is looked up by a list of known file names in an ordered set of directories: what
the caller passed with --font-dir, then $HQ_PDF_FIX_FONT_DIR, the working
directory's fonts/, a fonts/ folder bundled next to the package, a per-user data
directory, and finally the platform's own font directories (where macOS, Windows
and Linux keep compatible faces under different names).
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "HQ_PDF_FIX_FONT_DIR"


@dataclass(frozen=True)
class Face:
    """One typeface the converter can rebuild, with its subset tag.

    `fragment` is matched against the decoded /BaseFont name; order matters,
    because 仿宋 contains 宋 and must be tested before it.  `aliases` catches the
    same faces when a file names them in Latin (SimSun, Songti, STSongti ...),
    which is how already-subsetted files spell them.
    """

    key: str
    tag: str
    fragment: str
    candidates: tuple
    aliases: tuple = ()
    face_index: int = 0


FACES = (
    Face("FangSong", "MNOPQR", "仿宋",
         ("simfang.ttf", "FangSong.ttf", "fangsong.ttf", "STFangsong.ttf"),
         ("fangsong", "stfangsong")),
    Face("KaiTi", "STUVWX", "楷",
         ("simkai.ttf", "KaiTi.ttf", "kaiti.ttf", "STKaiti.ttf", "Kaiti.ttc"),
         ("kaiti", "stkaiti")),
    Face("SimHei", "GHIJKL", "黑",
         ("simhei.ttf", "simhei.ttc", "SimHei.ttf",
          "STHeiti Medium.ttc", "STHeiti Light.ttc"),
         ("simhei", "heiti", "stheiti")),
    Face("SimSun", "ABCDEF", "宋",
         ("simsun.ttc", "simsun.ttf", "SimSun.ttf", "songti.ttc", "Songti.ttc",
          "STSong.ttf", "STSongti-SC-Regular.otf"),
         ("simsun", "songti", "stsong")),
)


def _platform_dirs():
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"),
                Path.home() / "Library/Fonts"]
    if os.name == "nt":
        windir = os.environ.get("WINDIR") or r"C:\Windows"
        local = os.environ.get("LOCALAPPDATA")
        dirs = [Path(windir) / "Fonts"]
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            Path.home() / ".fonts", data_home / "fonts"]


def search_dirs(extra=(), env=None):
    """Ordered list of directories to look in, first hit wins."""
    env = os.environ if env is None else env
    dirs = [Path(value).expanduser() for value in extra if value]
    for value in (env.get(ENV_VAR) or "").split(os.pathsep):
        if value:
            dirs.append(Path(value).expanduser())
    dirs.append(Path.cwd() / "fonts")
    here = Path(__file__).resolve().parent
    dirs.append(here / "fonts")
    dirs.append(here.parent.parent / "fonts")          # source checkout (src/../..)
    dirs.append(Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
                / "hq_pdf_fix" / "fonts")
    dirs += _platform_dirs()
    seen, unique = set(), []
    for directory in dirs:
        key = str(directory)
        if key not in seen and directory.is_dir():
            seen.add(key)
            unique.append(directory)
    return unique


def find(face, dirs):
    """First existing file for `face` among `dirs`, or None."""
    for directory in dirs:
        for name in face.candidates:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def resolve(face, dirs):
    """Path for `face`, or raise LookupError with what was tried and how to fix it."""
    found = find(face, dirs)
    if found is not None:
        return found
    searched = "\n".join("  " + str(directory) for directory in dirs) or "  (none)"
    raise LookupError(
        "no font file for %s (%s) found. Looked for %s in:\n%s\n"
        "Point the converter at a directory holding the face, e.g.\n"
        "  hq_pdf_fix in.pdf --font-dir /path/to/fonts\n"
        "  %s=/path/to/fonts hq_pdf_fix in.pdf\n"
        "or name the file directly:\n"
        "  hq_pdf_fix in.pdf --font \"%s=/path/to/%s\""
        % (face.key, face.fragment, ", ".join(face.candidates), searched,
           ENV_VAR, face.fragment, face.candidates[0]))
