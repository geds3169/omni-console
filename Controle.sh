#!/usr/bin/env bash
# Controle complet du projet avant de construire une ISO : syntaxe, analyse
# statique, tests unitaires, tests de l'interface sous ecran virtuel.
# Usage : ./controle.sh            (depuis le dossier du projet)
# Prerequis (une fois) : sudo apt install shellcheck python3-tk python3-evdev xvfb imagemagick
#                        pip install pyflakes --break-system-packages
set -u
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
echec=0
etape() { printf '\n== %s\n' "$1"; }
passe() { "$@" || { echo "ECHEC : $*"; echec=1; }; }

etape "Syntaxe et shellcheck (build)"
passe bash -n omni-build.sh
passe shellcheck -S warning omni-build.sh

etape "Analyse statique Python"
passe python3 -m py_compile omni-console.py omni-installer.py
passe pyflakes omni-console.py omni-installer.py

etape "Tests de l'installateur (logique, sans disque)"
passe python3 -W ignore tests/test_installateur.py

etape "Tests des fonctions du build (faux chroot)"
passe bash tests/test_build.sh

etape "Interface sous ecran virtuel"
passe xvfb-run -a -s "-screen 0 1280x720x24" python3 tests/gui_installateur.py
passe xvfb-run -a -s "-screen 0 1280x720x24" python3 tests/gui_console.py

etape "Empreintes (a recopier dans ETAT-DU-PROJET.md et CONTENU.md si elles ont change)"
md5sum omni-build.sh omni-installer.py omni-console.py

if [[ ${echec} -eq 0 ]]; then echo; echo "TOUT EST BON"; else echo; echo "ECHECS : voir ci-dessus"; fi
exit "${echec}"
