#!/bin/bash
set -e

set -x
canonicalize --yes --skip-if-exists --convert-advanced-subtitles --staging-dir staging --metadata-provider tmdb "$@"
