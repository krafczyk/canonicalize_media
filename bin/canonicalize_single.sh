#!/bin/bash
canonicalize --yes --skip-if-exists --convert-advanced-subtitles --staging-dir staging --metadata-provider tmdb -i "$1"
