#!/bin/bash
# Launcher: opens the OpenJO engine at the main menu. Click START GAME to load the survival map.
cd "$(dirname "$0")" && python3 build.py || exit 1
ROOT="$PWD"
cd dist/JediOutcast && exec ./openjo_sp.x86_64 +set fs_basepath "$ROOT/game" +set fs_homepath "$ROOT/home" +set helpusobi 1 "$@"
