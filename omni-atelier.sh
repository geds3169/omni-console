#!/usr/bin/env bash
# omni-atelier.sh : les commandes de l'atelier en un seul endroit.
#
#   ./omni-atelier.sh etat          place disque, memoire, machines virtuelles en cours
#   ./omni-atelier.sh build         construit l'ISO (nettoyage complet, cache de Proton garde)
#   ./omni-atelier.sh nouveau [40G] disque de test neuf + installation depuis l'ISO
#   ./omni-atelier.sh lancer        demarre le systeme installe, console serie dans ce terminal
#
# Option --son (avec nouveau ou lancer) : active le son de la machine de test.
# Par defaut il est coupe : il sature l'atelier de messages « pulseaudio » inutiles.
#
# La console serie (TTY) est dans l'image : plus aucune manipulation du disque.
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISQUE="${OMNI_DISQUE:-${HOME}/disque-test.qcow2}"
ISO="${OMNI_ISO:-/root/omni-build/output/omni-console.iso}"
TAILLE_DEFAUT="40G"
MIN_LIBRE_BUILD_GO=16      # un build a besoin d'environ 13 Go, plus de la marge
MIN_LIBRE_DISQUE_GO=8      # un disque de test grossit jusqu'a sa taille reelle d'usage
RAM="2G"

die() { echo "ERREUR : $*" >&2; exit 1; }

# libre_go <chemin> : espace libre en Go sur le systeme de fichiers de ce chemin
libre_go() { df -BG --output=avail "$1" | tail -1 | tr -dc '0-9'; }

# machine_en_cours : vrai si une machine virtuelle de test tourne deja.
# L'atelier n'a que 3,4 Go de memoire : une seule machine, jamais pendant un build.
machine_en_cours() { pgrep -x qemu-system-x86 >/dev/null 2>&1 || pgrep -x qemu-system-x86_64 >/dev/null 2>&1; }

refuser_si_machine_en_cours() {
    machine_en_cours && die "une machine virtuelle de test tourne deja : ferme-la d'abord (memoire limitee)."
}

# iso_lisible : l'ISO doit etre lisible par l'utilisateur courant (QEMU ne tourne pas en root)
iso_lisible() {
    sudo test -f "${ISO}" || die "ISO introuvable : ${ISO} (lance d'abord : $0 build)"
    [[ -r "${ISO}" ]] || die "ISO illisible sans root : ${ISO}. Rends le dossier lisible : sudo chmod o+rx /root /root/omni-build /root/omni-build/output"
}

# qemu_commun <son|muet> : options communes aux deux modes de demarrage
# shellcheck disable=SC2054  # les virgules font partie des arguments de QEMU
qemu_commun() {
    QEMU=(qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m "${RAM}" -machine type=q35,accel=kvm
          -vga std -display gtk,gl=off,zoom-to-fit=on
          -drive "file=${DISQUE},format=qcow2,if=virtio" -nic user)
    if [[ "$1" == son ]]; then
        QEMU+=(-audiodev pa,id=snd0 -device ich9-intel-hda -device hda-output,audiodev=snd0)
    fi
}

cmd_etat() {
    echo "== Place disque (atelier)"; df -h /
    echo; echo "== Memoire"; free -h
    echo; echo "== Machines virtuelles de test en cours"
    machine_en_cours && pgrep -a qemu-system || echo "aucune"
    echo; echo "== Disque de test"
    if [[ -f "${DISQUE}" ]]; then qemu-img info "${DISQUE}" | grep -E "virtual size|disk size"; else echo "absent : ${DISQUE}"; fi
    echo; echo "== ISO"
    sudo ls -lh "${ISO}" 2>/dev/null || echo "absente : ${ISO}"
    echo; echo "== Empreintes des fichiers du projet"
    (cd "${DIR}" && md5sum omni-build.sh omni-installer.py omni-console.py)
}

cmd_build() {
    refuser_si_machine_en_cours
    local libre
    libre="$(libre_go /)"
    (( libre >= MIN_LIBRE_BUILD_GO )) || die "seulement ${libre} Go libres, il en faut ${MIN_LIBRE_BUILD_GO} pour un build. Voir : $0 etat"
    echo "Empreintes des fichiers :"; (cd "${DIR}" && md5sum omni-build.sh omni-installer.py omni-console.py)
    cd "${DIR}" && sudo ./omni-build.sh --clean-all
}

cmd_nouveau() {
    local taille="${TAILLE_DEFAUT}" son=muet arg
    for arg in "$@"; do
        case "${arg}" in
            --son) son=son ;;
            *) taille="${arg}" ;;
        esac
    done
    refuser_si_machine_en_cours
    iso_lisible
    local libre
    libre="$(libre_go "$(dirname "${DISQUE}")")"
    if [[ -f "${DISQUE}" ]]; then
        echo "Le disque de test ${DISQUE} existe. Il sera SUPPRIME et recree (${taille})."
        read -r -p "Tape oui pour continuer : " reponse
        [[ "${reponse}" == oui ]] || die "abandon, rien n'a ete modifie."
        rm -f "${DISQUE}"
        libre="$(libre_go "$(dirname "${DISQUE}")")"
    fi
    (( libre >= MIN_LIBRE_DISQUE_GO )) || die "seulement ${libre} Go libres pour le disque de test."
    qemu-img create -f qcow2 "${DISQUE}" "${taille}" || die "creation du disque impossible."
    qemu_commun "${son}"
    echo "Installation : choisis le disque dans l'installateur, puis lance : $0 lancer"
    "${QEMU[@]}" -cdrom "${ISO}" -boot order=d
}

cmd_lancer() {
    local son=muet
    [[ "${1:-}" == --son ]] && son=son
    refuser_si_machine_en_cours
    [[ -f "${DISQUE}" ]] || die "disque de test absent : ${DISQUE} (lance d'abord : $0 nouveau)"
    qemu_commun "${son}"
    echo "Console serie dans ce terminal. Quitter QEMU : Ctrl+A puis X."
    "${QEMU[@]}" -boot order=c,menu=off -serial mon:stdio
}

commande="${1:-}"
[[ $# -gt 0 ]] && shift
case "${commande}" in
    etat)    cmd_etat ;;
    build)   cmd_build ;;
    nouveau) cmd_nouveau "$@" ;;
    lancer)  cmd_lancer "$@" ;;
    *)       sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
