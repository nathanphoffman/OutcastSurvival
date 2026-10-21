#!/bin/bash
# Launches Jedi Outcast (Steam app 6030) once with the survival mod, without touching saved launch options.
exec steam -applaunch 6030 +set fs_game survival +set helpusobi 1 +devmap survival_pit
