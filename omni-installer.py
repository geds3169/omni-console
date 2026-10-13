#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Console - Installateur graphique (v3)
===========================================
Demarre directement depuis la cle (pas de mode live), pose le systeme sur le
disque choisi, puis rend la main : retirer la cle, redemarrer.

Plan du fichier :
  1. Constantes, traductions (fr/en/de/pt), tables de localisation
  2. Outils systeme : journal, execution de commandes, detection des disques
  3. Fonctions pures et testables : plan de partitionnement, fichiers de
     localisation, configuration de grub
  4. Installation : toute la logique, sans aucune interface (classe Installation)
  5. Interface : fenetre, pages, lecteur de musique, clavier virtuel

Regles suivies partout :
  - aucune commande n'est lancee autrement que par lancer(), qui la note dans
    /var/log/omni-installation.log : en cas d'echec, la raison est dans ce journal ;
  - le support de demarrage et tout disque en cours d'usage sont refuses, meme
    si l'interface est contournee ;
  - la logique (classe Installation) ne depend pas de Tk : elle se teste seule.
"""

import glob
import math
import os
import queue
import shlex
import shutil
import signal
import subprocess
import textwrap
import threading
import time
import traceback
import tkinter as tk
from tkinter import font as tkfont

COL_BG      = "#0d0221"
COL_PANEL   = "#1a0a3a"
COL_MAGENTA = "#ff2e97"
COL_CYAN    = "#2de2e6"
COL_TEXT    = "#f5f5ff"
COL_DIM     = "#8a7fb5"
COL_AMBER   = "#ff9e2c"
COL_DANGER  = "#ff4d4d"
COL_OK      = "#3ddc84"
COL_SELECT  = "#39ff14"  # vert fluo flashy pour selection
FONT_NAME = "DejaVu Sans"


T = {
    "fr": {
        "slides": [
            ("Bienvenue sur Omni Console", "Votre console de jeu prete a l'emploi."),
            ("Votre profil joueur", "Au premier demarrage, creez votre profil."),
            ("Reseau et affichage", "Connectez le Wi-Fi ou l'Ethernet, reglez l'ecran."),
            ("Cle Bluetooth", "Ajoutez une cle Bluetooth si besoin, puis configurez-la."),
            ("Manettes et Joy-Con", "Branchez, appuyez, jouez. Sans configuration."),
            ("Vos comptes de jeu", "Ajoutez Steam, Epic, GOG a votre profil."),
            ("Tous vos jeux reunis", "Toutes vos boutiques au meme endroit."),
            ("Plusieurs joueurs", "Chacun son profil, ses sauvegardes, son temps de jeu."),
            ("Discord et TeamSpeak", "Parlez avec vos amis pendant le jeu."),
            ("Overlay en jeu", "Desactivez-le pour les jeux qui ne l'aiment pas."),
            ("Mises a jour automatiques", "La console s'entretient toute seule."),
            ("Controle parental", "Age et temps de jeu regles par profil."),
        ],
        "welcome": "Bienvenue", "choose_lang": "Choisissez votre langue et votre region.",
        "language": "Langue", "keyboard": "Clavier", "timezone": "Fuseau horaire",
        "region": "Region", "city": "Ville", "next": "Suivant", "back": "Retour",
        "disk_title": "Disque d'installation", "disk_sub": "Choisissez le disque ou installer Omni Console.",
        "disk_warn": "Le disque choisi sera entierement efface.", "no_disk": "Aucun disque detecte.",
        "confirm_title": "Confirmation",
        "confirm_msg": "Omni Console va etre installe sur {d}.\n\nTout le contenu de ce disque sera efface definitivement.\nCette action est irreversible.",
        "erase_install": "Effacer et installer", "recap_lang": "Langue", "recap_kb": "Clavier",
        "recap_tz": "Fuseau horaire", "recap_disk": "Disque", "installing": "Installation en cours",
        "done_title": "Installation terminee", "done_msg": "Retirez la cle USB apres extinction, puis rallumez la console.",
        "reboot": "Redemarrer", "shutdown": "Eteindre", "prep": "Preparation du disque...", "part": "Partitionnement...",
        "format": "Formatage...", "copy": "Copie du systeme Omni...", "boot": "Installation du demarrage...",
        "settings": "Application des reglages...", "finished": "Installation terminee.",
        "boot_media": "support de demarrage, protege", "size": "Taille"},
    "en": {
        "slides": [
            ("Welcome to Omni Console", "Your ready-to-play game console."),
            ("Your player profile", "On first start, create your profile."),
            ("Network and display", "Connect Wi-Fi or Ethernet, adjust the screen."),
            ("Bluetooth dongle", "Add a Bluetooth dongle if needed, then set it up."),
            ("Controllers and Joy-Con", "Plug in, press, play. No setup."),
            ("Your game accounts", "Add Steam, Epic, GOG to your profile."),
            ("All your games together", "Every store in one place."),
            ("Multiple players", "Each with their profile, saves and playtime."),
            ("Discord and TeamSpeak", "Talk with friends while gaming."),
            ("In-game overlay", "Turn it off for games that dislike it."),
            ("Automatic updates", "The console maintains itself."),
            ("Parental controls", "Age rating and playtime set per profile."),
        ],
        "welcome": "Welcome", "choose_lang": "Choose your language and region.",
        "language": "Language", "keyboard": "Keyboard", "timezone": "Time zone",
        "region": "Region", "city": "City", "next": "Next", "back": "Back",
        "disk_title": "Installation disk", "disk_sub": "Choose the disk to install Omni Console on.",
        "disk_warn": "The chosen disk will be completely erased.", "no_disk": "No disk detected.",
        "confirm_title": "Confirmation",
        "confirm_msg": "Omni Console will be installed on {d}.\n\nAll data on this disk will be permanently erased.\nThis action cannot be undone.",
        "erase_install": "Erase and install", "recap_lang": "Language", "recap_kb": "Keyboard",
        "recap_tz": "Time zone", "recap_disk": "Disk", "installing": "Installing",
        "done_title": "Installation complete", "done_msg": "Remove the USB drive, then restart the console.",
        "reboot": "Restart", "shutdown": "Shut down", "prep": "Preparing disk...", "part": "Partitioning...",
        "format": "Formatting...", "copy": "Copying Omni system...", "boot": "Installing bootloader...",
        "settings": "Applying settings...", "finished": "Installation complete.",
        "boot_media": "boot media, protected", "size": "Size"},
    "de": {
        "slides": [
            ("Willkommen bei Omni Console", "Ihre spielfertige Konsole."),
            ("Ihr Spielerprofil", "Erstellen Sie beim ersten Start Ihr Profil."),
            ("Netzwerk und Anzeige", "WLAN oder Ethernet verbinden, Bildschirm einstellen."),
            ("Bluetooth-Stick", "Bei Bedarf Bluetooth-Stick hinzufuegen und einrichten."),
            ("Controller und Joy-Con", "Anschliessen, druecken, spielen. Ohne Einrichtung."),
            ("Ihre Spielkonten", "Steam, Epic, GOG zu Ihrem Profil hinzufuegen."),
            ("Alle Spiele vereint", "Alle Shops an einem Ort."),
            ("Mehrere Spieler", "Jeder mit Profil, Speicherstaenden und Spielzeit."),
            ("Discord und TeamSpeak", "Sprechen Sie mit Freunden beim Spielen."),
            ("In-Game-Overlay", "Fuer Spiele deaktivieren, die es nicht moegen."),
            ("Automatische Updates", "Die Konsole wartet sich selbst."),
            ("Kindersicherung", "Altersfreigabe und Spielzeit pro Profil."),
        ],
        "welcome": "Willkommen", "choose_lang": "Waehlen Sie Ihre Sprache und Region.",
        "language": "Sprache", "keyboard": "Tastatur", "timezone": "Zeitzone",
        "region": "Region", "city": "Stadt", "next": "Weiter", "back": "Zurueck",
        "disk_title": "Installationsdatentraeger", "disk_sub": "Waehlen Sie den Datentraeger fuer Omni Console.",
        "disk_warn": "Der gewaehlte Datentraeger wird vollstaendig geloescht.", "no_disk": "Kein Datentraeger erkannt.",
        "confirm_title": "Bestaetigung",
        "confirm_msg": "Omni Console wird auf {d} installiert.\n\nAlle Daten auf diesem Datentraeger werden dauerhaft geloescht.\nDiese Aktion kann nicht rueckgaengig gemacht werden.",
        "erase_install": "Loeschen und installieren", "recap_lang": "Sprache", "recap_kb": "Tastatur",
        "recap_tz": "Zeitzone", "recap_disk": "Datentraeger", "installing": "Installation laeuft",
        "done_title": "Installation abgeschlossen", "done_msg": "Entfernen Sie den USB-Stick und starten Sie neu.",
        "reboot": "Neu starten", "shutdown": "Herunterfahren", "prep": "Datentraeger wird vorbereitet...", "part": "Partitionierung...",
        "format": "Formatierung...", "copy": "Omni-System wird kopiert...", "boot": "Bootloader wird installiert...",
        "settings": "Einstellungen werden angewendet...", "finished": "Installation abgeschlossen.",
        "boot_media": "Startmedium, geschuetzt", "size": "Groesse"},
    "pt": {
        "slides": [
            ("Bem-vindo ao Omni Console", "A sua consola pronta a jogar."),
            ("O seu perfil de jogador", "No primeiro arranque, crie o seu perfil."),
            ("Rede e ecra", "Ligue o Wi-Fi ou Ethernet, ajuste o ecra."),
            ("Pen Bluetooth", "Adicione uma pen Bluetooth se necessario e configure-a."),
            ("Comandos e Joy-Con", "Ligue, prima, jogue. Sem configuracao."),
            ("As suas contas de jogo", "Adicione Steam, Epic, GOG ao seu perfil."),
            ("Todos os jogos juntos", "Todas as lojas num so lugar."),
            ("Varios jogadores", "Cada um com perfil, jogos guardados e tempo de jogo."),
            ("Discord e TeamSpeak", "Fale com os amigos enquanto joga."),
            ("Overlay no jogo", "Desative-o para jogos que nao gostam dele."),
            ("Atualizacoes automaticas", "A consola mantem-se sozinha."),
            ("Controlo parental", "Idade e tempo de jogo definidos por perfil."),
        ],
        "welcome": "Bem-vindo", "choose_lang": "Escolha o seu idioma e regiao.",
        "language": "Idioma", "keyboard": "Teclado", "timezone": "Fuso horario",
        "region": "Regiao", "city": "Cidade", "next": "Seguinte", "back": "Voltar",
        "disk_title": "Disco de instalacao", "disk_sub": "Escolha o disco onde instalar o Omni Console.",
        "disk_warn": "O disco escolhido sera completamente apagado.", "no_disk": "Nenhum disco detetado.",
        "confirm_title": "Confirmacao",
        "confirm_msg": "O Omni Console sera instalado em {d}.\n\nTodo o conteudo deste disco sera apagado definitivamente.\nEsta acao e irreversivel.",
        "erase_install": "Apagar e instalar", "recap_lang": "Idioma", "recap_kb": "Teclado",
        "recap_tz": "Fuso horario", "recap_disk": "Disco", "installing": "A instalar",
        "done_title": "Instalacao concluida", "done_msg": "Retire a pen USB e reinicie a consola.",
        "reboot": "Reiniciar", "shutdown": "Desligar", "prep": "A preparar o disco...", "part": "Particionamento...",
        "format": "Formatacao...", "copy": "A copiar o sistema Omni...", "boot": "A instalar o arranque...",
        "settings": "A aplicar as definicoes...", "finished": "Instalacao concluida.",
        "boot_media": "suporte de arranque, protegido", "size": "Tamanho"},
}


# Textes ajoutes en v3 (ecran d'erreur, disques trop petits, etapes). Meme
# regle que le reste : pas d'accents, pour ne dependre d'aucune police.
T_AJOUTS = {
    "fr": {"step_of": "etape {n} sur {m}", "retry": "Recommencer",
           "err_title": "Installation interrompue",
           "err_msg": "L'installation n'a pas pu aller au bout. Rien n'a ete lance sur le disque de la cle.",
           "err_log": "Detail technique : {f}",
           "disk_small": "trop petit ({m} Go minimum)",
           "system": "Preparation du systeme...", "account": "Creation de la session de jeu..."},
    "en": {"step_of": "step {n} of {m}", "retry": "Start over",
           "err_title": "Installation interrupted",
           "err_msg": "The installation could not be completed. Nothing was changed on the USB drive.",
           "err_log": "Technical details: {f}",
           "disk_small": "too small ({m} GB minimum)",
           "system": "Preparing the system...", "account": "Creating the game session..."},
    "de": {"step_of": "Schritt {n} von {m}", "retry": "Neu beginnen",
           "err_title": "Installation unterbrochen",
           "err_msg": "Die Installation konnte nicht abgeschlossen werden. Der USB-Stick wurde nicht veraendert.",
           "err_log": "Technische Details: {f}",
           "disk_small": "zu klein (mindestens {m} GB)",
           "system": "System wird vorbereitet...", "account": "Spielsitzung wird erstellt..."},
    "pt": {"step_of": "passo {n} de {m}", "retry": "Recomecar",
           "err_title": "Instalacao interrompida",
           "err_msg": "Nao foi possivel concluir a instalacao. A pen USB nao foi alterada.",
           "err_log": "Detalhe tecnico: {f}",
           "disk_small": "demasiado pequeno (minimo {m} GB)",
           "system": "A preparar o sistema...", "account": "A criar a sessao de jogo..."},
}
for _lg, _textes in T_AJOUTS.items():
    T[_lg].update(_textes)

# Langue -> locale du systeme installe. Les quatre locales sont generees
# dans l'image par omni-build.sh (etape locales) : en ajouter une ici impose de
# l'ajouter la-bas aussi.
LOCALES = {"fr": "fr_FR.UTF-8", "en": "en_US.UTF-8", "de": "de_DE.UTF-8", "pt": "pt_PT.UTF-8"}

# Disposition de clavier (nom XKB, identique pour X) -> nom de la console texte.
KEYMAPS_CONSOLE = {"fr": "fr", "us": "us", "de": "de", "pt": "pt-latin1", "be": "be-latin1"}

# Taille minimale d'un disque cible, quand la taille du systeme n'est pas connue.
# Quand elle l'est (casper/filesystem.size, ecrit par le build), le minimum se
# calcule : le systeme doit tenir avec une marge, plus la place des jeux.
GIB = 1024 ** 3
DISQUE_MINI_INCONNU = 16 * GIB     # sans mesure du systeme
DISQUE_MINI_ABSOLU = 12 * GIB      # jamais en dessous, meme si le systeme est petit
PLACE_MINI_JEUX = 4 * GIB          # EFI + partition de donnees
MARGE_SYSTEME = 1.3                # 30 % de marge pour les mises a jour

LANGUES = [
    ("Francais", "fr", "fr", "Europe", "Paris"),
    ("English", "en", "us", "America", "New_York"),
    ("Deutsch", "de", "de", "Europe", "Berlin"),
    ("Portugues", "pt", "pt", "Europe", "Lisbon"),
]
CLAVIERS = ["fr", "us", "de", "pt", "be", "ch"]

def lire_fuseaux():
    """Fuseaux horaires {region: [villes]} lus par timedatectl, ou dans /usr/share/zoneinfo en repli."""
    regions = {}
    try:
        out = subprocess.run(["timedatectl", "list-timezones"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            for z in out.stdout.strip().split("\n"):
                if "/" in z:
                    r, v = z.split("/", 1)
                    regions.setdefault(r, []).append(v)
            if regions:
                for r in regions:
                    regions[r].sort()
                return regions
    except Exception:
        pass
    base = "/usr/share/zoneinfo"
    for r in ["Africa", "America", "Antarctica", "Asia", "Atlantic",
              "Australia", "Europe", "Indian", "Pacific"]:
        d = os.path.join(base, r)
        if os.path.isdir(d):
            for root, _, files in os.walk(d):
                for f in files:
                    regions.setdefault(r, []).append(
                        os.path.relpath(os.path.join(root, f), d))
    for r in regions:
        regions[r].sort()
    return regions


# ===========================================================================
# Supports de demarrage : on ne doit JAMAIS proposer d'effacer le disque
# depuis lequel la console a demarre. On le cherche par plusieurs voies, car
# Ventoy passe par un fichier ISO, ce qui brouille les pistes.
# ===========================================================================
def _disque_parent(peripherique):
    """Remonte d'une partition (/dev/sda1) ou d'un loop a son disque (/dev/sda)."""
    if not peripherique:
        return ""
    nom = os.path.basename(peripherique)
    chemin = _sortie(["lsblk", "-no", "PKNAME", "/dev/" + nom])
    if chemin:
        return "/dev/" + chemin.split("\n")[0].strip()
    if os.path.exists("/dev/" + nom):
        return "/dev/" + nom
    return ""


def disques_de_demarrage():
    """Liste des disques a proteger : celui du systeme live, et pour Ventoy
    celui qui contient le fichier ISO."""
    proteges = set()

    # 1. Montages classiques du support live
    for point in ("/cdrom", "/run/live/medium", "/isodevice", "/lib/live/mount/medium", "/media/cdrom"):
        src = _sortie(["findmnt", "-n", "-o", "SOURCE", point])
        for ligne in src.split("\n"):
            ligne = ligne.strip()
            if not ligne.startswith("/dev/"):
                continue
            # Ventoy et les ISO montees passent par un peripherique loop :
            # on remonte alors au fichier, puis au disque qui le contient.
            if ligne.startswith("/dev/loop"):
                fichier = _sortie(["losetup", "-n", "-O", "BACK-FILE", ligne])
                if fichier:
                    porteur = _sortie(["findmnt", "-n", "-o", "SOURCE", "-T", fichier])
                    d = _disque_parent(porteur.split("\n")[0] if porteur else "")
                    if d:
                        proteges.add(d)
                continue
            d = _disque_parent(ligne)
            if d:
                proteges.add(d)

    # 2. Tout disque dont une partition porte un montage du systeme live
    table = _sortie(["lsblk", "-nr", "-o", "NAME,PKNAME,MOUNTPOINT"])
    for ligne in table.split("\n"):
        champs = ligne.split()
        if len(champs) < 3:
            continue
        parent, montage = champs[1], " ".join(champs[2:])
        if montage in ("/cdrom", "/run/live/medium", "/isodevice") or montage.startswith("/run/media/"):
            if parent:
                proteges.add("/dev/" + parent)

    # 3. Filet supplementaire : le peripherique indique par le noyau au demarrage
    try:
        with open("/proc/cmdline") as f:
            for mot in f.read().split():
                if mot.startswith(("live-media=", "cdrom-detect/try-usb=", "iso-scan/filename=")):
                    valeur = mot.split("=", 1)[1]
                    if valeur.startswith("/dev/"):
                        d = _disque_parent(valeur)
                        if d:
                            proteges.add(d)
    except Exception:
        pass

    return proteges



# ===========================================================================
# 2. Outils systeme : journal, execution de commandes, disques
# ===========================================================================
JOURNAL_INSTALL = "/var/log/omni-installation.log"
ETAT_INSTALL = "/var/log/omni-installation.etat"
OPTIONS_IMAGE = "/usr/local/share/omni/options-image.conf"
DOSSIER_SYSTEME = "/usr/local/share/omni/systeme"   # fichiers de session poses par omni-build.sh
DOSSIERS_MUSIQUE = ("/usr/local/share/omni/musique", "/usr/local/share/omni")
DOSSIER_SONS = "/usr/local/share/omni/sons"


class ErreurInstall(RuntimeError):
    """Echec d'une etape de l'installation. Le message est montre au joueur."""


def journaliser(texte):
    """Ajoute une ligne horodatee au journal de l'installation.

    Silencieux si le journal est illisible : une erreur de journalisation ne
    doit jamais interrompre une installation."""
    try:
        os.makedirs(os.path.dirname(JOURNAL_INSTALL), exist_ok=True)
        with open(JOURNAL_INSTALL, "a", encoding="utf-8", errors="replace") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), texte))
    except OSError:
        pass


def lancer(cmd, tolerant=False, timeout=None):
    """Lance une commande, la note dans le journal et renvoie le resultat.

    Une commande qui echoue leve ErreurInstall, sauf si tolerant=True : on
    renvoie alors le resultat (ou None si la commande n'a pas pu demarrer).
    C'est la seule porte d'entree vers le systeme : toute commande, reussie ou
    non, laisse une trace."""
    journaliser("$ " + " ".join(shlex.quote(c) for c in cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        journaliser("  IMPOSSIBLE : %s" % e)
        if tolerant:
            return None
        raise ErreurInstall("%s : %s" % (cmd[0], e)) from e
    sortie = ((r.stdout or "") + (r.stderr or "")).strip()
    if sortie:
        journaliser(textwrap.indent(sortie[-1500:], "  "))
    if r.returncode != 0:
        journaliser("  code de retour %d" % r.returncode)
        if not tolerant:
            raison = (r.stderr or r.stdout or "").strip()[-160:] or "code %d" % r.returncode
            raise ErreurInstall("%s : %s" % (" ".join(cmd[:3]), raison))
    return r


def _sortie(cmd):
    """Sortie d'une commande, chaine vide si elle echoue (lecture seule)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def lire_options_image(chemin=None):
    """Options fixees par omni-build.sh pour cette image, une CLE=VALEUR par ligne.

    Elles decident par exemple de la console serie. Fichier absent : aucune
    option (comportement de production)."""
    options = {}
    try:
        with open(chemin or OPTIONS_IMAGE, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne and not ligne.startswith("#") and "=" in ligne:
                    cle, valeur = ligne.split("=", 1)
                    options[cle.strip()] = valeur.strip()
    except OSError:
        pass
    return options


def chercher_musique():
    """Premier fichier audio de la musique d'installation, ou chaine vide.

    Le build depose la musique dans DOSSIERS_MUSIQUE[0] ; l'ancien emplacement
    (a la racine du dossier omni) reste cherche pour les images deja faites."""
    for dossier in DOSSIERS_MUSIQUE:
        for motif in ("*.ogg", "*.mp3", "*.wav"):
            trouves = sorted(glob.glob(os.path.join(dossier, motif)))
            if trouves:
                return trouves[0]
    return ""


def lire_taille_systeme():
    """Taille du systeme a copier en octets, 0 si inconnue.

    Le build ecrit cette valeur dans casper/filesystem.size : elle permet une
    vraie barre de progression pendant la copie, sans rien estimer."""
    for chemin in ("/cdrom/casper/filesystem.size", "/run/live/medium/casper/filesystem.size"):
        try:
            with open(chemin, encoding="utf-8") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            continue
    return 0


def octets_utilises(chemin):
    """Octets occupes sur le systeme de fichiers qui porte chemin."""
    st = os.statvfs(chemin)
    return (st.f_blocks - st.f_bfree) * st.f_frsize


def uuid_de(partition):
    """UUID d'une partition formatee (lu par blkid)."""
    return lancer(["blkid", "-s", "UUID", "-o", "value", partition]).stdout.strip()


def nom_partition(disque, numero):
    """Chemin de la partition numero d'un disque : /dev/sda -> /dev/sda3,
    /dev/nvme0n1 ou /dev/mmcblk0 -> ...p3 (le nom finit par un chiffre)."""
    return disque + (("p" + str(numero)) if disque[-1].isdigit() else str(numero))


def lister_disques():
    """Disques candidats a l'installation, ou liste vide si lsblk echoue.

    On ne propose JAMAIS de disque invente : une liste vide affiche « aucun
    disque detecte », ce qui est vrai. Ecartes : loop, zram, lecteurs optiques,
    disques en lecture seule. Les disques trop petits sont listes avec
    petit=True (affiches mais non selectionnables)."""
    disques = []
    mini = disque_minimal_octets()
    sortie = _sortie(["lsblk", "-dbn", "-P", "-o", "NAME,SIZE,MODEL,TYPE,RM,RO"])
    for ligne in sortie.splitlines():
        try:
            champs = dict(tok.split("=", 1) for tok in shlex.split(ligne) if "=" in tok)
            octets = int(champs.get("SIZE", "0"))
        except ValueError:
            continue
        nom = champs.get("NAME", "")
        if champs.get("TYPE") != "disk" or nom.startswith(("zram", "loop", "sr")):
            continue
        if champs.get("RO", "0") == "1" or octets < 4 * 1024 ** 3:
            continue
        amovible = champs.get("RM", "0") == "1"
        modele = champs.get("MODEL", "").strip() or "Disque"
        disques.append({"chemin": "/dev/" + nom, "octets": octets, "taille": taille_lisible(octets),
                        "modele": modele + ("  (USB)" if amovible else ""), "amovible": amovible,
                        "petit": octets < mini, "mini_go": math.ceil(mini / GIB)})
    return disques


def taille_lisible(octets):
    """12345678901 -> « 11 Go »."""
    for unite, seuil in (("To", 1024 ** 4), ("Go", 1024 ** 3), ("Mo", 1024 ** 2)):
        if octets >= seuil:
            return "%.0f %s" % (octets / seuil, unite)
    return "%d o" % octets


def points_de_montage(disque):
    """Points de montage reels des partitions d'un disque (le swap actif est ignore :
    il se desactive, il n'interdit rien)."""
    montages = []
    for ligne in _sortie(["lsblk", "-nr", "-o", "PATH,MOUNTPOINT", disque]).splitlines():
        morceaux = ligne.split(" ", 1)
        if len(morceaux) == 2 and morceaux[1].strip() and morceaux[1].strip() != "[SWAP]":
            montages.append(morceaux[1].strip())
    return montages


def desactiver_swap(disque):
    """Coupe l'espace d'echange actif sur ce disque : le live Ubuntu active seul
    une partition swap de GPT, et wipefs refuse alors de l'effacer."""
    for ligne in _sortie(["lsblk", "-nr", "-o", "PATH,MOUNTPOINT", disque]).splitlines():
        morceaux = ligne.split(" ", 1)
        if len(morceaux) == 2 and morceaux[1].strip() == "[SWAP]":
            lancer(["swapoff", morceaux[0]], tolerant=True)


# ===========================================================================
# 3. Fonctions pures : testables sans disque ni interface
# ===========================================================================
def disque_minimal_octets(taille_systeme=None):
    """Taille minimale d'un disque cible, en octets.

    Systeme mesure (casper/filesystem.size) : sa taille plus 30 % de marge, plus
    la place de l'EFI et des jeux, sans descendre sous DISQUE_MINI_ABSOLU. Sinon
    DISQUE_MINI_INCONNU. Ainsi un disque de test assez grand n'est jamais
    refuse par un seuil arbitraire."""
    if taille_systeme is None:
        taille_systeme = lire_taille_systeme()
    if taille_systeme:
        return max(DISQUE_MINI_ABSOLU, int(taille_systeme * MARGE_SYSTEME) + PLACE_MINI_JEUX)
    return DISQUE_MINI_INCONNU


def plan_partitions(octets, taille_systeme=None):
    """Calcule la fin de la partition systeme pour un disque de `octets` octets.

    La partition systeme vaut la moitie du disque, bornee entre 10 et 30 Gio :
    sur un disque de 2 To, un ratio fixe gaspillerait des centaines de Go pour
    un systeme qui en occupe une dizaine. Si la taille du systeme est connue,
    la partition lui laisse 30 % de marge. Tout le reste va aux jeux.
    Leve ErreurInstall si le disque est trop petit."""
    if taille_systeme is None:
        taille_systeme = lire_taille_systeme()
    mini = disque_minimal_octets(taille_systeme)
    if octets < mini:
        raise ErreurInstall("Disque trop petit : %d Go minimum" % math.ceil(mini / GIB))
    go = octets / GIB
    gio = int(max(10, min(30, go / 2)))
    if taille_systeme:
        gio = max(gio, math.ceil(taille_systeme * MARGE_SYSTEME / GIB))
    gio = min(gio, int(go - 3))        # au moins 3 Gio pour les jeux
    return {"efi_fin": "514MiB", "sys_fin": "%dGiB" % gio}


def keymap_console(clavier, langue):
    """Nom de la disposition pour la console texte (/etc/vconsole.conf)."""
    if clavier == "ch":
        return "fr_CH" if langue == "fr" else "sg"
    return KEYMAPS_CONSOLE.get(clavier, "us")


def fichiers_localisation(choix):
    """Contenu des fichiers de localisation du systeme installe.

    Renvoie {chemin absolu dans le systeme installe: contenu} d'apres les choix
    du joueur (clavier, langue, fuseau). Fonction pure : aucun acces disque.

    Le clavier est ecrit trois fois, car trois mecanismes le lisent :
    /etc/default/keyboard (console et installateurs), /etc/vconsole.conf
    (console texte systemd) et la configuration d'Xorg (la session graphique)."""
    clavier = choix.get("clavier", "fr")
    langue = choix.get("code_langue", "fr")
    variante = "fr" if (clavier == "ch" and langue == "fr") else ""
    return {
        "/etc/default/keyboard":
            'XKBMODEL="pc105"\nXKBLAYOUT="%s"\nXKBVARIANT="%s"\nXKBOPTIONS=""\nBACKSPACE="guess"\n'
            % (clavier, variante),
        "/etc/vconsole.conf": "KEYMAP=%s\n" % keymap_console(clavier, langue),
        "/etc/X11/xorg.conf.d/00-keyboard.conf":
            'Section "InputClass"\n    Identifier "omni-clavier"\n    MatchIsKeyboard "on"\n'
            '    Option "XkbModel" "pc105"\n    Option "XkbLayout" "%s"\n    Option "XkbVariant" "%s"\n'
            'EndSection\n' % (clavier, variante),
        "/etc/default/locale": "LANG=%s\n" % LOCALES.get(langue, "en_US.UTF-8"),
        "/etc/timezone": (choix.get("fuseau") or "Europe/Paris") + "\n",
    }


def ecrire_localisation(cible, choix):
    """Ecrit les fichiers de localisation dans le systeme installe, pose le lien
    /etc/localtime (UTC si le fuseau est inconnu) et reactive la console texte
    que le build avait masquee."""
    for chemin, contenu in fichiers_localisation(choix).items():
        dest = cible + chemin
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(contenu)
    fuseau = choix.get("fuseau") or "Europe/Paris"
    if not os.path.isfile(os.path.join(cible, "usr/share/zoneinfo", fuseau)):
        journaliser("fuseau inconnu du systeme installe : %s, UTC retenu" % fuseau)
        fuseau = "UTC"
        with open(cible + "/etc/timezone", "w", encoding="utf-8") as f:
            f.write("UTC\n")
    lien = cible + "/etc/localtime"
    if os.path.lexists(lien):
        os.remove(lien)
    os.symlink("/usr/share/zoneinfo/" + fuseau, lien)
    demasquer_services(cible, ("console-setup.service", "keyboard-setup.service"))


def demasquer_services(cible, noms):
    """Retire le masquage (lien vers /dev/null) de services dans le systeme installe."""
    for nom in noms:
        lien = os.path.join(cible, "etc/systemd/system", nom)
        if os.path.islink(lien) and os.readlink(lien) == "/dev/null":
            os.remove(lien)


def contenu_grub_defaut(options, theme=False):
    """Contenu de /etc/default/grub du systeme installe.

    Demarrage direct sans menu (un appui sur Maj ou Echap l'affiche).
    options["CONSOLE_SERIE"] == "1" ajoute la console serie, indispensable pour
    diagnostiquer une console dont on ne peut pas ouvrir de terminal ;
    plymouth.ignore-serial-consoles evite que l'ecran de demarrage disparaisse
    parce qu'une console serie est declaree."""
    args = ["quiet", "splash", "loglevel=0"]
    if options.get("CONSOLE_SERIE") == "1":
        args += ["console=tty0", "console=ttyS0,115200", "plymouth.ignore-serial-consoles"]
    lignes = ["GRUB_DEFAULT=0", "GRUB_TIMEOUT=0", "GRUB_TIMEOUT_STYLE=hidden",
              "GRUB_RECORDFAIL_TIMEOUT=0", "GRUB_DISABLE_OS_PROBER=true", "GRUB_DISABLE_RECOVERY=true",
              'GRUB_DISTRIBUTOR="Omni Console"',
              'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(args), 'GRUB_CMDLINE_LINUX=""']
    if theme:
        lignes += ["GRUB_TERMINAL_OUTPUT=gfxterm", "GRUB_GFXMODE=auto", "GRUB_GFXPAYLOAD_LINUX=keep",
                   "GRUB_THEME=/boot/grub/themes/omni/theme.txt"]
    return "\n".join(lignes) + "\n"


def groupes_existants(cible, voulus):
    """Parmi `voulus`, les groupes qui existent dans le systeme installe.

    useradd echoue en bloc si un seul groupe manque : mieux vaut un compte
    sans ce groupe qu'une installation qui s'arrete a la derniere etape."""
    presents = set()
    try:
        with open(cible + "/etc/group", encoding="utf-8") as f:
            presents = {ligne.split(":", 1)[0] for ligne in f}
    except OSError:
        pass
    manquants = [g for g in voulus if g not in presents]
    if manquants:
        journaliser("groupes absents, ignores : %s" % ", ".join(manquants))
    return [g for g in voulus if g in presents]


# ===========================================================================
# 4. Installation : toute la logique, sans interface
# ===========================================================================
class Installation:
    """Installe Omni Console sur un disque, etape par etape.

    `signaler(pct, cle, detail)` est appele a chaque avancee : l'interface
    traduit `cle` (une cle de T) et affiche `detail`. Cette classe ne touche
    ni a Tk ni a la langue, ce qui permet de la tester sur un faux disque.

    Mode d'emploi : Installation(choix, proteges, signaler).executer(disque).
    Les montages sont toujours defaits en sortie, que l'installation reussisse
    ou non (bloc finally de executer)."""

    # (cle de traduction, pourcentage atteint a la fin de l'etape)
    ETAPES = (("prep", 5), ("part", 14), ("format", 28), ("copy", 70),
              ("system", 80), ("boot", 88), ("account", 96), ("finished", 100))
    GROUPES_JOUEUR = ("audio", "video", "input", "plugdev", "render", "bluetooth")

    def __init__(self, choix, proteges, signaler, cible="/target"):
        """Memorise les choix, le support protege et le rappel de progression ; lit les options de l'image et le mode UEFI/BIOS."""
        self.choix = choix
        self.proteges = set(proteges)
        self.signaler = signaler
        self.cible = cible
        self.options = lire_options_image()
        self.efi = os.path.isdir("/sys/firmware/efi")
        self.montages = []
        self.disque = ""
        self.sys_uuid = ""

    # ----- etapes et montages -----
    def etape(self, cle, detail=""):
        """Annonce l'etape `cle` : l'interface affiche son libelle et son numero."""
        numero = [c for c, _ in self.ETAPES].index(cle) + 1
        pct = self.ETAPES[numero - 2][1] if numero > 1 else 0
        journaliser("=== etape %d/%d : %s" % (numero, len(self.ETAPES), cle))
        try:
            with open(ETAT_INSTALL, "w", encoding="utf-8") as f:
                f.write("etape %d : %s\n" % (numero, cle))
        except OSError:
            pass
        self.signaler(pct, cle, detail)

    def chroot(self, *args, tolerant=False):
        """Lance une commande dans le systeme installe."""
        return lancer(["chroot", self.cible] + list(args), tolerant=tolerant)

    def monter(self, source, destination, *options):
        """Monte et se souvient du montage, pour le defaire dans l'ordre inverse."""
        os.makedirs(destination, exist_ok=True)
        lancer(["mount"] + list(options) + [source, destination])
        self.montages.append(destination)

    def demonter(self):
        """Defait tous les montages (le dernier monte en premier). Tente un
        demontage normal, puis differe : sans cela, le disque peut rester occupe."""
        for chemin in reversed(self.montages):
            r = lancer(["umount", chemin], tolerant=True)
            if r is None or r.returncode != 0:
                lancer(["umount", "-l", chemin], tolerant=True)
        self.montages = []

    # ----- deroulement -----
    def executer(self, disque):
        """Deroule toute l'installation sur `disque` (ex. /dev/sda)."""
        self.disque = disque
        journaliser("##### installation sur %s, choix : %s, options image : %s, mode %s"
                    % (disque, self.choix, self.options, "UEFI" if self.efi else "BIOS"))
        try:
            self.etape("prep")
            self.garde_fous(disque)
            self.etape("part")
            self.partitionner(disque)
            self.etape("format")
            self.formater(disque)
            self.etape("copy")
            self.copier(disque)
            self.etape("system")
            self.preparer_systeme(disque)
            self.etape("boot")
            self.installer_demarrage(disque)
            self.etape("account")
            self.configurer_joueur()
            self.etape("finished")
            self.finaliser()
        finally:
            self.demonter()

    def garde_fous(self, disque):
        """Refus ferme, avant toute ecriture : disque invalide, support de
        demarrage, disque en cours d'usage ou trop petit."""
        if not disque or not disque.startswith("/dev/") or not os.path.exists(disque):
            raise ErreurInstall("Disque cible invalide : %r" % disque)
        if disque in self.proteges or disque in disques_de_demarrage():
            raise ErreurInstall("Refus : %s est le support de demarrage" % disque)
        desactiver_swap(disque)
        occupes = points_de_montage(disque)
        if occupes:
            raise ErreurInstall("Refus : %s est en cours d'utilisation (%s)" % (disque, ", ".join(occupes[:3])))
        plan_partitions(int(lancer(["blockdev", "--getsize64", disque]).stdout.strip() or 0))

    def partitionner(self, disque):
        """Table GPT, quatre partitions : BIOS boot, EFI, systeme, donnees.

        Le meme schema sert aux machines UEFI et BIOS : le disque demarre sur
        les deux, et suit le joueur chez un ami."""
        plan = plan_partitions(int(lancer(["blockdev", "--getsize64", disque]).stdout.strip()))
        lancer(["wipefs", "-a", disque])
        parted = ["parted", "-s", disque]
        lancer(parted + ["mklabel", "gpt"])
        lancer(parted + ["mkpart", "BIOSBOOT", "1MiB", "2MiB"])
        lancer(parted + ["set", "1", "bios_grub", "on"])
        lancer(parted + ["mkpart", "EFI", "fat32", "2MiB", plan["efi_fin"]])
        lancer(parted + ["set", "2", "esp", "on"])
        lancer(parted + ["mkpart", "OMNI_SYS", "ext4", plan["efi_fin"], plan["sys_fin"]])
        lancer(parted + ["mkpart", "OMNI_DATA", "ext4", plan["sys_fin"], "100%"])
        lancer(["partprobe", disque], tolerant=True)
        lancer(["udevadm", "settle", "--timeout=15"], tolerant=True)
        # on attend les fichiers de peripherique plutot qu'un delai au hasard
        for _ in range(40):
            if all(os.path.exists(nom_partition(disque, n)) for n in (1, 2, 3, 4)):
                return
            time.sleep(0.5)
        raise ErreurInstall("Les partitions de %s n'apparaissent pas" % disque)

    def formater(self, disque):
        """Formate EFI (FAT32), systeme et donnees (ext4). Seulement 1 % reserve
        sur la partition de jeux : le reglage par defaut (5 %) gaspillerait
        100 Go sur un disque de 2 To."""
        lancer(["mkfs.vfat", "-F", "32", "-n", "OMNI_EFI", nom_partition(disque, 2)])
        lancer(["mkfs.ext4", "-F", "-m", "2", "-L", "OMNI_SYS", nom_partition(disque, 3)])
        lancer(["mkfs.ext4", "-F", "-m", "1", "-L", "OMNI_DATA", nom_partition(disque, 4)])

    def source_systeme(self):
        """Dossier ou lire le systeme a copier : /rofs (monte par casper), sinon
        le squashfs du support, monte ici."""
        if os.path.ismount("/rofs"):
            return "/rofs"
        for chemin in ("/cdrom/casper/filesystem.squashfs", "/run/live/medium/casper/filesystem.squashfs"):
            if os.path.isfile(chemin):
                self.monter(chemin, "/mnt/squash", "-t", "squashfs", "-o", "loop,ro")
                return "/mnt/squash"
        raise ErreurInstall("Le systeme a installer est introuvable sur le support")

    def copier(self, disque):
        """Monte les partitions et copie le systeme, avec une progression MESUREE :
        octets deja ecrits sur le disque / taille du systeme lue dans l'image."""
        self.monter(nom_partition(disque, 3), self.cible)
        self.monter(nom_partition(disque, 2), self.cible + "/boot/efi")
        source = self.source_systeme()
        total = lire_taille_systeme()
        base = octets_utilises(self.cible)
        journaliser("$ cp -ax %s/. %s/ (%d octets attendus)" % (source, self.cible, total))
        with open(JOURNAL_INSTALL, "a", encoding="utf-8") as journal:
            proc = subprocess.Popen(["cp", "-ax", source + "/.", self.cible + "/"],
                                    stdout=journal, stderr=journal)
            while proc.poll() is None:
                time.sleep(2)
                fait = octets_utilises(self.cible) - base
                if total:
                    ratio = max(0.0, min(1.0, fait / float(total)))
                    self.signaler(28 + int(42 * ratio), "copy",
                                  "%.1f / %.1f Go" % (fait / 1024 ** 3, total / 1024 ** 3))
        if proc.returncode != 0:
            raise ErreurInstall("La copie du systeme a echoue (voir %s)" % JOURNAL_INSTALL)

    def preparer_systeme(self, disque):
        """fstab, montages pour le chroot, puis noyau et initramfs PROPRES.

        Point critique : jamais l'initramfs du live. Il contient les scripts
        casper, qui cherchent un media USB au demarrage ; le systeme installe
        ne demarrerait pas sans la cle. On retire casper, puis on genere un
        vrai initramfs avec les outils du systeme installe."""
        efi_uuid = uuid_de(nom_partition(disque, 2))
        self.sys_uuid = uuid_de(nom_partition(disque, 3))
        dat_uuid = uuid_de(nom_partition(disque, 4))
        # nofail : si la partition de jeux manque (SSD retire), la console demarre
        # quand meme, au lieu de tomber sur un shell de secours que personne ne verra
        with open(self.cible + "/etc/fstab", "w", encoding="utf-8") as f:
            f.write("UUID=%s / ext4 defaults,errors=remount-ro 0 1\n" % self.sys_uuid)
            f.write("UUID=%s /boot/efi vfat umask=0077 0 1\n" % efi_uuid)
            f.write("UUID=%s /omni-data ext4 defaults,nofail,x-systemd.device-timeout=10 0 2\n" % dat_uuid)
        # la partition de donnees est montee MAINTENANT : sans cela, les dossiers
        # crees plus bas iraient sur la partition systeme et seraient masques au
        # demarrage par la vraie partition, vide et appartenant a root
        self.monter(nom_partition(disque, 4), self.cible + "/omni-data")
        for nom in ("dev", "proc", "sys"):
            self.monter("/" + nom, self.cible + "/" + nom, "--bind")
        self.monter("/dev/pts", self.cible + "/dev/pts", "--bind")
        if self.efi and os.path.isdir("/sys/firmware/efi/efivars"):
            # sans efivars, grub-install ne peut pas inscrire l'entree de demarrage ;
            # son absence n'est pas fatale (le chargeur « amovible » reste pose)
            try:
                self.monter("efivarfs", self.cible + "/sys/firmware/efi/efivars", "-t", "efivarfs")
            except (ErreurInstall, OSError) as e:
                journaliser("efivars non monte : %s" % e)

        self.chroot("bash", "-c", "apt-get purge -y casper lupin-casper 2>/dev/null; true", tolerant=True)
        for reste in ("/etc/initramfs-tools/scripts/casper-bottom",
                      "/usr/share/initramfs-tools/scripts/casper-bottom",
                      "/usr/share/initramfs-tools/scripts/casper",
                      "/usr/share/initramfs-tools/hooks/casper"):
            shutil.rmtree(self.cible + reste, ignore_errors=True)

        modules = sorted(glob.glob(self.cible + "/usr/lib/modules/*"))
        kver = os.path.basename(modules[-1]) if modules else ""
        if not kver:
            raise ErreurInstall("Aucun noyau dans le systeme copie")
        if not os.path.exists(self.cible + "/boot/vmlinuz-" + kver):
            # filet : reinstaller le paquet du noyau remet vmlinuz en place (necessite le reseau)
            self.chroot("apt-get", "install", "--reinstall", "-y", "linux-image-" + kver)
        if not os.path.exists(self.cible + "/boot/vmlinuz-" + kver):
            raise ErreurInstall("Noyau (vmlinuz) absent : le systeme ne pourrait pas demarrer")
        self.chroot("update-initramfs", "-c", "-k", kver)
        initrd = self.cible + "/boot/initrd.img-" + kver
        if not os.path.exists(initrd):
            raise ErreurInstall("Initramfs absent apres generation")
        if "casper" in _sortie(["lsinitramfs", initrd]):
            raise ErreurInstall("L'initramfs contient encore les scripts du live")

        ecrire_localisation(self.cible, self.choix)

    def installer_demarrage(self, disque):
        """Installe grub pour UEFI ET BIOS, quel que soit le mode de l'installation.

        Le mode actuel est obligatoire, l'autre se tente sans bloquer : le
        disque demarre sur les deux familles de machines. Le chargeur EFI est
        aussi pose au chemin « amovible » (EFI/BOOT/BOOTX64.EFI), que tout
        micrologiciel sait trouver meme s'il a oublie ses entrees."""
        theme = os.path.isfile(self.cible + "/boot/grub/themes/omni/theme.txt")
        with open(self.cible + "/etc/default/grub", "w", encoding="utf-8") as f:
            f.write(contenu_grub_defaut(self.options, theme))
        efi = ["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--recheck"]
        bios = ["grub-install", "--target=i386-pc", "--recheck", "--boot-directory=/boot", disque]
        if self.efi:
            self.chroot(*efi, "--bootloader-id=OMNI")
            self.chroot(*efi, "--removable", tolerant=True)
            self.chroot(*bios, tolerant=True)
        else:
            self.chroot(*bios)
            self.chroot(*efi, "--removable", tolerant=True)
        self.chroot("update-grub")
        self.chroot("grub-editenv", "/boot/grub/grubenv", "unset", "recordfail", tolerant=True)
        self._grub_de_secours()

    def _grub_de_secours(self):
        """Si update-grub n'a produit aucune entree, ecrit un grub.cfg minimal :
        mieux vaut un demarrage sans fioritures que pas de demarrage."""
        cfg = self.cible + "/boot/grub/grub.cfg"
        try:
            with open(cfg, encoding="utf-8") as f:
                if "menuentry" in f.read():
                    return
        except OSError:
            pass
        noyaux = sorted(glob.glob(self.cible + "/boot/vmlinuz-*"))
        initrds = sorted(glob.glob(self.cible + "/boot/initrd.img-*"))
        if not (noyaux and initrds):
            raise ErreurInstall("grub n'a produit aucune entree et aucun noyau n'est present")
        kver = os.path.basename(noyaux[-1]).replace("vmlinuz-", "")
        journaliser("grub.cfg vide : ecriture du fichier de secours")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write('set timeout=0\nmenuentry "Omni Console" {\n'
                    "    search --no-floppy --fs-uuid --set=root %s\n"
                    "    linux /boot/vmlinuz-%s root=UUID=%s ro quiet splash loglevel=0\n"
                    "    initrd /boot/initrd.img-%s\n}\n" % (self.sys_uuid, kver, self.sys_uuid, kver))

    def configurer_joueur(self):
        """Compte du joueur, dossier de donnees, session graphique supervisee.

        Le compte n'a AUCUN privilege : seul le guichet a intentions
        (/usr/local/sbin/omni-plateforme, regle sudoers posee par le build)
        peut agir en administrateur. Les fichiers de session viennent de
        l'image (DOSSIER_SYSTEME) : un seul endroit pour les ecrire, le build."""
        c = self.cible
        # (1) l'installateur ne doit pas survivre dans le systeme installe
        a_retirer = ["/etc/systemd/system/omni-x.service", "/etc/systemd/system/omni-debug.service",
                     "/root/.xinitrc", "/usr/local/bin/omni-installer", "/usr/local/bin/omni-session",
                     "/etc/systemd/system/default.target"]
        a_retirer += [p[len(c):] for p in glob.glob(c + "/etc/systemd/system/*.wants/omni-*.service")]
        for chemin in a_retirer:
            try:
                os.remove(c + chemin)
            except OSError:
                pass

        # (2) compte du joueur, sans mot de passe ni droits d'administration
        groupes = groupes_existants(c, self.GROUPES_JOUEUR)
        self.chroot("useradd", "-m", "-s", "/bin/bash", *(["-G", ",".join(groupes)] if groupes else []), "omni")
        self.chroot("bash", "-c", "passwd -d omni; passwd -u omni 2>/dev/null; true", tolerant=True)
        self.chroot("gpasswd", "-d", "omni", "sudo", tolerant=True)
        regle = c + "/etc/sudoers.d/omni-plateforme"
        if not os.path.isfile(regle):
            raise ErreurInstall("Regle sudoers du guichet absente de l'image")
        os.chmod(regle, 0o440)
        with open(c + "/etc/hostname", "w", encoding="utf-8") as f:
            f.write("omni\n")
        with open(c + "/etc/hosts", "w", encoding="utf-8") as f:
            f.write("127.0.0.1\tlocalhost\n127.0.1.1\tomni\n::1\tlocalhost ip6-localhost ip6-loopback\n")

        # (3) dossier de donnees : cree et donne au joueur. Jeux, profils et
        # sauvegardes vivent ici, jamais sur la partition systeme : une
        # restauration du systeme ne doit rien effacer.
        for sous in ("jeux", "jeux/gog", "roms", "saves", "profils", "cache", "compat"):
            os.makedirs(c + "/omni-data/" + sous, exist_ok=True)
        self.chroot("chown", "-R", "omni:omni", "/omni-data")
        self.chroot("chmod", "755", "/omni-data")
        essai = self.chroot("sudo", "-u", "omni", "test", "-w", "/omni-data/profils", tolerant=True)
        if essai is None or essai.returncode != 0:
            raise ErreurInstall("Le dossier de donnees n'est pas accessible au joueur")
        self.chroot("bash", "-c",
                    "install -d -o omni -g omni /home/omni/.omni/journaux && "
                    "ln -sfn /omni-data/profils /home/omni/.omni/profils && "
                    "ln -sfn /omni-data/cache /home/omni/.omni/cache && "
                    "ln -sfn /omni-data/jeux /home/omni/Jeux")

        # (4) session graphique : UN service supervise par systemd. Si
        # l'interface tombe, systemd la relance ; le joueur ne voit jamais un terminal.
        self.poser_fichier_systeme("omni-session-joueur", "/usr/local/bin/omni-session-joueur", 0o755)
        self.poser_fichier_systeme("omni-console.service", "/etc/systemd/system/omni-console.service", 0o644)
        self.poser_fichier_systeme("openbox-autostart", "/home/omni/.config/openbox/autostart", 0o644)
        self.chroot("chown", "-R", "omni:omni", "/home/omni")
        self.chroot("systemctl", "enable", "omni-console.service")
        self.chroot("systemctl", "set-default", "graphical.target")
        # plus d'autologin en console : la session passe par le service
        shutil.rmtree(c + "/etc/systemd/system/getty@tty1.service.d", ignore_errors=True)
        for lien in ("/etc/systemd/system/getty@tty1.service",
                     "/etc/systemd/system/getty.target.wants/getty@tty1.service"):
            if os.path.islink(c + lien) and os.readlink(c + lien) == "/dev/null":
                os.remove(c + lien)
        # (5) console serie : le service est deja dans l'image si l'option est active ;
        # sinon on retire son lien pour ne pas ouvrir de connexion inutile
        if self.options.get("CONSOLE_SERIE") != "1":
            try:
                os.remove(c + "/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service")
            except OSError:
                pass

    def poser_fichier_systeme(self, nom, destination, mode):
        """Copie un fichier de DOSSIER_SYSTEME (fourni par le build) dans le
        systeme installe. Un fichier absent est une image incomplete : on le dit."""
        source = os.path.join(DOSSIER_SYSTEME, nom)
        if not os.path.isfile(source):
            raise ErreurInstall("Fichier de session absent de l'image : %s" % nom)
        dest = self.cible + destination
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(source, dest)
        os.chmod(dest, mode)

    def finaliser(self):
        """Garde une copie du journal dans le systeme installe, puis ecrit tout sur le disque."""
        try:
            os.makedirs(self.cible + "/var/log", exist_ok=True)
            shutil.copyfile(JOURNAL_INSTALL, self.cible + "/var/log/omni-installation.log")
        except OSError:
            pass
        lancer(["sync"], tolerant=True)



# ===========================================================================
# 5. Interface
# ===========================================================================
class OmniInstaller(tk.Tk):
    """Fenetre de l'installateur : echelle, polices, lecteur de musique, banniere, navigation entre pages."""
    def __init__(self):
        """Plein ecran, echelle d'apres l'ecran, premiere page (langue). Lance la musique et la surveillance de l'ecran."""
        super().__init__()
        self.title("Omni Console - Installateur")
        self.configure(bg=COL_BG)
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        # --- Echelle : sur une television, une taille fixe donne un texte
        # minuscule. Tout est calcule a partir d'une reference 1280x720, puis
        # agrandi selon l'ecran. Le joueur peut encore ajuster dans la banniere.
        self.zoom = 1.0
        self.base = max(0.9, min(3.0, min(sw / 1280.0, sh / 720.0)))
        self._construire_polices()

        self.lang = "fr"
        self.fuseaux = lire_fuseaux()
        self.proteges = disques_de_demarrage()
        self.choix = {"langue": "Francais", "code_langue": "fr", "clavier": "fr",
                      "region": "Europe", "ville": "Paris", "fuseau": "Europe/Paris",
                      "disque": None}
        self.container = tk.Frame(self, bg=COL_BG)
        self.container.pack(fill="both", expand=True)
        self.page_actuelle = None
        self.page_actuelle_classe = None
        self.page_actuelle_kw = {}
        self.install = None     # etat de l'installation en cours (voir PageInstallation)
        self.afficher_banniere()
        self.audio_proc = None
        self.volume = 60
        self.musique_on = True
        self.creer_player()
        self.demarrer_musique()
        self.montrer_page(PageLangue)
        self._taille_connue = (sw, sh)
        self.bind("<Configure>", self._ecran_change)
        self.after(3000, self._surveiller)

    def _ecran_change(self, event=None):
        """L'ecran a change de taille : on refait la mise en page a la bonne
        echelle, et on remet la barre du lecteur par-dessus."""
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if (sw, sh) == getattr(self, "_taille_connue", (0, 0)):
            self._player.lift()
            return
        self._taille_connue = (sw, sh)
        self.geometry(f"{sw}x{sh}+0+0")
        self.base = max(0.9, min(3.0, min(sw / 1280.0, sh / 720.0)))
        self._construire_polices()
        self.afficher_banniere()
        self._player.destroy()
        self.creer_player()
        if getattr(self, "page_actuelle_classe", None) is not None:
            self.montrer_page(self.page_actuelle_classe, **self.page_actuelle_kw)

    def _surveiller(self):
        """La barre du lecteur doit rester visible et la musique continuer,
        y compris pendant l'installation."""
        try:
            self._player.lift()
            if self.musique_on and (self.audio_proc is None or self.audio_proc.poll() is not None):
                self.audio_proc = None
                self.demarrer_musique()
        except Exception:
            pass
        self.after(3000, self._surveiller)

    # ---- Echelle et polices ----
    def px(self, n):
        return max(1, int(round(n * self.base * self.zoom)))

    def _construire_polices(self):
        e = self.base * self.zoom
        self.f_titre = tkfont.Font(family=FONT_NAME, size=-int(34 * e), weight="bold")
        self.f_soustitre = tkfont.Font(family=FONT_NAME, size=-int(18 * e))
        self.f_normal = tkfont.Font(family=FONT_NAME, size=-int(14 * e))
        self.f_petit = tkfont.Font(family=FONT_NAME, size=-int(11 * e))
        self.f_mono = tkfont.Font(family="DejaVu Sans Mono", size=-int(11 * e))

    def regler_zoom(self, delta):
        """Agrandit ou reduit toute l'interface, television oblige."""
        self.zoom = max(0.7, min(2.0, self.zoom + delta))
        self._construire_polices()
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.configure(text="%d %%" % round(self.zoom * 100))
        self.afficher_banniere()
        if getattr(self, "page_actuelle_classe", None) is not None:
            self.montrer_page(self.page_actuelle_classe, **self.page_actuelle_kw)

    # ---- Lecteur de musique (player en haut a droite) ----
    def creer_player(self):
        """Petit lecteur en haut a droite : lecture/pause, volume, taille de l'affichage, clavier virtuel."""
        pf = tk.Frame(self, bg=COL_PANEL, highlightbackground=COL_CYAN,
                      highlightthickness=1)
        pf.place(relx=1.0, x=-self.px(20), y=self.px(16), anchor="ne")
        self._player = pf
        # Bouton lecture/pause
        self.btn_play = tk.Label(pf, text="\u23F8", font=self.f_normal,
                                 fg=COL_CYAN, bg=COL_PANEL, cursor="hand2", padx=10)
        self.btn_play.pack(side="left")
        self.btn_play.bind("<Button-1>", lambda e: self.toggle_musique())
        # Titre
        tk.Label(pf, text="\u266A Pont de verre", font=self.f_petit,
                 fg=COL_TEXT, bg=COL_PANEL, padx=6).pack(side="left")
        # Volume - / +
        moins = tk.Label(pf, text="\u2013", font=self.f_normal,
                         fg=COL_DIM, bg=COL_PANEL, cursor="hand2", padx=4)
        moins.pack(side="left"); moins.bind("<Button-1>", lambda e: self.regler_volume(-15))
        self.lbl_vol = tk.Label(pf, text=f"{self.volume}%", font=self.f_petit,
                                fg=COL_CYAN, bg=COL_PANEL, width=4)
        self.lbl_vol.pack(side="left")
        plus = tk.Label(pf, text="+", font=self.f_normal,
                        fg=COL_DIM, bg=COL_PANEL, cursor="hand2", padx=4)
        plus.pack(side="left"); plus.bind("<Button-1>", lambda e: self.regler_volume(15))
        # Taille de l'affichage (televisions)
        tk.Label(pf, text="A", font=self.f_petit, fg=COL_DIM, bg=COL_PANEL, padx=2).pack(side="left")
        pt = tk.Label(pf, text="\u2013", font=self.f_normal, fg=COL_DIM, bg=COL_PANEL,
                      cursor="hand2", padx=3)
        pt.pack(side="left"); pt.bind("<Button-1>", lambda e: self.regler_zoom(-0.1))
        self.lbl_zoom = tk.Label(pf, text="100 %", font=self.f_petit, fg=COL_CYAN,
                                 bg=COL_PANEL, width=5)
        self.lbl_zoom.pack(side="left")
        gd = tk.Label(pf, text="+", font=self.f_normal, fg=COL_DIM, bg=COL_PANEL,
                      cursor="hand2", padx=3)
        gd.pack(side="left"); gd.bind("<Button-1>", lambda e: self.regler_zoom(0.1))
        # Bouton clavier virtuel
        self.clavier_actif = None
        kb = tk.Label(pf, text="\u2328", font=self.f_normal, fg=COL_CYAN,
                      bg=COL_PANEL, cursor="hand2", padx=8)
        kb.pack(side="left")
        kb.bind("<Button-1>", lambda e: self.toggle_clavier())

    def toggle_clavier(self):
        # Ouvre/ferme un clavier virtuel lie au widget qui a le focus.
        """Ouvre ou ferme le clavier virtuel lie au champ qui a le focus."""
        if getattr(self, "clavier_actif", None) and self.clavier_actif.winfo_exists():
            self.clavier_actif.destroy()
            self.clavier_actif = None
            return
        cible = self.focus_get()
        if not isinstance(cible, tk.Entry):
            cible = None
        try:
            self.clavier_actif = ClavierVirtuel(self, cible if cible else self)
        except Exception:
            self.clavier_actif = None

    def _preparer_audio(self):
        """Le serveur de son a besoin d'un dossier d'execution. Sans lui, il ne
        demarre pas, et rien ne sort des haut-parleurs. On s'assure aussi que
        PipeWire tourne avant de lancer la musique."""
        if not os.environ.get("XDG_RUNTIME_DIR"):
            dossier = "/run/user/%d" % os.getuid()
            try:
                os.makedirs(dossier, exist_ok=True)
                os.chmod(dossier, 0o700)
            except Exception:
                dossier = "/tmp/omni-audio"
                os.makedirs(dossier, exist_ok=True)
            os.environ["XDG_RUNTIME_DIR"] = dossier
        if shutil.which("pipewire") and subprocess.run(
                ["pgrep", "-x", "pipewire"], capture_output=True).returncode != 0:
            for outil in ("pipewire", "wireplumber", "pipewire-pulse"):
                if shutil.which(outil):
                    try:
                        subprocess.Popen([outil], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
                    except Exception:
                        pass
            # on attend que le son reponde vraiment, plutot qu'un delai au hasard
            for _ in range(20):
                if subprocess.run(["pactl", "info"], capture_output=True).returncode == 0:
                    break
                time.sleep(0.5)

    def _cmd_audio(self):
        """Commande de lecture de la musique d'installation, ou None.

        Le fichier est cherche par chercher_musique() ; repli sur le dossier
        courant pour un essai hors ISO. Lecteurs essayes dans l'ordre : mpv,
        ffplay, cvlc."""
        chemin = chercher_musique()
        if not chemin:   # essai hors ISO
            locaux = sorted(glob.glob("./*.ogg") + glob.glob("./sons/pont_de_verre*.ogg"))
            chemin = locaux[0] if locaux else ""
        if not chemin:
            return None
        vol = self.volume / 100.0
        if shutil.which("mpv"):
            return ["mpv", "--no-video", "--loop", "--ao=pipewire,pulse,alsa",
                    "--volume=%d" % self.volume, "--really-quiet", chemin]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-loop", "0", "-autoexit",
                    "-volume", str(self.volume), "-loglevel", "quiet", chemin]
        if shutil.which("cvlc"):
            return ["cvlc", "--intf", "dummy", "--loop", "--gain=%s" % vol, chemin]
        return None

    def jouer_son(self, nom):
        """Joue un son court d'interface (hover/select/valid) sans bloquer."""
        f = "%s/omni-%s.ogg" % (DOSSIER_SONS, nom)
        if not os.path.exists(f):
            # repli test hors ISO
            alt = glob.glob("./sons/omni-%s.ogg" % nom) or glob.glob("./omni-%s.ogg" % nom)
            if not alt:
                return
            f = alt[0]
        try:
            if shutil.which("paplay"):
                subprocess.Popen(["paplay", f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif shutil.which("mpv"):
                subprocess.Popen(["mpv", "--no-video", "--really-quiet", "--volume=70", f],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def demarrer_musique(self):
        # le lecteur tourne a part, dans son propre groupe : ni l'installation
        # ni le demontage des systemes de fichiers ne doivent l'emporter
        """Lance la musique dans son propre groupe de processus : ni l'installation ni les demontages ne doivent l'emporter."""
        self.arreter_musique()
        self._preparer_audio()
        cmd = self._cmd_audio()
        if not cmd:
            return
        try:
            self.audio_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
            self.musique_on = True
            self.btn_play.configure(text="\u23F8")
        except Exception:
            self.audio_proc = None

    def arreter_musique(self):
        if self.audio_proc:
            try:
                os.killpg(os.getpgid(self.audio_proc.pid), signal.SIGTERM)
            except Exception:
                pass
            self.audio_proc = None

    def toggle_musique(self):
        # Etat reel = un processus tourne ?
        """Pause ou reprise de la musique (l'etat reel est un processus qui tourne)."""
        actif = self.audio_proc is not None
        if actif:
            self.arreter_musique()
            self.musique_on = False
            self.btn_play.configure(text="\u25B6")
        else:
            self.demarrer_musique()
            if self.audio_proc is not None:
                self.btn_play.configure(text="\u23F8")
            else:
                self.btn_play.configure(text="\u25B6")

    def regler_volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.lbl_vol.configure(text=f"{self.volume}%")
        if self.musique_on:
            self.demarrer_musique()

    def tr(self, cle):
        return T.get(self.lang, T["fr"]).get(cle, cle)

    def afficher_banniere(self):
        """Banniere du haut (soleil, titre, liseré), redessinee a chaque changement d'echelle."""
        if hasattr(self, "banniere") and self.banniere.winfo_exists():
            self.banniere.destroy()
        b = tk.Frame(self, bg=COL_BG, height=self.px(90))
        if hasattr(self, "container") and self.container.winfo_exists():
            b.pack(fill="x", side="top", before=self.container)
        else:
            b.pack(fill="x", side="top")
        b.pack_propagate(False)
        self.banniere = b
        s = tk.Canvas(b, width=self.px(70), height=self.px(70), bg=COL_BG, highlightthickness=0)
        s.place(x=self.px(40), y=self.px(12))
        for i, c in enumerate(["#ff9e2c", "#ff7e3d", "#ff5e5e", "#ff487f", "#ff3690", "#ff2e97"]):
            y = self.px(8) + i * self.px(9)
            s.create_rectangle(self.px(6), y, self.px(64), y + self.px(6), fill=c, outline="")
        tk.Label(b, text="OMNI CONSOLE", font=self.f_titre, fg=COL_MAGENTA, bg=COL_BG).place(
            x=self.px(125), y=self.px(22))
        tk.Frame(b, bg=COL_CYAN, height=self.px(3)).place(x=self.px(127), y=self.px(70), width=self.px(360))

    def montrer_page(self, PageClass, **kw):
        """Affiche une page (remplace la precedente). Les arguments nommes sont
        transmis a la page et memorises pour la redessiner si l'ecran change."""
        self.page_actuelle_classe = PageClass
        self.page_actuelle_kw = kw
        if self.page_actuelle is not None:
            self.page_actuelle.destroy()
        # Cadre exterieur qui remplit tout, avec le contenu centre dedans.
        self.page_actuelle = tk.Frame(self.container, bg=COL_BG)
        self.page_actuelle.pack(fill="both", expand=True)
        self.page_actuelle.grid_rowconfigure(0, weight=1)
        self.page_actuelle.grid_columnconfigure(0, weight=1)
        page = PageClass(self.page_actuelle, self, **kw)
        if getattr(PageClass, "PLEINE_LARGEUR", False):
            page.grid(row=0, column=0, sticky="nsew", padx=self.px(40), pady=self.px(20))
        else:
            page.grid(row=0, column=0)



def bouton(parent, texte, commande, couleur=COL_CYAN, largeur=18):
    """Bouton plein de l'installateur (survol, son), sous forme de Label."""
    app = parent.winfo_toplevel()
    police = getattr(app, "f_normal", (FONT_NAME, 14, "bold"))
    b = tk.Label(parent, text=texte, font=police,
                 fg=COL_BG, bg=couleur, width=largeur, pady=getattr(app, "px", lambda n: n)(10),
                 cursor="hand2")
    def _clic(e=None):
        try: app.jouer_son("valid")
        except Exception: pass
        commande()
    def _survol(e=None):
        b.configure(bg=COL_MAGENTA, fg=COL_TEXT)
        try: app.jouer_son("hover")
        except Exception: pass
    b.bind("<Button-1>", lambda e: _clic())
    b.bind("<Enter>", _survol)
    b.bind("<Leave>", lambda e: b.configure(bg=couleur, fg=COL_BG))
    return b


class PageLangue(tk.Frame):
    """Premiere page : langue, clavier, fuseau horaire (region puis ville)."""
    def __init__(self, parent, app):
        """Construit les trois colonnes de choix."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        tk.Label(self, text=app.tr("welcome"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 4))
        tk.Label(self, text=app.tr("choose_lang"), font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(anchor="w", pady=(0, app.px(20)))
        corps = tk.Frame(self, bg=COL_BG)
        corps.pack(fill="both", expand=True)

        col_l = tk.Frame(corps, bg=COL_BG)
        col_l.pack(side="left", fill="y", padx=(0, app.px(30)))
        tk.Label(col_l, text=app.tr("language"), font=app.f_normal, fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        self.var_langue = tk.StringVar(value=next(n for n, c, k, r, v in LANGUES if c == app.lang))
        for nom, code, clav, reg, vil in LANGUES:
            tk.Radiobutton(col_l, text=nom, variable=self.var_langue, value=nom,
                           font=app.f_normal, indicatoron=False, bd=0,
                           fg=COL_TEXT, bg=COL_PANEL, selectcolor=COL_MAGENTA,
                           activebackground=COL_MAGENTA, activeforeground=COL_BG,
                           anchor="w", width=14, padx=8, pady=4,
                           command=self.langue_choisie).pack(anchor="w", pady=1, fill="x")

        col_c = tk.Frame(corps, bg=COL_BG)
        col_c.pack(side="left", fill="y", padx=(0, app.px(30)))
        tk.Label(col_c, text=app.tr("keyboard"), font=app.f_normal, fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        self.var_clavier = tk.StringVar(value=app.choix["clavier"])
        for clav in CLAVIERS:
            tk.Radiobutton(col_c, text=clav.upper(), variable=self.var_clavier, value=clav,
                           font=app.f_normal, indicatoron=False, bd=0,
                           fg=COL_TEXT, bg=COL_PANEL, selectcolor=COL_MAGENTA,
                           activebackground=COL_MAGENTA, activeforeground=COL_BG,
                           anchor="w", width=6, padx=8, pady=4).pack(anchor="w", pady=1, fill="x")

        col_tz = tk.Frame(corps, bg=COL_BG)
        col_tz.pack(side="left", fill="both", expand=True)
        tk.Label(col_tz, text=app.tr("timezone"), font=app.f_normal, fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        tz = tk.Frame(col_tz, bg=COL_BG)
        tz.pack(fill="both", expand=True)

        cr = tk.Frame(tz, bg=COL_BG)
        cr.pack(side="left", fill="y", padx=(0, app.px(12)))
        tk.Label(cr, text=app.tr("region"), font=app.f_petit, fg=COL_DIM, bg=COL_BG).pack(anchor="w")
        self.list_region = tk.Listbox(cr, height=10, width=14, bg=COL_PANEL, fg=COL_TEXT,
            selectbackground=COL_MAGENTA, selectforeground=COL_TEXT, highlightthickness=0,
            bd=0, font=app.f_petit, exportselection=False)
        self.list_region.pack(fill="y")
        self.list_region.bind("<<ListboxSelect>>", self.region_choisie)

        cv = tk.Frame(tz, bg=COL_BG)
        cv.pack(side="left", fill="both", expand=True)
        tk.Label(cv, text=app.tr("city"), font=app.f_petit, fg=COL_DIM, bg=COL_BG).pack(anchor="w")
        cl = tk.Frame(cv, bg=COL_BG)
        cl.pack(fill="both", expand=True)
        sb = tk.Scrollbar(cl)
        sb.pack(side="right", fill="y")
        self.list_ville = tk.Listbox(cl, height=10, width=22, bg=COL_PANEL, fg=COL_TEXT,
            selectbackground=COL_MAGENTA, selectforeground=COL_TEXT, highlightthickness=0,
            bd=0, font=app.f_petit, exportselection=False, yscrollcommand=sb.set)
        self.list_ville.pack(side="left", fill="both", expand=True)
        sb.config(command=self.list_ville.yview)

        self.regions_tri = sorted(app.fuseaux.keys())
        for r in self.regions_tri:
            self.list_region.insert("end", r)
        if app.choix["region"] in self.regions_tri:
            idx = self.regions_tri.index(app.choix["region"])
            self.list_region.selection_set(idx)
            self.list_region.see(idx)
            self.remplir_villes(app.choix["region"], app.choix["ville"])

        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=app.px(16))
        bouton(bas, app.tr("next") + "  \u25B6", self.suivant).pack(side="right")

    def langue_choisie(self):
        """Change la langue de l'interface immediatement (la page est redessinee traduite)."""
        nom = self.var_langue.get()
        for n, code, clav, reg, vil in LANGUES:
            if n == nom:
                self.app.lang = code
                self.app.choix["code_langue"] = code
                self.app.choix["clavier"] = self.var_clavier.get()
                break
        self.app.montrer_page(PageLangue)

    def region_choisie(self, event=None):
        sel = self.list_region.curselection()
        if sel:
            self.remplir_villes(self.regions_tri[sel[0]])

    def remplir_villes(self, region, ville_defaut=None):
        """Remplit la liste des villes de la region choisie."""
        self.list_ville.delete(0, "end")
        villes = self.app.fuseaux.get(region, [])
        for v in villes:
            self.list_ville.insert("end", v)
        if ville_defaut and ville_defaut in villes:
            idx = villes.index(ville_defaut)
            self.list_ville.selection_set(idx)
            self.list_ville.see(idx)

    def suivant(self):
        """Enregistre langue, clavier et fuseau dans les choix, puis passe au choix du disque."""
        nom = self.var_langue.get()
        code = next(c for n, c, k, r, v in LANGUES if n == nom)
        self.app.choix["langue"] = nom
        self.app.choix["code_langue"] = code
        self.app.lang = code
        self.app.choix["clavier"] = self.var_clavier.get()
        sr = self.list_region.curselection()
        sv = self.list_ville.curselection()
        if sr:
            region = self.regions_tri[sr[0]]
            self.app.choix["region"] = region
            if sv:
                ville = self.list_ville.get(sv[0])
                self.app.choix["ville"] = ville
                self.app.choix["fuseau"] = f"{region}/{ville}"
        self.app.montrer_page(PageDisque)


class PageDisque(tk.Frame):
    """Choix du disque cible : le support de demarrage et les disques trop petits sont verrouilles."""
    def __init__(self, parent, app):
        """Construit la liste ; rien n'est coche au depart."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        # « AUCUN » plutot qu'une chaine vide : une variable vide met les boutons
        # dans un etat indetermine, qui a l'ecran ressemble a « coche » et ne
        # peut pas etre decoche. Sur un ecran de formatage, c'est dangereux.
        self.var_disque = tk.StringVar(value="AUCUN")
        tk.Label(self, text=app.tr("disk_title"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 4))
        tk.Label(self, text=app.tr("disk_sub"), font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(anchor="w", pady=(0, app.px(16)))
        tk.Label(self, text="\u26A0  " + app.tr("disk_warn"), font=app.f_normal, fg=COL_DANGER, bg=COL_BG).pack(anchor="w", pady=(0, app.px(16)))
        self.zone = tk.Frame(self, bg=COL_BG)
        self.zone.pack(fill="both", expand=True)
        self.charger_disques()
        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=app.px(16))
        bouton(bas, "\u25C0  " + app.tr("back"), lambda: app.montrer_page(PageLangue),
               couleur=COL_DIM, largeur=14).pack(side="left")
        self.btn_next = bouton(bas, app.tr("next") + "  \u25B6", self.suivant)
        self.btn_next.pack(side="right")

    def choisir(self, chemin):
        """Un seul disque coche a la fois, et rien de coche au depart."""
        self.var_disque.set(chemin)
        try:
            self.app.jouer_son("select")
        except Exception:
            pass
        for c, (marque, cadre) in self.marques.items():
            choisi = (c == chemin)
            marque.configure(text="\u25C9" if choisi else "\u25EF",
                             fg=COL_SELECT if choisi else COL_DIM)
            cadre.configure(bg=COL_PANEL)

    def charger_disques(self):
        """Dessine un disque par ligne (choix dessine, a deux etats seulement)."""
        self.marques = {}
        for w in self.zone.winfo_children():
            w.destroy()
        disques = lister_disques()
        if not disques:
            tk.Label(self.zone, text=self.app.tr("no_disk"), font=self.app.f_normal,
                     fg=COL_DIM, bg=COL_BG).pack(anchor="w")
            return
        for d in disques:
            protege = d["chemin"] in self.app.proteges or d["petit"]
            cadre = tk.Frame(self.zone, bg=COL_PANEL, padx=self.app.px(16), pady=self.app.px(12))
            cadre.pack(fill="x", pady=self.app.px(6))
            # Choix dessine par nous plutot qu'un bouton radio : Tk affiche un
            # etat intermediaire trompeur quand rien n'est selectionne, et sur
            # un ecran de formatage il faut deux etats, pas trois.
            marque = tk.Label(cadre, text="\U0001F512" if protege else "\u25EF",
                              font=self.app.f_normal,
                              fg=COL_AMBER if protege else COL_DIM, bg=COL_PANEL)
            marque.pack(side="left", padx=(0, self.app.px(12)))
            if not protege:
                self.marques[d["chemin"]] = (marque, cadre)
                for w in (cadre, marque):
                    w.bind("<Button-1>", lambda e, c=d["chemin"]: self.choisir(c))
                    w.configure(cursor="hand2")
            info = tk.Frame(cadre, bg=COL_PANEL)
            info.pack(side="left", fill="x", expand=True)
            l1 = tk.Label(info, text=f"{d['chemin']}  \u2014  {d['taille']}", font=self.app.f_normal,
                          fg=COL_DIM if protege else COL_TEXT, bg=COL_PANEL, anchor="w")
            l1.pack(anchor="w")
            if d["chemin"] in self.app.proteges:
                motif = self.app.tr("boot_media")
            elif d["petit"]:
                motif = self.app.tr("disk_small").format(m=d["mini_go"])
            else:
                motif = ""
            detail = d["modele"] + ("   \u2014  " + motif if motif else "")
            l2 = tk.Label(info, text=detail, font=self.app.f_petit,
                          fg=COL_AMBER if protege else COL_DIM,
                          bg=COL_PANEL, anchor="w")
            l2.pack(anchor="w")
            if not protege:
                for w in (info, l1, l2):
                    w.bind("<Button-1>", lambda e, c=d["chemin"]: self.choisir(c))
                    w.configure(cursor="hand2")

    def suivant(self):
        """Passe a la confirmation si un disque autorise est choisi, sinon fait clignoter le bouton."""
        choisi = self.var_disque.get()
        if not choisi or choisi == "AUCUN" or choisi in self.app.proteges:
            self.btn_next.configure(bg=COL_DANGER)
            self.after(300, lambda: self.btn_next.configure(bg=COL_CYAN))
            return
        self.app.choix["disque"] = choisi
        self.app.montrer_page(PageConfirmation)


class PageConfirmation(tk.Frame):
    """Recapitulatif et confirmation, avant toute ecriture sur le disque."""
    def __init__(self, parent, app):
        """Affiche l'avertissement d'effacement et le recapitulatif des choix."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        tk.Label(self, text=app.tr("confirm_title"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, app.px(16)))
        tk.Label(self, text=app.tr("confirm_msg").format(d=app.choix["disque"]), font=app.f_soustitre,
                 fg=COL_TEXT, bg=COL_BG, justify="left").pack(anchor="w", pady=(0, app.px(24)))
        recap = tk.Frame(self, bg=COL_PANEL, padx=app.px(20), pady=app.px(16))
        recap.pack(fill="x", pady=(0, app.px(16)))
        for label, val in [(app.tr("recap_lang"), app.choix["langue"]),
                           (app.tr("recap_kb"), app.choix["clavier"]),
                           (app.tr("recap_tz"), app.choix["fuseau"]),
                           (app.tr("recap_disk"), app.choix["disque"])]:
            l = tk.Frame(recap, bg=COL_PANEL)
            l.pack(fill="x", pady=2)
            tk.Label(l, text=f"{label} :", font=app.f_normal, fg=COL_CYAN, bg=COL_PANEL,
                     width=16, anchor="w").pack(side="left")
            tk.Label(l, text=str(val), font=app.f_normal, fg=COL_TEXT, bg=COL_PANEL, anchor="w").pack(side="left")
        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=app.px(16))
        bouton(bas, "\u25C0  " + app.tr("back"), lambda: app.montrer_page(PageDisque),
               couleur=COL_DIM, largeur=14).pack(side="left")
        bouton(bas, app.tr("erase_install"), lambda: app.montrer_page(PageInstallation),
               couleur=COL_DANGER, largeur=22).pack(side="right")



class PageInstallation(tk.Frame):
    """Pendant l'installation : diaporama pedagogique, barre de progression et
    etape en cours.

    L'installation tourne dans un fil (Installation.executer). Ce fil n'appelle
    JAMAIS Tk : il depose ses messages dans une file que cette page lit toutes
    les 150 ms depuis le fil principal.

    Son etat vit dans app.install, pas dans la page : si la page est redessinee
    (changement de taille de l'ecran, bouton de zoom), elle reprend l'etat
    courant et ne relance surtout PAS une seconde installation."""
    PLEINE_LARGEUR = True

    def __init__(self, parent, app):
        """Construit la page ; lance l'installation une seule fois (voir app.install)."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.index_diapo = 0
        tk.Label(self, text=app.tr("installing"), font=app.f_soustitre, fg=COL_TEXT, bg=COL_BG).pack(
            anchor="w", pady=(0, app.px(16)))
        # La zone de progression est posee AVANT la diapositive et ancree en
        # bas : quelle que soit la taille de la fenetre, elle reste visible.
        # C'est elle qui dit ce qui se passe, elle ne doit jamais etre rognee.
        pied = tk.Frame(self, bg=COL_BG)
        pied.pack(fill="x", side="bottom", pady=(app.px(8), 0))
        self.journal = tk.Label(pied, text="", font=app.f_normal, fg=COL_CYAN, bg=COL_BG, anchor="w")
        self.journal.pack(fill="x", anchor="w")
        ligne = tk.Frame(pied, bg=COL_BG)
        ligne.pack(fill="x")
        self.canvas = tk.Canvas(ligne, height=app.px(22), bg=COL_PANEL, highlightthickness=0)
        self.canvas.pack(side="left", fill="x", expand=True)
        self.barre = self.canvas.create_rectangle(0, 0, 0, app.px(22), fill=COL_CYAN, outline="")
        self.lbl_pct = tk.Label(ligne, text="0 %", font=app.f_normal, fg=COL_TEXT, bg=COL_BG, width=6)
        self.lbl_pct.pack(side="left")
        self.lbl_etape = tk.Label(pied, text="", font=app.f_petit, fg=COL_DIM, bg=COL_BG, anchor="w")
        self.lbl_etape.pack(fill="x", anchor="w")

        self.diapo_cadre = tk.Frame(self, bg=COL_PANEL)
        self.diapo_cadre.pack(fill="both", expand=True, pady=(0, app.px(16)), padx=app.px(20))
        self.diapo_cadre.pack_propagate(False)
        self.img = tk.Label(self.diapo_cadre, text="1", font=(FONT_NAME, -app.px(200), "bold"),
                            fg=COL_MAGENTA, bg=COL_PANEL)
        self.img.pack(pady=(app.px(16), 0))
        self.d_titre = tk.Label(self.diapo_cadre, text="", font=app.f_titre, fg=COL_CYAN, bg=COL_PANEL)
        self.d_titre.pack()
        self.d_desc = tk.Label(self.diapo_cadre, text="", font=app.f_soustitre, fg=COL_TEXT, bg=COL_PANEL)
        self.d_desc.pack(pady=(app.px(6), 0))

        if app.install is None:     # premiere construction : on lance, une seule fois
            app.install = {"file": queue.Queue(), "debut": time.time(), "pct": 0, "cle": "prep",
                           "detail": "", "fini": False}
            self._lancer_installation(app.install["file"])
        self.etat = app.install
        self._afficher()
        self.tourner()
        self.after(150, self._pomper)

    def _lancer_installation(self, file):
        """Demarre le fil d'installation. Il ne parle a l'interface que par `file`."""
        choix = dict(self.app.choix)
        proteges = set(self.app.proteges)

        def signaler(pct, cle, detail=""):
            file.put(("progres", pct, cle, detail))

        def travail():
            """Corps du fil d'installation : execute, puis depose « fin » ou « erreur » dans la file."""
            try:
                Installation(choix, proteges, signaler).executer(choix["disque"])
                file.put(("fin",))
            except ErreurInstall as e:
                journaliser("ECHEC : %s" % e)
                file.put(("erreur", str(e)))
            except Exception as e:  # imprevu : on garde sa trace pour le diagnostic
                journaliser("ECHEC IMPREVU : %r\n%s" % (e, traceback.format_exc()))
                file.put(("erreur", "Erreur imprevue : %s" % e))

        threading.Thread(target=travail, daemon=True).start()

    def _pomper(self):
        """Lit les messages du fil d'installation (fil principal uniquement)."""
        if not self.winfo_exists():
            return
        try:
            while True:
                msg = self.etat["file"].get_nowait()
                if msg[0] == "progres":
                    self.etat.update(pct=max(self.etat["pct"], msg[1]), cle=msg[2], detail=msg[3])
                    self._afficher()
                elif msg[0] == "fin":
                    self.etat["fini"] = True
                    self.etat.update(pct=100, cle="finished", detail="")
                    self._afficher()
                    self.after(1500, self._terminer, PageFin, {})
                    return
                elif msg[0] == "erreur":
                    self.etat["fini"] = True
                    self._terminer(PageErreur, {"message": msg[1]})
                    return
        except queue.Empty:
            pass
        self.after(150, self._pomper)

    def _terminer(self, classe, kw):
        """Fin de l'installation : l'etat est libere (une nouvelle tentative
        repartira de zero) et la page suivante s'affiche."""
        self.app.install = None
        self.app.montrer_page(classe, **kw)

    def _afficher(self):
        """Dessine l'etat courant : barre, libelle de l'etape, numero et duree."""
        e, app = self.etat, self.app
        largeur = self.canvas.winfo_width()
        self.canvas.coords(self.barre, 0, 0, largeur * e["pct"] / 100.0, app.px(22))
        self.lbl_pct.configure(text="%d %%" % e["pct"])
        self.journal.configure(text=(app.tr(e["cle"]) + (" " + e["detail"] if e["detail"] else "")))
        numero = [c for c, _ in Installation.ETAPES].index(e["cle"]) + 1
        ecoule = int(time.time() - e["debut"])
        self.lbl_etape.configure(text="%s   \u00b7   %d min %02d s" % (
            app.tr("step_of").format(n=numero, m=len(Installation.ETAPES)), ecoule // 60, ecoule % 60))

    def tourner(self):
        """Fait defiler le diaporama toutes les 4 secondes (l'heure de l'etape
        se met a jour au passage)."""
        if not self.winfo_exists():
            return
        slides = T.get(self.app.lang, T["fr"]).get("slides", [])
        if slides:
            t, d = slides[self.index_diapo % len(slides)]
            self.img.configure(text=str((self.index_diapo % len(slides)) + 1))
            self.d_titre.configure(text=t)
            self.d_desc.configure(text=d)
        self.index_diapo += 1
        if not self.etat["fini"]:
            self._afficher()
            self.after(4000, self.tourner)


def essayer_commandes(commandes):
    """Lance la premiere commande qui reussit parmi `commandes` (listes d'arguments).

    Renvoie True si l'une a abouti. Sert aux actions simples ; l'arret de la
    machine passe par arreter_machine(), plus tenace."""
    lancer(["sync"], tolerant=True)
    for cmd in commandes:
        r = lancer(cmd, tolerant=True, timeout=20)
        if r is not None and r.returncode == 0:
            return True
    return False


def arreter_machine(mode, attente_douce=10):
    """Eteint (mode « poweroff ») ou redemarre (mode « reboot ») la machine, jusqu'au bout.

    Dans la session live, l'arret normal peut rester bloque (invite « retirez le
    support » cachee derriere X, unite qui ne rend pas la main) : la machine virtuelle
    ne s'arretait jamais. On procede donc par paliers de plus en plus directs :
      1. arret propre, sans attendre sa fin (--no-block) ;
      2. arret force par systemd (-f), sans passer par les services ;
      3. arret immediat sans aucun service (-ff) ;
      4. appel noyau direct (sysrq), en dernier recours.
    Les disques sont synchronises et demontes avant, donc rien n'est perdu."""
    sysrq = {"poweroff": "o", "reboot": "b"}[mode]
    journaliser("##### arret demande : %s" % mode)
    lancer(["sync"], tolerant=True)
    # Les montages de la cible ne doivent plus exister : un disque encore occupe
    # est la premiere cause d'un arret qui n'aboutit pas.
    lancer(["umount", "-R", "-l", "/target"], tolerant=True)
    lancer(["sync"], tolerant=True)
    paliers = [(["systemctl", "--no-block", mode], attente_douce),
               (["systemctl", "-f", mode], 5),
               (["systemctl", "-ff", mode], 3)]
    for cmd, delai in paliers:
        lancer(cmd, tolerant=True, timeout=20)
        time.sleep(delai)       # si l'arret a reussi, on ne sort jamais de cette pause
        journaliser("arret : pas encore eteint apres %s" % " ".join(cmd))
    try:
        with open("/proc/sys/kernel/sysrq", "w") as f:
            f.write("1")
        with open("/proc/sysrq-trigger", "w") as f:
            f.write("s")        # sync
        with open("/proc/sysrq-trigger", "w") as f:
            f.write("u")        # remontage en lecture seule
        with open("/proc/sysrq-trigger", "w") as f:
            f.write(sysrq)      # arret ou redemarrage immediat
    except OSError as e:
        journaliser("arret : sysrq impossible (%s)" % e)
    return False


class PageErreur(tk.Frame):
    """Ecran d'echec : dit ce qui s'est passe, ou lire le detail technique, et
    propose de recommencer depuis le debut ou d'eteindre. Sans cet ecran, un
    echec laissait le diaporama tourner a l'infini devant un joueur perdu."""

    def __init__(self, parent, app, message=""):
        """Affiche le message d'echec, l'emplacement du journal et les deux sorties (recommencer, eteindre)."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        tk.Label(self, text="\u2717", font=app.f_titre, fg=COL_DANGER, bg=COL_BG).pack(pady=(app.px(30), app.px(10)))
        tk.Label(self, text=app.tr("err_title"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack()
        tk.Label(self, text=app.tr("err_msg"), font=app.f_soustitre, fg=COL_DIM, bg=COL_BG,
                 wraplength=int(app.winfo_screenwidth() * 0.8)).pack(pady=(app.px(10), app.px(20)))
        tk.Label(self, text=message, font=app.f_normal, fg=COL_AMBER, bg=COL_BG,
                 wraplength=int(app.winfo_screenwidth() * 0.8), justify="center").pack(pady=(0, app.px(10)))
        tk.Label(self, text=app.tr("err_log").format(f=JOURNAL_INSTALL), font=app.f_petit, fg=COL_DIM,
                 bg=COL_BG).pack(pady=(0, app.px(30)))
        barre = tk.Frame(self, bg=COL_BG)
        barre.pack()
        bouton(barre, app.tr("retry"), lambda: app.montrer_page(PageLangue),
               couleur=COL_OK, largeur=18).pack(side="left", padx=app.px(8))
        bouton(barre, app.tr("shutdown"), self.eteindre, couleur=COL_DIM,
               largeur=18).pack(side="left", padx=app.px(8))

    def eteindre(self):
        """Eteint la machine (le journal reste lisible sur le disque de la cle ensuite)."""
        threading.Thread(target=arreter_machine, args=("poweroff",), daemon=True).start()


class PageFin(tk.Frame):
    """Ecran final : l'installation a reussi, il reste a retirer la cle."""

    def __init__(self, parent, app):
        """Affiche le succes et les boutons redemarrer / eteindre."""
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.en_cours = False
        tk.Label(self, text="\u2713", font=app.f_titre, fg=COL_OK, bg=COL_BG).pack(pady=(app.px(60), app.px(10)))
        tk.Label(self, text=app.tr("done_title"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack()
        tk.Label(self, text=app.tr("done_msg"), font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(
            pady=(app.px(10), app.px(40)))
        self.msg = tk.Label(self, text="", font=app.f_petit, fg=COL_AMBER, bg=COL_BG)
        self.msg.pack(pady=(0, app.px(10)))
        barre = tk.Frame(self, bg=COL_BG)
        barre.pack()
        self.boutons = [bouton(barre, app.tr("reboot"), self.redemarrer, couleur=COL_OK, largeur=18),
                        bouton(barre, app.tr("shutdown"), self.eteindre, couleur=COL_DIM, largeur=18)]
        for b in self.boutons:
            b.pack(side="left", padx=app.px(8))

    def _agir(self, mode, attente):
        """Affiche `attente`, grise les boutons et lance l'arret dans un fil (l'ecran reste vivant)."""
        if self.en_cours:
            return                      # un seul arret a la fois, meme si on reclique
        self.en_cours = True
        self.msg.configure(text=attente)
        for b in self.boutons:
            b.configure(bg=COL_DIM, cursor="watch")
        self.update_idletasks()
        threading.Thread(target=arreter_machine, args=(mode,), daemon=True).start()

    def redemarrer(self):
        """Redemarre la console."""
        self._agir("reboot", "Redemarrage en cours...")

    def eteindre(self):
        """Eteint la console."""
        self._agir("poweroff", "Extinction en cours...")


# ===========================================================================
# Clavier virtuel (saisie a la souris si clavier physique HS ou mauvaise langue)
# ===========================================================================
# ===========================================================================
# Clavier virtuel (saisie a la souris si clavier physique HS ou mauvaise langue)
# ===========================================================================
class ClavierVirtuel(tk.Toplevel):
    # Dispositions disponibles
    """Clavier a l'ecran (AZERTY, QWERTY, symboles) pour le clavier physique absent ou mal regle."""
    DISPOS = {
        "AZERTY": [list("azertyuiop"), list("qsdfghjklm"), list("wxcvbn,;:!")],
        "QWERTY": [list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm,.?")],
    }
    SPECIAUX = list("@#&_-()[]{}/\\+=*%$\u20ac.'\"")

    def __init__(self, app, cible):
        """Fenetre flottante deplacable, placee sous le champ a remplir."""
        super().__init__(app)
        self.app = app
        self.cible = cible
        self.maj = False
        self.dispo = "AZERTY"
        self.montrer_speciaux = False
        self.overrideredirect(True)
        self.configure(bg=COL_PANEL, highlightbackground=COL_CYAN, highlightthickness=2)
        sw = app.winfo_screenwidth(); sh = app.winfo_screenheight()
        self._x = int(sw * 0.12); self._y = int(sh * 0.5)
        self.geometry(f"+{self._x}+{self._y}")
        self._construire()

    def _drag_start(self, e):
        self._dx = e.x_root - self._x
        self._dy = e.y_root - self._y

    def _drag_move(self, e):
        self._x = e.x_root - self._dx
        self._y = e.y_root - self._dy
        self.geometry(f"+{self._x}+{self._y}")

    def _construire(self):
        """Construit la barre (dispositions, symboles, fermer) et les rangees de touches."""
        for w in self.winfo_children():
            w.destroy()
        barre = tk.Frame(self, bg=COL_BG)
        barre.pack(fill="x")
        titre = tk.Label(barre, text="\u2328 Clavier", font=self.app.f_petit,
                         fg=COL_CYAN, bg=COL_BG, cursor="fleur")
        titre.pack(side="left", padx=6, pady=2)
        titre.bind("<Button-1>", self._drag_start)
        titre.bind("<B1-Motion>", self._drag_move)
        barre.bind("<Button-1>", self._drag_start)
        barre.bind("<B1-Motion>", self._drag_move)
        for d in self.DISPOS:
            coul = COL_MAGENTA if d == self.dispo else COL_DIM
            b = tk.Label(barre, text=d, font=self.app.f_petit, fg=COL_BG,
                         bg=coul, padx=8, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, dd=d: self.set_dispo(dd))
        cs = COL_MAGENTA if self.montrer_speciaux else COL_DIM
        bsp = tk.Label(barre, text="@#&", font=self.app.f_petit, fg=COL_BG,
                       bg=cs, padx=8, cursor="hand2")
        bsp.pack(side="left", padx=2)
        bsp.bind("<Button-1>", lambda e: self.bascule_speciaux())
        fermer = tk.Label(barre, text="\u2715", font=self.app.f_petit, fg=COL_BG,
                          bg=COL_DANGER, padx=8, cursor="hand2")
        fermer.pack(side="right", padx=2)
        fermer.bind("<Button-1>", lambda e: self.destroy())

        # Touches
        if self.montrer_speciaux:
            lignes = [self.SPECIAUX[i:i+10] for i in range(0, len(self.SPECIAUX), 10)]
        else:
            lignes = self.DISPOS[self.dispo]
        for ligne in lignes:
            fr = tk.Frame(self, bg=COL_PANEL); fr.pack()
            for c in ligne:
                aff = c.upper() if (self.maj and not self.montrer_speciaux) else c
                b = tk.Label(fr, text=aff, font=self.app.f_normal, fg=COL_TEXT,
                             bg=COL_BG, width=3, height=1, cursor="hand2")
                b.pack(side="left", padx=2, pady=2)
                b.bind("<Button-1>", lambda e, ch=c: self.taper(ch))
        # Commandes
        fr = tk.Frame(self, bg=COL_PANEL); fr.pack(pady=(2, 4))
        def cmd(t, fn, coul=COL_CYAN, w=6):
            b = tk.Label(fr, text=t, font=self.app.f_normal, fg=COL_BG,
                         bg=coul, width=w, cursor="hand2")
            b.pack(side="left", padx=2); b.bind("<Button-1>", lambda e: fn())
        cmd("Maj", self.bascule_maj)
        cmd("Espace", self.espace, COL_DIM, 14)
        cmd("\u2190", self.effacer, COL_DIM, 4)

    def set_dispo(self, d):
        self.dispo = d; self.montrer_speciaux = False; self._construire()

    def bascule_speciaux(self):
        self.montrer_speciaux = not self.montrer_speciaux; self._construire()

    def bascule_maj(self):
        self.maj = not self.maj; self._construire()

    def taper(self, c):
        ch = c.upper() if (self.maj and not self.montrer_speciaux) else c
        try: self.cible.insert("insert", ch)
        except Exception: pass

    def espace(self):
        try: self.cible.insert("insert", " ")
        except Exception: pass

    def effacer(self):
        try:
            pos = self.cible.index("insert")
            if pos != "0": self.cible.delete(f"{pos}-1c", pos)
        except Exception: pass



if __name__ == "__main__":
    OmniInstaller().mainloop()
