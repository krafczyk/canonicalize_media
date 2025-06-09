"""
TVDB (v4) metadata provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implements `search_movie`, `search_series`, and `get_episode`
with the same call-shape as OMDBProvider / TMDBProvider.

Dependencies
------------
• requests  (already in use elsewhere)
Environment
-----------
• TVDB_API_KEY   – your v4 “Developer” or “User” key
• TVDB_PIN       – only needed for USER-supported keys
"""

from __future__ import annotations
import os, sys, re, time, itertools
from collections.abc import Iterable
from types import ModuleType
from typing import Literal, TypedDict, NotRequired, override
from pprint import pprint

import requests

from av_info.db.core import MetadataProvider, MovieInfo, SeriesInfo, EpisodeInfo
from av_info.utils import first_year

# --------------------------------------------------------------------------- #
# 0.  Constants / helpers                                                     #
# --------------------------------------------------------------------------- #
TVDB_ROOT          = "https://api4.thetvdb.com/v4"
_LOGIN_EP          = f"{TVDB_ROOT}/login"
_BEARER: str | None = None
_BEARER_EXP: float = 0.0          # unix-timestamp when token expires

def _api_key() -> str:
    key = os.getenv("TVDB_API_KEY")
    if not key:
        sys.exit("Set TVDB_API_KEY in the environment first.")
    return key

def _pin() -> str | None:
    # not all keys need a PIN – ignore if env var absent
    return os.getenv("TVDB_PIN") or None

def _session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess

def _login(sess: requests.Session) -> None:
    """(Re)authenticate and cache the bearer token for the global process."""
    global _BEARER, _BEARER_EXP
    payload = {"apikey": _api_key()}
    if (pin := _pin()):
        payload["pin"] = pin
    resp = sess.post(_LOGIN_EP, json=payload, timeout=10)
    resp.raise_for_status()
    token = resp.json()["data"]["token"]          # :contentReference[oaicite:0]{index=0}
    _BEARER       = token
    _BEARER_EXP   = time.time() + 28 * 24 * 3600  # token is valid ~30 days

def _auth_header(sess: requests.Session) -> None:
    """Ensure `Authorization: Bearer …` is present and fresh."""
    global _BEARER, _BEARER_EXP
    if _BEARER is None or time.time() > _BEARER_EXP - 60:
        _login(sess)
    sess.headers["Authorization"] = f"Bearer {_BEARER}"

# ---- id helpers ----------------------------------------------------------- #
IMDB_RE = re.compile(r"tt\d{7,}")             # unchanged

def _uid_kind(uid: str) -> Literal["imdb", "tvdb", "other"]:
    if IMDB_RE.fullmatch(uid):
        return "imdb"
    #  series-123456       tvdb:123456        123456
    if re.fullmatch(r"(series-)?\d+", uid) or uid.startswith("tvdb:"):
        return "tvdb"
    return "other"

_ID_RE = re.compile(r"\d+")

def _tvdb_int(uid: str) -> int:
    """
    Extract the *numeric* TVDB id from any of the allowed uid flavours:
      12345,  tvdb:12345,  series-12345
    """
    if uid.startswith("tvdb:"):
        uid = uid.split(":", 1)[1]
    m = _ID_RE.search(uid)
    if not m:
        raise ValueError(f"'{uid}' does not contain a TVDB numeric id")
    return int(m.group())


# --------------------------------------------------------------------------- #
# 1.  Thin REST helpers                                                       #
# --------------------------------------------------------------------------- #
def _get(path: str, *, sess: requests.Session, **params):
    _auth_header(sess)
    resp = sess.get(f"{TVDB_ROOT}/{path.lstrip('/')}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def _paged(path: str, *, sess: requests.Session, max_pages: int, **params) -> Iterable[dict]:
    for page in range(0, max_pages):
        data = _get(path, sess=sess, page=page, **params)
        yield from data.get("data", [])
        if not data.get("links", {}).get("next"):
            break

def _hit_id(hit: dict) -> int:
    """
    Return the numeric tvdb_id field if present, otherwise strip the prefix
    from objectID/id ('series-123456', 'movie-987654', …).
    """
    if "tvdb_id" in hit and hit["tvdb_id"].isdigit():
        return int(hit["tvdb_id"])
    return _tvdb_int(str(hit.get("objectID", hit.get("id", ""))))

# --------------------------------------------------------------------------- #
# 2.  Static typing “views” of TVDB JSON                                      #
# --------------------------------------------------------------------------- #
class _SearchHit(TypedDict):
    # minimal subset we care about
    name: str
    objectID: int
    objectType: Literal["movie", "series", "episode"]
    year: NotRequired[str]

class _Movie(TypedDict):
    id: int
    name: str
    year: NotRequired[str]
    slug: NotRequired[str]

class _Series(TypedDict):
    id: int
    name: str
    year: NotRequired[str]
    slug: NotRequired[str]

class _Episode(TypedDict):
    id: int
    name: str
    aired: NotRequired[str]
    seasonNumber: int
    number: int    # episode within that season
    year: NotRequired[str]

# --------------------------------------------------------------------------- #
# 3.  Builders – TVDB → *Info dataclasses                                     #
# --------------------------------------------------------------------------- #
def _build_movie(item: _Movie) -> MovieInfo:
    year = first_year(str(item.get("year", "0000")))
    return MovieInfo(uid=str(item["id"]), title=item["name"], year=year)

def _build_series(item: _Series) -> SeriesInfo:
    year = first_year(str(item.get("year", "0000")))
    return SeriesInfo(uid=str(item["id"]), title=item["name"], year=year)

def _build_episode(item: _Episode, series: SeriesInfo) -> EpisodeInfo:
    return EpisodeInfo(
        uid=str(item["id"]),
        title=item["name"],
        year=first_year(str(item.get("year", "0000"))),
        season=str(item["seasonNumber"]),
        episode=str(item["number"]),
        series=series,
    )

# --------------------------------------------------------------------------- #
# 4.  Provider implementation                                                 #
# --------------------------------------------------------------------------- #
class TVDBProvider(MetadataProvider):
    """
    Minimal TheTVDB (v4) adaptor.  Relies on:

      • /login  to obtain a bearer token
      • /search and /search/remoteid/{imdb}                      :contentReference[oaicite:1]{index=1}
      • /movies/{id}   /series/{id}   /episodes/{id}
      • /series/{id}/episodes/default   (paged)                  :contentReference[oaicite:2]{index=2}
    """

    # ---------------- MOVIES ----------------
    @override
    def search_movie(self,
                     uid:   str | None,
                     title: str | None = None,
                     year:  str | None = None,
                     verbose: bool = False) -> list[MovieInfo]:
        if uid is None and title is None:
            raise ValueError("TVDB.search_movie needs 'uid' or 'title'")
        sess = _session()

        kind = _uid_kind(uid) if uid else "other"
        # -- IMDb id → remote-id search
        if kind == "imdb":
            data = _get(f"search/remoteid/{uid}", sess=sess)
            hits = [h for h in data["data"] if h["objectType"] == "movie"]
            return [_build_movie(_get(f"movies/{_hit_id(h)}", sess=sess)["data"]) for h in hits]

        # -- direct numeric tvdb id
        if kind == "tvdb":
            item = _get(f"movies/{_tvdb_int(uid)}", sess=sess)["data"]
            return [_build_movie(item)]

        # -- title search fallback
        params = {"query": title, "type": "movie"}
        if year:
            params["year"] = year
        hits = _get("search", sess=sess, **params)["data"]
        if verbose:
            print(f"TVDB search_movie results:")
            pprint(hits)
        return [_build_movie(_get(f"movies/{_hit_id(h)}", sess=sess)["data"])
                for h in hits if h["type"] == "movie"]

    # ---------------- SERIES ---------------
    @override
    def search_series(self,
                      uid:   str | None = None,
                      title: str | None = None,
                      year:  str | None = None,
                      verbose: bool = False) -> list[SeriesInfo]:
        if uid is None and title is None:
            raise ValueError("TVDB.search_series needs 'uid' or 'title'")
        sess = _session()
        kind = _uid_kind(uid) if uid else "other"

        if kind == "imdb":
            data = _get(f"search/remoteid/{uid}", sess=sess)
            hits = [h for h in data["data"] if h["objectType"] == "series"]
            return [_build_series(_get(f"series/{_hit_id(h)}", sess=sess)["data"]) for h in hits]

        if kind == "tvdb":
            item = _get(f"series/{_tvdb_int(uid)}", sess=sess)["data"]
            return [_build_series(item)]

        params = {"query": title, "type": "series"}
        if year:
            params["year"] = year
        hits = _get("search", sess=sess, **params)["data"]
        if verbose:
            print(f"TVDB search_series results:")
            pprint(hits)

        return [_build_series(_get(f"series/{_hit_id(h)}", sess=sess)["data"])
                for h in hits if h["type"] == "series"]

    # ---------------- EPISODE --------------
    @override
    def get_episode(self,
                    series:  SeriesInfo,
                    uid:     str | None = None,
                    title:   str | None = None,
                    year:    str | None = None,
                    season:  str | None = None,
                    episode: str | None = None,
                    verbose: bool = False) -> EpisodeInfo | None:
        if season is None or episode is None:
            raise ValueError("TVDB.get_episode needs season *and* episode numbers")

        sess = _session()
        sid_kind = _uid_kind(series.uid)
        if sid_kind != "tvdb":
            # If caller held an IMDb id, resolve once:
            ser_hits = self.search_series(uid=series.uid)
            if not ser_hits:
                return None
            tvdb_sid = int(ser_hits[0].uid)
        else:
            tvdb_sid = _tvdb_int(series.uid)

        # TVDB paginates episode lists – walk until we find the desired one
        for page in itertools.count(0):
            eps = _get(f"series/{tvdb_sid}/episodes/default",
                       sess=sess, page=page, seasonNumber=season)["data"]['episodes']
            if verbose:
                print(f"TVDB get_episode results:")
                pprint(eps)
            if not eps:
                break
            for ep in eps:
                if (int(ep["seasonNumber"]) == int(season)
                        and int(ep["number"]) == int(episode)):
                    return _build_episode(ep, series)
        return None
