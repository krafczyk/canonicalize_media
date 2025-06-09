from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class BaseInfo:
    uid: str
    title: str
    year: str

@dataclass
class MovieInfo(BaseInfo):
    ...


@dataclass
class SeriesInfo(BaseInfo):
    ...



@dataclass
class EpisodeInfo(BaseInfo):
    series: SeriesInfo
    season: str
    episode: str


class MetadataProvider(ABC):
    @abstractmethod
    def search_movie(self, uid: str|None, title: str|None=None, year: str|None = None) -> list[MovieInfo]:        ...

    @abstractmethod
    def search_series(
            self,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None) -> list[SeriesInfo]:
        ...

    @abstractmethod
    def get_episode(
            self,
            series: SeriesInfo,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None,
            season: str|None = None,
            episode: str|None = None) -> EpisodeInfo | None:
        ...
