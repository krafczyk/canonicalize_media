import re
#import difflib
from pathlib import Path
from av_info.db import ProviderSpec, BaseInfo, MovieInfo, SeriesInfo, EpisodeInfo, get_provider
from av_info.utils import clean, clean_tokens, tokenize, titles_equal, sanitize_filename
from av_info.utils import first_year as _first_year
#from collections.abc import Sequence


def build_media_path(
    media: BaseInfo,
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
    edition_part = f"{{edition-{clean(edition)}}}" if edition else ""

    fn_parts: list[str]

    # ------------------------------------------------------------------ #
    # Movies
    # ------------------------------------------------------------------ #
    if isinstance(media, MovieInfo):
        title = clean(media.title)
        year = _first_year(media.year)

        if edition:
            folder = Path(f"{title} ({year}) {edition_part}")
        else:
            folder = Path(f"{title} ({year})")

        # ---- filename ----
        fn_parts = [f"{title} ({year})"]

        # Optional – order is important for Plex:
        #  Title (Year) - 4K {edition-Director's Cut}.mkv
        if resolution:
            fn_parts.append(resolution)

        # Edition *must* be inside curly braces with the prefix
        if edition:
            fn_parts.append(edition_part)

        filename = " - ".join(fn_parts) + f".{ext.lstrip('.')}"
        # Sanitize '/'
        filename = sanitize_filename(filename)
        return folder / filename

    # ------------------------------------------------------------------ #
    # Series (show record)
    # ------------------------------------------------------------------ #
    if isinstance(media, SeriesInfo):
        series_title = clean(media.title)
        first_year = _first_year(media.year)
        filename = f"{series_title} ({first_year})"
        filename = sanitize_filename(filename)
        return Path(filename)

    # ------------------------------------------------------------------ #
    # Episode
    # ------------------------------------------------------------------ #
    if isinstance(media, EpisodeInfo):
        series_title = clean(media.series.title)
        first_year = _first_year(media.series.year)

        season_num = int(media.season)
        episode_num = int(media.episode)
        ep_title = clean(media.title)

        show_name = Path(f"{series_title} ({first_year})")
        season_dir = show_name / f"Season {season_num:02d}"

        # ---- filename ----
        fn_parts = [ str(show_name) , f"s{season_num:02d}e{episode_num:02d}", ep_title ]

        # Optional – order is important for Plex:
        #  Title (Year) - 4K {edition-Director's Cut}.mkv
        if resolution:
            fn_parts.append(resolution)

        # Edition *must* be inside curly braces with the prefix
        if edition:
            fn_parts.append(edition_part)

        filename = " - ".join(fn_parts) + f".{ext.lstrip('.')}"
        filename = sanitize_filename(filename)
        return season_dir / filename

    # ------------------------------------------------------------------ #
    # Unsupported / unknown
    # ------------------------------------------------------------------ #
    raise ValueError(f"Unsupported type: {media!r}")


# ---------------------------------------------------------------------------
# Regexes & constants
# ---------------------------------------------------------------------------
IMDB_RE      = re.compile(r"tt\d{7,8}")
SEAS_EP_RE   = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")       # s03e12 / S3E2 / s03e02 etc.
YEAR_RE      = re.compile(r"(19|20)\d{2}")
YEAR_TOKEN   = re.compile(r"\(((19|20)\d{2})\)")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
#def _best_match(
#    wanted: str,  # cleaned title we expect
#    candidates: Sequence[BaseInfo],
#    cutoff: float = 0.6,
#) -> BaseInfo | None:
#    """Pick the candidate whose Title is closest to 'wanted' (difflib ratio)."""
#    def score(item: BaseInfo) -> float:
#        return difflib.SequenceMatcher(None, wanted.lower(), item.title).ratio()
#    scored = sorted(((score(c), c) for c in candidates), reverse=True, key=lambda t: t[0])
#    return scored[0][1] if scored and scored[0][0] >= cutoff else None


def guess_series(
    path_str: str,
    *,
    uid: str | None = None,
    title: str | None = None,
    year: str | None = None,
    verbose: bool = False,
    provider: ProviderSpec = "omdb",
) -> SeriesInfo | None:
    """
    Try to resolve `path_str` to exactly one series.
    Returns None on failure.

    path_str: str - The filepath to use
    year: str - Override the year
    id: str - Override the id
    provider: ProviderSpec - The metadata provider to use
    -- The following options aren't required, but override certain options
    """
    provider = get_provider(provider)

    if uid:
        series_search = provider.search_series(
            uid=uid,
            verbose=verbose)

        if series_search:
            if len(series_search) == 1:
                return series_search[0]

        # If a uid is passed, we should return a value.
        # If it can't be found, we should return nothing.
        return None

    path      = Path(path_str)
    tokens = tokenize(path)
    if not title or not year:
        s_e_m = SEAS_EP_RE.search(path_str)
        if not s_e_m:
            # No SxxEyy marker found, so we can't guess a series
            return None

        series_search: list[SeriesInfo] | None = None

        # Heuristic: all tokens *before* the SxxEyy chunk form the series title
        idx = tokens[-1].index(s_e_m.group(0))
        series_title_tokens = clean_tokens(tokens[-1][:idx])
        series_year_token = None
        series_year = None
        for i, token in enumerate(series_title_tokens):
            # Remove any year token which may be present
            if year_m := YEAR_TOKEN.fullmatch(token):
                series_year_token = series_title_tokens.pop(i)
                series_year = year_m.group(1)
                break

        title = " ".join(series_title_tokens).strip()
        year = series_year or year

    # First, see if the title is enough for an exact match
    series_results = provider.search_series(
        title=title,
        verbose=verbose
    )

    title_matches = [s for s in series_results if titles_equal(s.title, title)]

    if len(title_matches) == 1:
        return title_matches[0]

    if year:
        title_year_matches = [
            s for s in series_results if titles_equal(s.title, title) and s.year == year ]
        if len(title_year_matches) == 1:
            return title_year_matches[0]

    # Let's look for all year tokens in the full filepath, sometimes filepaths have mistakes.
    all_tokens: list[str] = []
    for token_list in tokens:
        all_tokens.extend(token_list)

    years = [ int(m.group(1)) for m in YEAR_TOKEN.finditer(" ".join(all_tokens)) ]

    # For each candidate, measure the 'difference' between the years found
    # and the year for that series.

    closest_matches: list[SeriesInfo] = []
    closest_year_diff = 8000

    for candidate in title_matches:
        c_year = int(candidate.year)
        diffs = [abs(c_year - y) for y in years]
        min_diff = min(diffs)
        if min_diff < closest_year_diff:
            closest_matches = [candidate]
            closest_year_diff = min_diff
        elif min_diff == closest_year_diff:
            closest_matches.append(candidate)

    if closest_year_diff == 0 and len(closest_matches) == 1:
        # We found a series with the exact year match
        return closest_matches[0]

    # Not able to find it with title and year..
    return None


def guess_episode(
    path_str: str,
    *,
    uid: str | None = None,
    title: str | None = None,
    year: str | None = None,
    series_title: str | None = None,
    series_uid: str | None = None,
    series_year: str | None = None,
    season: str | None = None,
    episode: str | None = None,
    verbose: bool = False,
    provider: ProviderSpec = "omdb",
) -> EpisodeInfo | None:
    """
    Try to resolve `path_str` to exactly one episode.
    Returns None on failure.

    path_str: str - The filepath to use
    provider: ProviderSpec - The metadata provider to use
    -- The following options aren't required, but override certain options
    """
    provider = get_provider(provider)

    # guess series
    series = guess_series(
        path_str,
        uid=series_uid,
        title=series_title,
        year=series_year,
        provider=provider,
        verbose=verbose,
    )

    if series is None:
        return None

    imdb_id_m = None
    if uid or (imdb_id_m := IMDB_RE.search(path_str)):
        if not uid:
            if imdb_id_m is None:
                raise ValueError("Either 'uid' or an imdbid must be present.")
            uid = imdb_id_m.group(0)
        return provider.get_episode(
            uid=uid,
            series=series,)

    # -----------------------------------------------------------
    # 2. Detect episode markers (SxxEyy)
    # -----------------------------------------------------------
    if not season or not episode:
        s_e_m = SEAS_EP_RE.search(path_str)
        if not s_e_m:
            # No SxxEyy marker found, so we can't guess an episode
            return None

        path_season, path_episode = s_e_m.groups()
        if not season:
            season=path_season
        if not episode:
            episode=path_episode

    if not year:
        year = _first_year(series.year)
    # 2b. Query for the episode
    return provider.get_episode(
        series=series,
        title=title,
        year=year,
        season=season,
        episode=episode,
        verbose=verbose,
    )


def guess_movie(
    path_str: str,
    *,
    uid: str | None = None,
    title: str | None = None,
    year: str | None = None,
    verbose: bool = False,
    provider: ProviderSpec = "omdb",
) -> MovieInfo | None:
    """
    Try to resolve `path_str` to exactly one OMDb entry.
    Returns None on total failure.
    """
    provider = get_provider(provider)

    path      = Path(path_str)
    tokens    = tokenize(path)

    if uid is None:
        imdb_id_m = IMDB_RE.search(path_str)
        uid = imdb_id_m.group(0) if imdb_id_m else None

    # Build a candidate title: tokens up to the year (if any) or all tokens until first NOISE token
    # first, find the last year token in the path
    idx = None
    for i, token in enumerate(tokens[-1]):
        if year_m := YEAR_RE.fullmatch(token):
            idx = i

    if idx:
        title_tokens = clean_tokens(tokens[-1][:idx])
    else:
        title_tokens = clean_tokens(tokens[-1])

    # Check if the last token is a year specifier
    year_token_val = None
    if year_m := YEAR_TOKEN.fullmatch(title_tokens[-1]):
        year_token_val = year_m.group(1)

    if not year:
        year = year_token_val

    if not title:
        title = " ".join(title_tokens).strip()

    results = provider.search_movie(
        uid=uid,
        title=title,
        year=year,
        verbose=verbose)

    if results:
        if len(results) == 1:
            return results[0]
        elif len(results) > 1:
            matches: list[MovieInfo] = [
                m for m in results
                if titles_equal(m.title, title) ]

            if len(matches) == 1:
                return matches[0]

            if year:
                year_matches = [
                    m for m in matches
                    if m.year == year ]

                if len(year_matches) == 1:
                    return year_matches[0]

            # Let's look for all year tokens in the full filepath, sometimes filepaths have mistakes.
            all_tokens: list[str] = []
            for token_list in tokens:
                all_tokens.extend(token_list)
            all_tokens = clean_tokens(all_tokens)

            years = [ int(m.group(1)) for m in YEAR_TOKEN.finditer(" ".join(all_tokens)) ]

            # For each candidate, measure the 'difference' between the years found
            # and the year for that series.

            closest_matches: list[MovieInfo] = []
            closest_year_diff = 8000

            for candidate in matches:
                c_year = int(candidate.year)
                diffs = [abs(c_year - y) for y in years]
                min_diff = min(diffs)
                if min_diff < closest_year_diff:
                    closest_matches = [candidate]
                    closest_year_diff = min_diff
                elif min_diff == closest_year_diff:
                    closest_matches.append(candidate)

            if len(closest_matches) == 1:
                # We found a series with the exact year match
                return closest_matches[0]

        # -----------------------------------------------------------
        # 3b. Broader search() + fuzzy choose
        # -----------------------------------------------------------

        #elif len(exact_matches) > 1:
        #    # Too many close matches.
        #    return None

        #best = _best_match(title, results)

        #if not best:
        #    return None

        #return MovieInfo(
        #    uid=best["imdbID"],
        #    title=best["Title"],
        #    year=best["Year"],
        #)

    # -----------------------------------------------------------
    # Total failure – give up
    # -----------------------------------------------------------
    return None


def guess(
    path_str: str,
    *,
    uid: str | None = None,
    title: str | None = None,
    year: str | None = None,
    series_title: str | None = None,
    series_uid: str | None = None,
    series_year: str | None = None,
    season: str | None = None,
    episode: str | None = None,
    verbose: bool = False,
    provider: ProviderSpec = "omdb",
) -> BaseInfo | None:
    episode_only = False
    if series_title or series_uid or series_year:
        episode_only = True

    ep = guess_episode(
        path_str,
        uid=uid,
        title=title,
        year=year,
        series_title=series_title,
        series_uid=series_uid,
        series_year=series_year,
        season = season,
        episode = episode,
        verbose=verbose,
        provider=provider,
    )
    if ep:
        return ep

    if episode_only:
        # If we got here, we didn't find an episode but we were asked to guess one.
        return None

    # If we got here, we didn't find an episode.
    return guess_movie(
        path_str,
        uid=uid,
        title=title,
        verbose=verbose,
        provider=provider,
        year=year)
