import argparse
from av_info.db import get_provider
from av_info.plex import guess
from typing import cast
from pprint import pprint


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    _ = parser.add_argument("input", type=str, help="The filepath to use for guessing")
    _ = parser.add_argument("--uid", type=str, help="unique id", required=False)
    _ = parser.add_argument("--title", type=str, help="Title of the movie to look for")
    _ = parser.add_argument("--year", type=str, help="Year")
    _ = parser.add_argument("--series-uid", type=str, help="Series unique id")
    _ = parser.add_argument("--season", type=str, help="Season")
    _ = parser.add_argument("--episode", type=str, help="Episode")
    _ = parser.add_argument("--metadata-provider", type=str, default="omdb", help="The metadata provider to use")
    args = parser.parse_args()

    provider = get_provider(cast(str, args.metadata_provider))

    res = guess(
        cast(str, args.input),
        uid=cast(str|None, args.uid),
        title=cast(str|None, args.title),
        year=cast(str|None, args.year),
        series_uid=cast(str|None, args.series_uid),
        season=cast(str|None, args.season),
        episode=cast(str|None, args.episode),
        verbose=True,
        provider=provider
    )

    if res:
        print(f"guess result:")
        pprint(res)
    else:
        print("No results found.")


if __name__ == "__main__":
    main()
