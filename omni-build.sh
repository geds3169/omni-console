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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
readonly PROJECT_ROOT="${SCRIPT_DIR}"

# OMNI_WORK_ROOT : surcharge pour les tests (jamais utile en production)
readonly WORK_ROOT="${OMNI_WORK_ROOT:-/root/omni-build}"
readonly CHROOT_DIR="${WORK_ROOT}/chroot"
readonly IMAGE_DIR="${WORK_ROOT}/image"
readonly OUTPUT_DIR="${WORK_ROOT}/output"
readonly LOG_DIR="${WORK_ROOT}/logs"
readonly LOG_FILE="${LOG_DIR}/omni-build.log"
# Conserves d'un build a l'autre : evitent de retelecharger 1,4 Go de paquets
# et de refaire le systeme de base a chaque fois.
readonly CACHE_APT="${WORK_ROOT}/cache-apt"
readonly CACHE_BASE="${WORK_ROOT}/base-systeme.tgz"
# Gros telechargements exterieurs (Proton, installeurs) : conserves d'un build
# a l'autre. Une coupure reseau ne doit plus coûter 500 Mo et un build entier.
readonly CACHE_GROS="${WORK_ROOT}/cache-telechargements"

readonly ISO_NAME="omni-console.iso"
readonly ISO_VOLID="OMNI_CONSOLE"

readonly UBUNTU_SUITE="noble"
readonly UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu/"

# Dossier du theme Plymouth : trouve par trouver_theme_plymouth (omni-plymouth-theme/ ou plymouth/)
PLYMOUTH_THEME_SRC=""
readonly PLYMOUTH_THEME_DST="${CHROOT_DIR}/usr/share/plymouth/themes/omni"

readonly INSTALLER_SRC="${PROJECT_ROOT}/omni-installer.py"
readonly CONSOLE_SRC="${PROJECT_ROOT}/omni-console.py"

# Composants absents des depots Ubuntu : recuperes a leur source officielle,
# en version figee (build reproductible). Changer la version ici suffit.
readonly UMU_VERSION="1.4.4"
readonly PROTON_VERSION="GE-Proton11-7"
# Ubisoft Connect ne s'installe pas toujours avec le Proton le plus recent :
# version plus ancienne, telechargee a la demande (intention proton-ubisoft).
readonly UBISOFT_PROTON_VERSION="GE-Proton10-10"

# Console serie dans l'image (1 = oui). A mettre a 0 pour une image de diffusion.
CONSOLE_SERIE="${CONSOLE_SERIE:-1}"

# Version de l'image : date du build + debut de l'empreinte de l'interface.
# Lue par la console (affichee dans le journal) et par omni-selftest.
IMAGE_VERSION="$(date +%Y-%m-%d)-$(md5sum "${SCRIPT_DIR}/omni-console.py" 2>/dev/null | cut -c1-6)"

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
  # Langues generees dans l'image, clavier de la console texte
  locales kbd console-setup
  # Manettes : Bluetooth (les regles udev des manettes viennent avec le Steam officiel)
  bluez
  # Jeux : Vulkan (indispensable a Proton) + emulation
  mesa-vulkan-drivers libvulkan1
  retroarch libretro-nestopia libretro-snes9x libretro-mgba libretro-genesisplusgx
  libretro-beetle-psx libretro-gambatte
  # Telechargements (installeurs officiels des launchers, Proton)
  curl ca-certificates
  # Accelere l'installation des paquets pendant la construction
  eatmydata
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

# Toutes les etapes lourdes (Steam, Proton, pilotes) suivent le meme schema :
# un script depose dans le chroot, execute avec un delai maximum, journalise
# a part, et dont l'echec affiche les dernieres lignes utiles. Une seule
# fonction pour tout le monde : une correction profite a toutes les etapes.
#
#   etape_chroot <nom> <delai_secondes> <<'FIN'
#       ... commandes executees DANS le systeme en construction ...
#   FIN
#
# Retour : 0 si l'etape a reussi, 1 sinon. Journal : ${LOG_DIR}/<nom>.log
etape_chroot() {
    local nom="$1"
    local delai="${2:-900}"
    local script="${CHROOT_DIR}/usr/local/sbin/omni-etape-${nom}"
    local journal="${LOG_DIR}/${nom}.log"

    mkdir -p "${CHROOT_DIR}/usr/local/sbin"
    {
        cat <<'PREAMBULE'
#!/bin/bash
# Preambule commun a toutes les etapes executees dans le systeme en
# construction. Il fournit deux outils, pour ne pas reecrire la meme logique
# dans chaque etape :
#   omni_maj                 : met a jour les listes de paquets, en retentant
#                              si un miroir est en cours de synchronisation
#   omni_installer <paquets> : installe, en retentant apres un rafraichissement
#                              si un paquet a disparu du serveur entre-temps
set -e
export DEBIAN_FRONTEND=noninteractive
export DEBCONF_NONINTERACTIVE_SEEN=true

APTOPT="-o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=2"
# aucune question sur les fichiers de configuration, on garde ceux en place
APTOPT="${APTOPT} -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
APTOPT="${APTOPT} -o Dpkg::Use-Pty=0 -o DPkg::Lock::Timeout=60"

# eatmydata desactive les ecritures forcees sur disque : l'installation des
# paquets est nettement plus rapide, et le resultat est identique puisque
# l'image est ensuite compressee telle quelle.
if command -v eatmydata >/dev/null 2>&1; then
    APT="eatmydata apt-get"
else
    APT="apt-get"
fi

omni_maj() {
    local essai
    for essai in 1 2 3; do
        if timeout 300 ${APT} ${APTOPT} update; then
            return 0
        fi
        echo "== listes incompletes (essai ${essai}/3), nouvel essai dans 20 s"
        sleep 20
    done
    echo "== listes toujours incompletes : on continue avec ce qu'on a"
    return 0
}

omni_installer() {
    local essai
    for essai in 1 2 3; do
        if timeout 900 ${APT} ${APTOPT} install -y --no-install-recommends --fix-missing "$@"; then
            return 0
        fi
        echo "== installation ratee (essai ${essai}/3) : remise d'aplomb puis nouvel essai"
        # uniquement les processus lances par CETTE etape : le chroot partage la liste
        # des processus avec la machine d'atelier, un pkill par nom la viserait aussi
        pkill -9 -P $$ 2>/dev/null || true
        sleep 2
        rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock
        dpkg --configure -a 2>&1 | tail -3
        omni_maj
    done
    return 1
}
PREAMBULE
        cat
    } > "${script}"
    chmod +x "${script}"

    local code=0
    run_in_chroot "timeout ${delai} /usr/local/sbin/omni-etape-${nom}" > "${journal}" 2>&1 || code=$?
    cat "${journal}" >> "${LOG_FILE}"
    rm -f "${script}"

    if (( code == 0 )); then
        return 0
    fi

    if (( code == 124 )); then
        log_warn "Etape ${nom} : delai de ${delai} s depasse."
    fi

    log_warn "Etape ${nom} : echec. Dernieres lignes utiles :"
    grep -vE "^(Get:|Hit:|W: Target|Reading|Building|Fetched|Selecting|Preparing|Unpacking|Setting up)" \
        "${journal}" | tail -n 10 | while IFS= read -r l; do log_warn "    ${l}"; done
    log_warn "Journal complet : ${journal}"
    return 1
}

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

    # L'archive du systeme de base est conservee : les builds suivants ne
    # retelechargent plus les 200 Mo, meme en --clean-all.
    if [[ ! -f "${CACHE_BASE}" ]]; then
        log_info "Telechargement du systeme minimal (conserve pour les prochains builds)."

        if ! debootstrap \
            --arch=amd64 \
            --variant=minbase \
            --components=main,restricted,universe,multiverse \
            --make-tarball="${CACHE_BASE}" \
            "${UBUNTU_SUITE}" \
            "${CHROOT_DIR}.tmp" \
            "${UBUNTU_MIRROR}" \
            >>"${LOG_FILE}" 2>&1; then

            log_err "debootstrap a echoue."
            rm -rf "${CHROOT_DIR}.tmp"
            return 1
        fi
        rm -rf "${CHROOT_DIR}.tmp"
    else
        log_info "Systeme minimal repris de l'archive conservee."
    fi

    if ! debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --components=main,restricted,universe,multiverse \
        --unpack-tarball="${CACHE_BASE}" \
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
    # Les paquets deja telecharges sont repris d'un build a l'autre
    mkdir -p "${CACHE_APT}" "${CHROOT_DIR}/var/cache/apt/archives"
    mount_bind "${CACHE_APT}" "${CHROOT_DIR}/var/cache/apt/archives" || return 1
    mkdir -p "${CACHE_GROS}" "${CHROOT_DIR}/var/cache/omni"
    mount_bind "${CACHE_GROS}" "${CHROOT_DIR}/var/cache/omni" || return 1
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
            "command -v eatmydata >/dev/null && E=eatmydata || E=; \${E} apt-get -o Acquire::Retries=3 \
             -o Dpkg::Options::=--force-confold -o Dpkg::Use-Pty=0 \
             install -y --no-install-recommends --fix-missing ${pkgs}" \
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
    log_info "Etape 4b/6 : jeux, moteur Proton et pilotes de manettes."

    local kver
    kver="$(
        find "${CHROOT_DIR}/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' |
        sed 's/^vmlinuz-//' | sort -V | tail -1
    )"

    local bilan_ok=()
    local bilan_ko=()
    # Sans ces trois-la, la console ne peut ni installer ni lancer de jeu
    # Windows : leur echec arrete le build plutot que de produire une ISO
    # inutilisable qui ne se decouvre qu'au salon.
    local manque_obligatoire=()

    neutralize_chroot_cmds >>"${LOG_FILE}" 2>&1 || true

    # Le guichet et omni-poser-proton servent des maintenant (umu, Proton)
    ecrire_guichet_plateformes || return 1

    # ------------------------------------------------------------------------
    # Steam : client officiel de Valve (le paquet d'Ubuntu ouvre une fenetre en
    # anglais et reclame un mot de passe administrateur), plus les bibliotheques
    # 32 bits qu'il reclame a son premier lancement.
    # ------------------------------------------------------------------------

    log_info "Steam : client officiel de Valve + bibliotheques 32 bits."

    # Les paquets Steam d'Ubuntu sont interdits une fois pour toutes : ils
    # ramenent l'installateur Debian et entrent en conflit avec celui de Valve.
    mkdir -p "${CHROOT_DIR}/etc/apt/preferences.d"
    cat > "${CHROOT_DIR}/etc/apt/preferences.d/omni-steam" <<'PINSTEAM'
# Omni Console : Steam uniquement depuis le depot officiel de Valve
Package: steam steam-installer steam-devices steam-libs steam-libs-i386 steam-libs-amd64 steam-launcher
Pin: origin archive.ubuntu.com
Pin-Priority: -1
PINSTEAM

    if etape_chroot steam 2700 <<'FIN'
dpkg --configure -a || true
apt-get purge -y steam-installer steam-devices steam-libs steam-libs:i386 >/dev/null 2>&1 || true

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

omni_maj
echo "== lot 1 : pile graphique 32 bits"
omni_installer libc6:i386 libegl1 libegl1:i386 libgbm1 libgbm1:i386 \
    libgl1 libgl1:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 \
    mesa-vulkan-drivers:i386 libvulkan1:i386

echo "== lot 2 : portails de bureau"
omni_installer xdg-desktop-portal xdg-desktop-portal-gtk

echo "== lot 3 : bibliotheques attendues par Wine et Proton"
omni_installer libfreetype6 libfreetype6:i386 libfontconfig1 libfontconfig1:i386 \
    libgnutls30t64 libgnutls30t64:i386 libpng16-16t64 libpng16-16t64:i386 \
    libxml2 libxml2:i386 libxslt1.1 libxslt1.1:i386 \
    libx11-6:i386 libxext6:i386 libxrandr2:i386 libxi6:i386 \
    libxcursor1:i386 libxcomposite1:i386 libxfixes3:i386 \
    libdbus-1-3:i386 libpulse0:i386 libasound2t64:i386 \
    libusb-1.0-0:i386 libudev1:i386 libsdl2-2.0-0:i386 \
    libgssapi-krb5-2:i386 libkrb5-3:i386 libcups2t64:i386 \
    libodbc2:i386 libncurses6:i386 libtiff6:i386 libosmesa6:i386 \
    fonts-liberation fonts-dejavu

echo "== lot 4 : Steam et ses bibliotheques (depot de Valve)"
omni_installer steam-launcher
omni_installer steam-libs-amd64
omni_installer steam-libs-i386:i386

echo "== nettoyage : le depot est desormais fourni par le paquet de Valve"
rm -f /etc/apt/sources.list.d/omni-steam.list
omni_maj

echo "== controles"
dpkg -s steam-launcher >/dev/null
if dpkg -s steam-installer >/dev/null 2>&1; then
    echo "ERREUR : steam-installer (Debian) est toujours present"
    exit 1
fi
command -v steam
echo "== Steam installe"
FIN
    then
        bilan_ok+=("Steam")
    else
        manque_obligatoire+=("Steam")
        bilan_ko+=("Steam")
    fi

    # ------------------------------------------------------------------------
    # umu-launcher : fait tourner les launchers Windows sous Proton, hors de
    # Steam, avec son propre environnement d'execution complet.
    # ------------------------------------------------------------------------

    log_info "umu-launcher ${UMU_VERSION} (Proton hors Steam)."

    if etape_chroot umu 900 <<'FIN'
/usr/local/sbin/omni-poser-proton umu
FIN
    then
        bilan_ok+=("umu-launcher")
    else
        manque_obligatoire+=("umu-launcher")
        bilan_ko+=("umu-launcher")
    fi

    # ------------------------------------------------------------------------
    # Proton : hors de /usr, que le conteneur de Proton refuse (il le reserve
    # a son propre systeme). GE-Proton est librement redistribuable.
    # Meme script que celui que la console utilise pour se reparer.
    # ------------------------------------------------------------------------

    if [[ "${PROTON_EMBARQUE}" == "1" ]]; then
        log_info "Proton ${PROTON_VERSION} embarque dans l'image."

        if etape_chroot proton 3000 <<'FIN'
/usr/local/sbin/omni-poser-proton defaut
FIN
        then
            bilan_ok+=("Proton ${PROTON_VERSION}")
            log_ok "Moteur Proton complet : umu + ${PROTON_VERSION}."
        else
            manque_obligatoire+=("Proton")
            rm -rf "${CHROOT_DIR}/opt/omni/proton"
            bilan_ko+=("Proton")
        fi
    fi

    # ------------------------------------------------------------------------
    # Pilotes de manettes : confort, pas vitaux. Leur echec n'arrete rien.
    # ------------------------------------------------------------------------

    log_info "xpadneo ${XPADNEO_VERSION} pour le noyau ${kver} (manettes Xbox en Bluetooth)."

    if [[ -n "${kver}" ]] && etape_chroot xpadneo 900 <<FIN
v=v${XPADNEO_VERSION}
rm -rf /tmp/xpadneo && mkdir /tmp/xpadneo && cd /tmp/xpadneo
curl -fsSL --max-time 300 --retry 2 https://codeload.github.com/atar-axis/xpadneo/tar.gz/refs/tags/\${v} | tar xz --strip-components=1
rm -rf /usr/src/hid-xpadneo-\${v}
cp -r hid-xpadneo /usr/src/hid-xpadneo-\${v}
sed "s/@DO_NOT_CHANGE@/\${v}/g" hid-xpadneo/dkms.conf.in > /usr/src/hid-xpadneo-\${v}/dkms.conf
dkms status -m hid-xpadneo -v \${v} | grep -q hid-xpadneo || dkms add -m hid-xpadneo -v \${v}
dkms build -m hid-xpadneo -v \${v} -k ${kver}
dkms install -m hid-xpadneo -v \${v} -k ${kver}
rm -rf /tmp/xpadneo
FIN
    then
        bilan_ok+=("xpadneo")
    else
        bilan_ko+=("xpadneo")
    fi

    log_info "joycond (Joy-Con)."

    if etape_chroot joycond 900 <<FIN
rm -rf /tmp/joycond && mkdir /tmp/joycond && cd /tmp/joycond
curl -fsSL --max-time 300 --retry 2 https://codeload.github.com/DanielOgorchock/joycond/tar.gz/refs/heads/${JOYCOND_REF} | tar xz --strip-components=1
sed -i 's/-Werror//' CMakeLists.txt
cmake .
make -j"\$(nproc)"
make install
systemctl enable joycond.service
rm -rf /tmp/joycond
FIN
    then
        bilan_ok+=("joycond")
    else
        bilan_ko+=("joycond")
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
# Etape 5 - configuration (chaque domaine a sa fonction)
# ============================================================================

# ============================================================================
# Ressources du projet : un fichier absent est une erreur, jamais un oubli
# ============================================================================

# copier_obligatoire <source> <destination> <mode>
# Copie un fichier du projet dans l'image. Une source manquante arrete le build
# avec un message clair : mieux vaut un build qui echoue qu'une ISO sans interface.
copier_obligatoire() {
    local src="$1" dst="$2" mode="$3"

    if [[ ! -f "${src}" ]]; then
        log_err "Fichier du projet introuvable : ${src}"
        return 1
    fi

    if ! install -D -m "${mode}" -- "${src}" "${dst}"; then
        log_err "Copie impossible : ${src} -> ${dst}"
        return 1
    fi
}

# Le theme Plymouth se trouve dans omni-plymouth-theme/ (nom historique) ou
# plymouth/ (nom dans l'archive du projet). Renseigne PLYMOUTH_THEME_SRC.
trouver_theme_plymouth() {
    local d

    for d in "${PROJECT_ROOT}/omni-plymouth-theme" "${PROJECT_ROOT}/plymouth"; do
        if [[ -f "${d}/omni.plymouth" && -f "${d}/omni.script" ]]; then
            PLYMOUTH_THEME_SRC="${d}"
            return 0
        fi
    done

    log_err "Theme Plymouth introuvable : ni omni-plymouth-theme/ ni plymouth/ dans ${PROJECT_ROOT}"
    return 1
}

# Copie dans l'image tout ce que le projet fournit : installateur, interface,
# cartes, sons d'interface, musique. Chaque destination est UNIQUE et partagee
# par le build et par les programmes (voir DOSSIERS_MUSIQUE dans omni-installer.py).
installer_ressources_projet() {
    local partage="${CHROOT_DIR}/usr/local/share/omni"
    local ui="${partage}/ui"
    local f n

    log_info "Copie des ressources du projet."

    copier_obligatoire "${INSTALLER_SRC}" "${CHROOT_DIR}/usr/local/bin/omni-installer" 755 || return 1
    copier_obligatoire "${CONSOLE_SRC}" "${ui}/omni-console.py" 644 || return 1

    n=0
    for f in "${PROJECT_ROOT}"/cartes/*.jpg; do
        [[ -f "${f}" ]] || continue
        install -D -m 644 -- "${f}" "${ui}/cartes/$(basename -- "${f}")" || return 1
        n=$(( n + 1 ))
    done
    if (( n == 0 )); then
        log_err "Aucune planche de cartes dans ${PROJECT_ROOT}/cartes/"
        return 1
    fi

    # Sons d'interface (omni-hover, omni-select, omni-valid) : une seule copie,
    # l'interface les trouve par le lien ui/sons.
    n=0
    for f in "${PROJECT_ROOT}"/sons/omni-*.ogg; do
        [[ -f "${f}" ]] || continue
        install -D -m 644 -- "${f}" "${partage}/sons/$(basename -- "${f}")" || return 1
        n=$(( n + 1 ))
    done
    if (( n == 0 )); then
        log_warn "Aucun son d'interface dans ${PROJECT_ROOT}/sons/ : l'interface sera muette."
    fi
    ln -sfn ../sons "${ui}/sons"

    # Musique d'installation : sons/ (emplacement voulu), repli sur la racine
    # du projet (ancien emplacement). Tout fichier audio qui n'est pas un son
    # d'interface est de la musique.
    n=0
    for f in "${PROJECT_ROOT}"/sons/*.ogg "${PROJECT_ROOT}"/sons/*.mp3 \
             "${PROJECT_ROOT}"/*.ogg "${PROJECT_ROOT}"/*.mp3; do
        [[ -f "${f}" ]] || continue
        [[ "$(basename -- "${f}")" == omni-* ]] && continue
        install -D -m 644 -- "${f}" "${partage}/musique/$(basename -- "${f}")" || return 1
        n=$(( n + 1 ))
    done
    if (( n == 0 )); then
        log_warn "Aucune musique trouvee (attendue : ${PROJECT_ROOT}/sons/*.ogg)."
    else
        log_ok "Musique : ${n} fichier(s) dans /usr/local/share/omni/musique."
    fi

    log_ok "Ressources du projet copiees."
}

# Options de cette image, lues par l'installateur et par omni-selftest.
ecrire_options_image() {
    mkdir -p "${CHROOT_DIR}/usr/local/share/omni"

    cat > "${CHROOT_DIR}/usr/local/share/omni/options-image.conf" <<OPTIONS
# Options de cette image, une CLE=VALEUR par ligne (lues par omni-installer.py).
# Fixees par omni-build.sh : ne pas modifier a la main dans une image finie.
CONSOLE_SERIE=${CONSOLE_SERIE}
IMAGE_VERSION=${IMAGE_VERSION}
OPTIONS

    echo "${IMAGE_VERSION}" > "${CHROOT_DIR}/etc/omni-version"
    log_ok "Options de l'image ecrites (version ${IMAGE_VERSION})."
}

# Console serie : indispensable pour diagnostiquer une console dont on ne peut
# pas ouvrir de terminal. Le lien du getty vit dans l'image, donc il est copie
# a l'installation ; l'installateur le retire si CONSOLE_SERIE != 1.
configurer_console_serie() {
    if [[ "${CONSOLE_SERIE}" != "1" ]]; then
        log_info "Console serie desactivee (CONSOLE_SERIE=${CONSOLE_SERIE})."
        return 0
    fi

    mkdir -p "${CHROOT_DIR}/etc/systemd/system/getty.target.wants"
    ln -sf /usr/lib/systemd/system/serial-getty@.service \
        "${CHROOT_DIR}/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"

    log_ok "Console serie active (ttyS0, 115200)."
}

# Locales des quatre langues de l'installateur : sans elles, chaque lancement
# de Proton regenere en_US.UTF-8 a chaud (quelques secondes perdues).
generer_locales() {
    log_info "Generation des locales (fr, en, de, pt)."

    etape_chroot locales 300 <<'FIN'
locale-gen fr_FR.UTF-8 en_US.UTF-8 de_DE.UTF-8 pt_PT.UTF-8
locale -a | grep -qi '^fr_FR.utf8'
locale -a | grep -qi '^en_US.utf8'
FIN
}

# Theme du menu de demarrage (affiche seulement sur demande : Maj ou Echap).
# La police est convertie au format de grub ; sans elle, le theme est retire
# et le menu reste lisible, sans habillage.
configurer_theme_grub() {
    local dir="${CHROOT_DIR}/boot/grub/themes/omni"

    mkdir -p "${dir}"

    cat > "${dir}/theme.txt" <<'GRUBTHEME'
# Omni Console : menu de demarrage, aux couleurs de la console
desktop-color: "#0d0221"
title-text: "OMNI CONSOLE"
title-font: "DejaVu Sans Regular 28"
title-color: "#ff2e97"
message-font: "DejaVu Sans Regular 28"
message-color: "#f5f5ff"
terminal-font: "DejaVu Sans Regular 28"

+ boot_menu {
    left = 20%
    top = 30%
    width = 60%
    height = 40%
    item_font = "DejaVu Sans Regular 28"
    item_color = "#2de2e6"
    selected_item_font = "DejaVu Sans Regular 28"
    selected_item_color = "#ffc53d"
    item_height = 44
    item_spacing = 10
}
GRUBTHEME

    if ! run_in_chroot "grub-mkfont -s 28 -o /boot/grub/themes/omni/dejavu28.pf2 /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" \
        >>"${LOG_FILE}" 2>&1; then
        log_warn "Police du menu de demarrage non generee : menu sans habillage."
        rm -rf "${dir}"
        return 0
    fi

    log_ok "Theme du menu de demarrage pose."
}

# Guichet a intentions et moteur Proton. Ecrits UNE fois ici : le build et la
# console (qui peut se reparer seule) utilisent le meme omni-poser-proton.
ecrire_guichet_plateformes() {
    local sbin="${CHROOT_DIR}/usr/local/sbin"

    mkdir -p "${sbin}" "${CHROOT_DIR}/etc/sudoers.d"

    cat > "${sbin}/omni-plateforme" <<'OMNIPLAT'
#!/bin/sh
# Omni Console - service d'installation des plateformes (intentions uniquement)
set -u
export DEBIAN_FRONTEND=noninteractive

case "${1:-}" in
    proton)
        exec /usr/local/sbin/omni-poser-proton defaut ;;
    proton-ubisoft)
        exec /usr/local/sbin/omni-poser-proton ubisoft ;;
    donnees)
        # Redonne au joueur son dossier de donnees. Utile sur une console
        # installee avant la correction du montage pendant l'installation.
        [ -d /omni-data ] || exit 1
        chown -R omni:omni /omni-data
        chmod 755 /omni-data
        for sous in jeux jeux/gog roms saves profils cache compat; do
            install -d -o omni -g omni "/omni-data/${sous}"
        done
        exit 0 ;;
    jeux-autorisations)
        # Retablit l'isolation dont Steam et Proton ont besoin, et affiche les
        # valeurs obtenues : un reglage absent du noyau n'est pas une erreur.
        for reglage in kernel.apparmor_restrict_unprivileged_userns=0 \
                       kernel.unprivileged_userns_clone=1 \
                       user.max_user_namespaces=28633; do
            sysctl -w "${reglage}" 2>/dev/null || true
        done
        # Les profils AppArmor d'Ubuntu interdisent cette isolation meme quand
        # le reglage systeme est ouvert : on les decharge aussi.
        mkdir -p /etc/apparmor.d/disable
        for nom in unprivileged_userns bwrap-userns-restrict steam steam-runtime bwrap; do
            profil="/etc/apparmor.d/${nom}"
            [ -e "${profil}" ] || continue
            ln -sf "${profil}" "/etc/apparmor.d/disable/${nom}"
            apparmor_parser -R "${profil}" 2>/dev/null || true
            echo "profil neutralise : ${nom}"
        done
        sysctl -a 2>/dev/null | grep -E "userns|user_namespaces" || true
        exit 0 ;;
    eteindre|redemarrer)
        # Arret ou redemarrage demande depuis l'interface (le joueur n'a pas
        # de droits root). Arret propre d'abord ; si la machine est toujours
        # la quelques secondes plus tard, on force, puis appel noyau direct.
        if [ "$1" = "eteindre" ]; then mode=poweroff; sysrq=o; else mode=reboot; sysrq=b; fi
        sync
        systemctl --no-block "${mode}"
        setsid sh -c "sleep 12; systemctl -f ${mode}; sleep 5; systemctl -ff ${mode}; sleep 3; sync; echo ${sysrq} > /proc/sysrq-trigger" \
            >/dev/null 2>&1 </dev/null &
        exit 0 ;;
    steam) PKGS="steam-launcher steam-libs-amd64 steam-libs-i386:i386 libc6:i386 libegl1 libegl1:i386 libgbm1 libgbm1:i386 libgl1 libgl1:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 xdg-desktop-portal xdg-desktop-portal-gtk" ;;
    emu)   PKGS="retroarch libretro-nestopia libretro-snes9x libretro-mgba libretro-genesisplusgx libretro-beetle-psx libretro-gambatte" ;;
    *)     echo "omni-plateforme : intention inconnue" >&2; exit 2 ;;
esac

apt-get update >/dev/null 2>&1 || true
# shellcheck disable=SC2086
exec apt-get install -y --no-install-recommends -o APT::Status-Fd=1 ${PKGS}
OMNIPLAT

    chmod 755 "${sbin}/omni-plateforme"

    # omni-poser-proton <umu|defaut|ubisoft>
    #   umu     : le lanceur umu seul (paquets .deb de l'editeur)
    #   defaut  : umu + GE-Proton de reference (launchers Epic, EA)
    #   ubisoft : umu + une version plus ancienne, pour Ubisoft Connect
    # Les versions sont figees ici, a une seule place (variables du build).
    cat > "${sbin}/omni-poser-proton" <<'POSERPROTON'
#!/bin/bash
# Omni Console - installation du moteur Proton (umu + GE-Proton)
set -u
export DEBIAN_FRONTEND=noninteractive

UMU="@UMU@"
SUITE="@SUITE@"
declare -A VERSIONS=( [defaut]="@PROTON@" [ubisoft]="@PROTON_UBISOFT@" )
declare -A DESTINATIONS=( [defaut]=/opt/omni/proton [ubisoft]=/opt/omni/proton-ubisoft )

variante="${1:-defaut}"

# Cache de telechargement : celui du build s'il existe, sinon /tmp
CACHE=/var/cache/omni
[[ -d "${CACHE}" && -w "${CACHE}" ]] || CACHE=/tmp

# Le lanceur umu : deux paquets de l'editeur, installes avec leurs dependances
poser_umu() {
    command -v umu-run >/dev/null 2>&1 && return 0

    local base="https://github.com/Open-Wine-Components/umu-launcher/releases/download/${UMU}"

    echo "Telechargement du lanceur Proton (umu)"
    cd "${CACHE}" || return 1
    curl -fsSL --max-time 300 --retry 2 -o python3-umu.deb "${base}/python3-umu-launcher_${UMU}-1_amd64_ubuntu-${SUITE}.deb" || return 1
    curl -fsSL --max-time 300 --retry 2 -o umu.deb "${base}/umu-launcher_${UMU}-1_all_ubuntu-${SUITE}.deb" || return 1

    dpkg --add-architecture i386
    apt-get update >/dev/null 2>&1 || true
    apt-get install -y --no-install-recommends -o Dpkg::Options::=--force-confold ./python3-umu.deb ./umu.deb || return 1
    rm -f python3-umu.deb umu.deb
    command -v umu-run >/dev/null 2>&1
}

# Telecharge l'archive de Proton, avec reprise. Selon l'age de la version,
# l'archive porte ou non le suffixe -x86_64 : on essaie les deux noms.
# Affiche le chemin de l'archive complete.
telecharger_proton() {
    local version="$1" base nom essai archive

    base="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/${version}"

    for nom in "${version}-x86_64.tar.gz" "${version}.tar.gz"; do
        archive="${CACHE}/${nom}"
        if tar tzf "${archive}" >/dev/null 2>&1; then
            echo "${archive}"
            return 0
        fi
    done

    for nom in "${version}-x86_64.tar.gz" "${version}.tar.gz"; do
        archive="${CACHE}/${nom}"

        # le nom n'existe pas pour cette version : inutile de reessayer, on passe au suivant
        curl -fsIL --max-time 30 -o /dev/null "${base}/${nom}" || continue

        for essai in 1 2 3; do
            if curl -fL --continue-at - --max-time 2400 --retry 5 --retry-delay 10 \
                    --retry-all-errors --connect-timeout 30 -o "${archive}" "${base}/${nom}" >&2; then
                if tar tzf "${archive}" >/dev/null 2>&1; then
                    echo "${archive}"
                    return 0
                fi
            fi
            echo "== essai ${essai}/3 pour ${nom} interrompu" >&2
            sleep 5
        done
    done

    return 1
}

poser_proton() {
    local version="$1" dest="$2" archive

    if [[ -f "${dest}/toolmanifest.vdf" ]]; then
        return 0
    fi

    echo "Telechargement de ${version}, environ 500 Mo : c'est la partie longue"
    archive="$(telecharger_proton "${version}")" || { echo "Telechargement impossible" >&2; return 1; }

    echo "Decompression de ${version}"
    rm -rf "${dest}"
    mkdir -p "${dest}"
    tar xzf "${archive}" -C "${dest}" --strip-components=1 || return 1

    # umu exige le toolmanifest.vdf : sans lui, il refuse le dossier
    test -f "${dest}/toolmanifest.vdf" || return 1
    test -x "${dest}/proton" || return 1
    chmod -R a+rX "${dest}"
}

case "${variante}" in
    umu)
        poser_umu || exit 1 ;;
    defaut|ubisoft)
        poser_umu || exit 1
        poser_proton "${VERSIONS[${variante}]}" "${DESTINATIONS[${variante}]}" || exit 1 ;;
    *)
        echo "variante inconnue : ${variante}" >&2
        exit 2 ;;
esac

echo "Moteur Proton pret"
POSERPROTON

    sed -i \
        -e "s|@UMU@|${UMU_VERSION}|" \
        -e "s|@SUITE@|${UBUNTU_SUITE}|" \
        -e "s|@PROTON@|${PROTON_VERSION}|" \
        -e "s|@PROTON_UBISOFT@|${UBISOFT_PROTON_VERSION}|" \
        "${sbin}/omni-poser-proton"

    chmod 755 "${sbin}/omni-poser-proton"

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

    log_ok "Guichet a intentions et moteur Proton en place."
}

# Fichiers de la session du joueur et controle de sante. L'installateur les
# copie tels quels dans le systeme installe : ils sont ecrits ICI, a une seule
# place, ou shellcheck les controle comme le reste.
ecrire_fichiers_session_joueur() {
    local dest="${CHROOT_DIR}/usr/local/share/omni/systeme"

    mkdir -p "${dest}" "${CHROOT_DIR}/usr/local/sbin"

    cat > "${dest}/omni-session-joueur" <<'SESSIONJOUEUR'
#!/bin/sh
# Omni Console - session du joueur : fond, clavier, son, puis gestionnaire de fenetres.
# Lancee par omni-console.service (xinit). Tout ce qui precede openbox doit
# rester bref : le joueur attend devant l'ecran de demarrage.
xsetroot -solid '#0d0221' &

# Clavier choisi a l'installation. Xorg le lit deja dans sa configuration ;
# cette ligne double la mise pour les machines ou la regle d'Xorg ne s'applique pas.
if [ -r /etc/default/keyboard ]; then
    . /etc/default/keyboard
    setxkbmap -model "${XKBMODEL:-pc105}" -layout "${XKBLAYOUT:-us}" \
        -variant "${XKBVARIANT:-}" -option "${XKBOPTIONS:-}" 2>/dev/null
fi

pipewire &
wireplumber &
pipewire-pulse &

# on attend que le serveur de son reponde vraiment, au lieu de patienter un
# nombre de secondes au hasard
i=0
while [ "$i" -lt 20 ]; do
    pactl info >/dev/null 2>&1 && break
    i=$((i + 1))
    sleep 0.5
done

exec openbox-session
SESSIONJOUEUR

    cat > "${dest}/openbox-autostart" <<'AUTOSTART'
# L'interface Omni est relancee par openbox si elle s'arrete. Sa sortie va dans
# un journal : sans terminal, une erreur de l'interface ne laisserait aucune trace.
journal="$HOME/.omni/journaux/omni-console.log"
mkdir -p "$HOME/.omni/journaux"
while true; do
    # un plantage en boucle ne doit pas remplir le disque
    if [ -f "$journal" ] && [ "$(wc -c < "$journal")" -gt 5000000 ]; then
        tail -n 500 "$journal" > "$journal.tmp" && mv "$journal.tmp" "$journal"
    fi
    cd /usr/local/share/omni/ui && python3 omni-console.py >> "$journal" 2>&1
    sleep 2
done &
AUTOSTART

    cat > "${dest}/omni-console.service" <<'CONSOLESERVICE'
[Unit]
Description=Omni Console - session du joueur
After=systemd-user-sessions.service plymouth-quit.service sound.target
Conflicts=getty@tty1.service
Wants=plymouth-quit.service

[Service]
Type=simple
User=omni
WorkingDirectory=/home/omni
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
StandardError=journal
UnsetEnvironment=TERM
Environment=XDG_SESSION_TYPE=x11
UtmpIdentifier=tty1
UtmpMode=user
ExecStart=/usr/bin/xinit /usr/local/bin/omni-session-joueur -- :0 vt1 -keeptty -nolisten tcp
Restart=always
RestartSec=2

[Install]
WantedBy=graphical.target
CONSOLESERVICE

    cat > "${CHROOT_DIR}/usr/local/sbin/omni-selftest" <<'SELFTEST'
#!/bin/bash
# Omni Console - controle de sante. Affiche ce qui va et ce qui ne va pas.

# verifier <intitule> <critique|optionnel> <commande...>
verifier() {
    local intitule="$1" niveau="$2"
    shift 2

    if "$@" >/dev/null 2>&1; then
        printf '[ OK       ] %s\n' "${intitule}"
    elif [ "${niveau}" = critique ]; then
        printf '[ CRITIQUE ] %s\n' "${intitule}"
    else
        printf '[ ABSENT   ] %s\n' "${intitule}"
    fi
}

# en_joueur <commande...> : l'execute comme le joueur, que l'on soit root ou lui
en_joueur() {
    if [ "$(id -u)" = 0 ]; then
        runuser -u omni -- "$@"
    else
        "$@"
    fi
}

verifier "Noyau installe" critique bash -c 'ls /boot/vmlinuz-*'
verifier "Initramfs propre" critique bash -c 'ls /boot/initrd.img-* && ! lsinitramfs /boot/initrd.img-* | grep -q casper'
verifier "Demarrage GRUB" critique test -s /boot/grub/grub.cfg
verifier "Partition de donnees montee" critique mountpoint -q /omni-data
verifier "Donnees accessibles au joueur" critique en_joueur test -w /omni-data
verifier "Service de session" critique systemctl is-enabled omni-console.service
verifier "Serveur graphique" critique test -x /usr/bin/Xorg
verifier "Interface Omni" critique test -f /usr/local/share/omni/ui/omni-console.py
verifier "Clavier choisi a l'installation" critique grep -q '^XKBLAYOUT=' /etc/default/keyboard
verifier "Fuseau horaire choisi" critique test -L /etc/localtime
verifier "Langues du systeme" critique bash -c 'locale -a | grep -qi "utf8"'
verifier "Serveur de son" optionnel test -x /usr/bin/pipewire
verifier "Steam" optionnel command -v steam
verifier "Proton" optionnel test -f /opt/omni/proton/toolmanifest.vdf
verifier "umu" optionnel command -v umu-run
verifier "RetroArch" optionnel command -v retroarch
verifier "Bluetooth" optionnel systemctl is-enabled bluetooth.service
verifier "Lecture des manettes" optionnel python3 -c 'import evdev'
verifier "Console serie (diagnostic)" optionnel systemctl is-enabled serial-getty@ttyS0.service
SELFTEST

    chmod 755 "${CHROOT_DIR}/usr/local/sbin/omni-selftest"
    log_ok "Fichiers de session du joueur et autodiagnostic ecrits."
}

# Session graphique de l'INSTALLATEUR (systeme live, en root). Distincte de
# celle du joueur : c'est elle qui lance omni-installer.
configurer_session_installateur() {
    cat > "${CHROOT_DIR}/root/.xinitrc" <<'XINITRC'
#!/bin/sh
# Session X de l'installateur. La sortie va dans un journal : aucun terminal
# ne doit apparaitre, meme en cas d'erreur.
exec >>/var/log/omni-xinit.log 2>&1

echo
echo "=================================================="
echo "Omni X session"
date
echo "=================================================="

export DISPLAY="${DISPLAY:-:0}"
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=Openbox

# Le bus de session et le serveur de son doivent etre en place AVANT
# l'installateur : sinon l'installation se deroule en silence.
exec dbus-run-session -- /usr/local/bin/omni-session
XINITRC

    chmod +x "${CHROOT_DIR}/root/.xinitrc"

    cat > "${CHROOT_DIR}/usr/local/bin/omni-session" <<'OMNISESSION'
#!/bin/sh
# Omni Console - contenu de la session graphique de l'installateur : son,
# installateur, puis gestionnaire de fenetres, dans le meme bus.

# Pas de session logind ici : sans ce dossier, pipewire refuse de demarrer.
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"

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
    echo "Voir /var/log/omni-xinit.log et /var/log/omni-installation.log."
fi

exec /usr/bin/openbox-session
OMNISESSION

    chmod +x "${CHROOT_DIR}/usr/local/bin/omni-session"
    log_ok "Session de l'installateur ecrite."
}

# Aucun gestionnaire de connexion, aucun getty sur tty1 : le joueur ne voit jamais de terminal ni de login.
masquer_gestionnaires_de_session() {
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

}

# Manettes : regles udev (uaccess), module uinput, Bluetooth.
configurer_manettes() {
    # ------------------------------------------------------------------------
    # Manettes
    #
    # L'interface lit les manettes directement (python3-evdev), meme quand un
    # jeu est au premier plan (bouton Guide). Les manettes sont donc lisibles
    # par la session ; uinput servira a la souris virtuelle (stick = curseur).
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/udev/rules.d" "${CHROOT_DIR}/etc/modules-load.d"

    cat > "${CHROOT_DIR}/etc/udev/rules.d/70-omni-manettes.rules" <<'UDEVPAD'
# Omni Console : manettes accessibles au joueur qui a la session en cours.
# « uaccess » donne l'acces au seul utilisateur de la session active, au lieu
# de l'ouvrir a tous les programmes de la machine comme le ferait MODE=0666.
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_JOYSTICK}=="1", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="js*", TAG+="uaccess"
SUBSYSTEM=="hidraw", TAG+="uaccess"
# Peripherique virtuel (souris pilotee au stick dans les launchers) : reserve
# au groupe input, dont le compte joueur fait partie.
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
UDEVPAD

    printf '%s\n' uinput > "${CHROOT_DIR}/etc/modules-load.d/omni-uinput.conf"

    run_in_chroot "systemctl enable bluetooth.service 2>/dev/null || true" >>"${LOG_FILE}" 2>&1 || true

    log_ok "Regles manettes en place."

}

# Openbox : plein ecran partout, aucun bureau visible.
configurer_openbox() {
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

}

# Reseau : NetworkManager gere toutes les cartes (cable compris), DNS par systemd-resolved.
configurer_reseau() {
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

}

# Espaces de noms utilisateur : Steam et Proton en ont besoin pour leur bac a sable.
configurer_isolation() {
    # ------------------------------------------------------------------------
    # Espaces de noms utilisateur
    #
    # Ubuntu 24.04 les restreint par defaut (apparmor_restrict_unprivileged_userns).
    # Or Steam ET Proton s'en servent pour leur bac a sable : sans eux, Steam
    # affiche « Steam now requires user namespaces to be enabled » et Proton
    # echoue sur « bwrap: setting up uid map: Permission denied ».
    # Reference : bugs.launchpad.net/ubuntu/+source/apparmor/+bug/2065088
    # ------------------------------------------------------------------------

    mkdir -p "${CHROOT_DIR}/etc/sysctl.d"
    cat > "${CHROOT_DIR}/etc/sysctl.d/60-omni-jeux.conf" <<'SYSCTLJEUX'
# Omni Console : indispensables a Steam et a Proton, qui isolent leurs
# processus avec des espaces de noms utilisateur. Les trois doivent etre
# ouverts : Ubuntu 24.04 ferme le premier, une politique de securite peut
# fermer les autres.
kernel.apparmor_restrict_unprivileged_userns = 0
kernel.unprivileged_userns_clone = 1
user.max_user_namespaces = 28633
SYSCTLJEUX

    # Profil AppArmor permissif pour bwrap, l'outil d'isolation employe par
    # Steam et Proton : il complete le reglage ci-dessus sur les systemes ou
    # le profil restrictif d'Ubuntu est charge.
    mkdir -p "${CHROOT_DIR}/etc/apparmor.d"
    cat > "${CHROOT_DIR}/etc/apparmor.d/omni-bwrap" <<'AABWRAP'
abi <abi/4.0>,
include <tunables/global>

profile omni-bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/omni-bwrap>
}
AABWRAP

    # Ubuntu charge des profils AppArmor qui encadrent l'isolation. Steam
    # tourne sous un profil a son nom : c'est LUI qui decide de son droit a
    # creer un espace de noms, pas le reglage general du systeme. Un essai
    # fait hors de ce profil reussit donc pendant que Steam echoue.
    # On neutralise les profils concernes, Steam et Proton compris.
    run_in_chroot '
        mkdir -p /etc/apparmor.d/disable
        for profil in unprivileged_userns bwrap-userns-restrict steam \
                      steam-runtime steam.steam.steam bwrap; do
            if [ -e "/etc/apparmor.d/${profil}" ]; then
                ln -sf "/etc/apparmor.d/${profil}" "/etc/apparmor.d/disable/${profil}"
                echo "profil AppArmor neutralise : ${profil}"
            fi
        done
        # tout profil qui restreint explicitement les espaces de noms
        grep -rlE "^[[:space:]]*(deny[[:space:]]+)?userns" /etc/apparmor.d --include="*" 2>/dev/null |
        while read -r trouve; do
            nom="$(basename "${trouve}")"
            case "${nom}" in
                disable|abstractions|tunables|local) continue ;;
            esac
            if [ -f "${trouve}" ]; then
                ln -sf "${trouve}" "/etc/apparmor.d/disable/${nom}"
                echo "profil AppArmor restreignant les espaces de noms neutralise : ${nom}"
            fi
        done
    ' >>"${LOG_FILE}" 2>&1 || true

    # Version de l'image, lisible par l'interface et par l'autodiagnostic :
    # on saura toujours quelle construction tourne sur une console.
    # la version de l image est ecrite par ecrire_options_image

    log_ok "Isolation autorisee (Steam et Proton en ont besoin), image ${IMAGE_VERSION}."

}

# Mises a jour automatiques : systeme et noyau (unattended-upgrades), firmwares (fwupd).
configurer_majs_auto() {
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

}

# Service systemd qui lance X et la session de l'installateur.
configurer_service_x() {
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

}

# Service de collecte des informations de demarrage, activation des services, cible graphique.
configurer_service_debug() {
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

}

# Xwrapper, clavier de l'image, journal persistant, neutralisation de casper.
configurer_systeme_divers() {
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

}

# Plymouth : theme Omni, initramfs reconstruit et verifie.
configurer_plymouth() {
    # ------------------------------------------------------------------------
    # Plymouth
    # ------------------------------------------------------------------------

    log_info "Configuration de Plymouth."

    trouver_theme_plymouth || return 1
    log_info "Theme Plymouth : ${PLYMOUTH_THEME_SRC}"

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

step_apply_settings() {
    log_info "Etape 5/6 : configuration de l'image (session, reseau, jeux, Plymouth, installateur)."

    masquer_gestionnaires_de_session || return 1
    installer_ressources_projet || return 1
    ecrire_options_image || return 1
    configurer_console_serie || return 1
    generer_locales || return 1
    ecrire_fichiers_session_joueur || return 1
    configurer_manettes || return 1
    configurer_openbox || return 1
    configurer_reseau || return 1
    configurer_isolation || return 1
    configurer_majs_auto || return 1
    configurer_session_installateur || return 1
    configurer_service_x || return 1
    configurer_service_debug || return 1
    configurer_systeme_divers || return 1
    configurer_theme_grub || return 1
    configurer_plymouth || return 1

    log_ok "Etape 5/6 terminee : image configuree."
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

    # zstd : deux a trois fois plus rapide que la compression par defaut, et
    # l'image se decompresse aussi plus vite a l'installation et au demarrage.
    # -mem : sinon mksquashfs prend toute la memoire de la machine d'atelier.
    # /boot est CONSERVE : le systeme installe a besoin du vrai noyau, il ne
    # doit pas reutiliser celui du live (qui cherche un media USB au demarrage).
    if ! mksquashfs \
        "${CHROOT_DIR}" \
        "${IMAGE_DIR}/casper/filesystem.squashfs" \
        -comp zstd -Xcompression-level 3 \
        -mem 512M \
        -noappend \
        -no-duplicates \
        -no-recovery \
        -wildcards \
        -e "proc/*" \
        -e "sys/*" \
        -e "dev/*" \
        -e "run/*" \
        -e "tmp/*" \
        -e "var/cache/apt/archives/*" \
        -e "var/cache/omni/*" \
        -e "usr/local/sbin/omni-etape-*" \
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

    # Menu cache : la cle demarre directement sur l'installateur. Echap (ou Maj)
    # affiche le menu, qui garde deux entrees de diagnostic pour l'atelier.
    cat > "${IMAGE_DIR}/boot/grub/grub.cfg" <<'GRUBCFG'
insmod all_video
insmod gfxterm
insmod linux
insmod iso9660
insmod search
insmod search_fs_file

set timeout_style=hidden
set timeout=1
set default=0
set color_normal=light-cyan/black
set color_highlight=black/yellow

search --no-floppy --file --set=root /casper/vmlinuz

if [ -z "${root}" ]; then
    echo "ERREUR : impossible de trouver /casper/vmlinuz"
    sleep 10
fi

menuentry "Omni Console" {
    linux /casper/vmlinuz boot=casper quiet splash loglevel=0 rd.systemd.show_status=false vt.global_cursor_default=0 console=tty0 ---
    initrd /casper/initrd
}

menuentry "Omni Console (diagnostic, console serie)" {
    linux /casper/vmlinuz boot=casper splash plymouth:debug console=tty0 console=ttyS0,115200n8 systemd.log_level=info systemd.log_target=console ---
    initrd /casper/initrd
}

menuentry "Omni Console (affichage de secours)" {
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
        "Proton Ubisoft|${base_proton/${PROTON_VERSION}/${UBISOFT_PROTON_VERSION}}/${UBISOFT_PROTON_VERSION}.tar.gz" \
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

# Garde : permet de charger ce fichier pour tester ses fonctions sans lancer de build
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
