import argparse
from av_info import MediaContainer
from typing import cast


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths

    _ = parser.add_argument("--input", "-i", nargs="+", help="Input file(s)", required=True)
    args = parser.parse_args()

    inputs: list[str] = cast(list[str], args.input)


    for i in inputs:
        file_cont = MediaContainer(i)
        file_cont.analyze()
