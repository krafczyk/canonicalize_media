import argparse
import subprocess
from av_info import ffmpeg, mediainfo
from av_info.utils import get_h264_level_name, get_hevc_level_name
from pprint import pprint


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths
    _ = parser.add_argument("--input", "-i", nargs="+", help="Input file(s)", required=True)
    args = parser.parse_args()

    for i in args.input:
        container_dict = ffmpeg(i)
        for stream in container_dict['streams']:
            if stream['type'] == 'video':
                if stream['codec'] == 'h264':
                    stream['level_name'] = get_h264_level_name(stream['level'])
                elif stream['codec'] == 'hevc':
                    stream['level_name'] = get_hevc_level_name(stream['level'])
        pprint(container_dict)
        pprint(mediainfo(i))

