#!/usr/bin/env bash
# Teste les fonctions du build dans un faux chroot (aucun root, aucun reseau).
set -u
export OMNI_WORK_ROOT=/tmp/wr
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${PROJ}/omni-build.sh"
mkdir -p "${LOG_DIR}"
run_in_chroot() { return 0; }          # le faux chroot n'execute rien
etape_chroot() { cat >/dev/null; return 0; }
ok=0; ko=0
verifie() { if eval "$2"; then ok=$((ok+1)); else ko=$((ko+1)); echo "ECHEC : $1"; fi; }

mkdir -p "${CHROOT_DIR}/etc" "${CHROOT_DIR}/boot" "${CHROOT_DIR}/root"
installer_ressources_projet >/dev/null; verifie "ressources copiees" "[[ \$? -eq 0 ]]"
verifie "interface copiee" "[[ -f ${CHROOT_DIR}/usr/local/share/omni/ui/omni-console.py ]]"
verifie "installateur executable" "[[ -x ${CHROOT_DIR}/usr/local/bin/omni-installer ]]"
verifie "cartes copiees" "[[ -f ${CHROOT_DIR}/usr/local/share/omni/ui/cartes/planche1.jpg ]]"
verifie "sons d'interface" "[[ -f ${CHROOT_DIR}/usr/local/share/omni/sons/omni-hover.ogg ]]"
verifie "lien ui/sons" "[[ -f ${CHROOT_DIR}/usr/local/share/omni/ui/sons/omni-valid.ogg ]]"
verifie "musique dans musique/" "[[ -f ${CHROOT_DIR}/usr/local/share/omni/musique/pont_de_verre_instru.ogg ]]"
verifie "pas de son d'interface dans musique/" "! ls ${CHROOT_DIR}/usr/local/share/omni/musique | grep -q '^omni-'"
ecrire_options_image >/dev/null
verifie "options : serie" "grep -q '^CONSOLE_SERIE=1' ${CHROOT_DIR}/usr/local/share/omni/options-image.conf"
verifie "version image" "grep -Eq '^20[0-9-]+-[0-9a-f]{6}\$' ${CHROOT_DIR}/etc/omni-version"
configurer_console_serie >/dev/null
verifie "getty serie" "[[ -L ${CHROOT_DIR}/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service ]]"
CONSOLE_SERIE=0 configurer_console_serie >/dev/null
ecrire_guichet_plateformes >/dev/null
verifie "guichet" "[[ -x ${CHROOT_DIR}/usr/local/sbin/omni-plateforme ]]"
verifie "versions injectees" "grep -q 'GE-Proton11-7' ${CHROOT_DIR}/usr/local/sbin/omni-poser-proton && grep -q 'GE-Proton10-10' ${CHROOT_DIR}/usr/local/sbin/omni-poser-proton && ! grep -q '@' ${CHROOT_DIR}/usr/local/sbin/omni-poser-proton"
verifie "intentions eteindre/redemarrer" "grep -q 'eteindre|redemarrer)' ${CHROOT_DIR}/usr/local/sbin/omni-plateforme"
verifie "intention proton-ubisoft" "grep -q 'proton-ubisoft)' ${CHROOT_DIR}/usr/local/sbin/omni-plateforme"
ecrire_fichiers_session_joueur >/dev/null
for f in omni-session-joueur omni-console.service openbox-autostart; do verifie "systeme/$f" "[[ -s ${CHROOT_DIR}/usr/local/share/omni/systeme/$f ]]"; done
verifie "selftest" "[[ -x ${CHROOT_DIR}/usr/local/sbin/omni-selftest ]]"
configurer_session_installateur >/dev/null
verifie "XDG_RUNTIME_DIR de l'installateur" "grep -q 'XDG_RUNTIME_DIR=/run/user/0' ${CHROOT_DIR}/usr/local/bin/omni-session"
trouver_theme_plymouth; verifie "theme plymouth trouve" "[[ -f \${PLYMOUTH_THEME_SRC}/omni.plymouth ]]"
# shellcheck des scripts ecrits dans l'image
for f in usr/local/sbin/omni-plateforme usr/local/sbin/omni-poser-proton usr/local/sbin/omni-selftest usr/local/bin/omni-session usr/local/share/omni/systeme/omni-session-joueur; do
  verifie "shellcheck $f" "shellcheck -S warning ${CHROOT_DIR}/$f"
done
verifie "bash -n poser-proton" "bash -n ${CHROOT_DIR}/usr/local/sbin/omni-poser-proton"
# une source manquante doit echouer bruyamment
verifie "source absente => erreur" "! copier_obligatoire /nexiste/pas /tmp/wr/x 644 2>/dev/null"
echo "build : ${ok} ok, ${ko} echec(s)"
[[ ${ko} -eq 0 ]]
