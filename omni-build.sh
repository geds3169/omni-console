#!/usr/bin/env bash
set -uo pipefail
IFS=$' \t\n'

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
readonly BUILD_TOOLS=(debootstrap squashfs-tools xorriso isolinux grub-pc-bin grub-efi-amd64-bin mtools dosfstools)
readonly OMNI_CORE_PKGS=(ubuntu-minimal linux-generic linux-firmware casper initramfs-tools ubuntu-standard sudo xserver-xorg xserver-xorg-video-all xserver-xorg-input-all xinit x11-xserver-utils openbox xterm python3-tk python3)

CLEAN_MODE="keep-base"

if [[ -t 1 ]]; then
    readonly C_RESET=$'\033[0m' C_INFO=$'\033[36m' C_OK=$'\033[32m' C_WARN=$'\033[33m' C_ERR=$'\033[31m'
else
    readonly C_RESET="" C_INFO="" C_OK="" C_WARN="" C_ERR=""
fi
_timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
_log() { local lvl="$1" col="$2"; shift 2; local l; l="$(_timestamp) [${lvl}] $*"; printf '%s%s%s\n' "${col}" "${l}" "${C_RESET}"; printf '%s\n' "${l}" >> "${LOG_FILE}"; }
log_info() { _log "INFO" "${C_INFO}" "$@"; }
log_ok()   { _log " OK " "${C_OK}"   "$@"; }
log_warn() { _log "WARN" "${C_WARN}" "$@"; }
log_err()  { _log "ERR " "${C_ERR}"  "$@"; }

safe_rm() {
    local t="$1"
    if [[ -z "${t}" ]]; then log_err "safe_rm : cible vide."; return 1; fi
    local abs; if ! abs="$(realpath -m -- "${t}")"; then log_err "safe_rm : chemin insoluble : ${t}"; return 1; fi
    case "${abs}" in "/"|"${HOME}"|"") log_err "safe_rm : cible interdite : ${abs}"; return 1 ;; esac
    if [[ "${abs}" != "${WORK_ROOT}/"* ]]; then log_err "safe_rm : ${abs} hors de ${WORK_ROOT}."; return 1; fi
    if [[ ! -e "${abs}" ]]; then return 0; fi
    log_info "Suppression : ${abs}"; rm -rf -- "${abs}"
}

MOUNTED_POINTS=()
mount_special() { local type="$1" src="$2" mnt="$3"; local abs; abs="$(realpath -m -- "${mnt}")"; if [[ "${abs}" != "${CHROOT_DIR}/"* ]]; then log_err "mount hors chroot : ${abs}"; return 1; fi; mkdir -p "${abs}"; mount -t "${type}" "${src}" "${abs}"; MOUNTED_POINTS+=("${abs}"); log_info "Monte : ${abs}"; }
mount_bind()    { local src="$1" mnt="$2"; local abs; abs="$(realpath -m -- "${mnt}")"; if [[ "${abs}" != "${CHROOT_DIR}/"* ]]; then log_err "mount hors chroot : ${abs}"; return 1; fi; mkdir -p "${abs}"; mount --bind "${src}" "${abs}"; MOUNTED_POINTS+=("${abs}"); log_info "Monte (bind) : ${abs}"; }
unmount_all() {
    local i
    for (( i=${#MOUNTED_POINTS[@]}-1 ; i>=0 ; i-- )); do
        local m="${MOUNTED_POINTS[i]}"
        if mountpoint -q -- "${m}"; then
            if umount "${m}" 2>/dev/null; then log_info "Demonte : ${m}"
            elif umount -l "${m}" 2>/dev/null; then log_warn "Demonte (paresseux) : ${m}"
            else log_err "Echec demontage : ${m}"; fi
        fi
    done
    MOUNTED_POINTS=()
}
_on_exit() { local c=$?; unmount_all; if (( c==0 )); then log_ok "Script termine sans erreur."; else log_err "Script interrompu (code ${c}). Voir ${LOG_FILE}"; fi; exit "${c}"; }
trap _on_exit EXIT; trap 'exit 130' INT; trap 'exit 143' TERM

run_in_chroot() { chroot "${CHROOT_DIR}" /usr/bin/env -i HOME=/root LC_ALL=C LANG=C.UTF-8 PATH=/usr/sbin:/usr/bin:/sbin:/bin DEBIAN_FRONTEND=noninteractive /bin/bash -c "$*"; }

require_root() { if [[ "${EUID}" -ne 0 ]]; then echo "Lancer avec sudo : sudo $0 $*" >&2; exit 1; fi; }
prepare_workspace() { mkdir -p "${LOG_DIR}"; : >> "${LOG_FILE}"; log_info "Racine de travail : ${WORK_ROOT}"; mkdir -p "${OUTPUT_DIR}"; }

clean_previous() {
    log_info "Nettoyage (mode : ${CLEAN_MODE})."
    unmount_all
    safe_rm "${OUTPUT_DIR}"; mkdir -p "${OUTPUT_DIR}"
    safe_rm "${IMAGE_DIR}"
    if [[ "${CLEAN_MODE}" == "all" ]]; then safe_rm "${CHROOT_DIR}"; log_ok "Nettoyage complet effectue."
    else log_info "Systeme de base conserve (cache)."; log_ok "Nettoyage leger effectue."; fi
}

step_check_dependencies() {
    log_info "Etape 1/6 : verification des outils de construction."
    if ! apt-get update >>"${LOG_FILE}" 2>&1; then log_err "apt-get update a echoue."; return 1; fi
    local manquants=() outil
    for outil in "${BUILD_TOOLS[@]}"; do dpkg -s "${outil}" >/dev/null 2>&1 || manquants+=("${outil}"); done
    if (( ${#manquants[@]} > 0 )); then
        log_info "Installation des outils manquants : ${manquants[*]}"
        DEBIAN_FRONTEND=noninteractive apt-get install -y "${manquants[@]}" >>"${LOG_FILE}" 2>&1 || { log_err "Installation des outils echouee."; return 1; }
    else log_info "Tous les outils sont deja presents."; fi
    local o; for o in debootstrap xorriso mksquashfs grub-mkstandalone; do command -v "${o}" >/dev/null 2>&1 || { log_err "Outil introuvable : ${o}"; return 1; }; done
    local ko go; ko="$(df -Pk "${WORK_ROOT}" | awk 'NR==2 {print $4}')"; go=$(( ko / 1024 / 1024 ))
    log_info "Espace disponible : ${go} Go."; (( go < 5 )) && log_warn "Moins de 5 Go libres."
    log_ok "Etape 1/6 terminee : outils prets, ${go} Go disponibles."
}

step_open_base_iso() {
    log_info "Etape 2/6 : systeme de base Ubuntu (${UBUNTU_SUITE})."
    if [[ -x "${CHROOT_DIR}/bin/bash" || -x "${CHROOT_DIR}/usr/bin/bash" ]]; then
        log_info "Systeme de base deja present (cache), etape 2 sautee."; log_ok "Etape 2/6 terminee (cache)."; return 0
    fi
    mkdir -p "${CHROOT_DIR}"
    log_info "Telechargement du systeme minimal (plusieurs minutes)."
    debootstrap --arch=amd64 --variant=minbase --components=main,restricted,universe,multiverse "${UBUNTU_SUITE}" "${CHROOT_DIR}" "${UBUNTU_MIRROR}" >>"${LOG_FILE}" 2>&1 || { log_err "debootstrap a echoue."; return 1; }
    [[ -x "${CHROOT_DIR}/bin/bash" || -x "${CHROOT_DIR}/usr/bin/bash" ]] || { log_err "Systeme de base incomplet."; return 1; }
    local taille; taille="$(du -sh "${CHROOT_DIR}" 2>/dev/null | awk '{print $1}')"
    log_ok "Etape 2/6 terminee : systeme de base cree (${taille})."
}

step_enter_system() {
    log_info "Etape 3/6 : preparation de l'acces au systeme de base."
    mount_special proc  proc    "${CHROOT_DIR}/proc"     || return 1
    mount_special sysfs sysfs   "${CHROOT_DIR}/sys"      || return 1
    mount_bind    /dev          "${CHROOT_DIR}/dev"      || return 1
    mount_special devpts devpts "${CHROOT_DIR}/dev/pts"  || return 1
    cp /etc/resolv.conf "${CHROOT_DIR}/etc/resolv.conf"
    cat > "${CHROOT_DIR}/etc/apt/sources.list" <<SOURCES
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE} main restricted universe multiverse
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-updates main restricted universe multiverse
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-security main restricted universe multiverse
SOURCES
    if ! run_in_chroot "apt-get update" >>"${LOG_FILE}" 2>&1; then log_err "apt-get update interne a echoue."; return 1; fi
    log_ok "Etape 3/6 terminee : systeme accessible, depots prets."
}

neutralize_chroot_cmds() { run_in_chroot "if [ -x /usr/sbin/update-initramfs ] && [ ! -e /usr/sbin/update-initramfs.real ]; then mv /usr/sbin/update-initramfs /usr/sbin/update-initramfs.real; printf '#!/bin/sh\nexit 0\n' > /usr/sbin/update-initramfs; chmod +x /usr/sbin/update-initramfs; fi"; }
restore_chroot_cmds()    { run_in_chroot "if [ -e /usr/sbin/update-initramfs.real ]; then mv -f /usr/sbin/update-initramfs.real /usr/sbin/update-initramfs; fi"; }

step_install_omni() {
    log_info "Etape 4/6 : installation de la couche systeme demarrable."
    local pkgs; pkgs="$(printf '%s ' "${OMNI_CORE_PKGS[@]}")"
    log_info "Paquets : ${pkgs}"
    neutralize_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
    log_info "Installation (longue au premier passage : noyau + firmwares)."
    run_in_chroot "apt-get install -y --no-install-recommends ${pkgs}" >>"${LOG_FILE}" 2>&1 || true
    run_in_chroot "dpkg --configure -a" >>"${LOG_FILE}" 2>&1 || true
    restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
    local rate=0 p
    for p in "${OMNI_CORE_PKGS[@]}"; do
        if run_in_chroot "dpkg -s ${p} 2>/dev/null | grep -q '^Status: install ok installed'"; then :; else log_err "Paquet non installe : ${p}"; rate=1; fi
    done
    local noyau=""
    noyau="$(cd "${CHROOT_DIR}/boot" 2>/dev/null && ls vmlinuz-* 2>/dev/null | head -1 || true)"
    if [[ -z "${noyau}" ]]; then log_err "Aucun noyau (vmlinuz) dans /boot."; rate=1; fi
    if (( rate != 0 )); then return 1; fi
    local taille; taille="$(du -sh "${CHROOT_DIR}" 2>/dev/null | awk '{print $1}')"
    log_ok "Etape 4/6 terminee : noyau ${noyau} present, systeme a ${taille}."
}

step_apply_settings() {
    log_info "Etape 5/6 : lancement X direct (sans login, sans gestionnaire de session)."

    # Purger tout gestionnaire de session herite (nodm, lightdm, gdm, sddm).
    run_in_chroot "apt-get purge -y nodm lightdm lightdm-gtk-greeter gdm3 sddm 2>/dev/null; true" >>"${LOG_FILE}" 2>&1 || true
    rm -f "${CHROOT_DIR}/etc/systemd/system/omni-session.service"
    rm -f "${CHROOT_DIR}/etc/systemd/system/omni-xdump.service"
    rm -f "${CHROOT_DIR}/etc/lightdm/lightdm.conf.d/50-omni.conf" 2>/dev/null || true
    rm -f "${CHROOT_DIR}/etc/default/nodm" 2>/dev/null || true

    # Programme graphique lance par X : pour l'instant, une fenetre de test
    # plein ecran aux couleurs Omni. Deviendra la 1re page de l'installateur.
    # Copier le vrai installateur Python depuis le fichier a cote du builder.
    if [ -f /home/geds/omni-installer.py ]; then
        cp /home/geds/omni-installer.py "${CHROOT_DIR}/usr/local/bin/omni-installer"
        log_info "Installateur Python copie."
    else
        log_err "omni-installer.py introuvable a cote du builder."
        return 1
    fi
    chmod +x "${CHROOT_DIR}/usr/local/bin/omni-installer"

    # .xinitrc : ce que X lance au demarrage. Ici, directement l installateur.
    cat > "${CHROOT_DIR}/root/.xinitrc" <<'XINITRC'
#!/bin/sh
exec /usr/local/bin/omni-installer
XINITRC
    chmod +x "${CHROOT_DIR}/root/.xinitrc"

    # Service systemd : lance X directement en root sur VT1, avec -keeptty
    # (le log Xorg reclamait -keeptty pour l integration logind).
    cat > "${CHROOT_DIR}/etc/systemd/system/omni-x.service" <<'OMNIX'
[Unit]
Description=Omni Console - affichage graphique
After=systemd-user-sessions.service plymouth-quit-wait.service getty@tty1.service
Conflicts=getty@tty1.service

[Service]
Type=simple
# Diagnostic : tout ce que fait X et le client va aussi sur le port serie.
ExecStart=/bin/bash -c '/usr/bin/startx /root/.xinitrc -- vt1 -keeptty > /dev/ttyS0 2>&1'
Restart=on-failure
RestartSec=5
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
OMNIX
    run_in_chroot "systemctl enable omni-x.service 2>/dev/null; true" >>"${LOG_FILE}" 2>&1 || true
    run_in_chroot "systemctl set-default graphical.target" >>"${LOG_FILE}" 2>&1 || true

    # Autoriser X a demarrer pour tous.
    mkdir -p "${CHROOT_DIR}/etc/X11"
    cat > "${CHROOT_DIR}/etc/X11/Xwrapper.config" <<XWRAP
allowed_users=anybody
needs_root_rights=yes
XWRAP

    # Clavier francais.
    cat > "${CHROOT_DIR}/etc/default/keyboard" <<KBD
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
KBD

    # Neutraliser scripts casper superflus + services bloquants.
    for f in 30accessibility 24preseed 15autologin 34disable_kde_services 40install-ubiquity 41apt_cdrom 25adduser; do
        if [ -f "${CHROOT_DIR}/usr/share/initramfs-tools/scripts/casper-bottom/${f}" ]; then
            chmod -x "${CHROOT_DIR}/usr/share/initramfs-tools/scripts/casper-bottom/${f}" 2>/dev/null || true
        fi
    done
    mkdir -p "${CHROOT_DIR}/var/crash" "${CHROOT_DIR}/etc/xdg/autostart"
    run_in_chroot "systemctl mask casper-md5check.service casper-md5check.path console-setup.service keyboard-setup.service 2>/dev/null; true" >>"${LOG_FILE}" 2>&1 || true

    neutralize_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
    restore_chroot_cmds >>"${LOG_FILE}" 2>&1 || true
    run_in_chroot "update-initramfs -c -k all" >>"${LOG_FILE}" 2>&1 || log_warn "update-initramfs a signale un souci."
    log_ok "Etape 5/6 terminee : lancement X direct configure."
}

step_build_iso() {
    log_info "Etape 6/6 : fabrication de l'ISO."
    unmount_all

    # 1. Arborescence de l'image.
    safe_rm "${IMAGE_DIR}"
    mkdir -p "${IMAGE_DIR}/casper" "${IMAGE_DIR}/boot/grub" "${IMAGE_DIR}/EFI/boot"

    # 2. Compression du systeme en squashfs.
    log_info "Compression du systeme (mksquashfs, plusieurs minutes)."
    mksquashfs "${CHROOT_DIR}" "${IMAGE_DIR}/casper/filesystem.squashfs" \
        -noappend -no-duplicates -no-recovery -wildcards \
        -e "boot/*" -e "proc/*" -e "sys/*" -e "dev/*" -e "run/*" \
        -e "tmp/*" -e "var/cache/apt/archives/*" -e "root/*" >>"${LOG_FILE}" 2>&1 \
        || { log_err "mksquashfs a echoue."; return 1; }
    printf '%s' "$(du -sx --block-size=1 "${CHROOT_DIR}" | cut -f1)" > "${IMAGE_DIR}/casper/filesystem.size"

    # 3. Copie du noyau et de l'initrd.
    local kver; kver="$(cd "${CHROOT_DIR}/boot" && ls vmlinuz-* | head -1 | sed 's/vmlinuz-//')"
    cp "${CHROOT_DIR}/boot/vmlinuz-${kver}" "${IMAGE_DIR}/casper/vmlinuz" || { log_err "Copie du noyau echouee."; return 1; }
    cp "${CHROOT_DIR}/boot/initrd.img-${kver}" "${IMAGE_DIR}/casper/initrd" || { log_err "Copie de l'initrd echouee."; return 1; }
    log_info "Noyau ${kver} et initrd copies."

    # 4. Configuration grub (menu de demarrage).
    cat > "${IMAGE_DIR}/boot/grub/grub.cfg" <<GRUBCFG
search --set=root --file /casper/filesystem.squashfs
set default=0
set timeout=10
menuentry "Omni Console (live)" {
    linux /casper/vmlinuz boot=casper quiet splash ---
    initrd /casper/initrd
}
menuentry "Omni Console (debug serie)" {
    linux /casper/vmlinuz boot=casper console=ttyS0,115200 console=tty0 ---
    initrd /casper/initrd
}
menuentry "Omni Console (mode securise)" {
    linux /casper/vmlinuz boot=casper nomodeset quiet ---
    initrd /casper/initrd
}
GRUBCFG

    # 5. Chargeur UEFI (moderne).
    grub-mkstandalone --format=x86_64-efi --output="${IMAGE_DIR}/EFI/boot/bootx64.efi" \
        --locales="" --fonts="" "boot/grub/grub.cfg=${IMAGE_DIR}/boot/grub/grub.cfg" >>"${LOG_FILE}" 2>&1 \
        || { log_err "grub-mkstandalone UEFI a echoue."; return 1; }

    # Image EFI (partition FAT contenant le chargeur UEFI).
    ( cd "${IMAGE_DIR}/EFI/boot" && \
      dd if=/dev/zero of=efiboot.img bs=1M count=10 2>/dev/null && \
      mkfs.vfat efiboot.img >/dev/null 2>&1 && \
      LC_CTYPE=C mmd -i efiboot.img efi efi/boot && \
      LC_CTYPE=C mcopy -i efiboot.img bootx64.efi ::efi/boot/ ) >>"${LOG_FILE}" 2>&1 \
        || { log_err "Creation de l'image EFI echouee."; return 1; }

    # 6. Chargeur BIOS (ancien).
    grub-mkstandalone --format=i386-pc --output="${IMAGE_DIR}/boot/grub/core.img" \
        --install-modules="linux normal iso9660 biosdisk memdisk search tar ls" \
        --modules="linux normal iso9660 biosdisk search" \
        --locales="" --fonts="" "boot/grub/grub.cfg=${IMAGE_DIR}/boot/grub/grub.cfg" >>"${LOG_FILE}" 2>&1 \
        || { log_err "grub-mkstandalone BIOS a echoue."; return 1; }
    cat /usr/lib/grub/i386-pc/cdboot.img "${IMAGE_DIR}/boot/grub/core.img" > "${IMAGE_DIR}/boot/grub/bios.img" 2>>"${LOG_FILE}" \
        || { log_err "Assemblage bios.img echoue."; return 1; }

    # 7. Assemblage de l'ISO hybride (BIOS + UEFI).
    log_info "Assemblage de l'ISO (xorriso)."
    xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames -volid "${ISO_VOLID}" \
        -output "${OUTPUT_DIR}/${ISO_NAME}" \
        -eltorito-boot boot/grub/bios.img -no-emul-boot -boot-load-size 4 -boot-info-table \
        --eltorito-catalog boot/grub/boot.cat \
        --grub2-boot-info --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
        -partition_offset 16 \
        -eltorito-alt-boot -e EFI/boot/efiboot.img -no-emul-boot -isohybrid-gpt-basdat \
        "${IMAGE_DIR}" >>"${LOG_FILE}" 2>&1 \
        || { log_err "xorriso a echoue. Voir le journal."; return 1; }

    if [[ ! -f "${OUTPUT_DIR}/${ISO_NAME}" ]]; then log_err "ISO non produite."; return 1; fi
    local isotaille; isotaille="$(du -sh "${OUTPUT_DIR}/${ISO_NAME}" | awk '{print $1}')"
    log_ok "Etape 6/6 terminee : ISO produite (${isotaille})."
    log_info "ISO : ${OUTPUT_DIR}/${ISO_NAME}"
}

main() {
    require_root "$@"; prepare_workspace
    log_info "=== Debut du build Omni Console ==="
    clean_previous
    step_check_dependencies
    step_open_base_iso
    step_enter_system
    step_install_omni
    step_apply_settings
    step_build_iso
    log_ok "=== Build Omni Console termine ==="
    log_info "Journal complet : ${LOG_FILE}"
}
main "$@"
