import re
from pathlib import Path
from av_info.omdb import OMDbItem


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
    ext: str = "mkv",
    resolution: str | None = None,
    version: str | None = None,
    edition: str | None = None,
) -> Path:
    """
    Return a Path for either a Movie, Series, or Episode JSON record.

    Parameters
    ----------
    omdb        : dict  – OMDb reply already parsed with json.loads().
    ext         : str   – default file-extension to append if none supplied.
    resolution  : str   – optional  '1080p', '4K', etc. (movie files only).
    version     : str   – optional  'HDR', 'BluRay', etc. (movie files only).

    Returns
    -------
    pathlib.Path object representing  <folders>/<filename>
    """
    media_type = omdb.get("Type")
    if media_type == "movie":
        title = _clean(omdb["Title"])
        year  = _first_year(omdb["Year"])
        folder = Path(f"{title} ({year})")

        filename = f"{title} ({year})"
        if version:
            filename += f" - {version}"
        if resolution:
            filename += f" - {resolution}"
        filename += f".{ext.lstrip('.')}"
        return folder / filename

    # ---------------------------------------------------------------------
    # Series and Episodes
    # ---------------------------------------------------------------------
    if media_type in {"series", "episode"}:
        # For an episode JSON, SeriesTitle is present; for a series JSON, Title.
        show_title = _clean(omdb.get("SeriesTitle") or omdb["Title"])
        first_year = _first_year(omdb["Year"])
        show_dir   = Path(f"{show_title} ({first_year})")

        # If it's just the series record, stop here (no filename yet)
        if media_type == "series":
            return show_dir

        if 'Season' not in omdb or 'Episode' not in omdb:
            raise ValueError("OMDb episode record must contain 'Season' and 'Episode' fields.")

        # Episode record ➜ build season/episode structure
        season_num  = int(omdb["Season"])
        episode_num = int(omdb["Episode"])
        ep_title    = _clean(omdb["Title"])

        season_dir  = show_dir / f"Season {season_num:02d}"
        filename    = (
            f"{show_title} - S{season_num:02d}E{episode_num:02d} - {ep_title}.{ext.lstrip('.')}"
        )
        return season_dir / filename

    raise ValueError(f"Unsupported OMDb type: {media_type!r}")
