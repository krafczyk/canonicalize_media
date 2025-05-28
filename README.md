# Canonicalize Videos

A set of tools to automatically convert media files to formats that work on all of my devices. There are several tools to achieve this.
* ffmpeg interface for metadata about media files
* mediainfo interface for metadata about media files
* Tools to gather together metadata about a specific media file from different sources and present it in a unified manner
* Interface to omdb API for getting correct 'official' metadata about particular media
* Tools to build plex friendly filepaths from movie metadata
* Tools to guess and find correct omdb entries given a video file's filepath
* Tools to extract subtitle streams
* Tools to convert picture-based subtitles like pgs or vobsub to text based subtitles like .srt
* Tools to guess language of text-based subtitle streams

## Checking subtitle streams

Use tools like `mediainfo` to see what kinds of subtitle streams are embedded in a media file. By default, picture-based subtitle streams are copied verbatim to the output container. No automatic conversion to text-based is done.

`mediainfo <filepath>`

## Extracting picture-based subtitle streams

Once we know the stream id of the target subtitles, we extract it.

*FFmpeg extraction*: Works great for pgs subtitle streams. output should be something like `English.sup`
`bash extract_subtitle_stream_ffmpeg.sh <filepath> <stream_id> <output>`

*mkvextract extraction*: Works great for vobsub subtitle streams. output should be something like `English`
`bash extract_subtitle_stream_mkvextract.sh <filepath> <stream_id> <output>`

## Conversion of picture-based subtitle streams

Once we have a pgs `.sup` or vob `.idx/.sub` file, we can perform OCR conversion.

### PGS subtitles

The following creates a `.srt` file.
`bash pgstosrt.sh <sup_filepath>`

### VobSub subtitles

The following creates a `.srt` file from vobsub. Use the 'stem' component of the vobsub filenames.
`./VobSub2SRT/bin/vobsub2srt <subtitle_stem>`

## Canonicalization of media files

Automatic guessing of omdb entry allows the following to usually **just work (TM)**
`python canonicalize.py -i <media_filepath> [<srt_filepath>]`

You can also do `<srt_filepath>@@<srt_title>` to tell `canonicalize.py` what the title of that subtitle stream should be.

If `canonicalize.py` can't find an omdb entry for your media, you can explicitly tell it like this:
`python canonicalize.py --imdb-id <imdb_id> -i <media_filepath> [<srt_filepath> ...]`
