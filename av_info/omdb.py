from typing import TypedDict, Literal, NotRequired, Required
import sys
import os
import requests


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
    imdbID: Required[str]
    Type: Required[MediaType]
    Released: NotRequired[str]
    Runtime: NotRequired[str]
    Genre: NotRequired[str]
    Director: NotRequired[str]
    Actors: NotRequired[str]
    Plot: NotRequired[str]
    Language: NotRequired[str]
    Country: NotRequired[str]
    Poster: NotRequired[str]
    imdbRating: NotRequired[str]
    imdbVotes: NotRequired[str]
    Ratings: NotRequired[list[dict[str, str]]]
    Response: str          # "True" / "False"


# ---------------------------------------------------------------------------
# 2. A thin client around the OMDb *by-title* and *search* endpoints
# ---------------------------------------------------------------------------
def query_title(
    title: str,
    year: int | None = None,
    media_type: MediaType = "movie",
    *,
    api_key: str | None = None,
    session: requests.Session | None = None,
) -> OMDbItem | None:
    if api_key is None:
        api_key = get_api_key()

    params: dict[str, str] = {"t": title, "apikey": api_key}
    if year:
        params["y"] = str(year)
    if media_type != "movie":
        params["type"] = media_type
    sess = session or requests
    resp = sess.get(OMDB_API_URL, params=params, timeout=10)
    data = resp.json() # pyright: ignore[reportAny]
    return data if data.get("Response") == "True" else None  # pyright: ignore[reportAny]


def search_title(
    title: str,
    year: int | None = None,
    media_type: MediaType | None = None,
    *,
    api_key: str | None = None,
    session: requests.Session | None = None,
    max_pages: int = 3,
) -> list[OMDbItem]:
    if api_key is None:
        api_key = get_api_key()
    params: dict[str, str|int] = {"s": title, "apikey": api_key, "page": 1}
    if year:
        params["y"] = str(year)
    if media_type:
        params["type"] = media_type
    sess = session or requests
    out: list[OMDbItem] = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        r = sess.get(OMDB_API_URL, params=params, timeout=10).json() # pyright: ignore[reportAny]
        if r.get("Response") != "True": # pyright: ignore[reportAny]
            break
        out.extend(r.get("Search", [])) # pyright: ignore[reportAny]
        if len(out) >= int(r.get("totalResults", len(out))): # pyright: ignore[reportAny]
            break
    return out
