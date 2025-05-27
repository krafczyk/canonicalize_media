import re
import os
import difflib
from pathlib import Path
from av_info.omdb import OMDbItem, query, search, MediaType
from typing import NamedTuple


#_ILLEGAL = re.compile(r'[\\/:*?"<>|]+')      # chars not allowed in filenames
_ILLEGAL = re.compile(r'[\\*?"<>|]+')      # chars not allowed in filenames

def _clean(text: str) -> str:
    """Strip illegal filesystem characters and extra whitespace."""
    return _ILLEGAL.sub('', text).strip()

def _first_year(year_field: str) -> str:
    """
    OMDb's Year can be '2020', '2011–2019', '2024–', etc.
    Grab the first 4-digit run.
    """
    m = re.search(r'\d{4}', year_field or '')
    if not m:
        raise ValueError(f"Cannot parse year from {year_field!r}")
    return m.group()


def build_media_path(
    omdb: OMDbItem,
    *,
    ext: str = "mkv",
    resolution: str | None = None,
    version: str | None = None,
    edition: str | None = None,
) -> Path:
    """
    Build a Plex-friendly path for a Movie, Series, or Episode.

    Parameters
    ----------
    omdb        : OMDbItem | dict
        JSON object returned from the OMDb API.
    ext         : str
        Desired filename extension (default ``"mkv"``).
    resolution  : str | None
        Optional resolution tag (e.g. ``"1080p"``, ``"4K"``).
    version     : str | None
        Optional extra tag such as ``"HDR"`` or ``"BluRay"``.
    edition     : str | None
        Edition/cut name (e.g. ``"Director's Cut"``). Added as
        ``{edition-Director's Cut}`` per Plex naming.

    Returns
    -------
    pathlib.Path
        ``<folders>/<filename>``
    """
    media_type = omdb.get("Type")

    edition_part = f"{{edition-{_clean(edition)}}}" if edition else ""

    # ------------------------------------------------------------------ #
    # Movies
    # ------------------------------------------------------------------ #
    if media_type == "movie":
        title = _clean(omdb["Title"])
        year = _first_year(omdb["Year"])

        if edition:
            folder = Path(f"{title} ({year}) {edition_part}")
        else:
            folder = Path(f"{title} ({year})")

        # ---- filename ----
        fn_parts: list[str] = [f"{title} ({year})"]

        # Optional – order is important for Plex:
        #  Title (Year) - 4K {edition-Director's Cut}.mkv
        if resolution:
            fn_parts.append(resolution)

        # Edition *must* be inside curly braces with the prefix
        if edition:
            fn_parts.append(edition_part)

        filename = " - ".join(fn_parts) + f".{ext.lstrip('.')}"
        return folder / filename

    # ------------------------------------------------------------------ #
    # Series (show record)
    # ------------------------------------------------------------------ #
    if media_type == "series":
        series_title = _clean(omdb["Title"])
        first_year = _first_year(omdb["Year"])
        return Path(f"{series_title} ({first_year})")

    # ------------------------------------------------------------------ #
    # Episode
    # ------------------------------------------------------------------ #
    if media_type == "episode":
        # 1)  Retrieve the parent-series info, favouring a live lookup.
        series_id = omdb.get("seriesID")  # OMDb uses lowercase 'seriesID'
        series_meta: OMDbItem | None = None
        if not series_id:
            raise ValueError("Episode record must contain 'seriesID' field.")
        series_meta = query(imdb_id=series_id)
        if not series_meta:
            raise ValueError("Cannot find series metadata for episode.")

        series_title = _clean(series_meta["Title"])
        first_year = _first_year(series_meta["Year"])

        # 2)  Validate required fields
        if "Season" not in omdb or "Episode" not in omdb:
            raise ValueError("Episode record must contain 'Season' and 'Episode' fields.")

        season_num = int(omdb["Season"])
        episode_num = int(omdb["Episode"])
        ep_title = _clean(omdb["Title"])

        show_name = Path(f"{series_title} ({first_year})")
        season_dir = show_name / f"Season {season_num:02d}"

        # ---- filename ----
        fn_parts: list[str] = [ str(show_name) , f"s{season_num:02d}e{episode_num:02d}", ep_title ]

        # Optional – order is important for Plex:
        #  Title (Year) - 4K {edition-Director's Cut}.mkv
        if resolution:
            fn_parts.append(resolution)

        # Edition *must* be inside curly braces with the prefix
        if edition:
            fn_parts.append(edition_part)

        filename = " - ".join(fn_parts) + f".{ext.lstrip('.')}"
        return season_dir / filename

    # ------------------------------------------------------------------ #
    # Unsupported / unknown
    # ------------------------------------------------------------------ #
    raise ValueError(f"Unsupported OMDb type: {media_type!r}")


# ---------------------------------------------------------------------------
# Supporting functions for OMDb filename guessing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1.  Constants and quick-and-dirty helpers
# ---------------------------------------------------------------------------

COMMON_TAGS: set[str] = {
    # video / audio formats
    "x264", "x265", "h264", "hevc", "av1", "aac", "dts", "ddp", "atmos",
    # resolutions / quality
    "480p", "720p", "1080p", "2160p", "4k", "hdr", "hdr10", "hdr10+", "dv",
    # release sources / cut names
    "bluray", "blu-ray", "web", "webrip", "web-dl",
    "yify", "yts", "rarbg", "ettv", "yts.mx",
    "proper", "repack", "remux", "extended", "imax", "dc", "remastered",
    # containers / misc
    "mp4", "mkv", "avi"
}
_TAG_RX = re.compile(r"|".join(re.escape(t) for t in sorted(COMMON_TAGS, key=len, reverse=True)), re.I)
_YEAR_RX = re.compile(r"\b(19|20)\d{2}\b")
_SEASON_EP_RX = re.compile(r"[Ss](\d{1,2})[ ._-]?[Ee](\d{1,2})")

def _clean_tokens(s: str) -> str:
    s = _TAG_RX.sub(" ", s)                # drop technical tags
    s = re.sub(r"[\[\]()._-]+", " ", s)    # unify delimiters
    s = re.sub(r"\s{2,}", " ", s)          # squeeze spaces
    return s.strip()

def _title_similarity(a: str, b: str) -> float:
    """Return ratio 0-100 using stdlib’s quick ratio."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100

# ---------------------------------------------------------------------------
# 2.  Information we might extract from the filename
# ---------------------------------------------------------------------------

class Guess(NamedTuple):
    media_type: MediaType
    title:      str
    year:       int | None
    season:     int | None
    episode:    int | None

def _first_int(match: re.Match[str] | None) -> int | None:
    return int(match.group()) if match else None

def _guess_from_path(path: Path) -> Guess:
    stem = path.stem
    parents = path.parents

    # --- Detect SxxEyy ------------------------------------------------------
    se_match = _SEASON_EP_RX.search(stem)
    if not se_match:                       # some rippers use "3x02"
        se_match = re.search(r"(\d{1,2})x(\d{2})", stem)
    if se_match:
        season, ep = map(int, se_match.groups())
        # try series title = directory one or two levels up, else cleaned stem
        parent_titles = [
            _clean_tokens(p.name) for p in (parents[0:2])
            if p.name and not _YEAR_RX.search(p.name)
        ]
        title = max(parent_titles, key=len, default=_clean_tokens(stem.split(se_match.group(0))[0]))
        return Guess("episode", title, None, season, ep)

    # --- Looks like a movie -------------------------------------------------
    year_match = _YEAR_RX.search(stem)
    year = int(year_match.group()) if year_match else None
    before_year = stem[:year_match.start()] if year_match else stem
    title = _clean_tokens(before_year)
    return Guess("movie", title, year, None, None)

# ---------------------------------------------------------------------------
# 3.  Main public function
# ---------------------------------------------------------------------------

def omdb_from_filename(
    filename: str | os.PathLike,
    *,
    api_key: str | None = None,
    session=None,                         # type: ignore[override]
    fuzzy_threshold: float = 80.0,        # reject anything < threshold
) -> OMDbItem | None:
    """
    Given one file path, return the single best OMDbItem (or None).
    It starts with the most specific query and relaxes until it finds <= 1 hit.
    """

    path = Path(filename)
    g = _guess_from_path(path)

    # --- 3a. Try a direct *query* first (exact title & year) ----------------
    if g.media_type == "movie":
        item = query(
            title=g.title,
            year=g.year,
            media_type="movie",
            api_key=api_key,
            session=session,
        )
        if item is not None:
            return item

    # --- 3b. Do a *search* and score results --------------------------------
    # For a series episode we first find the series, then the episode
    if g.media_type == "episode":
        # 1. find the show’s seriesID via a ‘series’ search
        hits = search(
            title=g.title,
            media_type="series",
            api_key=api_key,
            session=session,
            max_pages=1,
        )
        if not hits:
            return None
        series = max(hits, key=lambda h: _title_similarity(h["Title"], g.title))
        if _title_similarity(series["Title"], g.title) < fuzzy_threshold:
            return None

        # 2. now query the exact episode
        ep = query(
            imdb_id=series["imdbID"],
            season=g.season,
            episode=g.episode,
            media_type="episode",
            api_key=api_key,
            session=session,
        )
        return ep

    # Movie fallback: widen the search progressively (title only, then add dirs)
    dirs = [p.name for p in path.parents if p.name]
    for extra in [""] + dirs:                   # start with basename, then climb
        search_title = f"{g.title} {extra}".strip()
        hits = search(
            title=search_title,
            media_type="movie",
            year=g.year,
            api_key=api_key,
            session=session,
            max_pages=3,
        )
        if not hits:
            continue
        # pick best fuzzy match
        best = max(hits, key=lambda h: _title_similarity(h["Title"], g.title))
        score = _title_similarity(best["Title"], g.title)
        if score >= fuzzy_threshold:
            return best

    return None
