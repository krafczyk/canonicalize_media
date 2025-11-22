from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import override


@dataclass
class BaseInfo:
    uid: str
    title: str
    year: str

    @abstractmethod
    def fullname(self) -> str:
        ...

@dataclass
class MovieInfo(BaseInfo):
    @override
    def fullname(self) -> str:
        return f"{self.title} ({self.year})"


@dataclass
class SeriesInfo(BaseInfo):
    @override
    def fullname(self) -> str:
        return f"{self.title} ({self.year})"



@dataclass
class EpisodeInfo(BaseInfo):
    series: SeriesInfo
    season: str
    episode: str

    @override
    def fullname(self) -> str:
        return f"{self.series.fullname()} s{int(self.season):02d}e{int(self.episode):02d} - {self.title}"


@dataclass
class DoubleEpisodeInfo(BaseInfo):
    series: SeriesInfo
    season: str
    episode1: str
    episode2: str

    @override
    def fullname(self) -> str:
        return f"{self.series.fullname()} s{int(self.season):02d}e{int(self.episode1):02d}-e{int(self.episode2)} - {self.title}"


class MetadataProvider(ABC):
    @abstractmethod
    def search_movie(self, uid: str|None, title: str|None=None, year: str|None = None, verbose: bool=False) -> list[MovieInfo]:        ...

    @abstractmethod
    def search_series(
            self,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None,
            verbose: bool = False) -> list[SeriesInfo]:
        ...

    @abstractmethod
    def get_episode(
            self,
            series: SeriesInfo,
            uid: str|None = None,
            title: str|None = None,
            year: str|None = None,
            season: str|None = None,
            episode: str|None = None,
            verbose: bool = False) -> EpisodeInfo | None:
        ...
