#!/bin/bash

pgstosrt_src="PgsToSrt-git"
pgstosrt_prefix="PgsToSrt"
if [ ! -e "$pgstosrt_src" ]; then
  git clone git@github.com:Tentacule/PgsToSrt "$pgstosrt_src"
fi;

if [ ! -e "$pgstosrt_prefix" ]; then
  cd "$pgstosrt_src/src"
  dotnet restore
  dotnet publish -c Release -o "../../$pgstosrt_prefix" --framework net6.0
fi;
