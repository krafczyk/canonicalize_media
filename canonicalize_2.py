import argparse
import av_info
from pprint import pprint

if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths
    _ = parser.add_argument("--input", "-i", nargs="+", help="Input file(s)", required=True)
    args = parser.parse_args()

    for i in args.input:
        container_dict = av_info.dump_container_data(i)
        pprint(container_dict)
