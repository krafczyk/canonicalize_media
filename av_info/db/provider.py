from av_info.db.core import MetadataProvider


ProviderSpec = str | None | MetadataProvider


def get_provider(provider_spec: ProviderSpec) -> MetadataProvider:
    if provider_spec is None:
        from av_info.db.omdb import OMDBProvider
        return OMDBProvider()

    if isinstance(provider_spec, MetadataProvider):
        return provider_spec

    known_providers = [ 'omdb', 'tmdb', 'tvdb' ]

    if provider_spec not in known_providers:
        raise ValueError(f"{provider_spec} not in the list of known providers: {known_providers}")

    if provider_spec == "omdb":
        from av_info.db.omdb import OMDBProvider
        return OMDBProvider()
    elif provider_spec == "tmdb":
        from av_info.db.tmdb import TMDBProvider
        return TMDBProvider()
    elif provider_spec == "tvdb":
        from av_info.db.tvdb import TVDBProvider
        return TVDBProvider()
    else:
        raise RuntimeError("Unknown metadata provider issue.")
