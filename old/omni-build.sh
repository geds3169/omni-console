#!/usr/bin/env bash
set -uo pipefail
IFS=$' \t\n'

# ============================================================================
# Omni Console - constructeur ISO
# Ubuntu 24.04 Noble / amd64
#
# BIOS + UEFI via grub-mkrescue
#
# Ajouts du 21 sept. 2026 :
#   - manettes : python3-evdev, regles udev, joycond (Joy-Con), xpadneo (Xbox BT)
#   - jeux : Steam officiel Valve (i386 + Vulkan 32 bits), umu-launcher (Proton hors Steam),
#     RetroArch + coeurs
#   - plein ecran sans jamais voir le bureau (regles Openbox)
#   - service d'installation a intentions (remplace un acces libre a apt-get)
#   - mises a jour automatiques (systeme, noyau, pilotes DKMS, firmwares)
#   - sons de l'interface copies a cote de omni-console.py
# ============================================================================

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="${SCRIPT_DIR}"

readonly WORK_ROOT="/root/omni-build"
readonly CHROOT_DIR="${WORK_ROOT}/chroot"
readonly IMAGE_DIR="${WORK_ROOT}/image"
readonly OUTPUT_DIR="${WORK_ROOT}/output"
readonly LOG_DIR="${WORK_ROOT}/logs"
readonly LOG_FILE="${LOG_DIR}/omni-build.log"

readonly ISO_NAME="omni-console.iso"
readonly ISO_VOLID="OMNI_CONSOLE"

readonly UBUNTU_SUITE="noble"
readonly UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu/"

readonly PLYMOUTH_THEME_SRC="${PROJECT_ROOT}/omni-plymouth-theme"
readonly PLYMOUTH_THEME_DST="${CHROOT_DIR}/usr/share/plymouth/themes/omni"

readonly INSTALLER_SRC="${PROJECT_ROOT}/omni-installer.py"

# Composants absents des depots Ubuntu : recuperes a leur source officielle,
# en version figee (build reproductible). Changer la version ici suffit.
readonly UMU_VERSION="1.4.4"
readonly PROTON_VERSION="GE-Proton11-7"

# Proton est embarque (librement redistribuable) : sinon 500 Mo au premier jeu
# Windows. Steam, lui, se telecharge chez Valve au premier lancement ; mettre
# STEAM_EMBARQUE=1 pour le preparer ici (usage personnel seulement, voir roadmap).
STEAM_EMBARQUE="${STEAM_EMBARQUE:-0}"
PROTON_EMBARQUE="${PROTON_EMBARQUE:-1}"
readonly XPADNEO_VERSION="0.10.4"
readonly JOYCOND_REF="master"

readonly BUILD_TOOLS=(
    debootstrap
    squashfs-tools
    xorriso
    grub-pc-bin
    grub-efi-amd64-bin
    grub-common
    grub2-common
    grub-pc
    mtools
    dosfstools
    initramfs-tools-core
)

readonly OMNI_CORE_PKGS=(
    ubuntu-minimal
    linux-generic
    linux-firmware
    casper
    initramfs-tools

    plymouth
    plymouth-themes
    plymouth-theme-ubuntu-text

    ubuntu-standard
    sudo

    xserver-xorg
    xserver-xorg-video-all
    xserver-xorg-input-all
    xinit
    x11-xserver-utils
    openbox
    xterm

    python3
    python3-tk
  mpv
  alsa-utils
  parted dosfstools e2fsprogs grub-efi-amd64 grub-pc-bin util-linux
  pulseaudio-utils
  pipewire pipewire-pulse wireplumber
  python3-pil python3-pil.imagetk network-manager
  # Resolution des noms (DNS) : NetworkManager d'Ubuntu s'appuie dessus
  systemd-resolved

  # Interface Omni : lecture des manettes + police de l'interface
  python3-evdev fonts-dejavu-core
  # Manettes : Bluetooth (les regles udev des manettes viennent avec le Steam officiel)
  bluez
  # Jeux : Vulkan (indispensable a Proton) + emulation
  mesa-vulkan-drivers libvulkan1
  retroarch libretro-nestopia libretro-snes9x libretro-mgba libretro-genesisplusgx
  libretro-beetle-psx libretro-gambatte
  # Telechargements (installeurs officiels des launchers, Proton)
  curl ca-certificates
  # Savoir si une fenetre (Steam, launcher) est vraiment affichee a l'ecran
  x11-utils xdotool wmctrl
  # Preparation de Steam sans ecran, pendant la construction
  xvfb
  # Bus de session : sans lui, Steam et les portails attendent des reponses
  # qui ne viennent jamais (c'est ce qui rendait son installation interminable)
  dbus-x11
  # Mises a jour automatiques : systeme + noyau (unattended-upgrades), firmwares (fwupd)
  unattended-upgrades fwupd
  # Pilotes construits pour le noyau (xpadneo) et reconstruits a chaque nouveau noyau
  dkms linux-headers-generic build-essential cmake pkg-config libevdev-dev libudev-dev
)

# ============================================================================
# Mode nettoyage
# ============================================================================

CLEAN_MODE="${CLEAN_MODE:-keep-base}"

usage() {
    cat <<EOF
Usage:
  sudo $0
  sudo $0 --keep-base
  sudo $0 --clean-all

Options:
  --keep-base   conserve le systeme de base Ubuntu existant
  --clean-all   supprime completement le chroot et repart de zero
  --verifier    ne construit rien : verifie que tous les paquets et
                telechargements des plateformes sont disponibles (1 a 2 min)
EOF
}

case "${1:-}" in
    "")
        ;;
    --keep-base)
        CLEAN_MODE="keep-base"
        ;;
    --clean-all)
        CLEAN_MODE="all"
        ;;
    --verifier)
        CLEAN_MODE="verifier"
        ;;
    *)
        usage
        exit 2
        ;;
esac

# ============================================================================
# Couleurs / logs
# ============================================================================

if [[ -t 1 ]]; then
    readonly C_RESET=$'\033[0m'
    readonly C_INFO=$'\033[36m'
    readonly C_OK=$'\033[32m'
    readonly C_WARN=$'\033[33m'
    readonly C_ERR=$'\033[31m'
else
    readonly C_RESET=""
    readonly C_INFO=""
    readonly C_OK=""
    readonly C_WARN=""
    readonly C_ERR=""
fi

_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

_log() {
    local lvl="$1"
    local col="$2"
    shift 2

    local l
    l="$(_timestamp) [${lvl}] $*"

    printf '%s%s%s\n' "${col}" "${l}" "${C_RESET}"

    mkdir -p "${LOG_DIR}" 2>/dev/null || true
    printf '%s\n' "${l}" >> "${LOG_FILE}" 2>/dev/null || true
}

log_info() {
    _log "INFO" "${C_INFO}" "$@"
}

log_ok() {
    _log " OK " "${C_OK}" "$@"
}

log_warn() {
    _log "WARN" "${C_WARN}" "$@"
}

log_err() {
    _log "ERR " "${C_ERR}" "$@"
}

# ============================================================================
# Securite fichiers
# ============================================================================

safe_rm() {
    local t="$1"

    if [[ -z "${t}" ]]; then
        log_err "safe_rm : cible vide."
        return 1
    fi

    local abs

    if ! abs="$(realpath -m -- "${t}")"; then
        log_err "safe_rm : chemin insoluble : ${t}"
        return 1
    fi

    case "${abs}" in
        "/"|"${HOME}"|"")
            log_err "safe_rm : cible interdite : ${abs}"
            return 1
            ;;
    esac

    if [[ "${abs}" != "${WORK_ROOT}/"* ]]; then
        log_err "safe_rm : ${abs} hors de ${WORK_ROOT}."
        return 1
    fi

    if [[ ! -e "${abs}" ]]; then
        return 0
    fi

    log_info "Suppression : ${abs}"

    rm -rf -- "${abs}"
}

# ============================================================================
# Montage chroot
# ============================================================================

MOUNTED_POINTS=()

mount_special() {
    local type="$1"
    local src="$2"
    local mnt="$3"
    local opts="${4:-}"

    local abs
    abs="$(realpath -m -- "${mnt}")"

    if [[ "${abs}" != "${CHROOT_DIR}/"* ]]; then
        log_err "mount hors chroot : ${abs}"
        return 1
    fi

    mkdir -p "${abs}"

    if mountpoint -q -- "${abs}"; then
        log_info "Deja monte : ${abs}"
        MOUNTED_POINTS+=("${abs}")
        return 0
    fi

    if [[ -n "${opts}" ]]; then
        if ! mount -t "${type}" -o "${opts}" "${src}" "${abs}"; then
            log_err "Echec montage ${type} : ${abs}"
            return 1
        fi
    elif ! mount -t "${type}" "${src}" "${abs}"; then
        log_err "Echec montage ${type} : ${abs}"
        return 1
    fi

    MOUNTED_POINTS+=("${abs}")

    log_info "Monte : ${abs}"
}

mount_bind() {
    local src="$1"
    local mnt="$2"

    local abs
    abs="$(realpath -m -- "${mnt}")"

    if [[ "${abs}" != "${CHROOT_DIR}/"* ]]; then
        log_err "mount hors chroot : ${abs}"
        return 1
    fi

    mkdir -p "${abs}"

    if mountpoint -q -- "${abs}"; then
        log_info "Deja monte : ${abs}"
        MOUNTED_POINTS+=("${abs}")
        return 0
    fi

    if ! mount --bind "${src}" "${abs}"; then
        log_err "Echec bind mount : ${src} -> ${abs}"
        return 1
    fi

    MOUNTED_POINTS+=("${abs}")

    log_info "Monte (bind) : ${abs}"
}

unmount_all() {
    local i

    for (( i=${#MOUNTED_POINTS[@]}-1; i>=0; i-- )); do
        local m="${MOUNTED_POINTS[i]}"

        if mountpoint -q -- "${m}"; then
            # premier essai, puis deux nouvelles tentatives : un montage encore
            # occupe se libere presque toujours en une seconde ou deux
            local essai
            local fait=0

            for essai in 1 2 3; do
                if umount "${m}" 2>/dev/null; then
                    log_info "Demonte : ${m}"
                    fait=1
                    break
                fi
                sleep 1
            done

            if (( fait == 0 )); then
                if umount -R "${m}" 2>/dev/null; then
                    log_info "Demonte (avec ses sous-montages) : ${m}"
                elif umount -l "${m}" 2>/dev/null; then
                    log_warn "Demonte en differe : ${m} etait encore occupe, le noyau le liberera."
                else
                    log_err "Echec demontage : ${m}"
                fi
            fi
        fi
    done

    MOUNTED_POINTS=()
}

_on_exit() {
    local c=$?

    unmount_all

    if (( c == 0 )); then
        log_ok "Script termine sans erreur."
    else
        log_err "Script interrompu (code ${c}). Voir ${LOG_FILE}"
    fi

    exit "${c}"
}

# ============================================================================
# Chroot
# ============================================================================

run_in_chroot() {
    chroot "${CHROOT_DIR}" \
        /usr/bin/env -i \
        HOME=/root \
        LC_ALL=C \
        LANG=C.UTF-8 \
        DEBCONF_NONINTERACTIVE_SEEN=true \
        DEBCONF_FRONTEND=noninteractive \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        DEBIAN_FRONTEND=noninteractive \
        /bin/bash -c "$*"
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Lancer avec sudo : sudo $0 $*" >&2
        exit 1
    fi
}

# ============================================================================
# Workspace
# ============================================================================

prepare_workspace() {
    mkdir -p "${LOG_DIR}" || exit 1
    : >> "${LOG_FILE}" || exit 1

    log_info "Racine de travail : ${WORK_ROOT}"
    log_info "Projet : ${PROJECT_ROOT}"

    mkdir -p "${OUTPUT_DIR}" || return 1
}

clean_previous() {
    log_info "Nettoyage (mode : ${CLEAN_MODE})."

    unmount_all

    safe_rm "${OUTPUT_DIR}" || return 1
    mkdir -p "${OUTPUT_DIR}" || return 1

    safe_rm "${IMAGE_DIR}" || return 1

    if [[ "${CLEAN_MODE}" == "all" ]]; then
        safe_rm "${CHROOT_DIR}" || return 1
        log_ok "Nettoyage complet effectue."
    else
        log_info "Systeme de base conserve (cache)."
        log_ok "Nettoyage leger effectue."
    fi
}

# ============================================================================
# Etape 1 - dependances
# ============================================================================

step_check_dependencies() {
    log_info "Etape 1/6 : verification des outils de construction."

    if ! apt-get update >>"${LOG_FILE}" 2>&1; then
        log_err "apt-get update a echoue."
        return 1
    fi

    local manquants=()
    local outil

    for outil in "${BUILD_TOOLS[@]}"; do
        dpkg -s "${outil}" >/dev/null 2>&1 || manquants+=("${outil}")
    done

    if (( ${#manquants[@]} > 0 )); then
        log_info "Installation des outils manquants : ${manquants[*]}"

        if ! DEBIAN_FRONTEND=noninteractive \
            apt-get install -y "${manquants[@]}" >>"${LOG_FILE}" 2>&1; then

            log_err "Installation des outils echouee."
            return 1
        fi
    else
        log_info "Tous les outils sont deja presents."
    fi

    local o

    for o in \
        debootstrap \
        xorriso \
        mksquashfs \
        grub-mkrescue \
        grub-mkstandalone \
        lsinitramfs; do

        if ! command -v "${o}" >/dev/null 2>&1; then
            log_err "Outil introuvable : ${o}"
            return 1
        fi
    done

    local ko
    local go

    ko="$(df -Pk "${WORK_ROOT}" | awk 'NR==2 {print $4}')"
    go=$(( ko / 1024 / 1024 ))

    log_info "Espace disponible : ${go} Go."

    local mo
    mo="$(free -m | awk '/^Mem:/ {print $2}')"

    if (( mo < 3500 )); then
        log_warn "Machine a ${mo} Mo de memoire : le build tiendra, mais lentement."
        log_warn "Ferme toute VM de test pendant la construction."
    fi

    if (( go < 5 )); then
        log_warn "Moins de 5 Go libres."
    fi

    log_ok "Etape 1/6 terminee : outils prets, ${go} Go disponibles."
}

# ============================================================================
# Etape 2 - debootstrap
# ============================================================================

step_open_base_iso() {
    log_info "Etape 2/6 : systeme de base Ubuntu (${UBUNTU_SUITE})."

    if [[ -x "${CHROOT_DIR}/bin/bash" ||
          -x "${CHROOT_DIR}/usr/bin/bash" ]]; then

        log_info "Systeme de base deja present (cache), etape 2 sautee."
        log_ok "Etape 2/6 terminee (cache)."
        return 0
    fi

    mkdir -p "${CHROOT_DIR}" || return 1

    log_info "Telechargement du systeme minimal."

    if ! debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --components=main,restricted,universe,multiverse \
        "${UBUNTU_SUITE}" \
        "${CHROOT_DIR}" \
        "${UBUNTU_MIRROR}" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "debootstrap a echoue."
        return 1
    fi

    if [[ ! -x "${CHROOT_DIR}/bin/bash" &&
          ! -x "${CHROOT_DIR}/usr/bin/bash" ]]; then

        log_err "Systeme de base incomplet."
        return 1
    fi

    local taille
    taille="$(du -sh "${CHROOT_DIR}" 2>/dev/null | awk '{print $1}')"

    log_ok "Etape 2/6 terminee : systeme de base cree (${taille})."
}

# ============================================================================
# Etape 3 - preparation chroot
# ============================================================================

step_enter_system() {
    log_info "Etape 3/6 : preparation de l'acces au systeme de base."

    mount_special proc proc "${CHROOT_DIR}/proc" || return 1
    mount_special sysfs sysfs "${CHROOT_DIR}/sys" || return 1
    mount_bind /dev "${CHROOT_DIR}/dev" || return 1
    # /dev/pts : on relie celui de la machine. Creer un nouveau jeu de terminaux
    # ici donnerait un /dev/ptmx incoherent, et la preconfiguration des paquets
    # attendrait un terminal qui n'arriverait jamais.
    mount_bind /dev/pts "${CHROOT_DIR}/dev/pts" || return 1
    # taille bornee : sur une machine d'atelier a 4 Go, un tmpfs libre prendrait
    # la moitie de la memoire
    mount_special tmpfs tmpfs "${CHROOT_DIR}/dev/shm" "size=256m" || return 1

    rm -f "${CHROOT_DIR}/etc/resolv.conf"

    if ! cp -L /etc/resolv.conf "${CHROOT_DIR}/etc/resolv.conf"; then
        log_err "Impossible de copier resolv.conf."
        return 1
    fi

    cat > "${CHROOT_DIR}/etc/apt/sources.list" <<SOURCES
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE} main restricted universe multiverse
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-updates main restricted universe multiverse
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-security main restricted universe multiverse
SOURCES

    bloquer_services

    # Un build precedent a pu etre interrompu en plein travail de dpkg : dans ce
    # cas le systeme de base reste bloque tant qu'on ne le remet pas d'aplomb.
    if run_in_chroot "dpkg --audit 2>/dev/null | grep -q ." >/dev/null 2>&1; then
        log_warn "Systeme de base laisse en plan par un build precedent : remise d'aplomb."
        run_in_chroot "dpkg --configure -a" >>"${LOG_FILE}" 2>&1 || true
    fi

    if ! run_in_chroot "apt-get update" >>"${LOG_FILE}" 2>&1; then
        log_err "apt-get update interne a echoue."
        return 1
    fi

    log_ok "Etape 3/6 terminee : systeme accessible, depots prets."
}

# ============================================================================
# Neutralisation update-initramfs pendant apt
# ============================================================================

# Pendant la construction, aucun paquet ne doit demarrer de service : le
# systeme du chroot n'est pas en fonctionnement, et le demarrage attend
# indefiniment (c'est ce qui figeait l'installation de Steam apres
# « Preconfiguring packages »). policy-rc.d est le mecanisme officiel de
# Debian pour refuser ces demarrages ; il est retire avant la fabrication
# de l'ISO pour que la vraie console demarre ses services normalement.
bloquer_services() {
    printf '%s\n' '#!/bin/sh' 'exit 101' > "${CHROOT_DIR}/usr/sbin/policy-rc.d"
    chmod +x "${CHROOT_DIR}/usr/sbin/policy-rc.d"
    log_info "Demarrage des services interdit pendant la construction."
}

debloquer_services() {
    rm -f "${CHROOT_DIR}/usr/sbin/policy-rc.d"
    log_info "Demarrage des services de nouveau autorise (console finale)."
}

neutralize_chroot_cmds() {
    # dpkg-preconfigure : inutile en mode non interactif, et c'est lui qui se
    # figeait juste apres « Preconfiguring packages ».
    run_in_chroot '
        if [ -x /usr/sbin/dpkg-preconfigure ] &&
           [ ! -e /usr/sbin/dpkg-preconfigure.real ]; then
            mv /usr/sbin/dpkg-preconfigure /usr/sbin/dpkg-preconfigure.real
            printf "%s\n" "#!/bin/sh" "exit 0" > /usr/sbin/dpkg-preconfigure
            chmod +x /usr/sbin/dpkg-preconfigure
        fi
    '

    run_in_chroot '
        if [ -x /usr/sbin/update-initramfs ] &&
           [ ! -e /usr/sbin/update-initramfs.real ]; then

            mv /usr/sbin/update-initramfs \
               /usr/sbin/update-initramfs.real

            printf "%s\n" \
                "#!/bin/sh" \
                "exit 0" \
                > /usr/sbin/update-initramfs

            chmod +x /usr/sbin/update-initramfs
        fi
    '
}

restore_chroot_cmds() {
    run_in_chroot '
        if [ -e /usr/sbin/dpkg-preconfigure.real ]; then
            mv -f /usr/sbin/dpkg-preconfigure.real /usr/sbin/dpkg-preconfigure
        fi
    '

    run_in_chroot '
        if [ -e /usr/sbin/update-initramfs.real ]; then
            mv -f \
                /usr/sbin/update-initramfs.real \
                /usr/sbin/update-initramfs
        fi
    '
}

# ============================================================================
# Etape 4 - installation systeme
# ============================================================================

step_install_omni() {
    log_info "Etape 4/6 : installation de la couche systeme demarrable."

    local pkgs
    pkgs="$(printf '%s ' "${OMNI_CORE_PKGS[@]}")"

    log_info "Paquets : ${pkgs}"

    neutralize_chroot_cmds >>"${LOG_FILE}" 2>&1 || {
        log_err "Impossible de neutraliser update-initramfs."
        return 1
    }

    log_info "Installation des paquets."

    # Ubuntu publie ses mises a jour en continu : un paquet liste il y a dix
    # minutes peut avoir disparu du serveur (erreur 404). Dans ce cas on
    # rafraichit la liste et on recommence, au lieu de tout arreter.
    local essai
    local pose=0

    for essai in 1 2 3; do
        if run_in_chroot \
            "apt-get -o Acquire::Retries=3 install -y --no-install-recommends --fix-missing ${pkgs}" \
            > "${LOG_DIR}/paquets.log" 2>&1; then
            pose=1
            break
        fi

        if grep -q "dpkg was interrupted" "${LOG_DIR}/paquets.log"; then
            log_warn "dpkg avait ete interrompu (essai ${essai}/3) : remise d'aplomb puis nouvel essai."
            run_in_chroot "dpkg --configure -a" >>"${LOG_FILE}" 2>&1 || true
            sleep 5
        elif grep -q "404\|Unable to fetch\|Hash Sum mismatch" "${LOG_DIR}/paquets.log"; then
            log_warn "Liste de paquets perimee (essai ${essai}/3) : rafraichissement puis nouvel essai."
            run_in_chroot "apt-get update" >>"${LOG_FILE}" 2>&1 || true
            sleep 5
        else
            break
        fi
    done

    if (( pose == 0 )); then
        cat "${LOG_DIR}/paquets.log" >> "${LOG_FILE}"
        log_err "Installation des paquets echouee. Dernieres lignes :"
        grep -E "^(E:|dpkg: |Errors were|  )" "${LOG_DIR}/paquets.log" | tail -n 12 |
            while IFS= read -r l; do log_err "    ${l}"; done
        tail -n 6 "${LOG_DIR}/paquets.log" | while IFS= read -r l; do log_err "    ${l}"; done
        log_err "Journal complet de cette etape : ${LOG_DIR}/paquets.log"
        restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
        return 1
    fi

    cat "${LOG_DIR}/paquets.log" >> "${LOG_FILE}"

    if ! run_in_chroot \
        "dpkg --configure -a" \
        > "${LOG_DIR}/configure.log" 2>&1; then

        cat "${LOG_DIR}/configure.log" >> "${LOG_FILE}"
        log_err "dpkg --configure -a a echoue. Dernieres lignes :"
        tail -n 12 "${LOG_DIR}/configure.log" | while IFS= read -r l; do log_err "    ${l}"; done
        restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
        return 1
    fi

    if ! restore_chroot_cmds >>"${LOG_FILE}" 2>&1; then
        log_err "Restauration de update-initramfs impossible."
        return 1
    fi

    local rate=0
    local p

    for p in "${OMNI_CORE_PKGS[@]}"; do
        if run_in_chroot \
            "dpkg -s ${p} 2>/dev/null | grep -q '^Status: install ok installed'"
        then
            :
        else
            log_err "Paquet non installe : ${p}"
            rate=1
        fi
    done

    if [[ ! -f "${CHROOT_DIR}/usr/lib/x86_64-linux-gnu/plymouth/script.so" ]]; then
        log_err "Renderer Plymouth 'script.so' absent."
        rate=1
    else
        log_ok "Renderer Plymouth script.so present."
    fi

    local noyau=""

    noyau="$(
        cd "${CHROOT_DIR}/boot" 2>/dev/null &&
        find . -maxdepth 1 -type f -name 'vmlinuz-*' \
            -printf '%f\n' |
        sort -V |
        tail -1 ||
        true
    )"

    if [[ -z "${noyau}" ]]; then
        log_err "Aucun noyau (vmlinuz) dans /boot."
        rate=1
    fi

    if (( rate != 0 )); then
        return 1
    fi

    local taille
    taille="$(du -sh "${CHROOT_DIR}" 2>/dev/null | awk '{print $1}')"

    log_ok "Etape 4/6 terminee : noyau ${noyau} present, systeme a ${taille}."
}

# ============================================================================
# Etape 4b - jeux et manettes (composants hors depots Ubuntu)
#
# Chaque composant est tente separement. Un echec est signale en WARN mais ne
# bloque pas le build : la console demarre quand meme, seule la fonction
# concernee manquera. Le bilan s'affiche a la fin de l'etape.
# ============================================================================

step_install_jeux() {
    log_info "Etape 4b/6 : jeux et manettes (Steam, Proton, Joy-Con, Xbox Bluetooth)."

    local kver
    kver="$(
        find "${CHROOT_DIR}/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' |
        sed 's/^vmlinuz-//' | sort -V | tail -1
    )"

    local bilan_ok=()
    local bilan_ko=()
    # Sans ces trois-la, la console ne peut pas faire tourner de jeu Windows :
    # leur echec arrete le build au lieu de produire une ISO inutilisable.
    local manque_obligatoire=()

    neutralize_chroot_cmds >>"${LOG_FILE}" 2>&1 || true

    # ------------------------------------------------------------------------
    # Steam : client natif embarque (cahier des charges) + Vulkan 32 bits
    # ------------------------------------------------------------------------

    log_info "Steam : client officiel de Valve + bibliotheques 32 bits."

    # Le paquet Ubuntu « steam-installer » affiche au premier lancement une
    # fenetre Debian en anglais (« Steam installer... Install »), puis ouvre un
    # terminal pour les bibliotheques manquantes. On utilise donc le paquet
    # officiel de Valve + ses bibliotheques : premier lancement sans question,
    # seule la fenetre de mise a jour de Steam apparait.
    # Les paquets Steam d'Ubuntu (steam-installer, steam-devices, steam-libs...)
    # ramenent l'installateur Debian et sont en conflit avec le Steam de Valve.
    # On les interdit une fois pour toutes : seul le depot de Valve peut les fournir.
    mkdir -p "${CHROOT_DIR}/etc/apt/preferences.d"
    cat > "${CHROOT_DIR}/etc/apt/preferences.d/omni-steam" <<'PINSTEAM'
# Omni Console : Steam uniquement depuis le depot officiel de Valve
Package: steam steam-installer steam-devices steam-libs steam-libs-i386 steam-libs-amd64 steam-launcher
Pin: origin archive.ubuntu.com
Pin-Priority: -1
PINSTEAM

    # Le depot de Valve est declare AVANT toute installation : ses paquets
    # dependent les uns des autres, et apt doit pouvoir les resoudre.
    # Tout est encadre par des delais : une etape qui ne repond pas s'arrete au
    # lieu de bloquer le build, et dit ou elle en etait.
    cat > "${CHROOT_DIR}/usr/local/sbin/omni-install-steam" <<'INSTSTEAM'
#!/bin/bash
# Installation du Steam officiel de Valve pendant la construction de l'ISO.
set -e
export DEBIAN_FRONTEND=noninteractive
# --force-confdef / --force-confold : aucune question sur les fichiers de
# configuration, on garde toujours celui en place (sinon dpkg attend une reponse).
APTOPT="-o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=2"
APTOPT="${APTOPT} -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
APTOPT="${APTOPT} -o Dpkg::Use-Pty=0"
# ne jamais attendre indefiniment un verrou laisse par une tentative precedente
APTOPT="${APTOPT} -o DPkg::Lock::Timeout=60"

echo "== remise d'aplomb apres une eventuelle interruption"
dpkg --configure -a || true

echo "== nettoyage des paquets Steam d'Ubuntu"
apt-get purge -y steam-installer steam-devices steam-libs steam-libs:i386 steam-libs-i386:i386 >/dev/null 2>&1 || true

echo "== architecture 32 bits"
dpkg --add-architecture i386

echo "== licence Steam acceptee d'avance (sinon la question bloque le build)"
for proprio in steam steam-launcher steam-installer; do
    echo "${proprio} steam/question select I AGREE" | debconf-set-selections
    echo "${proprio} steam/license note" | debconf-set-selections
done

echo "== cle et depot de Valve"
curl -fsSL --max-time 120 --retry 2 -o /usr/share/keyrings/steam.gpg \
    https://repo.steampowered.com/steam/archive/stable/steam.gpg
test -s /usr/share/keyrings/steam.gpg
# nom different de celui du paquet Valve : sinon dpkg demande lequel garder
echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/steam.gpg] https://repo.steampowered.com/steam/ stable steam" \
    > /etc/apt/sources.list.d/omni-steam.list

# Les miroirs d'Ubuntu se synchronisent en permanence : un index peut etre
# momentanement incoherent. On reessaie au lieu de tout arreter.
maj_listes() {
    date "+== %H:%M:%S mise a jour des listes de paquets"
    for essai in 1 2 3; do
        if timeout 300 apt-get ${APTOPT} update; then
            return 0
        fi
        echo "== listes incompletes (essai ${essai}/3), nouvel essai dans 20 s"
        sleep 20
    done
    echo "== listes toujours incompletes : on continue avec ce qu'on a"
    return 0
}

# Diagnostic : quand une tentative est coupee, on note QUI etait encore en
# train de travailler. C'est la seule facon de savoir ce qui bloquait.
menage_apt() {
    echo "-- processus encore en cours :"
    ps -eo stat,etime,cmd | grep -E "apt|dpkg|debconf|ldconfig" | grep -v grep | head -10
    pkill -9 -f "apt-get|apt-config|dpkg|debconf" 2>/dev/null
    sleep 2
    rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock
    dpkg --configure -a 2>&1 | tail -5
}

installer() {
    date "+== %H:%M:%S installation : $*"
    for essai in 1 2 3; do
        # apt travaille en fond ; toutes les 2 minutes on note ce qui tourne,
        # pour savoir QUI bloque si le delai est depasse
        timeout 600 apt-get ${APTOPT} install -y --no-install-recommends --fix-missing "$@" &
        apt_pid=$!
        compte=0
        while kill -0 ${apt_pid} 2>/dev/null; do
            sleep 20
            compte=$((compte + 1))
            if [ $((compte % 6)) -eq 0 ]; then
                date "+-- %H:%M:%S toujours en cours, processus actifs :"
                ps -eo stat,etime,cmd | grep -E "apt|dpkg|debconf|ldconfig|perl" | grep -v grep | head -8
            fi
        done
        if wait ${apt_pid}; then
            return 0
        fi
        date "+== %H:%M:%S essai ${essai} rate"
        menage_apt
        maj_listes
        sleep 5
    done
    return 1
}

echo "== mise a jour des listes"
maj_listes

# horodatage de chaque etape : en cas de blocage, on sait exactement ou
# En trois lots separes : si un seul bloque, le journal le designe tout de suite.
date "+== %H:%M:%S lot 1 : pile graphique 32 bits (depots Ubuntu)"
installer libc6:i386 libegl1 libegl1:i386 libgbm1 libgbm1:i386 \
    libgl1 libgl1:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 \
    mesa-vulkan-drivers:i386 libvulkan1:i386

date "+== %H:%M:%S lot 2 : portails de bureau"
installer xdg-desktop-portal xdg-desktop-portal-gtk

# Proton fait tourner les launchers Windows en s'appuyant sur les bibliotheques
# de la console. Sans elles, Wine s'arrete sur « cannot find the FreeType font
# library ». On les installe dans les deux architectures.
date "+== %H:%M:%S lot 2b : bibliotheques attendues par Wine et Proton"
installer libfreetype6 libfreetype6:i386 libfontconfig1 libfontconfig1:i386 \
    libgnutls30t64 libgnutls30t64:i386 libpng16-16t64 libpng16-16t64:i386 \
    libxml2 libxml2:i386 libxslt1.1 libxslt1.1:i386 \
    libx11-6:i386 libxext6:i386 libxrandr2:i386 libxi6:i386 \
    libxcursor1:i386 libxcomposite1:i386 libxfixes3:i386 \
    libdbus-1-3:i386 libpulse0:i386 libasound2t64:i386 \
    libusb-1.0-0:i386 libudev1:i386 libsdl2-2.0-0:i386 \
    libgssapi-krb5-2:i386 libkrb5-3:i386 libcups2t64:i386 \
    libodbc2:i386 libncurses6:i386 libtiff6:i386 libosmesa6:i386 \
    fonts-liberation fonts-dejavu

date "+== %H:%M:%S lot 3 : Steam et ses bibliotheques (depot de Valve)"
installer steam-launcher
installer steam-libs-amd64
installer steam-libs-i386:i386

echo "== nettoyage : le depot est desormais fourni par le paquet de Valve"
rm -f /etc/apt/sources.list.d/omni-steam.list
maj_listes

date "+== %H:%M:%S controles"
dpkg -s steam-launcher >/dev/null
if dpkg -s steam-installer >/dev/null 2>&1; then
    echo "ERREUR : steam-installer (Debian) est toujours present"
    exit 1
fi
command -v steam
echo "== Steam installe"
INSTSTEAM
    chmod +x "${CHROOT_DIR}/usr/local/sbin/omni-install-steam"

    if run_in_chroot "timeout 2700 /usr/local/sbin/omni-install-steam" > "${LOG_DIR}/steam.log" 2>&1; then
        cat "${LOG_DIR}/steam.log" >> "${LOG_FILE}"
        bilan_ok+=("Steam")
    else
        cat "${LOG_DIR}/steam.log" >> "${LOG_FILE}"
        manque_obligatoire+=("Steam")
        log_warn "Steam n'a pas pu etre installe."
        log_warn "Chronologie des etapes (la derniere est celle qui a bloque) :"
        grep "^== " "${LOG_DIR}/steam.log" | while IFS= read -r l; do log_warn "    ${l}"; done
        log_warn "Dernieres lignes du journal :"
        grep -vE "^(Get:|W: Target|Reading|Building|Fetched)" "${LOG_DIR}/steam.log" | tail -n 12 |
            while IFS= read -r l; do log_warn "    ${l}"; done
        log_warn "Journal complet de cette etape : ${LOG_DIR}/steam.log"
        rm -f "${CHROOT_DIR}/usr/local/sbin/omni-install-steam"
        bilan_ko+=("Steam")
    fi

    # ------------------------------------------------------------------------
    # umu-launcher : fait tourner les launchers et jeux Windows sous Proton
    # hors de Steam. Paquets officiels du projet, version figee.
    # Proton lui-meme est telecharge par umu au premier lancement d'un jeu.
    # ------------------------------------------------------------------------

    log_info "umu-launcher ${UMU_VERSION} (Proton hors Steam)."

    if run_in_chroot "
        set -e
        export DEBIAN_FRONTEND=noninteractive
        dpkg --configure -a || true
        # umu depend de bibliotheques graphiques 32 bits
        dpkg --add-architecture i386
        for essai in 1 2 3; do apt-get update && break; sleep 20; done
        cd /tmp
        base=https://github.com/Open-Wine-Components/umu-launcher/releases/download/${UMU_VERSION}
        curl -fsSL --max-time 300 --retry 2 -o python3-umu.deb \${base}/python3-umu-launcher_${UMU_VERSION}-1_amd64_ubuntu-${UBUNTU_SUITE}.deb
        curl -fsSL --max-time 300 --retry 2 -o umu.deb \${base}/umu-launcher_${UMU_VERSION}-1_all_ubuntu-${UBUNTU_SUITE}.deb
        apt-get install -y --no-install-recommends ./python3-umu.deb ./umu.deb
        rm -f python3-umu.deb umu.deb
        command -v umu-run
    " >>"${LOG_FILE}" 2>&1; then
        bilan_ok+=("umu-launcher")
    else
        manque_obligatoire+=("umu-launcher")
        log_warn "umu-launcher n'a pas pu etre installe. Voir le journal du build."
        bilan_ko+=("umu-launcher")
    fi

    # ------------------------------------------------------------------------
    # xpadneo : pilote des manettes Xbox en Bluetooth (DKMS).
    # Construit pour le noyau de l'ISO (pas celui de la machine de build),
    # puis reconstruit automatiquement a chaque nouveau noyau.
    # ------------------------------------------------------------------------

    log_info "xpadneo ${XPADNEO_VERSION} pour le noyau ${kver}."

    if [[ -n "${kver}" ]] && run_in_chroot "
        set -e
        v=v${XPADNEO_VERSION}
        rm -rf /tmp/xpadneo && mkdir /tmp/xpadneo && cd /tmp/xpadneo
        curl -fsSL --max-time 300 --retry 2 https://codeload.github.com/atar-axis/xpadneo/tar.gz/refs/tags/\${v} | tar xz --strip-components=1
        rm -rf /usr/src/hid-xpadneo-\${v}
        cp -r hid-xpadneo /usr/src/hid-xpadneo-\${v}
        sed \"s/@DO_NOT_CHANGE@/\${v}/g\" hid-xpadneo/dkms.conf.in > /usr/src/hid-xpadneo-\${v}/dkms.conf
        dkms status -m hid-xpadneo -v \${v} | grep -q hid-xpadneo || dkms add -m hid-xpadneo -v \${v}
        dkms build -m hid-xpadneo -v \${v} -k ${kver}
        dkms install -m hid-xpadneo -v \${v} -k ${kver}
        rm -rf /tmp/xpadneo
    " >>"${LOG_FILE}" 2>&1; then
        bilan_ok+=("xpadneo")
    else
        log_warn "xpadneo n'a pas pu etre installe. Voir xpadneo dans le journal du build."
        bilan_ko+=("xpadneo")
    fi

    # ------------------------------------------------------------------------
    # joycond : associe les Joy-Con (a deux = une manette, seul = mini-manette)
    # ------------------------------------------------------------------------

    log_info "joycond (Joy-Con)."

    if run_in_chroot "
        set -e
        rm -rf /tmp/joycond && mkdir /tmp/joycond && cd /tmp/joycond
        curl -fsSL --max-time 300 --retry 2 https://codeload.github.com/DanielOgorchock/joycond/tar.gz/refs/heads/${JOYCOND_REF} | tar xz --strip-components=1
        sed -i 's/-Werror//' CMakeLists.txt
        cmake .
        make -j\"\$(nproc)\"
        make install
        systemctl enable joycond.service
        rm -rf /tmp/joycond
    " >>"${LOG_FILE}" 2>&1; then
        bilan_ok+=("joycond")
    else
        log_warn "joycond n'a pas pu etre installe. Voir joycond dans le journal du build."
        bilan_ko+=("joycond")
    fi

    # ------------------------------------------------------------------------
    # Steam pret a l'emploi : on fait ici, une fois, ce que chaque console
    # refaisait a son premier lancement (telechargement, decompression,
    # verification). Steam refuse de tourner en root : compte temporaire et
    # ecran virtuel, puis le resultat est garde comme modele dans l'ISO.
    # ------------------------------------------------------------------------

    if [[ "${STEAM_EMBARQUE}" == "1" ]] && run_in_chroot "command -v steam" >/dev/null 2>&1; then
        log_info "Preparation de Steam (une seule fois, ici) : compter 10 a 20 minutes."

        cat > "${CHROOT_DIR}/usr/local/sbin/omni-preparer-steam" <<'PREPSTEAM'
#!/bin/bash
# Lance Steam sans ecran, attend qu'il ait fini de se telecharger et de se
# verifier, puis l'arrete. Utilise uniquement pendant la construction de l'ISO.
set -u
export HOME=/home/omnibuild
cd "$HOME" || exit 1
nohup xvfb-run -a -s "-screen 0 1280x720x24" steam -silent > /tmp/steam-prep.log 2>&1 &
fini=0
for _ in $(seq 1 180); do
    sleep 10
    if [ -x "$HOME/.local/share/Steam/steam.sh" ] && [ -d "$HOME/.local/share/Steam/ubuntu12_64" ]; then
        t1=$(du -sb "$HOME/.local/share/Steam" | cut -f1)
        sleep 20
        t2=$(du -sb "$HOME/.local/share/Steam" | cut -f1)
        if [ "$t1" = "$t2" ]; then fini=1; break; fi
    fi
done
steam -shutdown > /dev/null 2>&1 || true
sleep 10
pkill -u omnibuild > /dev/null 2>&1 || true
[ "$fini" = 1 ]
PREPSTEAM
        chmod +x "${CHROOT_DIR}/usr/local/sbin/omni-preparer-steam"

        if run_in_chroot "
            set -e
            id omnibuild >/dev/null 2>&1 || useradd -m -s /bin/bash omnibuild
            su - omnibuild -c /usr/local/sbin/omni-preparer-steam
            rm -rf /usr/local/share/omni/steam-template
            mkdir -p /usr/local/share/omni/steam-template
            cp -a /home/omnibuild/.local/share/Steam/. /usr/local/share/omni/steam-template/
            rm -rf /usr/local/share/omni/steam-template/logs /usr/local/share/omni/steam-template/userdata \
                   /usr/local/share/omni/steam-template/config/loginusers.vdf
            chmod -R a+rX /usr/local/share/omni/steam-template
            userdel -r omnibuild >/dev/null 2>&1 || true
            du -sh /usr/local/share/omni/steam-template
        " >>"${LOG_FILE}" 2>&1; then
            bilan_ok+=("Steam prêt à l'emploi")
        else
            log_warn "Steam n'a pas pu etre prepare : les consoles le telechargeront au premier lancement."
            run_in_chroot "userdel -r omnibuild >/dev/null 2>&1 || true" >>"${LOG_FILE}" 2>&1 || true
            bilan_ko+=("préparation de Steam")
        fi
        rm -f "${CHROOT_DIR}/usr/local/sbin/omni-preparer-steam"
    fi

    # ------------------------------------------------------------------------
    # Proton embarque : sinon umu telecharge 500 Mo au premier jeu Windows.
    # GE-Proton est librement redistribuable.
    # ------------------------------------------------------------------------

    if [[ "${PROTON_EMBARQUE}" == "1" ]]; then
        log_info "Proton ${PROTON_VERSION} embarque dans l'image."
        if run_in_chroot "
            set -e
            rm -rf /opt/omni/proton
            mkdir -p /opt/omni/proton
            cd /tmp
            base=https://github.com/GloriousEggroll/proton-ge-custom/releases/download/${PROTON_VERSION}
            # pas de guillemets ici : une adresse ne contient pas d'espace, et
            # des guillemets mal echappes la rendraient invalide
            curl -fsSL --max-time 1800 --retry 2 -o proton.tar.gz \${base}/${PROTON_VERSION}-x86_64.tar.gz \
                || curl -fsSL --max-time 1800 --retry 2 -o proton.tar.gz \${base}/${PROTON_VERSION}.tar.gz
            tar xzf proton.tar.gz -C /opt/omni/proton --strip-components=1
            rm -f proton.tar.gz
            # umu exige le toolmanifest.vdf : sans lui il refuse le dossier
            test -f /opt/omni/proton/toolmanifest.vdf
            test -x /opt/omni/proton/proton
            chmod -R a+rX /opt/omni/proton
        " > "${LOG_DIR}/proton.log" 2>&1; then
            cat "${LOG_DIR}/proton.log" >> "${LOG_FILE}"
            bilan_ok+=("Proton ${PROTON_VERSION}")
            log_ok "Moteur Proton complet : umu + ${PROTON_VERSION}."
        else
            cat "${LOG_DIR}/proton.log" >> "${LOG_FILE}"
            manque_obligatoire+=("Proton")
            log_warn "Proton n'a pas pu etre embarque. Dernieres lignes :"
            tail -n 8 "${LOG_DIR}/proton.log" | while IFS= read -r l; do log_warn "    ${l}"; done
            rm -rf "${CHROOT_DIR}/opt/omni/proton"
            bilan_ko+=("Proton")
        fi
    fi

    restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true

    if (( ${#bilan_ok[@]} > 0 )); then
        log_ok "Installes : ${bilan_ok[*]}"
    fi

    if (( ${#bilan_ko[@]} > 0 )); then
        log_warn "A reprendre : ${bilan_ko[*]}"
    fi

    if (( ${#manque_obligatoire[@]} > 0 )); then
        log_err "Composants indispensables manquants : ${manque_obligatoire[*]}"
        log_err "Une console sans eux ne peut ni installer ni lancer de jeu Windows."
        log_err "Corrige le probleme ci-dessus puis relance le build (--keep-base suffit)."
        return 1
    fi

    log_ok "Etape 4b/6 terminee : environnement de jeu complet."
    return 0
}

# ============================================================================
# Etape 5 - configuration
# ============================================================================

step_apply_settings() {
    log_info "Etape 5/6 : configuration X + clavier + Plymouth + installateur."

    # ------------------------------------------------------------------------
    # Pas de display manager
    # ------------------------------------------------------------------------

    run_in_chroot \
        "apt-get purge -y nodm lightdm lightdm-gtk-greeter gdm3 sddm 2>/dev/null || true" \
        >>"${LOG_FILE}" 2>&1 || true

    # ------------------------------------------------------------------------
    # IMPORTANT :
    # Aucun getty ne doit prendre tty1.
    #
    # Sinon on voit temporairement un terminal avec demande de login
    # avant ou pendant le lancement de X.
    # ------------------------------------------------------------------------

    run_in_chroot \
        "systemctl mask getty@tty1.service" \
        >>"${LOG_FILE}" 2>&1 || {
            log_err "Impossible de masquer getty@tty1.service."
            return 1
        }

    run_in_chroot \
        "systemctl disable getty@tty1.service 2>/dev/null || true" \
        >>"${LOG_FILE}" 2>&1 || true

    # Evite egalement les getty virtuels supplementaires.
    run_in_chroot \
        "systemctl mask console-getty.service 2>/dev/null || true" \
        >>"${LOG_FILE}" 2>&1 || true

    # ------------------------------------------------------------------------
    # Installateur
    # ------------------------------------------------------------------------

    if [[ ! -f "${INSTALLER_SRC}" ]]; then
        log_err "omni-installer.py introuvable : ${INSTALLER_SRC}"
        return 1
    fi

    mkdir -p "${CHROOT_DIR}/usr/local/bin"

    cp "${INSTALLER_SRC}" \
       "${CHROOT_DIR}/usr/local/bin/omni-installer" \
       || {
           log_err "Copie de omni-installer.py echouee."
           return 1
       }

    chmod +x "${CHROOT_DIR}/usr/local/bin/omni-installer"
    # Interface Omni (console post-installation)
    mkdir -p "${CHROOT_DIR}/usr/local/share/omni/ui/cartes"
    if [ -f /home/geds/mon-projet/omni-console.py ]; then
        cp /home/geds/mon-projet/omni-console.py "${CHROOT_DIR}/usr/local/share/omni/ui/"
        cp /home/geds/mon-projet/cartes/*.jpg "${CHROOT_DIR}/usr/local/share/omni/ui/cartes/" 2>/dev/null
        log_ok "Interface Omni copiee."
    fi
    # Musique d'installation
    mkdir -p "${CHROOT_DIR}/usr/local/share/omni"
    for f in "${PROJECT_ROOT}"/*.mp3 "${PROJECT_ROOT}"/*.ogg; do
        [ -f "$f" ] && cp "$f" "${CHROOT_DIR}/usr/local/share/omni/"
    done
    log_ok "Musique copiee dans l'ISO."
    if [ -d "${PROJECT_ROOT}/sons" ]; then
        mkdir -p "${CHROOT_DIR}/usr/local/share/omni/sons"
        cp "${PROJECT_ROOT}"/sons/*.ogg "${CHROOT_DIR}/usr/local/share/omni/sons/" 2>/dev/null
        # L'interface cherche ses sons a cote d'elle (ui/sons)
        mkdir -p "${CHROOT_DIR}/usr/local/share/omni/ui/sons"
        cp "${PROJECT_ROOT}"/sons/*.ogg "${CHROOT_DIR}/usr/local/share/omni/ui/sons/" 2>/dev/null
        log_ok "Sons interface copies."
    fi

    log_ok "Nouveau omni-installer.py installe dans l'ISO."

    # ------------------------------------------------------------------------
    # Service d'installation a intentions
    #
    # L'interface ne recoit PAS le droit d'utiliser apt-get librement : elle
    # demande « steam » ou « emu », et ce service installe une liste de
    # paquets figee. Rien d'autre n'est accepte (cahier des charges §3).
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/usr/local/sbin"

    cat > "${CHROOT_DIR}/usr/local/sbin/omni-plateforme" <<'OMNIPLAT'
#!/bin/sh
# Omni Console - service d'installation des plateformes (intentions uniquement)
set -u
export DEBIAN_FRONTEND=noninteractive

case "${1:-}" in
    proton)
        exec /usr/local/sbin/omni-poser-proton ;;
    steam) PKGS="steam-launcher steam-libs-amd64 steam-libs-i386:i386 libc6:i386 libegl1 libegl1:i386 libgbm1 libgbm1:i386 libgl1 libgl1:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 xdg-desktop-portal xdg-desktop-portal-gtk" ;;
    emu)   PKGS="retroarch libretro-nestopia libretro-snes9x libretro-mgba libretro-genesisplusgx libretro-beetle-psx libretro-gambatte" ;;
    *)     echo "omni-plateforme : intention inconnue" >&2; exit 2 ;;
esac

apt-get update >/dev/null 2>&1 || true
# shellcheck disable=SC2086
exec apt-get install -y --no-install-recommends -o APT::Status-Fd=1 ${PKGS}
OMNIPLAT

    chmod 755 "${CHROOT_DIR}/usr/local/sbin/omni-plateforme"

    # Moteur Proton (umu + GE-Proton) installable depuis la console elle-meme :
    # si l'etape du build a echoue, la console se repare sans reconstruire l'ISO.
    cat > "${CHROOT_DIR}/usr/local/sbin/omni-poser-proton" <<POSERPROTON
#!/bin/bash
# Omni Console - installation du moteur Proton (umu + GE-Proton)
set -u
export DEBIAN_FRONTEND=noninteractive
UMU="${UMU_VERSION}"
PROTON="${PROTON_VERSION}"
SUITE="${UBUNTU_SUITE}"
POSERPROTON
    cat >> "${CHROOT_DIR}/usr/local/sbin/omni-poser-proton" <<'POSERPROTON2'

echo "Vérification des composants déjà présents"
if ! command -v umu-run >/dev/null 2>&1; then
    echo "Téléchargement du lanceur Proton (umu)"
    cd /tmp || exit 1
    base="https://github.com/Open-Wine-Components/umu-launcher/releases/download/${UMU}"
    curl -fsSL --max-time 300 --retry 2 -o python3-umu.deb         "${base}/python3-umu-launcher_${UMU}-1_amd64_ubuntu-${SUITE}.deb" || exit 1
    curl -fsSL --max-time 300 --retry 2 -o umu.deb         "${base}/umu-launcher_${UMU}-1_all_ubuntu-${SUITE}.deb" || exit 1
    echo "Installation du lanceur Proton"
    dpkg --add-architecture i386
    apt-get update >/dev/null 2>&1 || true
    apt-get install -y --no-install-recommends -o Dpkg::Options::=--force-confold         ./python3-umu.deb ./umu.deb || exit 1
    rm -f python3-umu.deb umu.deb
fi

if [ ! -f /opt/omni/proton/toolmanifest.vdf ]; then
    echo "Téléchargement de Proton, environ 500 Mo : c'est la partie longue"
    rm -rf /opt/omni/proton
    mkdir -p /opt/omni/proton
    cd /tmp || exit 1
    b="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/${PROTON}"
    curl -fsSL --max-time 3600 --retry 2 -o proton.tar.gz "${b}/${PROTON}-x86_64.tar.gz"         || curl -fsSL --max-time 3600 --retry 2 -o proton.tar.gz "${b}/${PROTON}.tar.gz" || exit 1
    echo "Décompression de Proton"
    tar xzf proton.tar.gz -C /opt/omni/proton --strip-components=1 || exit 1
    rm -f proton.tar.gz
    chmod -R a+rX /opt/omni/proton
fi

echo "Contrôle final"
command -v umu-run >/dev/null 2>&1 || exit 1
test -f /opt/omni/proton/toolmanifest.vdf || exit 1
echo "Moteur Proton prêt"
POSERPROTON2
    chmod 755 "${CHROOT_DIR}/usr/local/sbin/omni-poser-proton"

    mkdir -p "${CHROOT_DIR}/etc/sudoers.d"

    cat > "${CHROOT_DIR}/etc/sudoers.d/omni-plateforme" <<'SUDOERS'
# L'utilisateur omni peut demander l'installation d'une plateforme connue,
# et uniquement cela.
omni ALL=(root) NOPASSWD: /usr/local/sbin/omni-plateforme
SUDOERS

    chmod 440 "${CHROOT_DIR}/etc/sudoers.d/omni-plateforme"

    if ! run_in_chroot "visudo -cf /etc/sudoers.d/omni-plateforme" >>"${LOG_FILE}" 2>&1; then
        log_err "Regle sudoers omni-plateforme invalide."
        return 1
    fi

    log_ok "Service d'installation a intentions en place."

    # ------------------------------------------------------------------------
    # Manettes
    #
    # L'interface lit les manettes directement (python3-evdev), meme quand un
    # jeu est au premier plan (bouton Guide). Les manettes sont donc lisibles
    # par la session ; uinput servira a la souris virtuelle (stick = curseur).
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/udev/rules.d" "${CHROOT_DIR}/etc/modules-load.d"

    cat > "${CHROOT_DIR}/etc/udev/rules.d/70-omni-manettes.rules" <<'UDEVPAD'
# Omni Console : manettes lisibles par la session console
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_JOYSTICK}=="1", MODE="0666"
# Peripherique virtuel (souris pilotee au stick dans les launchers)
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0666", OPTIONS+="static_node=uinput"
UDEVPAD

    printf '%s\n' uinput > "${CHROOT_DIR}/etc/modules-load.d/omni-uinput.conf"

    run_in_chroot "systemctl enable bluetooth.service 2>/dev/null || true" >>"${LOG_FILE}" 2>&1 || true

    log_ok "Regles manettes en place."

    # ------------------------------------------------------------------------
    # Openbox : jamais de bureau visible
    #
    # - toute fenetre (launchers, navigateur, jeux) sans bordure et agrandie
    # - les petites fenetres de dialogue restent centrees
    # - aucun menu au clic sur le fond, aucun raccourci clavier Openbox
    # - le fond de l'ecran est aux couleurs d'Omni
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/xdg/openbox"

    cat > "${CHROOT_DIR}/etc/xdg/openbox/rc.xml" <<'OBRC'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <resistance><strength>10</strength><screen_edge_strength>20</screen_edge_strength></resistance>
  <focus><focusNew>yes</focusNew><followMouse>no</followMouse></focus>
  <placement><policy>Smart</policy><center>yes</center></placement>
  <theme><name>Clearlooks</name><titleLayout></titleLayout></theme>
  <desktops><number>1</number></desktops>
  <keyboard></keyboard>
  <mouse>
    <dragThreshold>1</dragThreshold>
    <context name="Root"></context>
  </mouse>
  <menu><file>menu.xml</file></menu>
  <applications>
    <application class="*">
      <decor>no</decor>
      <maximized>yes</maximized>
      <focus>yes</focus>
    </application>
    <application type="dialog">
      <decor>no</decor>
      <maximized>no</maximized>
      <position force="yes"><x>center</x><y>center</y></position>
    </application>
  </applications>
</openbox_config>
OBRC

    cat > "${CHROOT_DIR}/etc/xdg/openbox/autostart" <<'OBAUTO'
# Omni Console : fond de l'ecran aux couleurs d'Omni, jamais de bureau
xsetroot -solid "#0d0221" &
OBAUTO

    log_ok "Openbox configure (plein ecran, aucun bureau)."

    # ------------------------------------------------------------------------
    # Reseau
    #
    # Par defaut, le NetworkManager d'Ubuntu ne gere QUE le Wi-Fi : la prise
    # RJ45 (et la carte reseau d'une VM) restait sans adresse. On lui confie
    # toutes les cartes, cable compris, et le DNS passe par systemd-resolved.
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/netplan" "${CHROOT_DIR}/etc/NetworkManager/conf.d"

    cat > "${CHROOT_DIR}/etc/netplan/01-omni-network-manager.yaml" <<'NETPLAN'
network:
  version: 2
  renderer: NetworkManager
NETPLAN

    chmod 600 "${CHROOT_DIR}/etc/netplan/01-omni-network-manager.yaml"

    # meme nom que le fichier d'Ubuntu : le remplace, toutes les cartes sont gerees
    cat > "${CHROOT_DIR}/etc/NetworkManager/conf.d/10-globally-managed-devices.conf" <<'NMALL'
[keyfile]
unmanaged-devices=none
NMALL

    run_in_chroot "systemctl enable NetworkManager.service systemd-resolved.service 2>/dev/null || true" \
        >>"${LOG_FILE}" 2>&1 || true

    log_ok "Reseau configure (cable + Wi-Fi, DNS)."

    # ------------------------------------------------------------------------
    # Mises a jour automatiques
    #
    # Systeme + noyau : unattended-upgrades (securite ET mises a jour).
    # Pilotes DKMS (xpadneo) : reconstruits automatiquement a chaque noyau.
    # Firmwares : fwupd (verification periodique).
    # Launchers : ils se mettent a jour eux-memes a leur ouverture.
    # Redemarrage jamais impose pendant une partie.
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/apt/apt.conf.d"

    cat > "${CHROOT_DIR}/etc/apt/apt.conf.d/20auto-upgrades" <<'AUTOUPG'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
AUTOUPG

    cat > "${CHROOT_DIR}/etc/apt/apt.conf.d/52omni-unattended" <<'OMNIUPG'
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}:${distro_codename}-updates";
};
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
OMNIUPG

    run_in_chroot "systemctl enable fwupd-refresh.timer 2>/dev/null || true" >>"${LOG_FILE}" 2>&1 || true

    log_ok "Mises a jour automatiques configurees."

    # ------------------------------------------------------------------------
    # .xinitrc
    #
    # IMPORTANT :
    # Aucun xterm de secours n'est lance.
    # En cas d'erreur de l'installateur, l'erreur est seulement journalisee.
    # ------------------------------------------------------------------------

    cat > "${CHROOT_DIR}/root/.xinitrc" <<'XINITRC'
#!/bin/sh

exec >>/var/log/omni-xinit.log 2>&1

echo
echo "=================================================="
echo "Omni X session"
date
echo "=================================================="

export DISPLAY="${DISPLAY:-:0}"
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=OPENBOX
export XDG_CURRENT_DESKTOP=Openbox

echo "DISPLAY=${DISPLAY}"
echo "Demarrage de omni-installer..."

# ---------------------------------------------------------------------------
# L'installateur constitue l'interface graphique principale.
# Il ne faut PAS lancer xterm en cas d'erreur :
# cela provoquait la fenetre terminal visible precedemment.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Le bus de session et le serveur de son doivent etre en place AVANT
# l'installateur : sinon l'installation se deroule en silence, et la console
# ensuite aussi. Tout vit dans la meme session.
# ---------------------------------------------------------------------------

exec dbus-run-session -- /usr/local/bin/omni-session

# ---------------------------------------------------------------------------
# Openbox reste le gestionnaire de fenetres de la session.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Son : pipewire et wireplumber sont normalement demarres par la session
# utilisateur de systemd, qui n'existe pas ici (la session est lancee par
# xinit). Sans eux, AUCUN son ne sort : ni l'interface, ni les jeux.
# ---------------------------------------------------------------------------

# (session, son et installateur sont demarres ensemble, plus haut)
XINITRC

    chmod +x "${CHROOT_DIR}/root/.xinitrc"

    # Session : son, installateur, puis gestionnaire de fenetres. Dans cet
    # ordre, et dans le meme bus, sinon l'installation se fait en silence.
    cat > "${CHROOT_DIR}/usr/local/bin/omni-session" <<'OMNISESSION'
#!/bin/sh
# Omni Console - contenu de la session graphique

# serveur de son : personne d'autre ne le demarre ici
pipewire &
sleep 1
wireplumber &
pipewire-pulse &
sleep 1

/usr/local/bin/omni-installer
rc=$?
echo "omni-installer a termine avec le code ${rc}"

if [ "${rc}" -ne 0 ]; then
    echo "ERREUR : omni-installer a echoue."
    echo "Voir /var/log/omni-xinit.log et le journal systemd."
fi

exec /usr/bin/openbox-session
OMNISESSION

    chmod +x "${CHROOT_DIR}/usr/local/bin/omni-session"

    # ------------------------------------------------------------------------
    # Service X
    #
    # On conserve un service systemd dedie.
    # xinit lance directement Xorg + la session.
    #
    # Le getty de tty1 est masque ci-dessus.
    # ------------------------------------------------------------------------

    cat > "${CHROOT_DIR}/etc/systemd/system/omni-x.service" <<'OMNIX'
[Unit]
Description=Omni Console - session graphique X11
After=systemd-user-sessions.service plymouth-start.service local-fs.target
Wants=plymouth-quit.service
Conflicts=getty@tty1.service
Before=graphical.target

[Service]
Type=simple

User=root
Group=root

Environment=HOME=/root
Environment=DISPLAY=:0
Environment=XDG_SESSION_TYPE=x11
Environment=XDG_CURRENT_DESKTOP=Openbox

WorkingDirectory=/root

StandardInput=null
StandardOutput=journal
StandardError=journal

# ---------------------------------------------------------------------------
# Plymouth doit disparaitre juste avant le passage a X.
# ---------------------------------------------------------------------------

ExecStartPre=/bin/sh -c '/usr/bin/plymouth quit >/dev/null 2>&1 || true'
ExecStartPre=/bin/sh -c '/usr/bin/plymouth deactivate >/dev/null 2>&1 || true'

# Nettoyage d'une eventuelle session X precedente.
ExecStartPre=/bin/sh -c 'rm -f /tmp/.X0-lock /tmp/.X11-unix/X0 >/dev/null 2>&1 || true'

ExecStartPre=/bin/sleep 1

# ---------------------------------------------------------------------------
# xinit lance Xorg sur tty1 puis /root/.xinitrc.
# ---------------------------------------------------------------------------

ExecStart=/usr/bin/xinit /root/.xinitrc -- :0 vt1 -keeptty -nolisten tcp

Restart=on-failure
RestartSec=2

TimeoutStartSec=30
TimeoutStopSec=10

[Install]
WantedBy=graphical.target
OMNIX

    # ------------------------------------------------------------------------
    # Service debug
    # ------------------------------------------------------------------------

    cat > "${CHROOT_DIR}/etc/systemd/system/omni-debug.service" <<'OMNIDEBUG'
[Unit]
Description=Omni Console - collecte des informations de demarrage
After=local-fs.target

[Service]
Type=oneshot

ExecStart=/bin/sh -c '\
mkdir -p /var/log/omni; \
{ \
echo "=================================================="; \
echo "OMNI BOOT DEBUG"; \
date; \
echo "=================================================="; \
echo; \
echo "--- kernel ---"; \
cat /proc/cmdline; \
echo; \
echo "--- systemd failed ---"; \
systemctl --failed --no-pager || true; \
echo; \
echo "--- omni-x status ---"; \
systemctl status omni-x.service --no-pager || true; \
echo; \
echo "--- journal omni-x ---"; \
journalctl -u omni-x.service --no-pager || true; \
echo; \
echo "--- X log ---"; \
cat /var/log/Xorg.0.log 2>/dev/null || true; \
echo; \
echo "--- xinit log ---"; \
cat /var/log/omni-xinit.log 2>/dev/null || true; \
} > /var/log/omni/boot.log 2>&1'

RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
OMNIDEBUG

    run_in_chroot \
        "systemctl daemon-reload" \
        >>"${LOG_FILE}" 2>&1 || true

    run_in_chroot \
        "systemctl enable omni-x.service" \
        >>"${LOG_FILE}" 2>&1 || {
            log_err "Impossible d'activer omni-x.service."
            return 1
        }

    run_in_chroot \
        "systemctl enable omni-debug.service" \
        >>"${LOG_FILE}" 2>&1 || {
            log_err "Impossible d'activer omni-debug.service."
            return 1
        }

    run_in_chroot \
        "systemctl set-default graphical.target" \
        >>"${LOG_FILE}" 2>&1 || {
            log_err "Impossible de definir graphical.target."
            return 1
        }

    # ------------------------------------------------------------------------
    # Xwrapper
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/X11"

    cat > "${CHROOT_DIR}/etc/X11/Xwrapper.config" <<'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP

    # ------------------------------------------------------------------------
    # Clavier
    #
    # On conserve une configuration XKB de base.
    # La gestion plus intelligente du clavier utilisateur pourra etre faite
    # ensuite au niveau de l'interface.
    # ------------------------------------------------------------------------

    cat > "${CHROOT_DIR}/etc/default/keyboard" <<'KBD'
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
KBD

    # ------------------------------------------------------------------------
    # Journal systemd persistant
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/var/log/journal"

    # ------------------------------------------------------------------------
    # Casper
    # ------------------------------------------------------------------------

    for f in \
        30accessibility \
        24preseed \
        15autologin \
        34disable_kde_services \
        40install-ubiquity \
        41apt_cdrom \
        25adduser
    do
        if [[ -f "${CHROOT_DIR}/usr/share/initramfs-tools/scripts/casper-bottom/${f}" ]]; then
            chmod -x \
                "${CHROOT_DIR}/usr/share/initramfs-tools/scripts/casper-bottom/${f}" \
                2>/dev/null || true
        fi
    done

    mkdir -p \
        "${CHROOT_DIR}/var/crash" \
        "${CHROOT_DIR}/etc/xdg/autostart"

    run_in_chroot \
        "systemctl mask casper-md5check.service casper-md5check.path console-setup.service keyboard-setup.service 2>/dev/null || true" \
        >>"${LOG_FILE}" 2>&1 || true

    # ------------------------------------------------------------------------
    # Plymouth
    # ------------------------------------------------------------------------

    log_info "Configuration de Plymouth."

    if [[ ! -d "${PLYMOUTH_THEME_SRC}" ]]; then
        log_err "Repertoire Plymouth introuvable : ${PLYMOUTH_THEME_SRC}"
        return 1
    fi

    if [[ ! -f "${PLYMOUTH_THEME_SRC}/omni.plymouth" ]]; then
        log_err "Fichier omni.plymouth absent."
        return 1
    fi

    if [[ ! -f "${PLYMOUTH_THEME_SRC}/omni.script" ]]; then
        log_err "Fichier omni.script absent."
        return 1
    fi

    if ! grep -Eq \
        '^[[:space:]]*ModuleName[[:space:]]*=[[:space:]]*script[[:space:]]*$' \
        "${PLYMOUTH_THEME_SRC}/omni.plymouth"; then

        log_err "omni.plymouth ne declare pas ModuleName=script."
        return 1
    fi

    rm -rf "${PLYMOUTH_THEME_DST}"
    mkdir -p "${PLYMOUTH_THEME_DST}"

    cp -a \
        "${PLYMOUTH_THEME_SRC}/." \
        "${PLYMOUTH_THEME_DST}/" \
        || {
            log_err "Copie du theme Plymouth echouee."
            return 1
        }

    if [[ ! -f "${PLYMOUTH_THEME_DST}/omni.plymouth" ||
          ! -f "${PLYMOUTH_THEME_DST}/omni.script" ]]; then

        log_err "Theme Plymouth incomplet dans le chroot."
        return 1
    fi

    # ------------------------------------------------------------------------
    # Theme actif
    # ------------------------------------------------------------------------

    run_in_chroot \
        "update-alternatives \
            --install \
            /usr/share/plymouth/themes/default.plymouth \
            default.plymouth \
            /usr/share/plymouth/themes/omni/omni.plymouth \
            200" \
        >>"${LOG_FILE}" 2>&1 \
        || {
            log_err "Enregistrement du theme Plymouth impossible."
            return 1
        }

    run_in_chroot \
        "update-alternatives \
            --set \
            default.plymouth \
            /usr/share/plymouth/themes/omni/omni.plymouth" \
        >>"${LOG_FILE}" 2>&1 \
        || {
            log_err "Selection du theme Plymouth impossible."
            return 1
        }

    local theme_selected

    theme_selected="$(
        run_in_chroot \
            "readlink -f /usr/share/plymouth/themes/default.plymouth" \
            2>/dev/null ||
            true
    )"

    if [[ "${theme_selected}" != "/usr/share/plymouth/themes/omni/omni.plymouth" ]]; then
        log_err "Theme Plymouth actif inattendu : ${theme_selected}"
        return 1
    fi

    log_ok "Theme Plymouth actif : Omni."

    mkdir -p "${CHROOT_DIR}/etc/plymouth"

    cat > "${CHROOT_DIR}/etc/plymouth/plymouthd.conf" <<'PLYMOUTHD'
[Daemon]
Theme=omni
ShowDelay=0
DeviceTimeout=8
PLYMOUTHD

    # ------------------------------------------------------------------------
    # Initramfs
    # ------------------------------------------------------------------------

    log_info "Reconstruction de l'initramfs avec Plymouth."

    local have_initrd=0

    if compgen -G "${CHROOT_DIR}/boot/initrd.img-*" >/dev/null 2>&1; then
        have_initrd=1
    fi

    if (( have_initrd == 0 )); then

        if ! run_in_chroot \
            "update-initramfs -c -k all" \
            >>"${LOG_FILE}" 2>&1; then

            log_err "Creation de l'initramfs echouee."
            return 1
        fi
    else

        if ! run_in_chroot \
            "update-initramfs -u -k all" \
            >>"${LOG_FILE}" 2>&1; then

            log_err "Mise a jour de l'initramfs echouee."
            return 1
        fi
    fi

    # ------------------------------------------------------------------------
    # Verification initramfs
    # ------------------------------------------------------------------------

    local initrd_file

    initrd_file="$(
        find "${CHROOT_DIR}/boot" \
            -maxdepth 1 \
            -type f \
            -name 'initrd.img-*' \
            -printf '%p\n' |
        sort -V |
        tail -1
    )"

    if [[ -z "${initrd_file}" || ! -f "${initrd_file}" ]]; then
        log_err "Aucun initramfs trouve apres reconstruction."
        return 1
    fi

    log_info "Verification de l'initramfs : ${initrd_file}"

    local initrd_listing
    initrd_listing="$(lsinitramfs "${initrd_file}")"

    for required in \
        "usr/share/plymouth/themes/default.plymouth" \
        "usr/share/plymouth/themes/omni/omni.plymouth" \
        "usr/share/plymouth/themes/omni/omni.script" \
        "usr/lib/x86_64-linux-gnu/plymouth/script.so"
    do
        if ! grep -F "${required}" <<<"${initrd_listing}" >/dev/null; then
            log_err "Element absent de l'initramfs : ${required}"
            return 1
        fi
    done

    if grep -F \
        "usr/lib/x86_64-linux-gnu/plymouth/renderers/drm.so" \
        <<<"${initrd_listing}" >/dev/null; then

        log_ok "Renderer DRM Plymouth present."
    else
        log_warn "Renderer DRM Plymouth absent de l'initramfs."
    fi

    local png
    local png_rel

    while IFS= read -r -d '' png; do
        png_rel="${png#${PLYMOUTH_THEME_SRC}/}"

        if ! grep -F \
            "usr/share/plymouth/themes/omni/${png_rel}" \
            <<<"${initrd_listing}" >/dev/null; then

            log_err "PNG du theme absent de l'initramfs : ${png_rel}"
            return 1
        fi
    done < <(find "${PLYMOUTH_THEME_SRC}" -type f -iname '*.png' -print0)

    local initrd_size
    initrd_size="$(du -sh "${initrd_file}" | awk '{print $1}')"

    log_ok "Plymouth + theme Omni presents dans l'initramfs (${initrd_size})."

    log_ok "Etape 5/6 terminee : X + installateur + Plymouth configures."
}

# ============================================================================
# Etape 6 - ISO
# ============================================================================

step_build_iso() {
    log_info "Etape 6/6 : fabrication de l'ISO."

    unmount_all

    # Le build a copie le resolv.conf de la machine hote dans le systeme :
    # on remet le lien normal, sinon la console garde le DNS de l'hote.
    debloquer_services

    rm -f "${CHROOT_DIR}/etc/resolv.conf"
    ln -s ../run/systemd/resolve/stub-resolv.conf "${CHROOT_DIR}/etc/resolv.conf"
    log_ok "resolv.conf rendu au systeme (DNS de la console)."

    safe_rm "${IMAGE_DIR}" || return 1

    mkdir -p \
        "${IMAGE_DIR}/casper" \
        "${IMAGE_DIR}/boot/grub"

    # ------------------------------------------------------------------------
    # SquashFS
    # ------------------------------------------------------------------------

    log_info "Compression du systeme (mksquashfs)."

    # -mem : sans limite, mksquashfs prend toute la memoire disponible et fait
    # ramer la machine d'atelier
    if ! mksquashfs \
        "${CHROOT_DIR}" \
        "${IMAGE_DIR}/casper/filesystem.squashfs" \
        -mem 512M \
        -noappend \
        -no-duplicates \
        -no-recovery \
        -wildcards \
        -e "boot/*" \
        -e "proc/*" \
        -e "sys/*" \
        -e "dev/*" \
        -e "run/*" \
        -e "tmp/*" \
        -e "var/cache/apt/archives/*" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "mksquashfs a echoue."
        return 1
    fi

    printf '%s' \
        "$(du -sx --block-size=1 "${CHROOT_DIR}" | cut -f1)" \
        > "${IMAGE_DIR}/casper/filesystem.size"

    # ------------------------------------------------------------------------
    # Noyau + initrd
    # ------------------------------------------------------------------------

    local kver

    kver="$(
        find "${CHROOT_DIR}/boot" \
            -maxdepth 1 \
            -type f \
            -name 'vmlinuz-*' \
            -printf '%f\n' |
        sed 's/^vmlinuz-//' |
        sort -V |
        tail -1
    )"

    if [[ -z "${kver}" ]]; then
        log_err "Impossible de determiner la version du noyau."
        return 1
    fi

    local kernel_src="${CHROOT_DIR}/boot/vmlinuz-${kver}"
    local initrd_src="${CHROOT_DIR}/boot/initrd.img-${kver}"

    if [[ ! -f "${kernel_src}" ]]; then
        log_err "Noyau absent : ${kernel_src}"
        return 1
    fi

    if [[ ! -f "${initrd_src}" ]]; then
        log_err "Initramfs absent : ${initrd_src}"
        return 1
    fi

    cp \
        "${kernel_src}" \
        "${IMAGE_DIR}/casper/vmlinuz" \
        || {
            log_err "Copie du noyau echouee."
            return 1
        }

    cp \
        "${initrd_src}" \
        "${IMAGE_DIR}/casper/initrd" \
        || {
            log_err "Copie de l'initrd echouee."
            return 1
        }

    if [[ ! -s "${IMAGE_DIR}/casper/vmlinuz" ]]; then
        log_err "ERREUR CRITIQUE : IMAGE_DIR/casper/vmlinuz absent ou vide."
        return 1
    fi

    if [[ ! -s "${IMAGE_DIR}/casper/initrd" ]]; then
        log_err "ERREUR CRITIQUE : IMAGE_DIR/casper/initrd absent ou vide."
        return 1
    fi

    log_ok "Noyau ${kver} copie vers casper/vmlinuz."
    log_ok "Initramfs copie vers casper/initrd."

    # ------------------------------------------------------------------------
    # Verification finale initrd
    # ------------------------------------------------------------------------

    local iso_initrd_listing

    iso_initrd_listing="$(lsinitramfs "${IMAGE_DIR}/casper/initrd")"

    for required in \
        "usr/share/plymouth/themes/omni/omni.plymouth" \
        "usr/share/plymouth/themes/omni/omni.script" \
        "usr/lib/x86_64-linux-gnu/plymouth/script.so"
    do
        if ! grep -F "${required}" <<<"${iso_initrd_listing}" >/dev/null; then
            log_err "Element absent de l'initrd ISO : ${required}"
            return 1
        fi
    done

    log_ok "Verification initrd ISO : theme Omni + renderer presents."

    # ------------------------------------------------------------------------
    # GRUB
    # ------------------------------------------------------------------------

    cat > "${IMAGE_DIR}/boot/grub/grub.cfg" <<'GRUBCFG'
insmod all_video
insmod gfxterm
insmod linux
insmod iso9660
insmod search
insmod search_fs_file

set timeout=1
set default=0

search --no-floppy --file --set=root /casper/vmlinuz

if [ -z "${root}" ]; then
    echo "ERREUR : impossible de trouver /casper/vmlinuz"
    sleep 10
fi

menuentry "Omni Console (live)" {
    linux /casper/vmlinuz boot=casper quiet splash loglevel=0 rd.systemd.show_status=false vt.global_cursor_default=0 console=tty0 ---
    initrd /casper/initrd
}

menuentry "Omni Console (debug serie)" {
    linux /casper/vmlinuz boot=casper splash plymouth:debug console=tty0 console=ttyS0,115200n8 systemd.log_level=info systemd.log_target=console ---
    initrd /casper/initrd
}

menuentry "Omni Console (mode securise)" {
    linux /casper/vmlinuz boot=casper nomodeset console=tty0 ---
    initrd /casper/initrd
}
GRUBCFG

    log_info "Configuration GRUB creee."

    # ------------------------------------------------------------------------
    # Verification arborescence
    # ------------------------------------------------------------------------

    log_info "Verification de l'arborescence ISO."

    local required_iso_file

    for required_iso_file in \
        "${IMAGE_DIR}/casper/vmlinuz" \
        "${IMAGE_DIR}/casper/initrd" \
        "${IMAGE_DIR}/casper/filesystem.squashfs" \
        "${IMAGE_DIR}/casper/filesystem.size" \
        "${IMAGE_DIR}/boot/grub/grub.cfg"
    do
        if [[ ! -f "${required_iso_file}" ]]; then
            log_err "Fichier absent de l'arborescence ISO : ${required_iso_file}"
            return 1
        fi
    done

    log_ok "Arborescence ISO valide avant fabrication."

    # ------------------------------------------------------------------------
    # Construction BIOS + UEFI
    # ------------------------------------------------------------------------

    log_info "Assemblage BIOS + UEFI avec grub-mkrescue."

    safe_rm "${OUTPUT_DIR}/${ISO_NAME}" || return 1

    # -volid : nom du volume de l'ISO, visible au montage et utilise par casper
    if ! grub-mkrescue \
        -o "${OUTPUT_DIR}/${ISO_NAME}" \
        "${IMAGE_DIR}" \
        -- -volid "${ISO_VOLID}" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "grub-mkrescue a echoue."
        return 1
    fi

    # ------------------------------------------------------------------------
    # Verification ISO
    # ------------------------------------------------------------------------

    if [[ ! -f "${OUTPUT_DIR}/${ISO_NAME}" ]]; then
        log_err "ISO non produite."
        return 1
    fi

    if [[ ! -s "${OUTPUT_DIR}/${ISO_NAME}" ]]; then
        log_err "ISO produite mais vide."
        return 1
    fi

    log_info "Verification du contenu reel de l'ISO."

    local verify_ok=1
    local xorriso_check

    xorriso_check="$(
        xorriso \
            -indev "${OUTPUT_DIR}/${ISO_NAME}" \
            -ls /casper/vmlinuz \
            2>>"${LOG_FILE}" ||
        true
    )"

    if grep -Eq 'vmlinuz' <<<"${xorriso_check}"; then
        log_ok "ISO finale contient /casper/vmlinuz."
    else
        log_err "ERREUR CRITIQUE : /casper/vmlinuz absent de l'ISO finale."
        verify_ok=0
    fi

    xorriso_check="$(
        xorriso \
            -indev "${OUTPUT_DIR}/${ISO_NAME}" \
            -ls /casper/initrd \
            2>>"${LOG_FILE}" ||
        true
    )"

    if grep -Eq 'initrd' <<<"${xorriso_check}"; then
        log_ok "ISO finale contient /casper/initrd."
    else
        log_err "ERREUR CRITIQUE : /casper/initrd absent de l'ISO finale."
        verify_ok=0
    fi

    xorriso_check="$(
        xorriso \
            -indev "${OUTPUT_DIR}/${ISO_NAME}" \
            -ls /casper/filesystem.squashfs \
            2>>"${LOG_FILE}" ||
        true
    )"

    if grep -Eq 'filesystem\.squashfs' <<<"${xorriso_check}"; then
        log_ok "ISO finale contient /casper/filesystem.squashfs."
    else
        log_err "ERREUR CRITIQUE : filesystem.squashfs absent de l'ISO finale."
        verify_ok=0
    fi

    xorriso_check="$(
        xorriso \
            -indev "${OUTPUT_DIR}/${ISO_NAME}" \
            -ls /boot/grub/grub.cfg \
            2>>"${LOG_FILE}" ||
        true
    )"

    if grep -Eq 'grub\.cfg' <<<"${xorriso_check}"; then
        log_ok "ISO finale contient /boot/grub/grub.cfg."
    else
        log_err "ERREUR CRITIQUE : /boot/grub/grub.cfg absent de l'ISO finale."
        verify_ok=0
    fi

    if (( verify_ok == 0 )); then
        log_err "Verification du contenu ISO echouee."
        return 1
    fi

    log_ok "Verification du contenu reel de l'ISO terminee avec succes."

    local isotaille
    isotaille="$(du -sh "${OUTPUT_DIR}/${ISO_NAME}" | awk '{print $1}')"

    log_ok "Etape 6/6 terminee : ISO produite (${isotaille})."
    log_info "ISO : ${OUTPUT_DIR}/${ISO_NAME}"

    log_info "Verification xorriso :"

    xorriso \
        -indev "${OUTPUT_DIR}/${ISO_NAME}" \
        -report_el_torito plain \
        >>"${LOG_FILE}" 2>&1 || true

    log_ok "ISO BIOS + UEFI construite avec grub-mkrescue."
}

# ============================================================================
# Mode verification : rien n'est installe ni construit. On demande a apt ce
# qu'il FERAIT, et on verifie que chaque telechargement repond. Quelques
# minutes au lieu d'un build complet.
# ============================================================================

step_verifier() {
    log_info "Verification des dependances (aucune installation)."

    if [[ ! -x "${CHROOT_DIR}/bin/bash" && ! -x "${CHROOT_DIR}/usr/bin/bash" ]]; then
        log_err "Aucun systeme de base : lancer d'abord un build normal."
        return 1
    fi

    step_enter_system || return 1

    local souci=0

    # --- paquets du systeme et de l'emulation ---
    local pkgs
    pkgs="$(printf '%s ' "${OMNI_CORE_PKGS[@]}")"

    log_info "Paquets du systeme et des emulateurs..."

    if run_in_chroot "apt-get install -s -y --no-install-recommends ${pkgs}" > "${LOG_DIR}/verif.log" 2>&1; then
        log_ok "Tous les paquets du systeme sont disponibles."
    else
        log_err "Paquets du systeme : probleme."
        grep -E "^(E:|Note|.*not installable|.*unmet)" "${LOG_DIR}/verif.log" | tail -n 8 |
            while IFS= read -r l; do log_err "    ${l}"; done
        souci=1
    fi

    # --- Steam : depot de Valve + bibliotheques 32 bits ---
    log_info "Steam (depot officiel de Valve)..."

    if run_in_chroot '
        set -e
        export DEBIAN_FRONTEND=noninteractive
        dpkg --add-architecture i386
        curl -fsSL --max-time 60 -o /tmp/steam.gpg https://repo.steampowered.com/steam/archive/stable/steam.gpg
        test -s /tmp/steam.gpg
        cp /tmp/steam.gpg /usr/share/keyrings/steam.gpg
        echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/steam.gpg] https://repo.steampowered.com/steam/ stable steam" \
            > /etc/apt/sources.list.d/omni-verif-steam.list
        apt-get update >/dev/null 2>&1 || true
        apt-get install -s -y --no-install-recommends steam-launcher steam-libs-amd64 steam-libs-i386:i386
        apt-get install -s -y --no-install-recommends \
            libc6:i386 libegl1 libegl1:i386 libgbm1 libgbm1:i386 \
            libgl1 libgl1:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 \
            xdg-desktop-portal xdg-desktop-portal-gtk \
            mesa-vulkan-drivers:i386 libvulkan1:i386
        rm -f /etc/apt/sources.list.d/omni-verif-steam.list
    ' > "${LOG_DIR}/verif-steam.log" 2>&1; then
        log_ok "Steam et ses bibliotheques 32 bits sont disponibles."
    else
        log_err "Steam : probleme."
        tail -n 10 "${LOG_DIR}/verif-steam.log" | while IFS= read -r l; do log_err "    ${l}"; done
        souci=1
    fi

    run_in_chroot "rm -f /etc/apt/sources.list.d/omni-verif-steam.list; apt-get update >/dev/null 2>&1 || true" \
        >>"${LOG_FILE}" 2>&1 || true

    # --- telechargements hors depots ---
    local base_umu="https://github.com/Open-Wine-Components/umu-launcher/releases/download/${UMU_VERSION}"
    local base_proton="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/${PROTON_VERSION}"

    local nom
    local url

    for nom in \
        "umu (python3)|${base_umu}/python3-umu-launcher_${UMU_VERSION}-1_amd64_ubuntu-${UBUNTU_SUITE}.deb" \
        "umu (lanceur)|${base_umu}/umu-launcher_${UMU_VERSION}-1_all_ubuntu-${UBUNTU_SUITE}.deb" \
        "Proton|${base_proton}/${PROTON_VERSION}-x86_64.tar.gz" \
        "xpadneo|https://codeload.github.com/atar-axis/xpadneo/tar.gz/refs/tags/v${XPADNEO_VERSION}" \
        "joycond|https://codeload.github.com/DanielOgorchock/joycond/tar.gz/refs/heads/${JOYCOND_REF}" \
        "installateur Epic|https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi" \
        "installateur EA|https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/EAappInstaller.exe" \
        "installateur Ubisoft|https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe"
    do
        url="${nom#*|}"
        nom="${nom%%|*}"

        # depuis le systeme en construction : c'est lui qui a curl, et c'est lui
        # qui telechargera pour de vrai pendant le build
        local code
        code="$(run_in_chroot "curl -sIL --max-time 45 -o /dev/null -w '%{http_code}' '${url}'" 2>/dev/null || echo 000)"
        code="${code##*$'\n'}"

        if [[ "${code}" == "200" || "${code}" == "302" ]]; then
            log_ok "${nom} : disponible."
        else
            log_err "${nom} : injoignable (code ${code})."
            log_err "    ${url}"
            souci=1
        fi
    done

    unmount_all

    if (( souci == 0 )); then
        log_ok "Verification terminee : tout est disponible, le build peut etre lance."
    else
        log_err "Verification terminee : corriger les points ci-dessus avant de lancer un build."
    fi

    return "${souci}"
}

# ============================================================================
# Main
# ============================================================================

main() {
    require_root "$@"

    prepare_workspace

    trap _on_exit EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    log_info "=== Debut du build Omni Console ==="
    log_info "Mode nettoyage : ${CLEAN_MODE}"

    if [[ "${CLEAN_MODE}" == "verifier" ]]; then
        step_verifier || exit 1
        exit 0
    fi

    clean_previous || exit 1
    step_check_dependencies || exit 1
    step_open_base_iso || exit 1
    step_enter_system || exit 1
    step_install_omni || exit 1
    step_install_jeux || exit 1
    step_apply_settings || exit 1
    step_build_iso || exit 1

    log_ok "=== Build Omni Console termine ==="
    log_info "Journal complet : ${LOG_FILE}"
}

main "$@"
