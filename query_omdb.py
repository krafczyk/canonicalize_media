import argparse
from av_info.omdb import query
from typing import cast
from pprint import pprint

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--imdb", type=str, help="IMDB id", required=False)
    _ = parser.add_argument("--title", type=str, help="Title of the movie to look for")
    _ = parser.add_argument("--year", type=str, help="Year")
    _ = parser.add_argument("--season", type=str, help="Season")
    _ = parser.add_argument("--episode", type=str, help="Episode")
    _ = parser.add_argument("--type", type=str, help="Type of media")
    args = parser.parse_args()

    query_response = query(
        imdb_id=cast(str|None,args.imdb),
        title=cast(str,args.title),
        year=cast(int|None,args.year),
        season=cast(int|None,args.season),
        episode=cast(int|None,args.episode),
        media_type=args.type)

    if query_response:
        pprint(query_response, sort_dicts=False)
    else:
        print("No results found.")
