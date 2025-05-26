import argparse
from av_info.omdb import search_title
from typing import cast
from pprint import pprint

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("title", type=str, help="Title of the movie to look for")
    _ = parser.add_argument("--year", type=str, help="Year", required=False)
    _ = parser.add_argument("--type", type=str, help="Type of media", default="movie")
    args = parser.parse_args()

    query_response = search_title(
        cast(str,args.title),
        cast(int|None,args.year),
        media_type=args.type)

    if query_response:
        for q in query_response:
            print(f"Found: {q['Title']} ({q['Year']})")
            print(f"IMDb ID: {q['imdbID']}")
            print(f"Type: {q['Type']}")
        pprint(query_response)
    else:
        print("No results found.")
