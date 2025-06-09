"""
TMDB metadata provider
~~~~~~~~~~~~~~~~~~~~~~

A very thin wrapper around the most common TMDB v3 endpoints plus a concrete
``MetadataProvider`` implementation that exposes **search_movie**, **search_series**
and **get_episode** in exactly the same shape as the existing OMDB provider.

Environment
-----------
Set **TMDB_API_KEY** (v3 auth key) or pass *api_key="…"*
"""

import os
import sys
import re
from collections.abc import Iterable
from types import ModuleType
from typing import Literal, NotRequired, TypedDict, override

import requests

from av_info.db.core import MetadataProvider, MovieInfo, SeriesInfo, EpisodeInfo
from av_info.utils import first_year

# --------------------------------------------------------------------------- #
# 0.  Basic constants / helpers                                               #
# --------------------------------------------------------------------------- #
TMDB_API_ROOT = "https://api.themoviedb.org/3"

def get_api_key() -> str:
    """Fetch TMDB API key from the environment, fail fast if missing."""
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        sys.exit("Error: Set TMDB_API_KEY in the environment first.")
    return api_key


SessionType = requests.Session | ModuleType | None


IMDB_RE = re.compile(r"tt\d{7,}")        # e.g. tt0111161

def _uid_kind(uid: str) -> Literal["imdb", "tmdb", "other"]:
    if IMDB_RE.fullmatch(uid):
        return "imdb"
    if uid.startswith("tmdb:") and uid[5:].isdigit():
        return "tmdb"
    if uid.isdigit():                    # bare TMDB numeric
        return "tmdb"
    return "other"

def _tmdb_int(uid: str) -> int:
    """Return the *numeric* TMDB id, raising ValueError if not possible."""
    if uid.startswith("tmdb:"):
        uid = uid.split(":", 1)[1]
    if not uid.isdigit():
        raise ValueError(f"'{uid}' is not a TMDB id")
    return int(uid)


# --------------------------------------------------------------------------- #
# 1.  Minimal static typing helpers                                           #
# --------------------------------------------------------------------------- #
class _MovieResult(TypedDict):
    id: int
    title: str
    release_date: NotRequired[str]
    overview: NotRequired[str]
    media_type: Literal["movie"]       # injected locally for parity


class _TVResult(TypedDict):
    id: int
    name: str
    first_air_date: NotRequired[str]
    overview: NotRequired[str]
    media_type: Literal["tv"]          # injected locally for parity


class _EpisodeResult(TypedDict):
    id: int
    name: str
    air_date: NotRequired[str]
    season_number: int
    episode_number: int
    overview: NotRequired[str]
    show_id: int                # injected (parent TMDB id)


# --------------------------------------------------------------------------- #
# 2.  Low-level REST helpers                                                  #
# --------------------------------------------------------------------------- #
def _get(
    path: str,
    *,
    api_key: str,
    session: SessionType = None,
    **params,
):
    sess = session or requests
    params = {"api_key": api_key, **params}
    resp = sess.get(f"{TMDB_API_ROOT}/{path.lstrip('/')}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()  # pyright: ignore[reportAny]


def _find_by_imdb(
    imdb_id: str,
    *,
    api_key: str,
    session: SessionType = None,
) -> list[_MovieResult | _TVResult]:
    """
    Map an IMDb ID to TMDB entities (movie or TV).  TMDB returns *both* lists;
    we normalise them and tack on ``media_type`` so downstream code can tell.
    """
    data = _get(
        f"find/{imdb_id}",
        api_key=api_key,
        session=session,
        external_source="imdb_id",
    )
    results: list[_MovieResult | _TVResult] = []

    for mv in data.get("movie_results", []):
        mv["media_type"] = "movie"  # type: ignore[index]
        results.append(mv)          # type: ignore[arg-type]

    for tv in data.get("tv_results", []):
        tv["media_type"] = "tv"     # type: ignore[index]
        results.append(tv)          # type: ignore[arg-type]

    return results


def _paged(
    path: str,
    *,
    api_key: str,
    max_pages: int,
    session: SessionType = None,
    **params,
) -> Iterable[dict]:
    """Generic generator for TMDB list/search endpoints that use ``page``."""
    for page in range(1, max_pages + 1):
        page_data = _get(path, api_key=api_key, session=session, page=page, **params)
        yield from page_data.get("results", [])
        if page >= page_data.get("total_pages", page):
            break


# --------------------------------------------------------------------------- #
# 3.  Build helpers – adapt raw JSON → *Info dataclasses                      #
# --------------------------------------------------------------------------- #
def _build_movie(item: _MovieResult) -> MovieInfo:
    uid = item.get("imdb_id") or str(item["id"])          # plain numeric for TMDB
    return MovieInfo(uid=uid, title=item["title"], year=first_year(item.get("release_date", "0000")[:4]))


def _build_series(item: _TVResult) -> SeriesInfo:
    uid = item.get("imdb_id") or str(item["id"])
    first_air_date = item.get("first_air_date", "0000")
    if first_air_date == "":
        first_air_date = "0000"
    return SeriesInfo(uid=uid, title=item["name"], year=first_year(first_air_date[:4]))


def _build_episode(item: _EpisodeResult, series: SeriesInfo) -> EpisodeInfo:
    if item["show_id"] != int(series.uid.split(":")[-1]) and not series.uid.startswith("tmdb:"):
        raise ValueError("Episode does not belong to supplied series")

    uid = item.get("imdb_id") or f"tmdb:{item['id']}"
    return EpisodeInfo(
        uid=uid,
        title=item["name"],
        year=first_year(item.get("air_date", "0000")[:4]),
        season=str(item["season_number"]),
        episode=str(item["episode_number"]),
        series=series,
    )


# --------------------------------------------------------------------------- #
# 4.  High-level, provider-style facade                                       #
# --------------------------------------------------------------------------- #
class TMDBProvider(MetadataProvider):
    """
    A concrete ``MetadataProvider`` backed by the public TMDB API.
    Behaviour matches the existing OMDBProvider so external caller code
    doesn't need to change.
    """

    # ---------------  MOVIES  ------------------------------------------------
    @override
    def search_movie(self, uid: str|None, title: str|None=None, year: str|None = None, verbose: bool=False) -> list[MovieInfo]:
        api_key, sess = get_api_key(), None
        if uid is None and title is None:
            raise ValueError("search_movie needs either 'uid' or 'title'")
        kind = _uid_kind(uid) if uid else "other"

        # --- ① UID supplied -----------------------------------------------------
        if kind == "imdb":
            hits = _find_by_imdb(uid, api_key=api_key, session=sess)
            movies = [h for h in hits if h["media_type"] == "movie"]          # type: ignore[index]
            return [_build_movie(m) for m in movies]

        if kind == "tmdb":
            try:
                raw = _get(f"movie/{_tmdb_int(uid)}", api_key=api_key, session=sess, append_to_response="external_ids")
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    return []
                raise
            raw["media_type"] = "movie"                                       # type: ignore[index]
            return [_build_movie(raw)]                                        # type: ignore[arg-type]

        # --- ② Fallback title search -------------------------------------------
        params = {"query": title} if title else {}
        if year:
            params["primary_release_year"] = year
        results = _paged("search/movie", api_key=api_key, session=sess, max_pages=3, **params)
        return [_build_movie(m) for m in results]                              # type: ignore[arg-type]

    # ---------------  SERIES  ------------------------------------------------
    @override
    def search_series(
            self,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None,
            verbose: bool = False) -> list[SeriesInfo]:
        api_key, sess = get_api_key(), None
        if uid is None and title is None:
            raise ValueError("search_series needs either 'uid' or 'title'")

        kind = _uid_kind(uid) if uid else "other"

        if kind == "imdb":
            hits = _find_by_imdb(uid, api_key=api_key, session=sess)
            shows = [h for h in hits if h["media_type"] == "tv"]              # type: ignore[index]
            return [_build_series(s) for s in shows]

        if kind == "tmdb":
            try:
                raw = _get(f"tv/{_tmdb_int(uid)}", api_key=api_key, session=sess, append_to_response="external_ids")
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    return []
                raise
            raw["media_type"] = "tv"                                          # type: ignore[index]
            return [_build_series(raw)]                                       # type: ignore[arg-type]

        params = {"query": title} if title else {}
        if year:
            params["first_air_date_year"] = year
        results = _paged("search/tv", api_key=api_key, session=sess, max_pages=3, **params)
        return [_build_series(s) for s in results]                            # type: ignore[arg-type]

    # ---------------  EPISODES  ---------------------------------------------
    @override
    def get_episode(
            self,
            series: SeriesInfo,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None,
            season: str|None = None,
            episode: str|None = None,
            verbose: bool = False) -> EpisodeInfo | None:
        if season is None or episode is None:
            raise ValueError("TMDB requires *both* season and episode numbers")

        api_key, sess = get_api_key(), None

        # --- resolve numerical series id ---------------------------------------
        skind = _uid_kind(series.uid)
        if skind == "tmdb":
            sid = _tmdb_int(series.uid)
        elif skind == "imdb":
            hits = _find_by_imdb(series.uid, api_key=api_key, session=sess)
            tv_hits = [h for h in hits if h["media_type"] == "tv"]            # type: ignore[index]
            if not tv_hits:
                return None
            sid = tv_hits[0]["id"]                                            # type: ignore[index]
        else:
            raise ValueError("Series UID must be an IMDb or TMDB id")

        # --- pull episode detail -----------------------------------------------
        ep_raw: _EpisodeResult = _get(
            f"tv/{sid}/season/{int(season)}/episode/{int(episode)}",
            api_key=api_key,
            session=sess,
            append_to_response="external_ids",
        )
        ep_raw["show_id"] = sid                                               # type: ignore[index]
        ext = ep_raw.get("external_ids", {})
        if "imdb_id" in ext:
            ep_raw["imdb_id"] = ext["imdb_id"]                                # type: ignore[index]
        return _build_episode(ep_raw, series)
