import sys
import os


TMDB_API_URL = "https://api.themoviedb.org/3"


def get_tmdb_api_key() -> str:
    """Fetch TMDB API key from the environment, fail fast if missing."""
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        sys.exit("Error: Set TMDB_API_KEY in the environment first.")
    return api_key


