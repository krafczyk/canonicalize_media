#find /data1/media_server/TV\ Shows/Regular\ Show\ \(2010\)\ Season\ 1-8\ S01-08\ \(1080p\ MiXED\ x265\ HEVC\ 10bit\ MiXED\ 2.0\ ImE\) -path "*Season 0*" -type f \( -name "*mkv" -or -name "*mp4" \) -print0 | sort -z | xargs -0 -n1 -P 4 python canonicalize.py --yes --skip-if-exists --convert-advanced-subtitles --staging-dir staging --metadata-provider tmdb -i
#find /data1/media_server/TV\ Shows -path "*Key.and.Peele*" -type f \( -name "*mkv" -or -name "*mp4" \) -print0 | sort -z | xargs -0 -n1 -P 4 python canonicalize.py --yes --skip-if-exists --convert-advanced-subtitles --staging-dir staging --metadata-provider tmdb -i

if [ -z "TMDB_API_KEY" ]; then
    source tmdb_api_key.sh
fi;
canonicalize --yes --skip-if-exists --convert-advanced-subtitles --staging-dir staging --metadata-provider tmdb "$@"
