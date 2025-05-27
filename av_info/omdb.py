from typing import TypedDict, Literal, NotRequired, Required, cast
import sys
import os
import requests
import itertools
from typing import Iterable


OMDB_API_URL = "https://www.omdbapi.com/"


def get_api_key() -> str:
    api_key = os.getenv("OMDB_API_KEY")  # fail fast if missing
    if not api_key:
        sys.exit("Set OMDB_API_KEY in the environment first.")
    return api_key


MediaType = Literal["movie", "series", "episode"]


class OMDbItem(TypedDict, total=False):
    Title: Required[str]
    Year: Required[str]              # still a string in OMDb JSON
    Rated: NotRequired[str]
    Season: NotRequired[str]
    Episode: NotRequired[str]
    Genre: NotRequired[str]
    Director: NotRequired[str]
    Writer: NotRequired[str]
    Actors: NotRequired[str]
    Plot: NotRequired[str]
    Language: NotRequired[str]
    Country: NotRequired[str]
    Awards: NotRequired[str]
    Poster: NotRequired[str]
    Ratings: NotRequired[list[dict[str, str]]]
    Metascore: NotRequired[str]
    Released: NotRequired[str]
    Runtime: NotRequired[str]
    imdbRating: NotRequired[str]
    imdbVotes: NotRequired[str]
    imdbID: Required[str]
    seriesID: NotRequired[str]
    Type: Required[MediaType]
    Response: str          # "True" / "False"


# ---------------------------------------------------------------------------
# 2. A thin client around the OMDb *by-title* and *search* endpoints
# ---------------------------------------------------------------------------
def query_title(
    *,
    title: str | None = None,
    imdb_id: str | None = None,
    year: int | None = None,
    season: int | None = None,
    episode: int | None = None,
    media_type: MediaType | None = None,
    api_key: str | None = None,
    session: requests.Session | None = None) -> OMDbItem | None:
    """
    Query OMDb for a movie, series, season, or episode.

    Exactly one of ``title`` **or** ``imdb_id`` must be supplied.

    Parameters
    ----------
    title :
        Exact title (e.g. ``"The Matrix"``).  Ignored if *imdb_id* is given.
    imdb_id :
        IMDb identifier (e.g. ``"tt0133093"``).  Overrides *title*.
    year :
        Release year to disambiguate a title search.
    season, episode :
        ``season`` alone ⇒ season listing; ``season`` *and* ``episode`` ⇒ single
        episode.  Both cases require ``media_type`` to be ``"series"`` or
        ``"episode"`` respectively.
    media_type :
        One of ``"movie"``, ``"series"``, ``"episode"`` (as expected by OMDb).
    api_key :
        Your OMDb API key.  Falls back to :func:`get_api_key` when ``None``.
    session :
        Optional :class:`requests.Session` for connection pooling.

    Returns
    -------
    dict | None
        Parsed JSON from OMDb on success, ``None`` on “Movie not found”.
    """
    # -- basic validation ----------------------------------------------------
    if imdb_id is None and title is None:
        raise ValueError("Pass either 'title' or 'imdb_id'")

    if imdb_id is not None and title is not None:
        raise ValueError("'title' and 'imdb_id' are mutually exclusive")

    if season is not None and media_type == "movie":
        raise ValueError("Season/episode look-ups require media_type 'series' or 'episode'")

    if episode is not None and season is None:
        raise ValueError("An episode number makes sense only together with a season")

    if episode is not None and media_type != "episode":
        raise ValueError("If 'episode' is given, media_type must be 'episode'")

    # ------------------------------------------------------------------------
    api_key = api_key or get_api_key()

    params: dict[str, str] = {"apikey": api_key}

    if imdb_id:
        params["i"] = imdb_id
    else:  # title search
        params["t"] = title  # type: ignore[arg-type]
        if year:
            params["y"] = str(year)

    # The TYPE parameter only applies to the base search, not to Season/Episode
    if media_type is not None and ((season is None and episode is None) and media_type != "movie"):
        params["type"] = media_type

    if season is not None:
        params["Season"] = str(season)
    if episode is not None:
        params["Episode"] = str(episode)

    sess = session or requests
    resp = sess.get(OMDB_API_URL, params=params, timeout=10)
    resp.raise_for_status()

    data: dict = resp.json()      # pyright: ignore[reportAny]
    return data if data.get("Response") == "True" else None


def _search_pages(
    sess: requests.Session,
    params: dict[str, str],
    max_pages: int,
) -> Iterable[OMDbItem]:
    """Generator yielding one decoded-JSON result per OMDb search page."""
    for page in range(1, max_pages + 1):
        params["page"] = str(page)
        resp = sess.get(OMDB_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data: dict = resp.json()                                       # pyright: ignore[reportAny]
        if data.get("Response") != "True":
            break
        yield data
        # Stop early once we’ve collected everything OMDb says exists
        if (page * 10) >= int(data.get("totalResults", page * 10)):
            break


def search_title(
    *,
    title: str | None = None,
    imdb_id: str | None = None,
    year: int | None = None,
    season: int | None = None,
    episode: int | None = None,
    seriesID: str | None = None,
    media_type: MediaType | None = None,
    api_key: str | None = None,
    session: requests.Session | None = None,
    max_pages: int = 3,
) -> list[OMDbItem]:
    """
    Search OMDb and return a list of matches.

    Exactly **one** of ``title`` *or* ``imdb_id`` must be supplied.

    * If *imdb_id* is given we perform a direct lookup (delegating to
      :pyfunc:`query_title`) and wrap the single result in a list.
    * Otherwise we perform a paged ``s=`` search and return up to
      ``max_pages`` × 10 results.

    Parameters
    ----------
    title, imdb_id, year, media_type :
        Passed straight through to OMDb, subject to the same rules as its API.
    api_key :
        Falls back to :pyfunc:`get_api_key` if omitted.
    session :
        Re-use an existing :class:`requests.Session` for connection pooling.
    max_pages :
        Soft cap on pagination requests (OMDb returns 10 results per page).

    Returns
    -------
    list[dict]
        Zero or more raw-JSON items from OMDb.
    """
    # ------------ validation -------------------------------------------------
    if imdb_id and (year or media_type):
        raise ValueError("'year' and 'media_type' are ignored when 'imdb_id' is used")

    api_key = api_key or get_api_key()
    sess = session or requests

    # ------------ direct lookup by IMDb ID -----------------------------------
    if imdb_id:
        single = query_title(imdb_id=imdb_id, api_key=api_key, session=sess)
        return [single] if single else []

    # ------------ paged title search -----------------------------------------
    params: dict[str, str] = {"apikey": api_key, "page": "1"}
    if title:
        params["s"] = title
    if year:
        params["y"] = str(year)
    if media_type:
        params["type"] = media_type

    if season is not None:
        params["Season"] = str(season)
    if episode is not None:
        params["Episode"] = str(episode)
    if seriesID is not None:
        params["seriesID"] = seriesID

    # Flatten the generator of page dicts into one list of result items
    pages = _search_pages(sess, params, max_pages)
    results_iter = (page["Search"] for page in pages)                 # pyright: ignore[reportAny]
    results: list[dict] = list(itertools.chain.from_iterable(results_iter))
    return results
