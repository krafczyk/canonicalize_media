import re
import os
import difflib
from pathlib import Path
from av_info.omdb import OMDbItem, query, search, MediaType
from typing import NamedTuple, Sequence, TypedDict


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
# Regexes & constants
# ---------------------------------------------------------------------------
IMDB_RE      = re.compile(r"tt\d{7,8}")
SEAS_EP_RE   = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")       # s03e12 / S3E2 / s03e02 etc.
YEAR_RE      = re.compile(r"(19|20)\d{2}")
NOISE_TOKENS = {
    "720p","1080p","2160p","4k","hdr","dv","hevc","x264","x265","10bit","bluray",
    "brrip","webrip","web","yify","yts","dd","dts","aac","hmax",
    "extended","uncut"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tokenize(path: Path) -> list[str]:
    """Split dirname + basename on space, dot, underscore and dash."""
    stem = path.stem
    parts = re.split(r"[.\s_\-]+", stem)
    return [p for p in parts if p]

def _clean_tokens(tokens: Sequence[str]) -> list[str]:
    return [t for t in tokens if t.lower() not in NOISE_TOKENS]

def _best_match(
    wanted: str,  # cleaned title we expect
    candidates: Sequence[OMDbItem],
    cutoff: float = 0.6,
) -> OMDbItem | None:
    """Pick the candidate whose Title is closest to 'wanted' (difflib ratio)."""
    def score(item: OMDbItem) -> float:
        return difflib.SequenceMatcher(None, wanted.lower(), item["Title"].lower()).ratio()
    scored = sorted(((score(c), c) for c in candidates), reverse=True, key=lambda t: t[0])
    return scored[0][1] if scored and scored[0][0] >= cutoff else None

# ---------------------------------------------------------------------------
# The public helper
# ---------------------------------------------------------------------------
def guess_omdb_from_path(
    path_str: str,
    *,
    api_key: str | None = None,
    session=None,
    max_pages: int = 3,
) -> OMDbItem | None:
    """
    Try to resolve `path_str` to exactly one OMDb entry.
    Returns None on total failure.
    """
    path      = Path(path_str)
    tokens    = _tokenize(path)
    imdb_id_m = IMDB_RE.search(path_str)
    imdb_id   = imdb_id_m.group(0) if imdb_id_m else None

    # -----------------------------------------------------------
    # 1. Direct IMDb-ID lookup – the shortest path to success
    # -----------------------------------------------------------
    if imdb_id:
        if item := query(imdb_id=imdb_id, api_key=api_key, session=session):
            return item

    # -----------------------------------------------------------
    # 2. Detect episode markers (SxxEyy)
    # -----------------------------------------------------------
    s_e_m = SEAS_EP_RE.search(path_str)
    if s_e_m:
        season, episode = map(int, s_e_m.groups())
        # Heuristic: all tokens *before* the SxxEyy chunk form the series title
        idx = tokens.index(s_e_m.group(0))
        series_title_tokens = _clean_tokens(tokens[:idx])
        series_title        = " ".join(series_title_tokens)
        if not series_title:
            # Fallback: parent directory often carries the series name
            series_title = path.parent.stem.replace(".", " ").replace("_", " ")

        # 2a. Find the series
        series_search = search(
            title=series_title,
            media_type="series",
            api_key=api_key,
            session=session,
            max_pages=max_pages,
        )

        if series_search:
            ic(series_title, series_search)
            series = _best_match(series_title, series_search) or series_search[0]
            series_id = series["imdbID"]

            # 2b. Query for the episode
            ep = query(
                imdb_id=series_id,
                season=season,
                episode=episode,
                api_key=api_key,
                session=session,
            )
            if ep and ep.get("Response") == "True":
                return ep

        # If we got here, treat it as an *entire season* or miniseries
        #       (rare edge-case) and fall through to the "series" flow below.
        media_hint: MediaType | None = "series"
    else:
        media_hint = None  # we’ll decide next

    # -----------------------------------------------------------
    # 3. Movie / Series heuristics
    # -----------------------------------------------------------
    year_m   = YEAR_RE.search(path_str)
    year     = int(year_m.group(0)) if year_m else None

    if not media_hint:
        # If pathname contains "Season", "Sxx", or lives under "TV Shows" dir
        lowered = path_str.lower()
        if any(k in lowered for k in ["season ", "/season", "s0", "tv shows"]):
            media_hint = "series"
        else:
            media_hint = "movie"

    # Build a candidate title: tokens up to the year (if any) or all tokens until first NOISE token
    if year and str(year) in tokens:
        idx = tokens.index(str(year))
        title_tokens = _clean_tokens(tokens[:idx])
    else:
        title_tokens = _clean_tokens(tokens)
    title = " ".join(title_tokens).strip()

    if not title:
        # Final fallback – use parent dir
        title = path.parent.stem.replace(".", " ").replace("_", " ")

    # -----------------------------------------------------------
    # 3a. Try an exact query() first for movies
    # -----------------------------------------------------------
    if media_hint == "movie":
        item = query(
            title=title,
            year=year,
            media_type="movie",
            api_key=api_key,
            session=session,
        )
        if item:
            return item

    # -----------------------------------------------------------
    # 3b. Broader search() + fuzzy choose
    # -----------------------------------------------------------
    results = search(
        title=title,
        year=year,
        media_type=media_hint,
        api_key=api_key,
        session=session,
        max_pages=max_pages,
    )
    if results:
        # First, prefer exact year match (when we have a year)
        if year:
            exact_year = [r for r in results if r.get("Year", "").startswith(str(year))]
        else:
            exact_year = []

        pick_from = exact_year or results
        best      = _best_match(title, pick_from) or pick_from[0]

        # If it’s a series and we *really* wanted a whole-series match, we’re done.
        return best

    # -----------------------------------------------------------
    # Total failure – give up
    # -----------------------------------------------------------
    return None
