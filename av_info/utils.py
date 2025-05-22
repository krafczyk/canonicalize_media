import os
import re
from langcodes import Language


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
    Given a path like "English(SDH).srt" or "/subs/fra.srt", try to
    guess the language and return its ISO 639-2/T code (e.g. "eng", "fra").
    Returns None if no match is found.
    """
    # 1) Basename without extension
    base = os.path.splitext(os.path.basename(path))[0]
    # 2) Drop anything in parentheses
    cleaned = re.sub(r'\(.*?\)', '', base)
    # 3) Split on non-alphanumeric to yield tokens
    tokens = re.split(r'[^A-Za-z0-9]+', cleaned)
    for tok in tokens:
        if not tok:
            continue
        t = tok.lower()
        # Try interpreting as a tag first (pt, por, eng, spa, etc)
        if len(t) in (2, 3):
            try:
                code3 = Language.get(t).to_alpha3()
                return code3
            except Exception:
                pass
        # Otherwise, try interpreting it as a language name
        try:
            code3 = Language.get(t).to_alpha3()
            return code3
        except Exception:
            pass
    return None
