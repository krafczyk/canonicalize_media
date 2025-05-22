import os
import re
from pathlib import Path
import langcodes
from langcodes import Language, tag_is_valid


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
