import re
from pathlib import Path
from av_info.omdb import OMDbItem, query


_ILLEGAL = re.compile(r'[\\/:*?"<>|]+')      # chars not allowed in filenames

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

