import re
import os
from pathlib import Path
import langcodes
import numpy as np
from langcodes import Language, tag_is_valid
from collections.abc import Sequence
import unicodedata


def version_tuple(ver_str: str) -> tuple[int,...]:
    return tuple(map(int, ver_str.split('.')))


def get_h264_level_name(level: int) -> str:
    """Return the H.264 level name for a given numeric level value."""
    mapping = {
        10: "1.0",
        11: "1.1",
        12: "1.2",
        13: "1.3",
        20: "2.0",
        21: "2.1",
        22: "2.2",
        30: "3.0",
        31: "3.1",
        32: "3.2",
        40: "4.0",
        41: "4.1",
        42: "4.2",
        50: "5.0",
        51: "5.1",
        52: "5.2"
    }
    return mapping.get(level, "unknown")


def get_hevc_level_name(level:int) -> str:
    """Return the HEVC level name for a given numeric level value."""
    mapping = {
        30:  "1",
        60:  "2",
        63:  "2.1",
        90:  "3",
        93:  "3.1",
        120: "4",
        123: "4.1",
        150: "5",
        153: "5.1",
        156: "5.2",
        180: "6",
        183: "6.1",
        186: "6.2"
    }
    return mapping.get(level, "unknown")


def guess_lang_from_filename(path: str) -> str | None:
    """
    Given a filename (possibly with a path) like
    ".../Subs/Danish.srt" or "pt.srt" or "English(SDH).srt", return
    the ISO 639-2/T code (e.g. "dan", "por", "eng") or None.
    """
    stem = Path(path).stem
    cleaned = re.sub(r'\(.*?\)', '', stem)
    tokens = re.split(r'[^A-Za-z]+', cleaned)

    for tok in tokens:
        if not tok:
            continue
        lower = tok.lower()

        # 1) If it's already a valid BCP-47 tag, normalize to 3-letter
        if tag_is_valid(lower):
            try:
                return Language.get(lower).to_alpha3()
            except Exception:
                pass

        # 2) Fuzzy-match a language *name* (e.g. "Danish", "français")
        try:
            lang = langcodes.find(tok)  # <-- recognizes names as well as tags :contentReference[oaicite:0]{index=0}
            # lang might be something like Language.make(language='da')
            return lang.to_alpha3()
        except Exception:
            pass

    return None


def ask_continue(prompt: str = "Continue? [N/y] ") -> bool:
    """
    Ask the user whether to continue.
    Returns True only if the user enters 'y' or 'Y'.
    Empty input or anything else is treated as 'no'.
    """
    while True:
        reply = input(prompt).strip()          # read a line, strip whitespace
        if not reply:                          # user just hit Enter → default = No
            return False
        if reply.lower() == "y":               # accepted affirmative
            return True
        if reply.lower() == "n":               # explicit negative
            return False
        print("Please enter 'y' or 'n'.")      # loop again for any other input


_ILLEGAL = re.compile(r'[\\*?"<>|]+')      # chars not allowed in filenames
NOISE_TOKENS = {
    "720p","1080p","2160p","4k","hdr","dv","hevc","x264","x265","10bit","bluray",
    "brrip","webrip","web","yify","yts","dd","dts","aac","hmax",
    "extended","uncut"
}

def clean(text: str) -> str:
    """Strip illegal filesystem characters and extra whitespace."""
    return _ILLEGAL.sub('', text).strip()

def first_year(year_field: str) -> str:
    """
    OMDb's Year can be '2020', '2011–2019', '2024–', etc.
    Grab the first 4-digit run.
    """
    m = re.search(r'\d{4}', year_field or '')
    if not m:
        raise ValueError(f"Cannot parse year from {year_field!r}")
    return m.group()

def tokenize(path: Path) -> list[list[str]]:
    """Split each path segment (dirs + filename without extension) on space, doct, underscore and dash."""
    # 1. Remove the extension from the final segment
    no_ext = path.with_suffix('')
    # 2. Build a list of the segments, skipping root (Unix "/") or drive letters (Windows "C:\\")
    segments = [
        seg for seg in no_ext.parts
        if seg not in (path.root, path.drive)]

    return [
        [ tok for tok in re.split(r"[.\s_\-]+", seg) if tok ]
        for seg in segments
    ]

def clean_tokens(tokens: Sequence[str]) -> list[str]:
    return [t for t in tokens if t.lower() not in NOISE_TOKENS]

# ---- 1.  Declare your substitutions here ----------------------------
#
#   • Keys are regex patterns (use raw strings, ^/$ anchors unnecessary).
#   • Values are the canonical form you want that pattern replaced with.
#
#   Put every variant of a word/symbol on the *left* and its
#   single canonical representative on the *right*.
#
DEFAULT_SUBS: dict[str, str] = {
    r"&": "and",               # symbol to word
    r"\band\b": "and",         # word to word (ensures whole-word match)
    r"’": "'",                 # curly apostrophe to straight
    r"—|–": "-",               # em/en dash to hyphen
    r"\s*\(\s*the\s*\)\s*": " ",  # scrub trailing/leading "(The)"
    # add more as you encounter them…
}

def sanitize_filename(filepath: str) -> str:
    return filepath.replace('/', '_')

# Pre-compile patterns once for speed.
_SUB_PATTERNS = [(re.compile(pat, flags=re.IGNORECASE), repl)
                 for pat, repl in DEFAULT_SUBS.items()]

# Characters we simply erase (punctuation that rarely changes semantics)
_PUNCT_TABLE = str.maketrans("", "", r"""!"#$%()*+,./:;?@[\]^_`{|}~""")

# ---- 2.  Normalisation routine --------------------------------------
def normalise_title(title: str, extra_subs: dict[str, str] | None = None) -> str:
    """
    Return a canonical representation of *title* suitable for equality tests.
    Supply *extra_subs* to add/override substitution rules at call-time.
    """
    # a.  Unicode → closest ASCII (e.g. “Pokémon” → “Pokemon”)
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()

    # b.  Lower-case & collapse runs of whitespace
    t = re.sub(r"\s+", " ", t.lower())

    # c.  Apply core and caller-supplied substitution rules
    patterns = _SUB_PATTERNS.copy()
    if extra_subs:
        patterns += [(re.compile(p, re.I), r) for p, r in extra_subs.items()]

    for pat, repl in patterns:
        t = pat.sub(repl, t)

    # d.  Strip punctuation we don’t care about
    t = t.translate(_PUNCT_TABLE)

    # e.  Final tidy-up
    return t.strip()

# ---- 3.  Convenience wrapper ----------------------------------------
def titles_equal(a: str, b: str, extra_subs: dict[str,str] | None = None) -> bool:
    """Case/format-insensitive comparison of two media titles."""
    return normalise_title(a, extra_subs=extra_subs) == normalise_title(b, extra_subs=extra_subs)


def get_device() -> int | None:
    device = None
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        device = int(os.environ["CUDA_VISIBLE_DEVICES"].split(",")[0])
    return device
