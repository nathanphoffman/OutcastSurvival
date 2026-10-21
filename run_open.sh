#!/bin/bash
# Runs the self-built OpenJO engine (separate from the Steam install and from other projects).
# Game files: game/base (symlinks to your Steam assets + our pk3). Configs/saves: home/.
cd "$(dirname "$0")" && python3 build.py || exit 1
ROOT="$PWD"
cd dist/JediOutcast && exec ./openjo_sp.x86_64 +set fs_basepath "$ROOT/game" +set fs_homepath "$ROOT/home" +set helpusobi 1 "$@" +devmap survival_pit
