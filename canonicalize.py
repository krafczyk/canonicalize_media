import argparse
from pprint import pprint
from av_info import MediaContainer


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths
    _ = parser.add_argument("--input", "-i", nargs="+", help="Input file(s)", required=True)
    args = parser.parse_args()

    for i in args.input:
        file_cont = MediaContainer(i)
        #pprint(file_cont.ffmpeg)
        pprint(file_cont.mediainfo)

        #file_cont.analyze()
