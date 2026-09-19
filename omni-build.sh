#!/usr/bin/env bash
set -uo pipefail
IFS=$' \t\n'

# ============================================================================
# Omni Console - constructeur ISO
# Ubuntu 24.04 Noble / amd64
#
# BIOS + UEFI via grub-mkrescue
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
# Sécurité fichiers
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

    if ! mount -t "${type}" "${src}" "${abs}"; then
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
            if umount "${m}" 2>/dev/null; then
                log_info "Demonte : ${m}"
            elif umount -l "${m}" 2>/dev/null; then
                log_warn "Demonte (paresseux) : ${m}"
            else
                log_err "Echec demontage : ${m}"
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
# Etape 1 - dépendances
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
# Etape 3 - préparation chroot
# ============================================================================

step_enter_system() {
    log_info "Etape 3/6 : preparation de l'acces au systeme de base."

    mount_special proc proc "${CHROOT_DIR}/proc" || return 1
    mount_special sysfs sysfs "${CHROOT_DIR}/sys" || return 1
    mount_bind /dev "${CHROOT_DIR}/dev" || return 1

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

    if ! run_in_chroot "apt-get update" >>"${LOG_FILE}" 2>&1; then
        log_err "apt-get update interne a echoue."
        return 1
    fi

    log_ok "Etape 3/6 terminee : systeme accessible, depots prets."
}

# ============================================================================
# Neutralisation update-initramfs pendant apt
# ============================================================================

neutralize_chroot_cmds() {
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
        if [ -e /usr/sbin/update-initramfs.real ]; then
            mv -f \
                /usr/sbin/update-initramfs.real \
                /usr/sbin/update-initramfs
        fi
    '
}

# ============================================================================
# Etape 4 - installation système
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

    if ! run_in_chroot \
        "apt-get install -y --no-install-recommends ${pkgs}" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "Installation des paquets echouee."
        restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
        return 1
    fi

    if ! run_in_chroot \
        "dpkg --configure -a" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "dpkg --configure -a a echoue."
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

    # Evite également les getty virtuels supplémentaires.
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
        log_ok "Sons interface copies."
    fi

    log_ok "Nouveau omni-installer.py installe dans l'ISO."

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

/usr/local/bin/omni-installer
rc=$?

echo "omni-installer a termine avec le code ${rc}"

if [ "${rc}" -ne 0 ]; then
    echo "ERREUR : omni-installer a echoue."
    echo "Voir /var/log/omni-xinit.log et le journal systemd."
fi

# ---------------------------------------------------------------------------
# Openbox reste le gestionnaire de fenêtres de la session.
# ---------------------------------------------------------------------------

exec /usr/bin/openbox-session
XINITRC

    chmod +x "${CHROOT_DIR}/root/.xinitrc"

    # ------------------------------------------------------------------------
    # Service X
    #
    # On conserve un service systemd dédié.
    # xinit lance directement Xorg + la session.
    #
    # Le getty de tty1 est masqué ci-dessus.
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

# Nettoyage d'une éventuelle session X précédente.
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
    # La gestion plus intelligente du clavier utilisateur pourra être faite
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
    # Vérification initramfs
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

    safe_rm "${IMAGE_DIR}" || return 1

    mkdir -p \
        "${IMAGE_DIR}/casper" \
        "${IMAGE_DIR}/boot/grub"

    # ------------------------------------------------------------------------
    # SquashFS
    # ------------------------------------------------------------------------

    log_info "Compression du systeme (mksquashfs)."

    if ! mksquashfs \
        "${CHROOT_DIR}" \
        "${IMAGE_DIR}/casper/filesystem.squashfs" \
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
    # Vérification finale initrd
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
    # Vérification arborescence
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

    if ! grub-mkrescue \
        -o "${OUTPUT_DIR}/${ISO_NAME}" \
        "${IMAGE_DIR}" \
        >>"${LOG_FILE}" 2>&1; then

        log_err "grub-mkrescue a echoue."
        return 1
    fi

    # ------------------------------------------------------------------------
    # Vérification ISO
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

    clean_previous || exit 1
    step_check_dependencies || exit 1
    step_open_base_iso || exit 1
    step_enter_system || exit 1
    step_install_omni || exit 1
    step_apply_settings || exit 1
    step_build_iso || exit 1

    log_ok "=== Build Omni Console termine ==="
    log_info "Journal complet : ${LOG_FILE}"
}

main "$@"

