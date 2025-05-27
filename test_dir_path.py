import argparse
from av_info.omdb import query
from av_info.plex import build_media_path
from pprint import pprint


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--imdb", type=str, help="IMDB id", required=False)
    _ = parser.add_argument("--title", type=str, help="Title of the movie to look for")
    _ = parser.add_argument("--year", type=str, help="Year")
    _ = parser.add_argument("--type", type=str, help="Type of media")
    _ = parser.add_argument("--season", type=str, help="Season number")
    _ = parser.add_argument("--episode", type=str, help="Episode number")
    _ = parser.add_argument("--resolution", type=str, help="Resolution of the media file")
    _ = parser.add_argument("--version", type=str, help="Version of the media file (e.g., HDR, BluRay)")
    _ = parser.add_argument("--edition", type=str, help="Edition of the media file (e.g., Director's Cut, Extended Edition)")
    args = parser.parse_args()

    query_response = query(
        imdb_id=args.imdb,
        title=args.title,
        year=args.year,
        media_type=args.type,
        season=args.season,
        episode=args.episode)


    if query_response:
        pprint(query_response, sort_dicts=False)
        print(build_media_path(
            query_response,
            resolution=args.resolution,
            version=args.version,
            edition=args.edition
        ))

    else:
        print("No results found.")
