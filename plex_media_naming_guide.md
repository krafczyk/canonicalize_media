# Plex Media Naming Guide

“variable-based” cheat-sheet for both Movies and TV Shows, using regular hyphens throughout:

```
/Movies
└── <Movie_Title> (<Year>)/
    ├── <Movie_Title> (<Year>).<ext>
    ├── <Movie_Title> (<Year>) - <Resolution>.<ext>
    ├── <Movie_Title> (<Year>) - <Version>.<ext>
    └── <Movie_Title> (<Year>) {edition-<Edition_Name>} - <Resolution>.<ext>

/TV_Shows
└── <Show_Name> (<First_Air_Year>)/
    ├── Season <Season_Num>/
    │   ├── <Show_Name> - S<Season_Num>E<Episode_Num> - <Episode_Title>.<ext>
    │   └── …  
    ├── Specials/
    │   └── <Show_Name> - S00E<Special_Num> - <Special_Title>.<ext>
    └── <Show_Name> - YYYY-MM-DD - <Episode_Title>.<ext>   # date-based series
```

## Legend

`<Movie_Title>` or `<Show_Name>`: Use the exact title as it appears in your metadata source.

`<Year>` / `<First_Air_Year>`: Four-digit year for disambiguation.

`<Resolution>`: e.g. 1080p, 4K, etc.

`<Version>`: e.g. Director’s Cut, Remastered, etc.

`{edition-<Edition_Name>}`: Plex-style tag for extended cuts, director’s cuts, etc.

`<Season_Num>` / `<Episode_Num>`: Always two digits (e.g. 01, 02, …).

`<Episode_Title>`: Exact episode name for better library display.

`<Special_Num>` / `<Special_Title>`: For bonus content—use Season 00 numbering.

`<ext>`: File extension: mkv, mp4, avi, etc.
