#!/bin/bash
# Rebuilds the map (new random force-upgrade order each time), then launches Jedi Outcast (Steam app 6030)
# once with the survival mod, without touching saved launch options.
cd "$(dirname "$0")" && python3 build.py || exit 1
exec steam -applaunch 6030 +set fs_game survival +set helpusobi 1 +devmap "${SURV_MAP:-survival_chasm}"
