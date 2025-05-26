import argparse
from av_info.omdb import query_title
from typing import cast
from pprint import pprint
from av_info.utils import guess_imdb_id_from_media_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("filepath", type=str, help="Filepath of the media to use")
    _ = parser.add_argument("--type", type=str, help="The type to search with", default="movie")
    args = parser.parse_args()

    print(guess_imdb_id_from_media_file(cast(str,args.filepath), media_type=args.type))
