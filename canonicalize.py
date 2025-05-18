import argparse
from av_info import MediaContainer
from typing import cast


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths

    _ = parser.add_argument("input", nargs="+", help="Input file(s), format is <filename>@@<Title>@@<Language> where the two extra fields are only relevant for extra audio/subtitle tracks.")
    args = parser.parse_args()

    inputs: list[str] = cast(list[str], args.input)

    containers: list[MediaContainer] = []

    for i in inputs:
        input_file = i
        if '@@' in i:
            input_file = i.split('@@')[0]

        file_cont = MediaContainer(input_file)
        file_cont.analyze()
        stream_lengths = (len(file_cont.video), len(file_cont.audio), len(file_cont.subtitle))
        if len(file_cont.subtitle) == 1 and sum(stream_lengths) == 1:
            title = i.split('@@')[1]
            language = i.split('@@')[2]
            file_cont.subtitle[0].title = title
            file_cont.subtitle[0].language = language
        if len(file_cont.audio) == 1 and sum(stream_lengths) == 1:
            title = i.split('@@')[1]
            language = i.split('@@')[2]
            file_cont.audio[0].title = title
            file_cont.audio[0].language = language
        containers.append(file_cont)

        print(f"File {i}")
        file_cont.summarize()
