# test_guessing.py
import pytest
from typing import cast

from av_info.db import get_provider, ProviderSpec, BaseInfo, EpisodeInfo, SeriesInfo, MovieInfo  # noqa: F401  (imported for type hints)
from av_info.plex import guess

from mk_ic import install
install()

# --- test data --------------------------------------------------------------

filepath_dict = {
    "../temp/Adventure Time (2010) Season 1-10 S01-S10 + Extras (1080p BluRay x265 HEVC 10bit AAC 2.0 ImE)/Season 03/Adventure Time (2008) - S03E19 - Holly Jolly Secrets (1080p BluRay x265 ImE).mkv":
        EpisodeInfo(
            uid="tt2119588",
            series=SeriesInfo(uid="tt1305826", title="Adventure Time", year="2010"),
            title="Holly Jolly Secrets",
            year="2011",
            season="3",
            episode="19",
        ),
    "/data1/media_server/TV Shows/Key.and.Peele.S01.1080p.BluRay.DDP.5.1.x265-EDGE2020/Key.&.Peele.S01E01.Series.Premiere.1080p.BluRay.DDP.5.1.H.265.-EDGE2020.mkv":
        EpisodeInfo(
            uid="",
            series=SeriesInfo(uid="", title="Key and Peele", year="2012"),
            title="Bitch",
            year="2012",
            season="1",
            episode="1",
        ),
    "/data1/media_server/Movies/The.Nightmare.Before.Christmas.1993.1080p.BluRay.x264-FiDELiO/The.Nightmare.Before.Christmas.1993.1080p.BluRay.x264-FiDELiO.mkv":
        MovieInfo(
            uid="",
            title="The Nightmare Before Christmas",
            year="1993"),
    "/data1/media_server/Movies/Splice (2009) [1080p]/Splice.2009.1080p.BrRip.x264.YIFY.mp4":
        MovieInfo(
            uid="",
            title="Splice",
            year="2009"),
    # add more edge-cases here …
}

# Expand this list whenever you implement a new backend
PROVIDERS: list[ProviderSpec] = ["omdb", "tmdb"]


def movie_equality(
    lhs: MovieInfo, rhs: MovieInfo) -> bool:
    return (lhs.title == rhs.title and
            lhs.year == rhs.year)


def series_equality(
    lhs: SeriesInfo, rhs: SeriesInfo) -> bool:
    """
    Compare two SeriesInfo instances for equality.
    Don't include uid since it is not guaranteed to be the same
    """
    return (lhs.title == rhs.title and
            lhs.year == rhs.year)


def episode_equality(
    lhs: EpisodeInfo, rhs: EpisodeInfo) -> bool:
    return (lhs.title == rhs.title and
            lhs.year == rhs.year and
            series_equality(lhs.series, rhs.series) and
            lhs.season == rhs.season and
            lhs.episode == rhs.episode)


# --- fixtures / parametrisation --------------------------------------------

@pytest.fixture(params=PROVIDERS, scope="module")
def provider(request):
    """
    Creates (and implicitly registers) a provider instance for each backend
    name in PROVIDERS.  The fixture’s parametrisation multiplies with the
    explicit @pytest.mark.parametrize below, so every provider is exercised
    against every filepath.
    """
    return get_provider(request.param)


@pytest.mark.parametrize(
    ("filepath", "expected"),
    list(filepath_dict.items()),
)
def test_guess(provider: ProviderSpec, filepath: str, expected: BaseInfo):
    """
    Ensure guess() produces the expected EpisodeInfo/MovieInfo for every filepath
    under every provider.
    """
    result = guess(filepath, provider=provider)
    if not result:
        raise ValueError(f"guess returned None for {filepath}")
    ic(result)
    if isinstance(result, EpisodeInfo):
        if not isinstance(expected, EpisodeInfo):
            raise TypeError(f"Expected EpisodeInfo for {filepath}, got {type(expected)}: {expected!r}")
        assert episode_equality(result, expected), f"{filepath}: expected {expected!r}, got {result!r}"
    elif isinstance(result, MovieInfo):
        if not isinstance(expected, MovieInfo):
            raise TypeError(f"Expected MovieInfo for {filepath}, got {type(expected)}: {expected!r}")
        assert movie_equality(result, expected), f"{filepath}: expected {expected!r}, got {result!r}"
    elif isinstance(result, SeriesInfo):
        if not isinstance(expected, SeriesInfo):
            raise TypeError(f"Expected SeriesInfo for {filepath}, got {type(expected)}: {expected!r}")
        assert series_equality(result, expected), f"{filepath}: expected {expected!r}, got {result!r}"
    else:
        raise TypeError(f"Unexpected result type {type(result)} for {filepath}: {result!r}")

