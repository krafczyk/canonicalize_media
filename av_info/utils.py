import os
import re
from pathlib import Path
import langcodes
from langcodes import Language, tag_is_valid
from collections.abc import Iterator
from av_info.omdb import MediaType, OMDbItem, query_title, search_title
from typing import cast
import requests
from rapidfuzz import fuzz, process
from pprint import pprint


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


_year_pat = re.compile(r"(19|20)\d{2}")

def candidate_pairs_from_path(path: str) -> Iterator[tuple[str, int | None]]:
    """
    Yield (title, year) pairs with decreasing confidence.
    Strategy:
      • First line - folder or filename stripped of tags
      • Optional year in parentheses / bare 4-digit token
      • Gradually remove more noise.
    """
    p = Path(path)
    stem = p.stem
    pieces: list[Path | str] = [stem] + list(p.parents)
    for raw in pieces:
        # 1) Split on dots, brackets, dashes, underscores, etc.
        raw = cast(str, raw)
        tokens = re.split(r"[.\-_()\[\]]+", raw)
        tokens = [t for t in tokens if t]
        # 2) Detect a year token (first one wins)
        yr: int | None = None
        for t in tokens:
            m = _year_pat.fullmatch(t)
            if m:
                yr = int(t)
                tokens.remove(t)
                break
        # 3) Drop common "junk" tokens (resolution, codecs, release groups...)
        junk = {"1080p", "720p", "2160p", "480p", "hdr", "webrip", "bluray",
                "x264", "x265", "10bit", "yts", "yify", "dvdrip", "web",
                "dl", "h264", "hevc"}
        clean_tokens = [t for t in tokens if t.lower() not in junk]
        if not clean_tokens:
            continue
        title = " ".join(clean_tokens)
        yield title, yr

# ---------------------------------------------------------------------------
# 4. Orchestrator – search OMDb until something scores ≥ threshold
# ---------------------------------------------------------------------------
def find_best_match(
    path: str,
    *,
    media_type: MediaType = "movie",
    threshold: int = 90,
    max_titles: int = 10,
) -> OMDbItem | None:
    session = requests.Session()
    for title, yr in candidate_pairs_from_path(path):
        # 1) direct hit first
        data = query_title(title, yr, media_type, session=session)
        if data:
            return data
        # 2) fall back to search list + fuzzy ranking
        pool = search_title(title, yr, media_type, session=session)
        if pool:
            # highest token-set-ratio against pool
            choices = {item["Title"]: item for item in pool}
            best, score, _ = process.extractOne(
                title, choices.keys(), scorer=fuzz.token_set_ratio)
            if score >= threshold:
                return choices[best]
    return None


def guess_imdb_id_from_media_file(filepath: str, media_type: MediaType = "movie") -> str | None:
    res = find_best_match(filepath, media_type=media_type)
    if res is not None:
        pprint(res)
        return res['imdbID']
    return None
