#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Console - Interface joueurs
=================================
Profils (cartes steampunk), bibliotheque par plateforme, reglages.
Aucune authentification : l'interface gere les joueurs elle-meme.

Plan du fichier :
  1. Charte graphique et outils de dessin (palette, neon, icones)
  2. Fonctions systeme (reseau, affichage, audio, disques)
  3. Plateformes : detection, installation, ouverture, journaux
  4. Jeux installes : lecture des fichiers de suivi des launchers
  5. Cartes de profil, profils et reglages enregistres
  6. Application : echelle, manette, menu rapide, navigation
  7. Ecrans : Qui joue, Profil, Plateformes, Bibliotheque, Journal, Reglages

Regles suivies partout :
  - toute operation longue passe par demarrer_installation() et tient un
    journal lisible, jamais la sortie brute d'un outil Linux ;
  - aucune fenetre de terminal ne doit pouvoir s'ouvrir (env_sans_terminal) ;
  - ce qui est mesure vient du systeme, jamais d'une estimation.

Mode demonstration (atelier, VM sans reseau) : lancer avec OMNI_DEMO=1.
Les installations sont simulees et quelques jeux fictifs s'affichent,
pour juger le rendu sans vraie machine.
"""

import tkinter as tk
from tkinter import font as tkfont
import json
import math
import os
import queue
import random
import re
import signal
import socket
import glob
import time
import uuid
import shutil
import threading
import subprocess
import urllib.request

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_OK = True
except Exception:
    PIL_OK = False

DEMO = os.environ.get("OMNI_DEMO") == "1"

# ---------------------------------------------------------------------------
# Charte Omni (reprise des maquettes). Le theme courant T peut etre remplace
# par une palette adaptee (daltonisme, contraste renforce).
# ---------------------------------------------------------------------------
PALETTE_BASE = {
    "bg":     "#0d0221",
    "panel":  "#10042b",
    "panel2": "#1a0a3a",
    "tuile":  "#130630",
    "sel":    "#240e4f",
    "mag":    "#ff007f",
    "cyan":   "#00f6ff",
    "amber":  "#ffae00",
    "ok":     "#3ddc84",
    "danger": "#ff4d6d",
    "text":   "#ffffff",
    "text2":  "#d0c9e8",
    "dim":    "#8a7fa8",
    "or":     "#ffc53d",
    "violet": "#1c0a3d",
}
PALETTES_DALTON = {
    "aucun": {},
    # rouge/vert confondus : on passe sur un couple orange / bleu
    "deuteranopie": {"mag": "#ff9f1c", "ok": "#3fb8ff", "danger": "#ffe14d", "amber": "#ffe14d"},
    "protanopie":   {"mag": "#ffb000", "ok": "#3fb8ff", "danger": "#fff066", "amber": "#fff066"},
    # bleu/jaune confondus : on passe sur un couple rouge / turquoise
    "tritanopie":   {"mag": "#ff2d55", "cyan": "#2ee6c8", "ok": "#ffffff", "amber": "#ff8a00", "danger": "#ff8a00"},
}
T = dict(PALETTE_BASE)
SOLEIL = ["#ffae00", "#ff7a00", "#ff4e00", "#ff2a00", "#ff0055", "#ff007f"]
FONT_NAME = "DejaVu Sans"

# Alias gardes pour le code existant
COL_BG = T["bg"]; COL_PANEL = T["panel2"]; COL_MAGENTA = T["mag"]; COL_CYAN = T["cyan"]
COL_TEXT = T["text"]; COL_DIM = T["dim"]; COL_OK = T["ok"]; COL_AMBER = T["amber"]
COL_DANGER = T["danger"]   # manquait : faisait planter le clavier et la page Wi-Fi

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARTES_DIR = os.path.join(BASE_DIR, "cartes")
SONS_DIR = os.path.join(BASE_DIR, "sons")
OMNI_DIR = os.path.expanduser("~/.omni")
PROFILS_FILE = os.path.join(OMNI_DIR, "profils.json")
REGLAGES_FILE = os.path.join(OMNI_DIR, "reglages.json")
PLATEFORMES_FILE = os.path.join(OMNI_DIR, "plateformes.json")
CACHE_DIR = os.path.join(OMNI_DIR, "cache")
LAUNCHERS_DIR = os.path.join(OMNI_DIR, "launchers")


def appliquer_palette(dalton="aucun", contraste=False):
    T.clear()
    T.update(PALETTE_BASE)
    T.update(PALETTES_DALTON.get(dalton, {}))
    if contraste:
        T.update({"dim": "#d6d0f0", "text2": "#ffffff", "panel": "#07011a",
                  "panel2": "#12052e", "tuile": "#0c0326"})


def mel(c1, c2, t):
    """Melange deux couleurs hex (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hex_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


# ---------------------------------------------------------------------------
# Fonctions systeme (reseau, affichage, audio) via outils standards Linux.
# ---------------------------------------------------------------------------
def _run(cmd, timeout=8):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def wifi_lister():
    """Reseaux Wi-Fi visibles (nmcli), tries par signal, sans doublon de nom. En demo, trois reseaux fictifs."""
    r = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"])
    reseaux = []
    if r and r.returncode == 0:
        vus = set()
        for ligne in r.stdout.strip().split("\n"):
            parts = ligne.split(":")
            if len(parts) >= 3 and parts[0] and parts[0] not in vus:
                vus.add(parts[0])
                reseaux.append({"ssid": parts[0], "signal": parts[1] or "0",
                                "securise": bool(parts[2].strip())})
    if DEMO and not reseaux:
        reseaux = [{"ssid": "Box-Salon", "signal": "82", "securise": True},
                   {"ssid": "Voisin_5G", "signal": "41", "securise": True},
                   {"ssid": "Invites", "signal": "35", "securise": False}]
    reseaux.sort(key=lambda x: int(x["signal"] or 0), reverse=True)
    return reseaux


def wifi_connecter(ssid, mdp=None):
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if mdp:
        cmd += ["password", mdp]
    r = _run(cmd, timeout=25)
    return bool(r and r.returncode == 0)


def reseau_actuel():
    """Nom de la connexion active (cable ou Wi-Fi), ou None."""
    r = _run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
    if r and r.returncode == 0:
        for ligne in r.stdout.strip().split("\n"):
            parts = ligne.split(":")
            if len(parts) >= 2 and parts[1] in ("802-11-wireless", "802-3-ethernet"):
                return parts[0]
    return None


def affichage_sortie():
    r = _run(["xrandr", "--current"])
    if r and r.returncode == 0:
        for ligne in r.stdout.split("\n"):
            if " connected" in ligne:
                return ligne.split()[0]
    return None


def resolutions_dispo():
    """Resolutions proposees par l'ecran (xrandr), sans doublon."""
    r = _run(["xrandr", "--current"])
    res = []
    if r and r.returncode == 0:
        for ligne in r.stdout.split("\n"):
            l = ligne.strip()
            if "x" in l and l[:1].isdigit():
                mode = l.split()[0]
                if mode not in res:
                    res.append(mode)
    return res


def resolution_actuelle():
    r = _run(["xrandr", "--current"])
    if r and r.returncode == 0:
        for ligne in r.stdout.split("\n"):
            if "*" in ligne:
                return ligne.split()[0]
    return None


def appliquer_resolution(sortie, mode):
    r = _run(["xrandr", "--output", sortie, "--mode", mode])
    return bool(r and r.returncode == 0)


def audio_sorties():
    """Sorties audio (pactl) : liste de {nom, desc}. Repli sur le format court si le JSON n'est pas disponible."""
    r = _run(["pactl", "-f", "json", "list", "sinks"])
    sorties = []
    if r and r.returncode == 0:
        try:
            for s in json.loads(r.stdout):
                sorties.append({"nom": s.get("name", ""), "desc": s.get("description", s.get("name", ""))})
        except Exception:
            pass
    if not sorties:
        r = _run(["pactl", "list", "short", "sinks"])
        if r and r.returncode == 0:
            for ligne in r.stdout.strip().split("\n"):
                parts = ligne.split("\t")
                if len(parts) >= 2:
                    sorties.append({"nom": parts[1], "desc": parts[1]})
    return sorties


def audio_sortie_active():
    r = _run(["pactl", "get-default-sink"])
    return r.stdout.strip() if r and r.returncode == 0 else None


def audio_definir_sortie(nom):
    r = _run(["pactl", "set-default-sink", nom])
    return bool(r and r.returncode == 0)


def espace_disque():
    """(total, utilise, libre en Go, pourcentage utilise, dossier mesure) : la partition de donnees si elle est montee, sinon la racine."""
    try:
        cible = "/omni-data" if os.path.ismount("/omni-data") else "/"
        t, u, l = shutil.disk_usage(cible)
        go = 1024 ** 3
        return (round(t / go, 1), round(u / go, 1), round(l / go, 1), int(u / t * 100) if t else 0, cible)
    except Exception:
        return (0, 0, 0, 0, "/")


def taille_dossiers(chemins):
    """Somme des tailles de plusieurs dossiers (page Stockage)."""
    return sum(taille_dossier(c) for c in chemins)


# ---------------------------------------------------------------------------
# Plateformes
# integree = Omni installe et lance lui-meme ; deleguee = launcher officiel
# sous Proton (umu-run), ouvert en plein ecran pour installer / se connecter.
# Les pastilles sont maison (sigle + couleur), pas les logos officiels.
# ---------------------------------------------------------------------------
PLATEFORMES = [
    {"id": "steam",   "nom": "Steam",           "sigle": "ST",  "type": "integree", "couleur": "#00f6ff", "unite": "jeux"},
    {"id": "gog",     "nom": "GOG",             "sigle": "GOG", "type": "integree", "couleur": "#ffae00", "unite": "jeux"},
    {"id": "emu",     "nom": "Émulateurs",      "sigle": "EM",  "type": "integree", "couleur": "#3ddc84", "unite": "ROMs"},
    {"id": "epic",    "nom": "Epic Games",      "sigle": "EG",  "type": "deleguee", "couleur": "#ff007f", "unite": "jeux"},
    {"id": "ea",      "nom": "EA App",          "sigle": "EA",  "type": "deleguee", "couleur": "#ff4d4d", "unite": "jeux"},
    {"id": "ubisoft", "nom": "Ubisoft Connect", "sigle": "UB",  "type": "deleguee", "couleur": "#4d7cff", "unite": "jeux"},
]
PLAT = {p["id"]: p for p in PLATEFORMES}

# Launchers delegues : installateur officiel telecharge a la demande (jamais
# embarque dans l'ISO), installe dans son propre prefixe Proton.
LAUNCHERS = {
    "epic": {"url": "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi",
             "fichier": "EpicInstaller.msi", "install": ["msiexec", "/i", "{f}", "/qn"],
             "exe": "pfx/drive_c/Program Files (x86)/Epic Games/Launcher/Portal/Binaries/Win32/EpicGamesLauncher.exe"},
    # EA App : meme recette que le script Lutris (installateur officiel sous Proton, installation
    # silencieuse), executee par Omni : aucune fenetre Lutris n'apparait.
    # l'installateur d'EA est un petit programme qui telecharge le reste ensuite
    "ea": {"url": "https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/EAappInstaller.exe",
           "fichier": "EAappInstaller.exe", "install": ["{f}", "/quiet"], "taille_mini": 400 * 1024,
           "exe": "pfx/drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe"},
    "ubisoft": {"url": "https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe",
                "fichier": "UbisoftConnectInstaller.exe", "install": ["{f}", "/S"],
                "proton": "ubisoft",
                "exe": "pfx/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe"},
}


PROFIL_COURANT = {"id": "commun"}


def prefixe(pid):
    """Prefixe Proton du launcher pour le joueur actif : chaque profil a son
    propre compte connecte (destine a vivre dans le coffre du profil)."""
    return os.path.join(OMNI_DIR, "profils", PROFIL_COURANT["id"], "launchers", pid)


# ---------------------------------------------------------------------------
# Moteur Proton. Une SEULE fonction lance tout ce qui tourne sous Proton
# (installateur d'un launcher, launcher, jeu) : lancer_umu(). Elle prepare le
# prefixe, le dossier d'installation et l'environnement, une fois pour toutes.
# Chaque launcher ne fournit que deux informations : sa commande, et la
# version de Proton qui lui convient (LAUNCHERS[pid]["proton"]).
# ---------------------------------------------------------------------------
# Proton doit vivre HORS de /usr : son conteneur (pressure-vessel) refuse ce
# dossier, qu'il reserve a son propre systeme. Les deux dossiers sont poses par
# omni-poser-proton (build ou guichet), jamais par l'interface elle-meme.
DOSSIERS_PROTON = {"defaut": "/opt/omni/proton", "ubisoft": "/opt/omni/proton-ubisoft"}
MODELE_PROTON = DOSSIERS_PROTON["defaut"]
RECETTES_FILE = os.path.join(OMNI_DIR, "recettes.json")


def proton_valide(variante="defaut"):
    """Un Proton utilisable contient son toolmanifest.vdf : sans lui umu refuse
    le dossier et il vaut mieux le laisser telecharger le sien."""
    return os.path.isfile(os.path.join(DOSSIERS_PROTON.get(variante, MODELE_PROTON), "toolmanifest.vdf"))


def proton_embarque_valide():
    """Vrai si le Proton de reference est present (compatibilite avec l'ancien nom)."""
    return proton_valide("defaut")


def variante_proton(pid):
    """Version de Proton voulue pour ce launcher, avec repli sur celle de
    reference si la version dediee n'est pas (ou plus) installee."""
    voulue = LAUNCHERS.get(pid, {}).get("proton", "defaut")
    return voulue if proton_valide(voulue) else "defaut"


def racine_wine(pid):
    """Racine du prefixe Windows du launcher. Proton cree lui-meme le sous-dossier
    « pfx » sous STEAM_COMPAT_DATA_PATH : tout ce qui est « Windows » (drive_c,
    registre) vit DANS pfx, pas a cote."""
    return os.path.join(prefixe(pid), "pfx")


def dossier_installation(pid):
    """Dossier reel, absolu et deja cree, exige par Proton (STEAM_COMPAT_INSTALL_PATH).

    Proton en deduit sa « lettre de lecteur » a partir du dossier parent : vide,
    inexistant ou reduit a la racine d'une partition, il s'arrete sur
    « unable to use parent for game drive ». Un sous-dossier du cache convient."""
    chemin = assurer_dossier(os.path.join(CACHE_DIR, "installation", PROFIL_COURANT["id"], pid))
    return os.path.realpath(chemin)


def env_proton(pid):
    """Environnement d'un launcher Windows.

    Proton attend STEAM_COMPAT_DATA_PATH : il y cree lui-meme « pfx ». Lui
    donner directement un WINEPREFIX provoque l'erreur « unable to use parent
    for game drive » ; WINEPREFIX reste renseigne pour umu, qui sert de secours."""
    env = dict(os.environ)
    dossier = assurer_dossier(prefixe(pid))
    compat = assurer_dossier(os.path.join(OMNI_DIR, "compat"))
    variante = variante_proton(pid)
    if proton_valide(variante):
        env["PROTONPATH"] = DOSSIERS_PROTON[variante]
    else:
        env.pop("PROTONPATH", None)
    env["STEAM_COMPAT_DATA_PATH"] = dossier
    # affectation directe : une valeur heritee du systeme (vide ou perimee) ferait echouer Proton
    env["STEAM_COMPAT_INSTALL_PATH"] = dossier_installation(pid)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = compat
    env["WINEPREFIX"] = racine_wine(pid)
    env["GAMEID"] = "umu-" + pid
    return env_isolation(env)


def lancer_umu(arguments, pid, **kw):
    """Lance une commande sous Proton (umu) et renvoie le processus.

    On travaille depuis le dossier du joueur : le conteneur de Proton refuse /usr
    (« Can't chdir ») ou se trouve l'interface. umu d'abord : il apporte son propre
    environnement complet (polices, audio, graphique). Proton seul sert de secours."""
    dossier = assurer_dossier(prefixe(pid))
    env = env_proton(pid)
    if shutil.which("umu-run"):
        commande = ["umu-run"] + arguments
    elif proton_valide(variante_proton(pid)):
        commande = [os.path.join(DOSSIERS_PROTON[variante_proton(pid)], "proton"), "run"] + arguments
    else:
        raise OSError("aucun moteur Proton disponible")
    # Proton isole lui aussi ses processus : meme precaution que pour Steam
    return subprocess.Popen(sans_privileges(commande), cwd=dossier, env=env, **kw)


def chemin_windows(chemin_unix):
    """Chemin Windows d'un fichier du systeme : lecteur Z: (la racine du systeme
    dans Wine). Sert a donner un .msi a msiexec."""
    return "Z:" + chemin_unix.replace("/", "\\")


def strategies_installation(pid, fichier):
    """Voies a essayer, dans l'ordre, pour installer le launcher `pid` depuis `fichier`.

    Un .exe se lance tel quel. Un .msi n'est pas un programme : il passe par
    msiexec, et la bonne facon de le designer a umu ne se devine pas, elle se
    mesure. On essaie donc trois voies, chacune controlee par la presence du
    launcher ensuite ; celle qui reussit est memorisee (recettes.json)."""
    L = LAUNCHERS[pid]
    arguments = [a.replace("{f}", fichier) for a in L["install"]]
    if not arguments or arguments[0] != "msiexec":
        return [("programme", arguments)]
    msi = chemin_windows(fichier)
    system32 = os.path.join(racine_wine(pid), "drive_c", "windows", "system32", "msiexec.exe")
    voies = [("msiexec, chemin Windows", ["C:\\windows\\system32\\msiexec.exe", "/i", msi, "/qn"]),
             ("msiexec, chemin du systeme", [system32, "/i", msi, "/qn"]),
             # derniere chance : le .msi seul, que Wine confie a msiexec (fenetre visible, non silencieux)
             ("msi direct", [fichier])]
    connue = lire_recettes().get(pid)
    voies.sort(key=lambda v: v[0] != connue)      # la voie qui a deja marche passe en premier
    return voies


def lire_recettes():
    """Voies d'installation qui ont reussi sur cette console, {pid: nom}."""
    try:
        with open(RECETTES_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def noter_recette(pid, nom):
    """Memorise la voie qui a reussi pour ce launcher."""
    recettes = lire_recettes()
    recettes[pid] = nom
    try:
        os.makedirs(OMNI_DIR, exist_ok=True)
        with open(RECETTES_FILE, "w") as f:
            json.dump(recettes, f, indent=2)
    except OSError:
        pass


def _etat_demo():
    try:
        with open(PLATEFORMES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _marquer_demo(pid, val):
    etat = _etat_demo()
    etat[pid] = val
    os.makedirs(OMNI_DIR, exist_ok=True)
    with open(PLATEFORMES_FILE, "w") as f:
        json.dump(etat, f, indent=2)


def dossiers_gog():
    return ["/omni-data/jeux/gog", os.path.expanduser("~/Jeux/GOG"), os.path.expanduser("~/GOG Games")]


def dossiers_roms():
    return ["/omni-data/roms", os.path.expanduser("~/Jeux/ROMs")]


def plateforme_presente(pid):
    """Detection reelle : une plateforme est installee si on la trouve sur le
    systeme. Plus besoin de la marquer a la main."""
    if DEMO:
        return bool(_etat_demo().get(pid))
    if pid == "steam":
        # le lanceur de Valve ne suffit pas : le client doit avoir ete telecharge
        return bool(shutil.which("steam")) and steam_racine() is not None
    if pid == "emu":
        return bool(shutil.which("retroarch"))
    if pid == "gog":
        return any(os.path.isdir(d) for d in dossiers_gog())
    if pid in LAUNCHERS:
        return bool(_exe_du_launcher(pid))
    return False


SERVICE_INSTALL = "/usr/local/sbin/omni-plateforme"


def _apt(intention, prog, base, part):
    """Demande au service d'installation (root) une INTENTION, jamais une commande :
    il ne connait que quelques plateformes et leurs paquets fixes (cahier des charges).
    Progression reelle via APT::Status-Fd. Retourne (ok, msg)."""
    if not os.path.isfile(SERVICE_INSTALL):
        return False, "Le service d'installation de la console est absent."
    cmd = ["sudo", "-n", SERVICE_INSTALL, intention]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))
    except Exception:
        return False, "Impossible de lancer l'installation."
    prog(base, "Demande transmise au service d'installation")
    erreurs = []
    for ligne in p.stdout:
        champs = ligne.strip().split(":", 3)
        if len(champs) == 4 and champs[0] in ("dlstatus", "pmstatus"):
            try:
                pct = float(champs[2])
            except ValueError:
                continue
            paquet = champs[1].split(":")[0]
            if champs[0] == "dlstatus":
                m = re.search(r"(\d+) of (\d+)", champs[3])
                txt = "Téléchargement des composants (%s sur %s)" % m.groups() if m else "Téléchargement des composants"
                prog(base + int(pct * part * 0.5 / 100), txt)
            else:
                action = champs[3].lower()
                if action.startswith(("installed", "configured")):
                    txt = "%s : prêt" % paquet
                elif "configur" in action:
                    txt = "%s : configuration" % paquet
                else:
                    txt = "%s : installation" % paquet
                prog(base + int(part * 0.5 + pct * part * 0.5 / 100), txt)
        elif ligne.startswith(("E:", "dpkg: error", "dpkg : erreur")) or "error processing package" in ligne:
            detail = ligne.strip().lstrip("E:").strip()
            erreurs.append(detail[:140])
            del erreurs[:-4]
            prog(base, "Refus du système : " + detail[:90])
    p.wait()
    if p.returncode == 0:
        return True, ""
    precis = " · ".join(erreurs[-2:]) if erreurs else "raison inconnue"
    return False, "L'installation a été refusée : %s" % precis


# ---------------------------------------------------------------------------
# Aucun terminal ne doit jamais s'ouvrir : si un launcher en reclame un
# (Steam le fait pour demander des composants), Omni intercepte la demande,
# la note et l'affiche proprement dans son journal.
# ---------------------------------------------------------------------------
BIN_SANS_TERMINAL = os.path.join(OMNI_DIR, "bin-sans-terminal")
JOURNAL_TERMINAL = os.path.join(OMNI_DIR, "terminal-refuse.log")


def reparer_dossier_donnees(prog=None):
    """Le dossier de donnees appartient parfois a l'administrateur : le joueur
    ne peut alors rien y installer. On demande sa reparation au guichet a
    intentions plutot que de laisser un « Permission denied » incomprehensible."""
    if not os.path.isdir("/omni-data"):
        return False
    if os.access("/omni-data", os.W_OK):
        return True
    if prog:
        prog(-1, "Dossier de données inaccessible : correction des droits")
    _run(["sudo", "-n", SERVICE_INSTALL, "donnees"], timeout=60)
    return os.access("/omni-data", os.W_OK)


def assurer_dossier(chemin):
    """Cree un dossier, meme si un lien symbolique du chemin pointe vers un
    endroit qui n'existe pas encore. C'est le cas du dossier des profils, qui
    renvoie vers la partition de donnees : tant qu'elle est vide, la creation
    echoue avec « No such file or directory »."""
    chemin = os.path.expanduser(chemin)
    parties = []
    courant = chemin
    while courant and courant != "/":
        parties.append(courant)
        courant = os.path.dirname(courant)
    for element in reversed(parties):
        if os.path.islink(element) and not os.path.exists(element):
            # lien casse : on cree d'abord sa cible
            cible = os.path.realpath(element)
            os.makedirs(cible, exist_ok=True)
    os.makedirs(chemin, exist_ok=True)
    return chemin


# Trois reglages conditionnent l'isolation dont Steam et Proton ont besoin.
# Ubuntu 24.04 en restreint un par defaut ; les deux autres peuvent etre
# fermes par une politique de securite. On les verifie tous les trois, et on
# affiche leur valeur : un message precis vaut mieux qu'une supposition.
REGLAGES_ISOLATION = {
    "/proc/sys/kernel/apparmor_restrict_unprivileged_userns": "0",
    "/proc/sys/kernel/unprivileged_userns_clone": "1",
    "/proc/sys/user/max_user_namespaces": None,   # doit etre superieur a zero
}
FICHIER_USERNS = "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"


def etat_isolation():
    """Valeurs reelles des trois reglages, et liste de ceux qui bloquent."""
    valeurs = {}
    bloquants = []
    for fichier, attendu in REGLAGES_ISOLATION.items():
        try:
            with open(fichier) as f:
                valeur = f.read().strip()
        except Exception:
            continue  # reglage absent de ce noyau : il ne bloque rien
        valeurs[fichier] = valeur
        if attendu is None:
            if valeur.isdigit() and int(valeur) <= 0:
                bloquants.append((fichier, valeur))
        elif valeur != attendu:
            bloquants.append((fichier, valeur))
    return valeurs, bloquants


def essai_isolation_reel():
    """Ne pas deduire, mesurer : on tente reellement de creer un espace de noms
    utilisateur, comme le font Steam et Proton. Renvoie (reussi, explication).

    Les reglages du noyau peuvent etre ouverts et la creation echouer quand
    meme (profil de securite, politique du conteneur). Seul l'essai tranche."""
    code = ("import os, sys\n"
            "try:\n"
            "    os.unshare(os.CLONE_NEWUSER)\n"
            "    sys.exit(0)\n"
            "except Exception as e:\n"
            "    sys.stderr.write(str(e))\n"
            "    sys.exit(1)\n")
    r = _run(["python3", "-c", code], timeout=15)
    if r is None:
        return False, "essai impossible"
    if r.returncode == 0:
        return True, "création d'un espace de noms réussie"
    detail = (r.stderr or "").strip()[:80] or "refus sans message"
    # le meme essai avec l'outil qu'emploient Steam et Proton
    if shutil.which("bwrap"):
        r2 = _run(["bwrap", "--unshare-user", "--dev-bind", "/", "/", "true"], timeout=15)
        if r2 is not None and r2.returncode == 0:
            return True, "bwrap y parvient (l'essai direct échoue : %s)" % detail
    return False, detail


def espaces_de_noms_ok():
    return not etat_isolation()[1] and essai_isolation_reel()[0]


def reparer_espaces_de_noms(prog=None):
    """Retablit les reglages par le guichet a intentions, puis DIT ce qu'il en
    est : sans valeurs affichees, un echec reste incomprehensible."""
    valeurs, bloquants = etat_isolation()
    reussi, explication = essai_isolation_reel()
    if not bloquants and reussi:
        if prog:
            prog(-1, "Isolation vérifiée : %s" % explication)
        return True
    if not bloquants and prog:
        # les reglages sont ouverts mais l'essai echoue : c'est autre chose
        prog(-1, "Réglages ouverts (%s) mais l'essai échoue : %s"
             % (" · ".join("%s=%s" % (os.path.basename(f), v) for f, v in valeurs.items()),
                explication))
    if prog:
        prog(-1, "Isolation refusée par le système : %s"
             % " · ".join("%s = %s" % (os.path.basename(f), v) for f, v in bloquants))
    _run(["sudo", "-n", SERVICE_INSTALL, "jeux-autorisations"], timeout=30)
    valeurs, bloquants = etat_isolation()
    reussi, explication = essai_isolation_reel()
    if prog:
        if reussi:
            prog(-1, "Isolation rétablie : %s" % explication)
        else:
            prog(-1, "Isolation toujours refusée après correction : %s" % explication)
    return reussi


def carte_3d_presente():
    """Vrai s'il y a une carte graphique capable d'accelerer l'affichage.

    On ne se fie pas a la seule presence d'un ecran : une machine virtuelle
    en expose un sans la moindre acceleration. Une carte utilisable fournit
    un « noeud de rendu » (renderD), que l'affichage simple d'une VM n'a pas.
    Sans ce controle, Omni lance le grand ecran de Steam, qui ne peut pas
    s'afficher, et le joueur attend deux minutes pour rien."""
    try:
        noeuds = os.listdir("/dev/dri")
    except Exception:
        return False
    if not any(n.startswith("renderD") for n in noeuds):
        return False
    # pilote purement logiciel : present dans les machines virtuelles
    for carte in ("/sys/class/drm/card0/device/driver",):
        try:
            pilote = os.path.basename(os.path.realpath(carte))
            if pilote in ("bochs-drm", "cirrus", "vmwgfx_stub", "simpledrm"):
                return False
        except Exception:
            pass
    return True


def sans_privileges(commande):
    """Lance un programme debarrasse des privileges residuels de la session.

    La session graphique est demarree par systemd : les programmes qu'elle
    lance heritent de capacites qu'une session de connexion ordinaire n'a pas.
    L'outil d'isolation de Steam (bwrap) refuse alors de demarrer
    (« Unexpected capabilities but not setuid ») et Steam traduit ce refus par
    « user namespaces to be enabled », ce qui envoie sur une fausse piste.

    Constate sur la console : le MEME Steam demarre depuis une console de
    connexion et echoue depuis la session graphique.

    Attention : « --bounding-set » demande un privilege que la session n'a pas
    toujours (« setpriv: apply bounding set: Operation not permitted »), et le
    programme n'est alors JAMAIS lance. On essaie donc les reglages du plus
    complet au plus simple, et on verifie que l'outil fonctionne vraiment
    avant de s'en servir. Sans quoi on lance la commande telle quelle : mieux
    vaut un Steam qui demarre qu'un Steam proprement bride qui ne demarre pas."""
    commande = list(commande)
    if not shutil.which("setpriv"):
        return commande
    for options in (["--inh-caps=-all", "--ambient-caps=-all", "--bounding-set=-all"],
                    ["--inh-caps=-all", "--ambient-caps=-all"],
                    ["--ambient-caps=-all"]):
        essai = _run(["setpriv"] + options + ["--", "true"], timeout=10)
        if essai is not None and essai.returncode == 0:
            return ["setpriv"] + options + ["--"] + commande
    return commande


def env_isolation(env):
    """Steam et Proton embarquent leur propre outil d'isolation (bwrap). Sur
    cette image, cet exemplaire refuse de demarrer : « Unexpected capabilities
    but not setuid ». Steam traduit ce refus par un message trompeur sur les
    espaces de noms, alors qu'ils sont bien autorises.

    On leur demande donc d'employer celui du systeme, qui est sain. Mesure
    verifiee en conditions reelles : sans cette variable, Steam s'arrete avant
    sa fenetre ; avec elle, il va jusqu'au bout."""
    if os.path.exists("/usr/bin/bwrap"):
        env["PRESSURE_VESSEL_BWRAP"] = "/usr/bin/bwrap"
        env["STEAM_BWRAP"] = "/usr/bin/bwrap"
    return env


def env_steam(env=None):
    """Sans carte 3D, l'interface de Steam tourne en rendu logiciel au lieu de
    redemarrer en boucle (ce qui n'en finissait jamais en machine virtuelle)."""
    env = env_isolation(env_sans_terminal(env))
    if not carte_3d_presente():
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        env["GALLIUM_DRIVER"] = "llvmpipe"
    return env


def env_sans_terminal(env=None):
    """Environnement ou tout programme de terminal (xterm, gnome-terminal...) est remplace par un faux qui note la demande dans un journal : aucune fenetre de terminal ne doit jamais s'ouvrir."""
    env = dict(env or os.environ)
    try:
        os.makedirs(BIN_SANS_TERMINAL, exist_ok=True)
        for nom in ("xterm", "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
                    "mate-terminal", "lxterminal", "uxterm"):
            chemin = os.path.join(BIN_SANS_TERMINAL, nom)
            if not os.path.isfile(chemin):
                with open(chemin, "w") as f:
                    f.write('#!/bin/sh\necho "$*" >> "%s"\nexit 0\n' % JOURNAL_TERMINAL)
                os.chmod(chemin, 0o755)
    except Exception:
        pass
    env["PATH"] = BIN_SANS_TERMINAL + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    return env


STEAM_ETAPES = [("checking for", "Recherche de la dernière version de Steam"),
                ("downloading", "Téléchargement de Steam"),
                ("extracting", "Décompression"),
                ("installing", "Installation"),
                ("cleaning up", "Nettoyage"),
                ("verifying", "Vérification de l'installation"),
                ("restarting", "Redémarrage de Steam"),
                ("steam runtime", "Préparation de l'environnement de Steam")]


def lire_suite(chemin, position):
    """Lit ce qu'un programme a ajoute a son journal depuis la derniere lecture.
    Renvoie (lignes nouvelles, nouvelle position)."""
    try:
        with open(chemin, errors="replace") as f:
            f.seek(position)
            bloc = f.read()
            return bloc.splitlines(), f.tell()
    except Exception:
        return [], position


def signaler_erreurs(lignes, prog, memoire, limite=4):
    """Remonte dans le journal d'Omni les lignes qui ressemblent a une erreur et
    garde les dernieres de cote pour le message final."""
    for ligne in lignes:
        bas = ligne.lower()
        if any(mot in bas for mot in MOTS_ERREUR) and len(ligne) > 12:
            memoire.append(ligne.strip()[:110])
            del memoire[:-limite]
            prog(-1, ligne.strip()[:90])


def taille_dossier(chemin, exclure=None):
    """Taille d'un dossier en octets, 0 s'il n'existe pas."""
    if not os.path.isdir(chemin):
        return 0
    cmd = ["du", "-sb"] + (["--exclude=%s" % exclure] if exclure else []) + [chemin]
    r = _run(cmd, timeout=30)
    if r is not None and r.returncode == 0 and r.stdout.strip():
        try:
            return int(r.stdout.split()[0])
        except Exception:
            pass
    return 0


def fenetre_visible(motif):
    """Attention : on exige une fenetre VISIBLE appartenant a ce programme."""
    """Vrai si une fenetre appartenant a ce programme est reellement affichee.
    On ne se fie pas au seul processus : Steam peut demarrer puis mourir."""
    for classe in ("^%s$" % motif, "^%s$" % motif.capitalize(), motif):
        r = _run(["xdotool", "search", "--onlyvisible", "--class", classe], timeout=5)
        if r is not None and r.returncode == 0 and r.stdout.strip():
            return True
    # deuxieme avis : la liste des fenetres, en ecartant celles d'Omni lui-meme
    r = _run(["wmctrl", "-lx"], timeout=5)
    if r is not None and r.returncode == 0:
        for ligne in r.stdout.splitlines():
            bas = ligne.lower()
            if motif.lower() in bas and "omni" not in bas:
                return True
    return False


MODELE_STEAM = "/usr/local/share/omni/steam-template"


def _taille_steam():
    """Taille reelle du Steam du joueur. Les differents chemins pointent souvent
    vers le meme dossier : on ne le compte qu'une fois."""
    vus = set()
    total = 0
    for d in ("~/.local/share/Steam", "~/.steam/debian-installation", "~/.steam/steam"):
        chemin = os.path.realpath(os.path.expanduser(d))
        if chemin in vus or not os.path.isdir(chemin):
            continue
        vus.add(chemin)
        total += taille_dossier(chemin, exclure="logs")
    return total


def steam_depuis_modele(prog):
    """Steam prepare a la fabrication de l'ISO : on le copie chez le joueur.
    Quelques secondes, au lieu du telechargement et de la verification."""
    if not os.path.isdir(MODELE_STEAM):
        return False
    cible = os.path.expanduser("~/.local/share/Steam")
    os.makedirs(os.path.dirname(cible), exist_ok=True)
    r = _run(["du", "-sb", MODELE_STEAM], timeout=60)
    total = int(r.stdout.split()[0]) if r and r.returncode == 0 and r.stdout.strip() else 0
    prog(2, "Installation de Steam depuis la console (aucun téléchargement)")
    p = subprocess.Popen(["cp", "-a", MODELE_STEAM + "/.", cible])
    while p.poll() is None:
        time.sleep(1)
        fait = _taille_steam()
        if total:
            prog(2 + int(fait * 90 / total), "Copie de Steam : %d / %d Mo" % (fait // 1048576, total // 1048576))
    lien = os.path.expanduser("~/.steam/steam")
    try:
        os.makedirs(os.path.expanduser("~/.steam"), exist_ok=True)
        if not os.path.exists(lien):
            os.symlink(cible, lien)
    except Exception:
        pass
    if p.returncode == 0:
        prog(95, "Steam est installé, dernière vérification par Valve")
        return True
    return False


def _lire_flux(flux, traiter):
    """Steam ecrit sa progression en reecrivant la meme ligne (retour chariot),
    jamais en passant a la ligne : on decoupe donc sur \r ET sur \n."""
    tampon = ""
    while True:
        try:
            bloc = os.read(flux.fileno(), 4096).decode("utf-8", "replace")
        except Exception:
            bloc = ""
        if not bloc:
            break
        tampon += bloc
        morceaux = re.split(r"[\r\n]", tampon)
        tampon = morceaux.pop()
        for m in morceaux:
            if m.strip():
                traiter(m.strip())


def _etape_steam():
    """Derniere etape lisible dans le journal que Steam tient lui-meme."""
    for chemin in ("~/.local/share/Steam/logs/bootstrap_log.txt",
                   "~/.steam/debian-installation/logs/bootstrap_log.txt"):
        f = os.path.expanduser(chemin)
        if os.path.isfile(f):
            try:
                with open(f, errors="replace") as fh:
                    lignes = fh.read().strip().split("\n")[-12:]
            except Exception:
                continue
            for ligne in reversed(lignes):
                bas = ligne.lower()
                for cle, texte in STEAM_ETAPES:
                    if cle in bas:
                        return texte
    return ""


def arreter_steam(prog=None, brutal=False):
    """Ferme Steam proprement, puis fermement s'il s'obstine. Une installation
    ne doit jamais laisser une fenetre ouverte devant le joueur."""
    if prog:
        prog(-1, "Fermeture de Steam" + (" (session figée)" if brutal else ""))
    if not brutal:
        _run(sans_privileges(["steam", "-shutdown"]), timeout=30)
    for _ in range(10):
        time.sleep(2)
        r = _run(["pgrep", "-x", "steam"], timeout=5)
        if r is None or r.returncode != 0:
            return
    for signal_ in ("-TERM", "-KILL"):
        for motif in (["-f", "steamwebhelper"], ["-f", "steam.sh"], ["-x", "steam"], ["-f", "reaper"]):
            _run(["pkill", signal_] + motif, timeout=10)
        time.sleep(2)


JOURNAUX_STEAM = ("~/.local/share/Steam/logs/console-linux.txt",
                  "~/.local/share/Steam/logs/bootstrap_log.txt",
                  "~/.steam/debian-installation/logs/console-linux.txt")

# Messages connus de Steam, traduits en cause reelle. Le message affiche a
# l'ecran est souvent trompeur : c'est la ligne juste avant qui designe le
# vrai coupable.
TRADUCTIONS_STEAM = (
    ("unexpected capabilities but not setuid",
     "l'outil d'isolation embarqué par Steam refuse de démarrer"),
    ("requires user namespaces",
     "Steam annonce une isolation interdite, alors que c'est souvent son propre outil qui échoue"),
    ("no space left", "plus de place sur le disque"),
    ("failed to load steamui", "l'interface de Steam n'a pas pu se charger"),
    ("unable to open x11 display", "aucun écran disponible pour Steam"),
    ("connection reset", "la connexion au serveur de Valve a été coupée"),
)


def dernieres_lignes_steam(nombre=12):
    """Ce que Steam a REELLEMENT ecrit, dans ses propres journaux. Omni ne
    capte pas sa sortie : le client la redirige lui-meme vers ces fichiers."""
    recoltees = []
    for chemin in JOURNAUX_STEAM:
        f = os.path.expanduser(chemin)
        if not os.path.isfile(f):
            continue
        try:
            with open(f, errors="replace") as fh:
                lignes = [l.rstrip() for l in fh.read().split("\n") if l.strip()]
        except Exception:
            continue
        recoltees.append((os.path.getmtime(f), os.path.basename(f), lignes[-nombre:]))
    recoltees.sort()
    return recoltees


def cause_probable_steam():
    """Cherche une cause connue dans les journaux de Steam, et la traduit."""
    for _, _, lignes in dernieres_lignes_steam(40):
        for ligne in reversed(lignes):
            bas = ligne.lower()
            for motif, explication in TRADUCTIONS_STEAM:
                if motif in bas:
                    return explication, ligne.strip()[:120]
    return None, None


def journal_steam_vers_fichier(chemin):
    """Recopie les journaux de Steam dans le journal brut d'Omni : le joueur
    doit lire la vraie erreur sans ouvrir de terminal."""
    try:
        with open(chemin, "a") as sortie:
            for _, nom, lignes in dernieres_lignes_steam(25):
                sortie.write("\n----- %s (écrit par Steam) -----\n" % nom)
                sortie.write("\n".join(lignes) + "\n")
    except Exception:
        pass


def steam_installer_silencieux(prog):
    """Installe le client Steam sans rien afficher : « steam -silent » telecharge
    et decompresse en arriere-plan, Omni suit l'avancement dans son journal."""
    if not shutil.which("steam"):
        prog(0, "Installation du lanceur de Steam")
        ok, msg = _apt("steam", prog, 0, 15)
        if not ok:
            return False, msg or "Le lanceur de Steam n'a pas pu être installé."
    if steam_racine() is not None:
        # deja installe : inutile de relancer quoi que ce soit
        prog(100, "Steam est déjà installé sur cette console")
        return True, ""
    if os.path.isdir(MODELE_STEAM) and steam_racine() is None:
        if steam_depuis_modele(prog):
            prog(100, "Steam est prêt")
            return True, ""
    if not reparer_espaces_de_noms(prog):
        detail = " · ".join("%s = %s" % (os.path.basename(f), v) for f, v in etat_isolation()[1])
        return False, ("Le système interdit à Steam son mécanisme d'isolation (%s). "
                       "C'est ce réglage qu'il faut lever dans l'image." % detail)
    prog(2, "Téléchargement du client Steam chez Valve")
    assurer_dossier(DOSSIER_JOURNAUX)
    chemin_journal = os.path.join(DOSSIER_JOURNAUX, "steam-install.log")
    try:
        with open(chemin_journal, "w") as f:
            f.write("Omni : installation de Steam, %s\n" % time.strftime("%H:%M:%S"))
    except Exception:
        pass
    try:
        p = subprocess.Popen(sans_privileges(["steam", "-silent"]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env_steam(), start_new_session=True)
    except Exception:
        return False, "Steam n'a pas pu être lancé."
    etat = {"manque": None}

    def traiter(ligne):
        """Lit une ligne de sortie de Steam : detecte une demande de composants manquants, la progression du telechargement (en Ko) et les etapes connues."""
        bas = ligne.lower()
        if "needs to install" in bas or "additional packages" in bas:
            etat["manque"] = ligne
            return
        ko = re.search(r"\(([\d,]+) of ([\d,]+) KB\)", ligne)
        if ko:
            recu, total = [int(x.replace(",", "")) for x in ko.groups()]
            if total:
                prog(5 + int(recu * 70 / total), "Téléchargement : %d / %d Mo" % (recu // 1024, total // 1024))
            return
        for cle, texte in STEAM_ETAPES:
            if cle in bas:
                prog(0, texte)
                return

    threading.Thread(target=_lire_flux, args=(p.stdout, traiter), daemon=True).start()
    debut = time.time()
    stable_depuis = None
    dernier = 0
    dernier_battement = time.time()
    while True:
        time.sleep(4)
        if etat["manque"]:
            paquets = sorted(set(re.findall(r"([a-z0-9][a-z0-9.+-]+:(?:i386|amd64))", etat["manque"])))
            try:
                os.killpg(p.pid, 15)
            except Exception:
                pass
            return False, ("Steam réclame des composants absents de la console"
                           + (" (%s)" % ", ".join(paquets[:6]) if paquets else "") + ".")
        octets = _taille_steam()
        racine = steam_racine()
        complet = racine is not None and os.path.isdir(os.path.join(racine, "ubuntu12_64"))
        # Steam affiche sa fenetre : le client est installe, le reste (connexion
        # au compte) appartient au joueur. On le laisse ouvert.
        if complet and fenetre_visible("steam"):
            # la fenetre prouve que le client est installe ; on le referme pour
            # rendre la main au joueur, il ouvrira Steam quand il le voudra
            arreter_steam(prog)
            prog(100, "Steam est installé")
            return True, ""
        if octets > dernier + 2 * 1024 * 1024:
            dernier, stable_depuis = octets, None
            prog(-1, "Installation en cours : %d Mo sur le disque" % (octets // 1048576))
        elif complet:
            stable_depuis = stable_depuis or time.time()
            if time.time() - stable_depuis > 25:
                prog(98, "Fin de l'installation")
                arreter_steam(prog)
                prog(100, "Steam est installé")
                return True, ""
        if time.time() - dernier_battement > 25:
            dernier_battement = time.time()
            prog(-1, "Installation en cours : %d Mo sur le disque, %d min écoulées"
                 % (octets // 1048576, int(time.time() - debut) // 60))
        # Steam se relance lui-meme pendant son installation (« Restarting
        # Steam by request »). Le programme lance au depart se termine alors,
        # tandis que le vrai client continue son travail. Se fier a sa sortie
        # revenait a declarer l'echec en pleine installation : on regarde donc
        # si une session Steam tourne encore, quelle qu'elle soit.
        if p.poll() is not None and not plateforme_en_marche("steam"):
            if complet:
                arreter_steam(prog)
                prog(100, "Steam est installé")
                return True, ""
            if time.time() - debut > 120:
                # On ne se contente pas du constat : Steam ecrit la raison dans
                # ses propres journaux, on va la chercher et on la montre.
                journal_steam_vers_fichier(chemin_journal)
                for _, _, lignes in dernieres_lignes_steam(4):
                    for l in lignes[-3:]:
                        prog(-1, l[:100])
                explication, ligne = cause_probable_steam()
                if explication:
                    return False, "Steam s'est arrêté : %s (%s)" % (explication, ligne)
                return False, ("Steam s'est arrêté avant d'avoir fini de s'installer. "
                               "Le journal brut contient ce qu'il a écrit.")
        if time.time() - debut > 5400:
            return False, "L'installation dure depuis 90 minutes : connexion coupée ?"


def _telecharger(url, dest, prog, base, part):
    """Telecharge `url` vers `dest` par blocs, en rapportant la progression entre base et base+part. Renvoie True si le fichier est complet."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OmniConsole"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            recu = 0
            while True:
                bloc = r.read(256 * 1024)
                if not bloc:
                    break
                f.write(bloc)
                recu += len(bloc)
                if total:
                    prog(base + int(recu * part / total),
                         "Téléchargement %d / %d Mo" % (recu // 1048576, total // 1048576))
        return True
    except Exception:
        return False


def diagnostic_internet():
    """Retourne None si Internet repond, sinon un message clair.

    Plusieurs serveurs et deux tentatives : un seul essai sur une seule adresse
    declarait la connexion perdue bien trop souvent, notamment en machine
    virtuelle ou le reseau met un instant a repondre."""
    joignable = False
    for essai in range(2):
        for hote in ("1.1.1.1", "8.8.8.8", "9.9.9.9"):
            try:
                socket.create_connection((hote, 443), timeout=6).close()
                joignable = True
                break
            except Exception:
                continue
        if joignable:
            break
        time.sleep(1)
    if not joignable:
        return ("Pas de connexion Internet. Vérifie le câble réseau ou choisis un Wi-Fi "
                "dans Réglages > Réseau.")
    try:
        socket.getaddrinfo("repo.steampowered.com", 443)
    except Exception:
        return ("Le réseau fonctionne mais les adresses Internet ne sont pas trouvées (DNS). "
                "Redémarre la console ; si ça continue, c'est un réglage du système.")
    return None


def _exe_du_launcher(pid):
    """Cherche l'executable du launcher dans son prefixe : les installateurs ne
    mettent pas toujours leurs fichiers au meme endroit d'une version a l'autre."""
    attendu = os.path.join(prefixe(pid), LAUNCHERS[pid]["exe"])
    if os.path.isfile(attendu):
        return attendu
    cible = os.path.basename(LAUNCHERS[pid]["exe"])
    r = _run(["find", prefixe(pid), "-name", cible, "-type", "f"], timeout=60)
    if r is not None and r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("\n")[0]
    return None


def installer_moteur_proton(prog, variante="defaut"):
    """Pose umu et Proton depuis la console, par le service d'installation.

    Utile quand l'etape du build a echoue, ou pour la version dediee d'un
    launcher (variante « ubisoft ») : plus besoin de refaire l'ISO."""
    if not os.path.isfile(SERVICE_INSTALL):
        return False, "Le service d'installation de la console est absent."
    intention = "proton" if variante == "defaut" else "proton-" + variante
    prog(2, "Installation du moteur Proton (%s)" % ("version de reference" if variante == "defaut" else variante))
    try:
        p = subprocess.Popen(["sudo", "-n", SERVICE_INSTALL, intention], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace")
    except OSError:
        return False, "Le service d'installation n'a pas pu être lancé."
    derniere = ""
    for ligne in p.stdout:
        ligne = ligne.strip()
        if ligne:
            derniere = ligne
            prog(-1, ligne[:90])
    p.wait()
    if p.returncode == 0 and shutil.which("umu-run") and proton_valide(variante):
        prog(20, "Moteur Proton prêt")
        return True, ""
    return False, "Le moteur Proton n'a pas pu être installé (%s)." % (derniere[:80] or "raison inconnue")


def preparer_moteur(pid, prog):
    """S'assure qu'umu et la bonne version de Proton sont presents pour ce launcher.

    Si la version dediee (Ubisoft) est indisponible, on se rabat sur celle de
    reference plutot que d'abandonner. Renvoie (ok, message)."""
    voulue = LAUNCHERS[pid].get("proton", "defaut")
    if shutil.which("umu-run") and proton_valide(voulue):
        prog(2, "Moteur Proton embarqué : prêt")
        return True, ""
    ok, msg = installer_moteur_proton(prog, voulue)
    if ok or voulue == "defaut":
        return ok, msg
    prog(-1, "Version dédiée de Proton indisponible : version de référence utilisée")
    if shutil.which("umu-run") and proton_valide("defaut"):
        return True, ""
    return installer_moteur_proton(prog, "defaut")


def telecharger_installeur(pid, prog):
    """Telecharge l'installateur officiel du launcher dans le cache. Renvoie
    (chemin, message d'erreur) : le chemin est None si le fichier est inutilisable."""
    L = LAUNCHERS[pid]
    assurer_dossier(os.path.join(CACHE_DIR, "installeurs"))
    dest = os.path.join(CACHE_DIR, "installeurs", L["fichier"])
    prog(4, "Téléchargement de l'installateur officiel")
    if not os.path.isfile(dest) and not _telecharger(L["url"], dest, prog, 4, 56):
        return None, "Téléchargement impossible. Vérifie la connexion Internet."
    if os.path.getsize(dest) < L.get("taille_mini", 5 * 1024 * 1024):
        os.remove(dest)
        return None, ("Le fichier reçu du site officiel n'est pas un installateur "
                      "(peut-être une page d'erreur). Réessaie plus tard.")
    return dest, ""


def essayer_voie(pid, nom, arguments, journal, prog, delai=1200):
    """Lance UNE voie d'installation sous Proton et attend sa fin.

    Toute la sortie de Proton est gardee dans `journal` ; les lignes d'erreur
    remontent en clair. Renvoie la liste des dernieres erreurs lues."""
    erreurs = []
    with open(journal, "a") as sortie:
        sortie.write("\n===== voie : %s =====\nCommande : %s\n" % (nom, " ".join(arguments)))
        sortie.flush()
        p = lancer_umu(arguments, pid, stdout=sortie, stderr=subprocess.STDOUT, start_new_session=True)
        debut = time.time()
        lu = os.path.getsize(journal)
        while p.poll() is None and time.time() - debut < delai:
            time.sleep(3)
            lignes, lu = lire_suite(journal, lu)
            signaler_erreurs(lignes, prog, erreurs)
            prog(-1, "Installation en cours : %d Mo dans le dossier du joueur, %d min"
                 % (taille_dossier(prefixe(pid)) // 1048576, int(time.time() - debut) // 60))
        if p.poll() is None:
            p.terminate()
    return erreurs


def _installer_launcher(pid, prog):
    """Installe un launcher Windows sous Proton, en racontant ce qui se passe.

    Les etapes communes (isolation, moteur, telechargement) sont faites une
    fois ; l'installation elle-meme essaie plusieurs voies (strategies_installation)
    et ne s'arrete qu'a la premiere qui laisse un launcher utilisable."""
    if not reparer_espaces_de_noms(prog):
        detail = " · ".join("%s = %s" % (os.path.basename(f), v) for f, v in etat_isolation()[1])
        return False, ("Le système interdit à Proton son mécanisme d'isolation (%s). "
                       "C'est ce réglage qu'il faut lever dans l'image." % detail)
    ok, msg = preparer_moteur(pid, prog)
    if not ok:
        return False, msg
    assurer_dossier(prefixe(pid))
    assurer_dossier(DOSSIER_JOURNAUX)
    fichier, erreur = telecharger_installeur(pid, prog)
    if not fichier:
        return False, erreur
    journal = os.path.join(DOSSIER_JOURNAUX, "%s-install.log" % pid)
    open(journal, "w").close()
    prog(62, "Installation sous Proton, première fois : c'est long")
    voies = strategies_installation(pid, fichier)
    echecs = []
    for numero, (nom, arguments) in enumerate(voies, 1):
        prog(-1, "Voie %d sur %d : %s" % (numero, len(voies), nom))
        try:
            erreurs = essayer_voie(pid, nom, arguments, journal, prog)
        except OSError:
            return False, "Le moteur Proton n'a pas pu être lancé."
        if _exe_du_launcher(pid):
            noter_recette(pid, nom)
            prog(100, "%s est installé" % PLAT[pid]["nom"])
            return True, ""
        echecs.append("%s : %s" % (nom, erreurs[-1] if erreurs else "rien d'installé"))
        _tuer_prefixe(prefixe(pid))           # un wineserver resté en vie fausserait la voie suivante
    if not os.path.isdir(os.path.join(racine_wine(pid), "drive_c")):
        cause = "Proton n'a pas réussi à créer l'environnement Windows"
    else:
        cause = "l'environnement Windows est là mais %s n'a pas été installé" % PLAT[pid]["nom"]
    return False, "%s (%d voie(s) essayée(s) : %s). Journal : %s" % (
        cause, len(voies), " | ".join(echecs)[:200], journal)


def plateforme_installer(pid, prog):
    """Installe une plateforme. prog(pct, message). Retourne (ok, message)."""
    if not DEMO and pid != "gog":
        prog(0, "Vérification de la connexion...")
        probleme = diagnostic_internet()
        if probleme:
            return False, probleme
    if DEMO:
        for i in range(0, 101, 4):
            prog(i, "Téléchargement..." if i < 50 else "Installation...")
            time.sleep(0.12)
        _marquer_demo(pid, True)
        return True, ""
    try:
        if pid == "steam":
            ok, msg = steam_installer_silencieux(prog)
        elif pid == "emu":
            ok, msg = _apt("emu", prog, 0, 95)
        elif pid == "gog":
            os.makedirs(dossiers_gog()[1], exist_ok=True)
            prog(100, "Dossier des jeux GOG prêt.")
            ok, msg = True, ""
        elif pid in LAUNCHERS:
            ok, msg = _installer_launcher(pid, prog)
        else:
            return False, "Plateforme inconnue."
        ok = ok and plateforme_presente(pid)
        if ok:
            prog(100, "Terminé.")
        return ok, msg or ("" if ok else "Installation incomplète.")
    except PermissionError as erreur:
        # cas connu : le dossier de donnees appartient a l'administrateur
        if reparer_dossier_donnees(prog):
            prog(-1, "Droits corrigés, nouvelle tentative")
            try:
                return plateforme_installer(pid, prog)
            except Exception as seconde:
                return False, "Erreur après correction des droits : %s" % str(seconde)[:140]
        return False, ("Le dossier de données n'est pas accessible au joueur (%s). "
                       "C'est à corriger dans l'installateur." % str(erreur)[:90])
    except Exception as erreur:
        # la vraie raison plutot qu'un message generique, qui ne sert a personne
        return False, "Erreur pendant l'installation : %s" % str(erreur)[:160]


# Version affichee partout : sans elle, impossible de savoir si une console
# teste bien la derniere correction livree.
def lire_version_image():
    """Version de l'image (ecrite par omni-build.sh dans /etc/omni-version), ou « inconnue »
    hors console installee (essai sur une machine de travail)."""
    try:
        with open("/etc/omni-version") as f:
            return f.read().strip() or "inconnue"
    except OSError:
        return "inconnue"


OMNI_VERSION = lire_version_image()

DOSSIER_JOURNAUX = os.path.join(OMNI_DIR, "journaux")
MOTS_ERREUR = ("error", "failed", "cannot", "no such", "missing", "not found", "assert", "segfault",
               "libgl", "vulkan", "gpu", "crash", "timeout")


def plateforme_en_marche(pid):
    """Vrai si la plateforme tourne vraiment.

    On ne peut pas se fier au programme qu'Omni a lance : « steam » n'est qu'un
    lanceur, il demarre le vrai client puis se termine aussitot."""
    if pid == "steam":
        motifs = [["pgrep", "-x", "steam"], ["pgrep", "-f", "steamwebhelper"],
                  ["pgrep", "-f", "steam.sh"]]
    elif pid == "emu":
        motifs = [["pgrep", "-x", "retroarch"]]
    else:
        motifs = [["pgrep", "-f", prefixe(pid)], ["pgrep", "-f", "wineserver"]]
    for cmd in motifs:
        r = _run(cmd, timeout=5)
        if r is not None and r.returncode == 0:
            return True
    return False


def ouverture_surveillee(pid, prog):
    """Ouvre un launcher en gardant sa sortie, puis attend qu'une de ses fenetres
    s'affiche vraiment. Si rien ne vient, on dit pourquoi au lieu de laisser
    l'ecran vide."""
    os.makedirs(DOSSIER_JOURNAUX, exist_ok=True)
    chemin = os.path.join(DOSSIER_JOURNAUX, "%s.log" % pid)
    prog(2, "Ouverture de %s" % PLAT[pid]["nom"])
    if pid == "steam" or pid in LAUNCHERS:
        reparer_espaces_de_noms(prog)
    if pid == "steam" and plateforme_en_marche("steam"):
        # Une instance deja en cours fait echouer la suivante : le nouveau
        # « steam » lui transmet la demande puis se tait. Si elle a une fenetre,
        # il suffit de la ramener devant ; sinon elle est figee, et on la coupe.
        if fenetre_visible("steam"):
            prog(100, "Steam était déjà ouvert")
            return True, ""
        prog(3, "Une session Steam est en cours, on attend qu'elle se termine")
        for _ in range(10):
            time.sleep(2)
            if not plateforme_en_marche("steam"):
                break
        if plateforme_en_marche("steam"):
            prog(-1, "Session Steam figée : elle est arrêtée pour repartir proprement")
            arreter_steam(prog, brutal=True)
    if not carte_3d_presente():
        prog(3, "Aucune carte 3D détectée : affichage logiciel, plus lent")
    fermer_autres_launchers(pid)
    try:
        sortie = open(chemin, "w")
        # le journal brut ne doit jamais etre vide : on y note ce qu'on lance
        sortie.write("Omni : ouverture de %s a %s\n" % (PLAT[pid]["nom"], time.strftime("%H:%M:%S")))
        sortie.flush()
        if pid == "steam":
            cmd = sans_privileges(["steam"] + (["-gamepadui"] if carte_3d_presente() else []))
            env = env_steam()
        elif pid == "emu":
            cmd, env = ["retroarch", "-f"], env_sans_terminal()
        elif pid in LAUNCHERS:
            exe = _exe_du_launcher(pid)
            if not exe:
                return False, ("%s n'est pas vraiment installé dans ton profil : refais l'installation."
                               % PLAT[pid]["nom"])
            p = lancer_umu([exe], pid, stdout=sortie, stderr=subprocess.STDOUT, start_new_session=True)
            cmd = None
        else:
            return False, "Cette plateforme n'a pas de launcher à ouvrir."
        if cmd is not None:
            # la commande exacte dans le journal : indispensable le jour ou
            # c'est l'outil de lancement, et non le programme, qui echoue
            sortie.write("Commande : %s\n" % " ".join(cmd))
            sortie.flush()
            p = subprocess.Popen(cmd, stdout=sortie, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    except Exception:
        return False, "%s n'a pas pu être lancé." % PLAT[pid]["nom"]
    debut = time.time()
    lu = 0
    dernieres = []
    # Sans carte 3D, l'interface de Steam se dessine par le processeur : sur une
    # machine modeste, le premier affichage demande plusieurs minutes. Deux
    # minutes d'attente revenaient a le tuer en plein travail.
    patience = 180 if carte_3d_presente() else 600
    while time.time() - debut < patience:
        time.sleep(3)
        if fenetre_visible(pid if pid != "emu" else "retroarch"):
            prog(100, "%s est à l'écran" % PLAT[pid]["nom"])
            return True, ""
        lignes, lu = lire_suite(chemin, lu)
        signaler_erreurs(lignes, prog, dernieres)
        # le lanceur peut s'etre termine alors que la plateforme, elle, demarre :
        # on ne conclut a l'abandon que si plus rien ne tourne
        if p.poll() is not None and not plateforme_en_marche(pid) and time.time() - debut > 30:
            detail = " · ".join(dernieres[-2:]) if dernieres else "aucune erreur explicite"
            return False, ("%s s'est refermé sans rien afficher (%s). Journal complet : %s"
                           % (PLAT[pid]["nom"], detail, chemin))
        if int(time.time() - debut) % 30 < 3:
            prog(-1, "Toujours en attente de la fenêtre, %d s écoulées sur %d"
                 % (int(time.time() - debut), patience))
    # Toujours rien a l'ecran. On ne tue plus Steam : il peut etre en train de
    # terminer son premier affichage, et le couper detruirait tout son travail.
    # Le joueur garde la main sur Omni, et peut ressayer ou revenir au menu.
    if pid != "steam":
        fermer_launcher(pid)
    # une erreur de l'outil de lancement lui-meme : le programme n'a jamais
    # demarre, inutile d'aller chercher plus loin
    for ligne in lire_suite(chemin, 0)[0]:
        if ligne.startswith(("Omni :", "Commande :")):
            continue  # nos propres traces ne sont pas des erreurs
        bas = ligne.lower()
        if any(m in bas for m in ("setpriv:", "execvp", "command not found", "not permitted")):
            return False, ("%s n'a pas pu être lancé : %s"
                           % (PLAT[pid]["nom"], ligne.strip()[:110]))
    if pid == "steam":
        journal_steam_vers_fichier(chemin)
        explication, ligne = cause_probable_steam()
        if explication:
            return False, "Steam n'a pas pu s'ouvrir : %s (%s)" % (explication, ligne)
    detail = " · ".join(dernieres[-2:]) if dernieres else ""
    minutes = int(patience // 60)
    if pid == "steam" and plateforme_en_marche("steam"):
        return False, ("Steam tourne toujours mais n'a pas affiché sa fenêtre en %d minutes. "
                       "Sans carte 3D, son premier démarrage est très lent : laisse-le "
                       "travailler, il peut apparaître d'un instant à l'autre. %s"
                       % (minutes, detail))
    return False, ("%s tourne mais n'affiche aucune fenêtre après %d minutes. "
                   "Sans carte 3D, son interface n'y arrive souvent pas. %s"
                   % (PLAT[pid]["nom"], minutes, detail))


# ---------------------------------------------------------------------------
# Lecture des jeux installes (fichiers de suivi des launchers)
# Un jeu = dict(id, titre, plateforme, genre, jaquette, etat, progression, lancement)
# ---------------------------------------------------------------------------
STEAM_RACINES = ["~/.local/share/Steam", "~/.steam/steam", "~/.steam/debian-installation",
                 "~/snap/steam/common/.local/share/Steam"]
STEAM_IGNORES = ("Proton", "Steam Linux Runtime", "Steamworks Common", "SteamVR")


def _acf(texte, cle):
    m = re.search(r'"%s"\s+"([^"]*)"' % cle, texte)
    return m.group(1) if m else ""


def steam_racine():
    """Dossier du client Steam du joueur, s'il est installe.

    Un client neuf n'a pas encore de dossier « steamapps », puisque aucun jeu
    n'est installe : on le reconnait donc a son lanceur ou a son environnement
    d'execution, jamais a ses jeux."""
    for r in STEAM_RACINES:
        p = os.path.expanduser(r)
        if any(os.path.exists(os.path.join(p, marque))
               for marque in ("steam.sh", "ubuntu12_64", "steamapps")):
            return os.path.realpath(p)
    return None


def jeux_steam():
    """Jeux Steam installes, lus dans les appmanifest_*.acf de toutes les bibliotheques (libraryfolders.vdf). Un jeu en cours de telechargement est marque comme tel."""
    racine = steam_racine()
    if not racine:
        return []
    biblios = {os.path.join(racine, "steamapps")}
    try:
        with open(os.path.join(racine, "steamapps", "libraryfolders.vdf")) as f:
            for chemin in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                biblios.add(os.path.join(chemin, "steamapps"))
    except Exception:
        pass
    jeux, vus = [], set()
    for b in biblios:
        for acf in glob.glob(os.path.join(b, "appmanifest_*.acf")):
            try:
                with open(acf, errors="ignore") as f:
                    t = f.read()
            except Exception:
                continue
            appid, nom = _acf(t, "appid"), _acf(t, "name")
            if not appid or appid in vus or nom.startswith(STEAM_IGNORES):
                continue
            vus.add(appid)
            etat = int(_acf(t, "StateFlags") or 0)
            a_dl = int(_acf(t, "BytesToDownload") or 0)
            dl = int(_acf(t, "BytesDownloaded") or 0)
            en_cours = not (etat & 4) or (a_dl and dl < a_dl)
            jeux.append({"id": "steam-" + appid, "titre": nom, "plateforme": "steam", "genre": "",
                         "jaquette": _steam_jaquette_locale(racine, appid),
                         "etat": "telechargement" if en_cours else "installe",
                         "progression": int(dl * 100 / a_dl) if a_dl else 0,
                         "lancement": {"appid": appid}})
    return sorted(jeux, key=lambda j: j["titre"].lower())


def _steam_jaquette_locale(racine, appid):
    lc = os.path.join(racine, "appcache", "librarycache")
    for c in [os.path.join(lc, "%s_library_600x900.jpg" % appid), os.path.join(lc, appid, "library_600x900.jpg"),
              os.path.join(lc, "%s_header.jpg" % appid), os.path.join(lc, appid, "header.jpg")]:
        if os.path.isfile(c):
            return c
    return None


def steam_connecte():
    racine = steam_racine()
    try:
        with open(os.path.join(racine, "config", "loginusers.vdf")) as f:
            return "AccountName" in f.read()
    except Exception:
        return False


def jeux_gog():
    """Jeux GOG : un dossier contenant start.sh (installateur Linux de GOG) dans les dossiers GOG connus."""
    jeux = []
    for d in dossiers_gog():
        for dossier in sorted(glob.glob(os.path.join(d, "*"))):
            start = os.path.join(dossier, "start.sh")
            if not os.path.isfile(start):
                continue
            titre = os.path.basename(dossier)
            try:
                with open(os.path.join(dossier, "gameinfo")) as f:
                    titre = f.readline().strip() or titre
            except Exception:
                pass
            icone = os.path.join(dossier, "support", "icon.png")
            jeux.append({"id": "gog-" + os.path.basename(dossier), "titre": titre, "plateforme": "gog",
                         "genre": "", "jaquette": icone if os.path.isfile(icone) else None,
                         "etat": "installe", "progression": 0, "lancement": {"script": start}})
    return jeux


# extension de ROM -> (systeme affiche, coeur libretro)
EMU_SYSTEMES = {
    ".nes": ("NES", "nestopia"), ".sfc": ("SNES", "snes9x"), ".smc": ("SNES", "snes9x"),
    ".gba": ("GBA", "mgba"), ".gb": ("GAME BOY", "mgba"), ".gbc": ("GAME BOY", "mgba"),
    ".md": ("MEGADRIVE", "genesis_plus_gx"), ".gen": ("MEGADRIVE", "genesis_plus_gx"),
    ".sms": ("MASTER SYSTEM", "genesis_plus_gx"), ".cue": ("PLAYSTATION", "mednafen_psx"),
    ".chd": ("PLAYSTATION", "mednafen_psx"),
}
LIBRETRO_DIRS = ["/usr/lib/x86_64-linux-gnu/libretro", "/usr/lib/libretro"]


def coeur_libretro(nom):
    for d in LIBRETRO_DIRS:
        c = os.path.join(d, nom + "_libretro.so")
        if os.path.isfile(c):
            return c
    return None


def jeux_emu():
    """ROMs reconnues par leur extension (EMU_SYSTEMES), avec le coeur libretro qui les lit."""
    jeux = []
    for d in dossiers_roms():
        for rom in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            ext = os.path.splitext(rom)[1].lower()
            if ext not in EMU_SYSTEMES:
                continue
            systeme, coeur = EMU_SYSTEMES[ext]
            titre = re.sub(r"\s*[\(\[].*?[\)\]]", "", os.path.splitext(os.path.basename(rom))[0]).strip()
            jeux.append({"id": "emu-" + rom, "titre": titre or rom, "plateforme": "emu", "genre": systeme,
                         "jaquette": None, "etat": "installe", "progression": 0,
                         "lancement": {"rom": rom, "coeur": coeur}})
    return jeux


def jeux_epic():
    """Jeux Epic installes, lus dans les manifestes du launcher (DANS le prefixe Proton, sous pfx)."""
    manifestes = os.path.join(racine_wine("epic"), "drive_c/ProgramData/Epic/EpicGamesLauncher/Data/Manifests")
    jeux = []
    for item in glob.glob(os.path.join(manifestes, "*.item")):
        try:
            with open(item) as f:
                m = json.load(f)
        except Exception:
            continue
        if m.get("bIsApplication") is False:
            continue
        jeux.append({"id": "epic-" + m.get("AppName", item), "titre": m.get("DisplayName", "?"),
                     "plateforme": "epic", "genre": "", "jaquette": None,
                     "etat": "telechargement" if m.get("bIsIncompleteInstall") else "installe",
                     "progression": 0, "lancement": {"appname": m.get("AppName", "")}})
    return jeux


DEMO_JEUX = {
    "steam": [("Hades", "ACTION"), ("Cyberpunk 2077", "RPG"), ("Neon Abyss", "ROGUELIKE"),
              ("Celeste", "PLATFORMER"), ("Dead Cells", "METROIDVANIA"), ("Portal 2", "PUZZLE"),
              ("Hollow Knight", "METROIDVANIA")],
    "gog": [("The Witcher 3", "RPG"), ("Disco Elysium", "RPG")],
    "emu": [("Super Metroid", "SNES"), ("Sonic 2", "MEGADRIVE"), ("Zelda Minish Cap", "GBA")],
    "epic": [("Alan Wake 2", "ACTION"), ("Fortnite", "BATTLE ROYALE")],
    "ea": [], "ubisoft": [],
}


def jeux_de(pid):
    """Jeux installes d'une plateforme. En demo, jeux fictifs ; sinon la fonction de lecture de la plateforme, ou une liste vide en cas d'erreur."""
    if DEMO:
        liste = []
        for i, (t, g) in enumerate(DEMO_JEUX.get(pid, [])):
            dl = pid == "steam" and i == 6
            liste.append({"id": "%s-demo-%d" % (pid, i), "titre": t, "plateforme": pid, "genre": g,
                          "jaquette": None, "etat": "telechargement" if dl else "installe",
                          "progression": 45 if dl else 0, "lancement": {}})
        return liste
    try:
        return {"steam": jeux_steam, "gog": jeux_gog, "emu": jeux_emu, "epic": jeux_epic}.get(pid, lambda: [])()
    except Exception:
        return []


def _tuer_prefixe(prefix):
    """Arrete tous les processus Windows d'un prefixe Proton (launcher + jeu)."""
    motif = ("WINEPREFIX=" + prefix).encode()
    cibles = []
    for pid in os.listdir("/proc"):
        if pid.isdigit() and int(pid) != os.getpid():
            try:
                with open("/proc/%s/environ" % pid, "rb") as f:
                    if motif in f.read():
                        cibles.append(int(pid))
            except Exception:
                pass
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for c in cibles:
            try:
                os.kill(c, sig)
            except Exception:
                pass
        if sig == signal.SIGTERM and cibles:
            time.sleep(3)


def fermer_launcher(pid):
    """Ferme le launcher d'une plateforme (regle : jamais deux launchers a la fois,
    et le launcher part avec le jeu quand le joueur quitte)."""
    if DEMO:
        return
    try:
        if pid == "steam":
            essai = _run(["pgrep", "-x", "steam"])
            if essai is not None and essai.returncode == 0:
                subprocess.Popen(sans_privileges(["steam", "-shutdown"]),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif pid in LAUNCHERS:
            threading.Thread(target=_tuer_prefixe, args=(prefixe(pid),), daemon=True).start()
    except Exception:
        pass


def fermer_autres_launchers(pid):
    for autre in ["steam"] + list(LAUNCHERS):
        if autre != pid:
            fermer_launcher(autre)


def lancer_jeu(jeu):
    """Lance un jeu depuis sa tuile et renvoie le processus (ou False/None). Le launcher des autres plateformes est ferme d'abord : jamais deux launchers a la fois."""
    if DEMO:
        return True
    fermer_autres_launchers(jeu["plateforme"])
    L = jeu.get("lancement", {})
    try:
        if jeu["plateforme"] == "steam":
            return subprocess.Popen(sans_privileges(["steam", "-silent", "steam://rungameid/" + L["appid"]]),
                                    env=env_steam())
        elif jeu["plateforme"] == "gog":
            return subprocess.Popen(["bash", L["script"]], cwd=os.path.dirname(L["script"]))
        elif jeu["plateforme"] == "emu":
            coeur = coeur_libretro(L["coeur"])
            cmd = ["retroarch", "-f"] + (["-L", coeur] if coeur else []) + [L["rom"]]
            return subprocess.Popen(cmd)
        elif jeu["plateforme"] == "epic":
            exe = _exe_du_launcher("epic")
            uri = "com.epicgames.launcher://apps/%s?action=launch&silent=true" % L["appname"]
            return lancer_umu([exe, uri], "epic") if exe else None
        return False
    except Exception:
        return False


def steam_infos_distantes(appid, dossier):
    """Telecharge jaquette + genre depuis le magasin Steam, mis en cache dans le
    profil. Appele en arriere-plan ; silencieux sans reseau."""
    os.makedirs(dossier, exist_ok=True)
    jaq = os.path.join(dossier, "steam_%s.jpg" % appid)
    info = os.path.join(dossier, "steam_%s.json" % appid)
    if not os.path.isfile(jaq):
        for nom in ("library_600x900.jpg", "header.jpg"):
            if _telecharger("https://cdn.akamai.steamstatic.com/steam/apps/%s/%s" % (appid, nom),
                            jaq, lambda p, m: None, 0, 1):
                break
    if not os.path.isfile(info):
        try:
            url = "https://store.steampowered.com/api/appdetails?appids=%s&l=french&filters=genres" % appid
            with urllib.request.urlopen(url, timeout=10) as r:
                d = json.load(r)
            genres = d.get(str(appid), {}).get("data", {}).get("genres", [])
            with open(info, "w") as f:
                json.dump({"genre": genres[0]["description"].upper() if genres else ""}, f)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cartes de profil (sprite sheets steampunk)
# ---------------------------------------------------------------------------
PLANCHES = {
    "planche1": {"fichier": "planche1.jpg", "cols": 5, "rows": 3},
    "planche2": {"fichier": "planche2.jpg", "cols": 4, "rows": 3},
    "planche3": {"fichier": "planche3.jpg", "cols": 5, "rows": 3},
    "planche4": {"fichier": "planche4.jpg", "cols": 4, "rows": 3},
}
_planches_pil = {}
_cache_img = {}


def _ouvrir_planche(nom):
    """Ouvre une planche de cartes de profil (une seule fois, puis en memoire)."""
    if nom in _planches_pil:
        return _planches_pil[nom]
    p = PLANCHES.get(nom)
    if not p:
        return None
    try:
        img = Image.open(os.path.join(CARTES_DIR, p["fichier"])).convert("RGBA")
        _planches_pil[nom] = img
        return img
    except Exception:
        return None


def _case_carte(planche, ligne, colonne):
    """Decoupe une carte dans sa planche (ligne, colonne), en rognant un petit bord de decoupe."""
    img = _ouvrir_planche(planche)
    if img is None:
        return None
    p = PLANCHES[planche]
    W, H = img.size
    cw, ch = W // p["cols"], H // p["rows"]
    mx, my = int(cw * 0.03), int(ch * 0.03)
    return img.crop((colonne * cw + mx, ligne * ch + my, (colonne + 1) * cw - mx, (ligne + 1) * ch - my))


def extraire_carte(planche, ligne, colonne, larg, haut):
    c = _case_carte(planche, ligne, colonne)
    return c.resize((larg, haut)) if c else None


def avatar_image(planche, ligne, colonne, taille):
    """Vignette carree (haut de la carte, la ou est le personnage)."""
    if not PIL_OK:
        return None
    cle = ("av", planche, ligne, colonne, taille)
    if cle in _cache_img:
        return _cache_img[cle]
    c = _case_carte(planche, ligne, colonne)
    if c is None:
        return None
    w, h = c.size
    cote = int(w * 0.82)
    x0 = (w - cote) // 2
    y0 = int(h * 0.10)
    img = ImageTk.PhotoImage(c.crop((x0, y0, x0 + cote, y0 + cote)).resize((taille, taille)))
    _cache_img[cle] = img
    return img


def jaquette_image(jeu, larg, haut, fichier=None):
    """Jaquette recadree ; a defaut, une affiche synthwave generee avec les initiales."""
    if not PIL_OK:
        return None
    cle = ("jaq", jeu["id"], larg, haut, fichier or jeu.get("jaquette"), T["mag"])
    if cle in _cache_img:
        return _cache_img[cle]
    src = fichier or jeu.get("jaquette")
    img = None
    if src and os.path.isfile(src):
        try:
            im = Image.open(src).convert("RGB")
            r = max(larg / im.width, haut / im.height)
            im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
            x0, y0 = (im.width - larg) // 2, (im.height - haut) // 2
            img = im.crop((x0, y0, x0 + larg, y0 + haut))
        except Exception:
            img = None
    if img is None:
        img = _affiche_generee(jeu, larg, haut)
    ph = ImageTk.PhotoImage(img)
    _cache_img[cle] = ph
    return ph


def _affiche_generee(jeu, larg, haut):
    """Affiche maison : ciel degrade, soleil raye pose sur l'horizon, grille au
    sol teintee a la couleur de la plateforme. Position du soleil propre a chaque jeu."""
    teinte = PLAT.get(jeu["plateforme"], {}).get("couleur", T["mag"])
    graine = sum(ord(c) for c in jeu["titre"])
    im = Image.new("RGB", (larg, haut), hex_rgb(T["bg"]))
    d = ImageDraw.Draw(im)
    horizon = int(haut * 0.64)
    for y in range(horizon):
        d.line([(0, y), (larg, y)], fill=hex_rgb(mel("#3a0d6e", T["bg"], 1 - y / horizon * 0.8)))
    r = int(haut * 0.36)
    cx = int(larg * (0.30 + (graine % 41) / 100.0))
    cy = horizon - int(r * 0.25)
    for y in range(cy - r, horizon):
        t = (y - (cy - r)) / float(2 * r)
        # bandes vides de plus en plus larges vers le bas
        if t > 0.30:
            periode = max(5, r // 5)
            if (y - (cy - r)) % periode < int(periode * (t - 0.26) * 2.4):
                continue
        demi = (r * r - (y - cy) ** 2) ** 0.5 if abs(y - cy) < r else 0
        col = hex_rgb(mel(SOLEIL[0], SOLEIL[-1], min(1, t * 1.25)))
        d.line([(cx - demi, y), (cx + demi, y)], fill=col)
    # silhouette de collines
    pts = [(0, horizon)]
    for k in range(9):
        x = k * larg / 8.0
        pts.append((x, horizon - int(haut * (0.03 + ((graine * (k + 3)) % 7) / 100.0))))
    pts.append((larg, horizon))
    d.polygon(pts, fill=hex_rgb(mel(T["bg"], "#2a0b5a", 0.4)))
    grille = hex_rgb(mel(teinte, T["bg"], 0.45))
    for k in range(1, 8):
        y = horizon + int((haut - horizon) * (k / 7.0) ** 1.9)
        d.line([(0, y), (larg, y)], fill=grille, width=max(1, haut // 300))
    for k in range(-10, 11):
        d.line([(larg // 2, horizon), (larg // 2 + k * larg // 6, haut)], fill=grille, width=max(1, haut // 300))
    d.line([(0, horizon), (larg, horizon)], fill=hex_rgb(teinte), width=max(2, haut // 150))
    return im


# ---------------------------------------------------------------------------
# Profils et reglages
# ---------------------------------------------------------------------------
def charger_profils():
    """Lit les profils enregistres. Complete les champs absents et migre l'ancien format (date en texte, etat global des plateformes)."""
    try:
        with open(PROFILS_FILE) as f:
            profils = json.load(f)
    except Exception:
        return []
    ancien = _etat_demo() if not DEMO else {}
    for p in profils:
        p.setdefault("id", uuid.uuid4().hex[:8])
        p.setdefault("plateformes", [])
        da = p.get("derniere_activite")
        if isinstance(da, str):
            try:
                p["derniere_activite"] = time.mktime(time.strptime(da, "%d/%m/%Y"))
            except Exception:
                p["derniere_activite"] = 0
        # reprise de l'ancien etat global des plateformes (avant le suivi par profil)
        if not p.get("migre"):
            for pid, inst in ancien.items():
                if inst and pid in PLAT and pid not in p["plateformes"]:
                    p["plateformes"].append(pid)
            p["migre"] = True
    return profils


def sauver_profils(profils):
    os.makedirs(OMNI_DIR, exist_ok=True)
    try:
        with open(PROFILS_FILE, "w") as f:
            json.dump(profils, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def charger_reglages():
    """Reglages d'affichage et de son, avec leurs valeurs par defaut si le fichier manque."""
    r = {"zoom": 1.0, "contraste": False, "dalton": "aucun", "sons": True}
    try:
        with open(REGLAGES_FILE) as f:
            r.update(json.load(f))
    except Exception:
        pass
    return r


def sauver_reglages(r):
    os.makedirs(OMNI_DIR, exist_ok=True)
    try:
        with open(REGLAGES_FILE, "w") as f:
            json.dump(r, f, indent=2)
    except Exception:
        pass


def il_y_a(ts):
    """Duree ecoulee depuis `ts` en clair : « a l'instant », « il y a 5 min », « le 03/10/2026 »..."""
    if not ts:
        return "jamais"
    d = time.time() - ts
    if d < 60:
        return "à l'instant"
    if d < 3600:
        return "il y a %d min" % (d // 60)
    if d < 86400:
        return "il y a %dh" % (d // 3600)
    if d < 7 * 86400:
        return "il y a %d j" % (d // 86400)
    return "le " + time.strftime("%d/%m/%Y", time.localtime(ts))


def toutes_les_cartes():
    return [(nom, r, c) for nom, p in PLANCHES.items() for r in range(p["rows"]) for c in range(p["cols"])]


# ---------------------------------------------------------------------------
# Dessin neon sur Canvas
# ---------------------------------------------------------------------------
# epaisseur des traits proportionnelle a l'ecran (1 en 1080p, 2 en 4K) : sinon les
# liseres neon deviennent des fils sur une grande TV
TRAIT = [1.0]


def rrect(cv, x0, y0, x1, y1, r, **kw):
    if "width" in kw:
        kw["width"] = max(1, round(kw["width"] * TRAIT[0]))
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


def neon(cv, x0, y0, x1, y1, r, col, fill="", w=2, halo=3, tags=None, halo_col=None):
    """Cadre neon : halo degrade autour + trait net. Renvoie l'id du trait."""
    hc = halo_col or col
    for i in range(halo, 0, -1):
        o = i * 2 * TRAIT[0]
        rrect(cv, x0 - o, y0 - o, x1 + o, y1 + o, r + o, outline=mel(hc, T["bg"], 0.45 + 0.17 * i),
              fill="", width=2, tags=tags)
    return rrect(cv, x0, y0, x1, y1, r, outline=col, fill=fill, width=w, tags=tags)


def soleil(cv, x, y, larg, haut, tags=None):
    """Soleil a six barres degradees ambre -> magenta."""
    h = haut / 6.0
    for i, c in enumerate(SOLEIL):
        rrect(cv, x, y + i * h, x + larg, y + i * h + h * 0.72, h * 0.36, fill=c, outline="", tags=tags)


# ----- Icones dessinees (pas de texte a la place d'un logo) -----
def ico_clavier(cv, cx, cy, s, col, tags=None):
    """Icone clavier, dessinee (pas de texte a la place d'un logo)."""
    w, h = s * 0.84, s * 0.56
    x0, y0 = cx - w / 2, cy - h / 2
    rrect(cv, x0, y0, x0 + w, y0 + h, s * 0.08, outline=col, fill="", width=max(2, s / 18), tags=tags)
    k = w / 8.2
    for rang, n, dec in [(0, 7, 0.6), (1, 6, 1.1)]:
        for i in range(n):
            kx = x0 + dec * k + i * k * 1.02
            ky = y0 + h * 0.20 + rang * h * 0.24
            cv.create_rectangle(kx, ky, kx + k * 0.62, ky + h * 0.14, fill=col, outline="", tags=tags)
    cv.create_rectangle(x0 + w * 0.26, y0 + h * 0.70, x0 + w * 0.74, y0 + h * 0.82, fill=col, outline="", tags=tags)


def ico_acces(cv, cx, cy, s, col, tags=None):
    """Pictogramme d'accessibilite universel (silhouette dans un cercle)."""
    r = s * 0.44
    lw = max(2, s / 16)
    cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=lw, tags=tags)
    t = s * 0.075
    cv.create_oval(cx - t, cy - r * 0.62 - t, cx + t, cy - r * 0.62 + t, fill=col, outline="", tags=tags)
    cv.create_line(cx - r * 0.58, cy - r * 0.30, cx, cy - r * 0.22, cx + r * 0.58, cy - r * 0.30,
                   fill=col, width=lw, capstyle="round", tags=tags)
    cv.create_line(cx, cy - r * 0.22, cx, cy + r * 0.12, fill=col, width=lw, tags=tags)
    cv.create_line(cx - r * 0.34, cy + r * 0.62, cx, cy + r * 0.12, cx + r * 0.34, cy + r * 0.62,
                   fill=col, width=lw, capstyle="round", joinstyle="round", tags=tags)


def ico_reglages(cv, cx, cy, s, col, tags=None):
    """Icone d'engrenage, dessinee."""
    r1, r2 = s * 0.26, s * 0.40
    lw = max(3, s / 10)
    for i in range(8):
        a = i * math.pi / 4
        cv.create_line(cx + math.cos(a) * r1, cy + math.sin(a) * r1, cx + math.cos(a) * r2, cy + math.sin(a) * r2,
                       fill=col, width=lw, tags=tags)
    cv.create_oval(cx - r1 * 1.05, cy - r1 * 1.05, cx + r1 * 1.05, cy + r1 * 1.05, outline=col, width=max(2, s / 14), tags=tags)
    cv.create_oval(cx - r1 * 0.38, cy - r1 * 0.38, cx + r1 * 0.38, cy + r1 * 0.38, outline=col, width=max(2, s / 18), tags=tags)


def ico_plus(cv, cx, cy, s, col, tags=None):
    lw = max(3, s / 8)
    cv.create_line(cx - s * 0.36, cy, cx + s * 0.36, cy, fill=col, width=lw, capstyle="round", tags=tags)
    cv.create_line(cx, cy - s * 0.36, cx, cy + s * 0.36, fill=col, width=lw, capstyle="round", tags=tags)


def ico_retour(cv, cx, cy, s, col, tags=None):
    lw = max(3, s / 9)
    cv.create_line(cx + s * 0.34, cy, cx - s * 0.30, cy, fill=col, width=lw, capstyle="round", tags=tags)
    cv.create_line(cx - s * 0.05, cy - s * 0.28, cx - s * 0.33, cy, cx - s * 0.05, cy + s * 0.28,
                   fill=col, width=lw, capstyle="round", joinstyle="round", tags=tags)


def ico_fermer(cv, cx, cy, s, col, tags=None):
    lw = max(3, s / 9)
    d = s * 0.28
    cv.create_line(cx - d, cy - d, cx + d, cy + d, fill=col, width=lw, capstyle="round", tags=tags)
    cv.create_line(cx - d, cy + d, cx + d, cy - d, fill=col, width=lw, capstyle="round", tags=tags)


def ico_joueurs(cv, cx, cy, s, col, tags=None):
    """Icone de deux joueurs, dessinee."""
    lw = max(2, s / 14)
    for dx, k in [(-s * 0.16, 0.8), (s * 0.12, 1.0)]:
        r = s * 0.13 * k
        hx = cx + dx
        cv.create_oval(hx - r, cy - s * 0.26 - r, hx + r, cy - s * 0.26 + r, outline=col, width=lw, tags=tags)
        cv.create_arc(hx - s * 0.24 * k, cy - s * 0.06, hx + s * 0.24 * k, cy + s * 0.40, start=0, extent=180,
                      style="arc", outline=col, width=lw, tags=tags)


def ico_lecture(cv, cx, cy, s, col, tags=None):
    d = s * 0.30
    cv.create_polygon(cx - d * 0.7, cy - d, cx - d * 0.7, cy + d, cx + d, cy, fill=col, outline="", tags=tags)


def ico_alim(cv, cx, cy, s, col, tags=None):
    """Symbole d'alimentation : arc ouvert en haut et barre verticale."""
    lw = max(3, s / 9)
    r = s * 0.30
    cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=120, extent=300, style="arc", outline=col, width=lw, tags=tags)
    cv.create_line(cx, cy - r * 1.1, cx, cy - r * 0.1, fill=col, width=lw, capstyle="round", tags=tags)


def ico_redem(cv, cx, cy, s, col, tags=None):
    """Fleche circulaire (redemarrer)."""
    lw = max(3, s / 9)
    r = s * 0.30
    cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=60, extent=270, style="arc", outline=col, width=lw, tags=tags)
    cv.create_polygon(cx + r * 0.95, cy - r * 0.9, cx + r * 0.2, cy - r * 0.95, cx + r * 0.75, cy - r * 0.25,
                      fill=col, outline="", tags=tags)


ICONES = {"alim": ico_alim, "redem": ico_redem, "clavier": ico_clavier, "acces": ico_acces, "reglages": ico_reglages, "plus": ico_plus,
          "retour": ico_retour, "fermer": ico_fermer, "joueurs": ico_joueurs, "lecture": ico_lecture}


def pastille(cv, x, y, s, plat, tags=None, estompee=False):
    """Pastille maison d'une plateforme : carre arrondi + sigle a sa couleur."""
    col = plat["couleur"] if not estompee else T["dim"]
    rrect(cv, x, y, x + s, y + s, s * 0.14, fill=T["bg"], outline=col, width=max(1, s / 22), tags=tags)
    taille = int(s * (0.30 if len(plat["sigle"]) > 2 else 0.34))
    cv.create_text(x + s / 2, y + s / 2, text=plat["sigle"], fill=col,
                   font=(FONT_NAME, -max(8, taille), "bold"), tags=tags)


# ---------------------------------------------------------------------------
# Boutons neon (Canvas) : texte et/ou icone, survol lumineux, etat inactif
# ---------------------------------------------------------------------------
class NeonBouton(tk.Canvas):
    """Bouton neon dessine sur un Canvas : texte et/ou icone, halo au survol, etat inactif, infobulle."""
    def __init__(self, parent, app, texte="", commande=None, couleur=None, icone=None,
                 largeur=None, hauteur=None, plein=False, taille=15, infobulle=None, son="select"):
        """Mesure le bouton d'apres son texte et sa police, puis le dessine."""
        self.app = app
        self.texte, self.commande, self.icone = texte, commande, icone
        self.couleur = couleur or T["cyan"]
        self.plein, self.taille, self.son = plein, taille, son
        self.actif, self.survol = True, False
        self.infobulle = infobulle
        self._bulle = None
        f = app.police(taille, True)
        h = hauteur or app.px(52)
        if largeur is None:
            largeur = f.measure(texte) + app.px(48) + (app.px(34) if icone and texte else 0)
            if icone and not texte:
                largeur = h
        self.W, self.H = int(largeur), int(h)
        m = app.px(8)
        super().__init__(parent, width=self.W + 2 * m, height=self.H + 2 * m, bg=parent["bg"],
                         highlightthickness=0, cursor="hand2")
        self.m = m
        self.bind("<Enter>", self._entre)
        self.bind("<Leave>", self._sort)
        self.bind("<Button-1>", self._clic)
        self._dessiner()

    def _dessiner(self):
        """Redessine le bouton selon son etat : survol, inactif, plein ou contour."""
        self.delete("all")
        m, W, H, a = self.m, self.W, self.H, self.app
        col = self.couleur if self.actif else T["dim"]
        r = a.px(8)
        if self.plein:
            fond = mel(col, "#ffffff", 0.15) if self.survol else col
            neon(self, m, m, m + W, m + H, r, fond, fill=fond, halo=3 if self.survol else 2, w=a.epais())
            enc = T["bg"]
        else:
            fond = mel(col, T["bg"], 0.78) if self.survol else T["panel"]
            neon(self, m, m, m + W, m + H, r, col, fill=fond, halo=3 if self.survol else 1, w=a.epais())
            enc = T["text"] if self.survol else col
        cx, cy = m + W / 2, m + H / 2
        if self.icone and self.texte:
            f = a.police(self.taille, True)
            tw = f.measure(self.texte)
            ix = cx - (tw + a.px(34)) / 2 + a.px(12)
            ICONES[self.icone](self, ix, cy, a.px(26), enc)
            self.create_text(ix + a.px(22), cy, text=self.texte, anchor="w", fill=enc, font=f)
        elif self.icone:
            ICONES[self.icone](self, cx, cy, H * 0.62, enc)
        else:
            self.create_text(cx, cy, text=self.texte, fill=enc, font=a.police(self.taille, True))

    def _entre(self, e):
        if not self.actif:
            return
        self.survol = True
        self._dessiner()
        if self.infobulle:
            self._montrer_bulle()

    def _sort(self, e):
        self.survol = False
        self._dessiner()
        if self._bulle is not None:
            self._bulle.destroy()
            self._bulle = None

    def _montrer_bulle(self):
        a = self.app
        self._bulle = tk.Label(a, text=self.infobulle, font=a.police(12, True), fg=T["bg"], bg=T["cyan"],
                               padx=a.px(8), pady=a.px(3))
        x = self.winfo_rootx() - a.winfo_rootx() + self.winfo_width() // 2
        y = self.winfo_rooty() - a.winfo_rooty() + self.winfo_height()
        self._bulle.place(x=x, y=y, anchor="n")

    def _clic(self, e):
        if self.actif and self.commande:
            self.app.jouer_son(self.son)
            if self._bulle is not None:
                self._bulle.destroy()
                self._bulle = None
            self.commande()

    def set_actif(self, actif, texte=None):
        self.actif = actif
        if texte is not None:
            self.texte = texte
        self.configure(cursor="hand2" if actif else "arrow")
        self._dessiner()

    def set_texte(self, texte, couleur=None):
        self.texte = texte
        if couleur:
            self.couleur = couleur
        self._dessiner()


def bouton(parent, texte, commande, couleur=None, largeur=None, app=None, **kw):
    """Compatibilite avec l'ancien code : bouton() cree un NeonBouton."""
    app = app or parent.winfo_toplevel()
    lg = app.px(largeur * 13) if largeur else None
    return NeonBouton(parent, app, texte, commande, couleur=couleur, largeur=lg, **kw)


class ZoneDefilante(tk.Frame):
    """Canvas defilant avec une barre de defilement neon fine (comme la maquette)."""

    def __init__(self, parent, app, largeur, hauteur, bg=None):
        """Canvas defilant avec sa barre de defilement dessinee a droite."""
        bg = bg or T["bg"]
        super().__init__(parent, bg=bg)
        self.app = app
        self.cv = tk.Canvas(self, width=largeur, height=hauteur, bg=bg, highlightthickness=0)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb = tk.Canvas(self, width=app.px(14), height=hauteur, bg=bg, highlightthickness=0)
        self.sb.pack(side="left", fill="y", padx=(app.px(8), 0))
        self.hauteur = hauteur
        self.contenu = hauteur
        self.cv.configure(yscrollcommand=self._maj_barre)
        for w in (self.cv, self.sb):
            w.bind("<Enter>", lambda e: self._lier(True))
            w.bind("<Leave>", lambda e: self._lier(False))
        self.sb.bind("<B1-Motion>", self._glisser)
        self.sb.bind("<Button-1>", self._glisser)

    def set_contenu(self, h):
        self.contenu = max(h, self.hauteur)
        self.cv.configure(scrollregion=(0, 0, int(self.cv["width"]), self.contenu))
        self._maj_barre(*self.cv.yview())

    def _maj_barre(self, debut, fin):
        """Dessine la poignee de la barre selon la portion visible (rien si tout tient)."""
        debut, fin = float(debut), float(fin)
        sb, a = self.sb, self.app
        sb.delete("all")
        h = self.hauteur
        if fin - debut >= 0.999:
            return
        w = a.px(8)
        x = (int(sb["width"]) - w) / 2
        rrect(sb, x, 0, x + w, h, w / 2, fill=mel(T["dim"], T["bg"], 0.55), outline="")
        y0, y1 = debut * h, max(debut * h + a.px(30), fin * h)
        neon(sb, x, y0, x + w, y1, w / 2, T["cyan"], fill=mel(T["cyan"], "#ffffff", 0.35), halo=1, w=1)

    def _glisser(self, e):
        self.cv.yview_moveto(max(0, min(1, e.y / self.hauteur - 0.1)))

    def _lier(self, oui):
        """Branche (ou debranche) la molette de la souris tant que le pointeur est dans la zone."""
        a = self.app
        if oui:
            a.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-2, "units"))
            a.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(2, "units"))
            a.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        else:
            for ev in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
                a.unbind_all(ev)


# Appui long sur le bouton Guide (ou Select + Start) : ouvre le menu Omni.
APPUIS_LONGS = ("GUIDE_BAS", "GUIDE_HAUT", "COMBO_BAS", "COMBO_HAUT")
DUREE_APPUI_LONG = 0.8      # secondes de maintien avant le menu
DELAI_CERCLE = 0.15         # le cercle n'apparait qu'apres ce delai : un simple appui ne le fait pas clignoter


class CercleAppui(tk.Toplevel):
    """Petit cercle, en haut a droite, qui se remplit pendant un appui long.

    Fenetre a part, toujours au premier plan : elle reste visible par-dessus un
    jeu, quand Omni est derriere."""

    def __init__(self, app):
        super().__init__(app)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.t = app.px(84)
        self.geometry("%dx%d+%d+%d" % (self.t, self.t, app.W - self.t - app.px(30), app.px(30)))
        self.cv = tk.Canvas(self, width=self.t, height=self.t, bg=T["violet"], highlightthickness=0)
        self.cv.pack()
        self.maj(0.0)

    def maj(self, ratio):
        """Redessine l'anneau rempli a `ratio` (0 a 1)."""
        cv, t = self.cv, self.t
        m = t * 0.12
        cv.delete("all")
        cv.create_oval(m, m, t - m, t - m, outline=mel(T["or"], T["bg"], 0.7), width=3)
        cv.create_arc(m, m, t - m, t - m, start=90, extent=-359.9 * ratio, style="arc", outline=T["or"], width=6)
        ICONES["reglages"](cv, t / 2, t / 2, t * 0.34, T["or"])


# ===========================================================================
# Application
# ===========================================================================
class OmniConsole(tk.Tk):
    """Fenetre principale : echelle, polices, navigation entre pages, manette, menu rapide, clavier virtuel, panneau d'accessibilite."""
    def __init__(self):
        """Prepare la fenetre plein ecran, charge reglages et profils, demarre les fils (manette, etat du systeme) et ouvre la premiere page."""
        super().__init__()
        # Omni est installe sous /usr, mais /usr est reserve dans les conteneurs
        # de Proton : on se place dans le dossier du joueur pour que tout ce qui
        # est lance depuis Omni herite d'un dossier de travail acceptable.
        try:
            os.chdir(os.path.expanduser("~"))
        except Exception:
            pass
        self.title("Omni Console")
        self.attributes("-fullscreen", True)
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", not self.attributes("-fullscreen")))
        self.update_idletasks()
        self.W, self.H = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+0+0")

        self.reglages = charger_reglages()
        self._appliquer_reglages()

        self.profils = charger_profils()
        self.joueur_actif = None
        self.cible_saisie = None
        self._clavier = None
        self._acces = None
        self._img_refs = []
        self.courante = None
        self.installs = {}      # suivi des installations en cours (par plateforme)
        self._fond_ph = None
        self._menu = None
        self._bandeau = None
        self._liste_courante = None
        self.en_arriere_plan = False
        self.file_manette = queue.Queue()
        self.manette = Manette(self.file_manette)
        self.manette.start()
        self.systeme = EtatSysteme()        # reseau, Bluetooth, peripheriques (icones d'etat, messages)
        self.systeme.start()
        self._appui_en_cours = None         # appui long en cours : {debut, declenche, genre}
        self._cercle = None
        self.suivi = SuiviJeux(self)
        self.bind_all("<KeyPress>", self._touche_clavier, add="+")
        self.bind("<FocusIn>", lambda e: setattr(self, "en_arriere_plan", False))
        self.after(30, self._lire_manette)
        self.after(2000, self._lire_systeme)
        # le clavier virtuel ecrit dans le dernier champ de texte touche
        self.bind_class("Entry", "<FocusIn>", self._focus_champ, add="+")

        self.container = tk.Frame(self, bg=T["bg"])
        self.container.pack(fill="both", expand=True)
        self.page = None
        self.montrer(PageSelection if self.profils else PageProfil)

    # ----- echelle et polices -----
    def _appliquer_reglages(self):
        """Applique palette (daltonisme, contraste), echelle et epaisseur de trait d'apres les reglages courants."""
        r = self.reglages
        appliquer_palette(r.get("dalton", "aucun"), r.get("contraste", False))
        self.configure(bg=T["bg"])
        base = max(0.8, min(6.0, min(self.W / 1280.0, self.H / 720.0)))
        self.S = base * float(r.get("zoom", 1.0))
        TRAIT[0] = max(1.0, base / 1.5)
        self._polices = {}

    def px(self, n):
        return int(round(n * self.S))

    # Les panneaux qui servent A REGLER l'affichage gardent leur taille de base,
    # sinon en « Très grand » ils sortent de l'ecran et deviennent inutilisables.
    def pxo(self, n):
        return int(round(n * min(self.S, self.S / max(1.0, float(self.reglages.get("zoom", 1.0))))))

    def police_o(self, taille, gras=False):
        cle = ("o", self.pxo(taille), gras)
        if cle not in self._polices:
            self._polices[cle] = tkfont.Font(family=FONT_NAME, size=-max(8, self.pxo(taille)),
                                             weight="bold" if gras else "normal")
        return self._polices[cle]

    def epais(self):
        return 3 if self.reglages.get("contraste") else 2

    def police_mono(self, taille):
        cle = ("mono", self.px(taille))
        if cle not in self._polices:
            self._polices[cle] = tkfont.Font(family="DejaVu Sans Mono", size=-max(8, self.px(taille)))
        return self._polices[cle]

    def police(self, taille, gras=False):
        cle = (self.px(taille), gras)
        if cle not in self._polices:
            self._polices[cle] = tkfont.Font(family=FONT_NAME, size=-max(8, self.px(taille)),
                                             weight="bold" if gras else "normal")
        return self._polices[cle]

    # ----- navigation -----
    def montrer(self, PageClass, **kw):
        """Affiche une page (remplace la precedente) et memorise laquelle, pour la redessiner si l'echelle change."""
        self.fermer_clavier()
        self.fermer_acces()
        self._liste_courante = None
        self.unbind_all("<Button-4>"); self.unbind_all("<Button-5>"); self.unbind_all("<MouseWheel>")
        if self.page is not None:
            self.page.destroy()
        self._img_refs = []
        self.cible_saisie = None
        self.courante = (PageClass, kw)
        self.container.configure(bg=T["bg"])
        self.page = PageClass(self.container, self, **kw)
        self.page.pack(fill="both", expand=True)

    def rafraichir(self):
        if self.courante:
            self.montrer(self.courante[0], **self.courante[1])

    def retour_reglages(self):
        if self.joueur_actif:
            self.montrer(PageAccueil)
        elif self.profils:
            self.montrer(PageSelection)
        else:
            self.montrer(PageGalerie)

    def garder(self, img):
        self._img_refs.append(img)
        return img

    # ----- reglages d'accessibilite (par profil + dernier choix global) -----
    def set_reglage(self, cle, val):
        """Change un reglage d'accessibilite : enregistre globalement et dans le profil actif, puis redessine."""
        acces_ouvert = self._acces is not None
        self.reglages[cle] = val
        sauver_reglages(self.reglages)
        if self.joueur_actif is not None:
            self.joueur_actif.setdefault("acces", {})[cle] = val
            sauver_profils(self.profils)
        self._appliquer_reglages()
        self.rafraichir()
        if acces_ouvert:
            self.toggle_acces()

    def appliquer_acces_profil(self, prof):
        if prof.get("acces"):
            self.reglages.update(prof["acces"])
            sauver_reglages(self.reglages)
            self._appliquer_reglages()

    def jouer_son(self, nom):
        """Joue un son court de l'interface (hover, select, valid) avec le premier lecteur disponible, sans bloquer."""
        if not self.reglages.get("sons", True):
            return
        f = os.path.join(SONS_DIR, "omni-%s.ogg" % nom)
        if not os.path.isfile(f):
            return
        # plusieurs lecteurs possibles : on prend le premier present sur la console
        for cmd in (["paplay", f], ["pw-play", f], ["mpv", "--no-video", "--really-quiet", f]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    continue

    # ----- en-tetes (reprennent les maquettes) -----
    def entete(self, parent, variante="barre"):
        """En-tete d'une page ancienne (soleil, titre, icones, badge du joueur)."""
        a = self
        if variante == "centre":
            h = a.px(178)
            cv = tk.Canvas(parent, width=a.W, height=h, bg=T["bg"], highlightthickness=0)
            lg = a.px(360)
            x = (a.W - lg) / 2
            soleil(cv, x, a.px(20), lg, a.px(74))
            cv.create_text(a.W / 2, a.px(128), text="OMNI CONSOLE", fill=T["mag"], font=a.police(44, True))
            cv.create_rectangle(x, a.px(158), x + lg, a.px(161), fill=T["cyan"], outline="")
            self._icones_entete(cv, a.W - a.px(30), a.px(26), avec_reglages=False)
            return cv
        h = a.px(96)
        cv = tk.Canvas(parent, width=a.W, height=h, bg=T["bg"], highlightthickness=0)
        soleil(cv, a.px(40), a.px(25), a.px(45), a.px(40))
        cv.create_text(a.px(105), a.px(46), text="OMNI CONSOLE", anchor="w", fill=T["mag"], font=a.police(26, True))
        larg_titre = a.police(26, True).measure("OMNI CONSOLE")
        cv.create_rectangle(a.px(105), a.px(63), a.px(105) + larg_titre * 1.25, a.px(66), fill=T["cyan"], outline="")
        droite = a.W - a.px(40)
        j = self.joueur_actif
        if j is not None:
            droite = self._badge_joueur(cv, droite, a.px(20), j) - a.px(18)
        self._icones_entete(cv, droite, a.px(20), avec_reglages=j is not None)
        return cv

    def _badge_joueur(self, cv, xd, y, j):
        """Dessine le badge du joueur actif ; un clic ramene a « Qui joue ? ». Renvoie son bord gauche."""
        a = self
        w, h = a.px(260), a.px(56)
        x = xd - w
        neon(cv, x, y, xd, y + h, a.px(8), T["cyan"], fill=T["tuile"], halo=2, tags="badge", w=1)
        av = avatar_image(j["planche"], j["ligne"], j["colonne"], a.px(40))
        rrect(cv, x + a.px(8), y + a.px(7), x + a.px(50), y + a.px(49), a.px(6), outline=T["mag"], fill=T["sel"], tags="badge")
        if av:
            a.garder(av)
            cv.create_image(x + a.px(29), y + a.px(28), image=av, tags="badge")
        cv.create_text(x + a.px(62), y + a.px(20), text=j["nom"], anchor="w", fill=T["text"],
                       font=a.police(14, True), tags="badge")
        cv.create_text(x + a.px(62), y + a.px(39), text="Niveau : %s" % j.get("niveau", 1), anchor="w",
                       fill=T["cyan"], font=a.police(11), tags="badge")
        ico_joueurs(cv, xd - a.px(26), y + h / 2, a.px(28), T["cyan"], tags="badge")
        cv.tag_bind("badge", "<Button-1>", lambda e: (self.jouer_son("select"), self.montrer(PageSelection)))
        cv.tag_bind("badge", "<Enter>", lambda e: cv.configure(cursor="hand2"))
        cv.tag_bind("badge", "<Leave>", lambda e: cv.configure(cursor=""))
        return x

    def _icones_entete(self, cv, xd, y, avec_reglages):
        """Boutons d'en-tete (clavier, accessibilite, reglages) alignes a droite."""
        a = self
        boutons = [("clavier", "Clavier", self.toggle_clavier), ("acces", "Accessibilité", self.toggle_acces)]
        if avec_reglages:
            boutons.append(("reglages", "Réglages", lambda: self.montrer(PageReglages)))
        taille = a.px(48)
        x = xd
        for ico, bulle, cmd in reversed(boutons):
            b = NeonBouton(cv, a, icone=ico, commande=cmd, hauteur=taille, infobulle=bulle)
            x -= int(b["width"])
            cv.create_window(x, y, window=b, anchor="nw")
            x -= a.px(4)

    # ----- joueur, fond, manette -----
    def choisir_joueur(self, prof):
        self.joueur_actif = prof
        PROFIL_COURANT["id"] = prof.get("id", "commun")
        self.appliquer_acces_profil(prof)

    def marque_manette(self):
        return getattr(self.manette, "marque", "xbox")

    def fond_image(self):
        cle = (self.W, self.H, T["mag"], T["cyan"], T["or"])
        if self._fond_ph is None or self._fond_ph[0] != cle:
            im = image_fond(self.W, self.H)
            self._fond_ph = (cle, ImageTk.PhotoImage(im) if im is not None else None)
        return self._fond_ph[1]

    def _touche_clavier(self, e):
        """Traduit une touche du clavier physique en commande de manette (fleches, Entree, Echap...)."""
        w = self.focus_get()
        dans_champ = isinstance(w, tk.Entry)
        k = e.keysym
        table = {"Up": "haut", "Down": "bas", "Left": "gauche", "Right": "droite", "Return": "A",
                 "KP_Enter": "A", "Escape": "B", "Prior": "LB", "Next": "RB", "F1": "GUIDE"}
        if not dans_champ:
            table.update({"space": "A", "BackSpace": "B", "x": "X", "y": "Y"})
        if dans_champ:
            if k == "Return":
                return      # le champ gere lui-meme la validation
            if k in ("Left", "Right") and getattr(self.page, "saisie_active", lambda: True)():
                return
        c = table.get(k)
        if c:
            self.commande(c)

    def _lire_manette(self):
        """Vide la file des commandes de manette toutes les 30 ms. Quand un jeu est devant, seuls Guide et les appuis longs passent."""
        try:
            while True:
                c = self.file_manette.get_nowait()
                if c in APPUIS_LONGS:       # transmis meme quand un jeu est devant
                    self._appui(c)
                    continue
                if self.en_arriere_plan and c != "GUIDE" and self._menu is None:
                    continue        # un jeu ou un launcher est devant : la manette est a lui
                self.commande(c)
        except queue.Empty:
            pass
        self.after(30, self._lire_manette)

    def _appui(self, c):
        """Appui (_BAS) ou relachement (_HAUT) de Guide ou de Select + Start.

        Menu ouvert : l'appui le ferme tout de suite. Sinon, un maintien de
        DUREE_APPUI_LONG ouvre le menu Omni, meme par-dessus un jeu. Un appui
        court ouvre aussi le menu, mais seulement quand Omni est devant : dans un
        jeu Steam, le bouton Guide appartient a Steam."""
        if c.endswith("_BAS"):
            if self._menu is not None:
                self.fermer_menu()
                self._appui_en_cours = None
                return
            self._appui_en_cours = {"debut": time.time(), "declenche": False, "genre": c.split("_")[0]}
            self.after(40, self._tic_appui)
            return
        appui, self._appui_en_cours = self._appui_en_cours, None
        self._fermer_cercle()
        if appui and not appui["declenche"] and appui["genre"] == "GUIDE" and not self.en_arriere_plan:
            self.ouvrir_menu()

    def _tic_appui(self):
        """Fait avancer le cercle pendant un appui long, puis ouvre le menu."""
        appui = self._appui_en_cours
        if not appui or appui["declenche"]:
            return
        ecoule = time.time() - appui["debut"]
        if self._cercle is None and ecoule > DELAI_CERCLE:
            self._cercle = CercleAppui(self)
        if self._cercle is not None:
            self._cercle.maj(min(1.0, ecoule / DUREE_APPUI_LONG))
        if ecoule >= DUREE_APPUI_LONG:
            appui["declenche"] = True
            self._fermer_cercle()
            self.ouvrir_menu()
            return
        self.after(40, self._tic_appui)

    def _fermer_cercle(self):
        """Ferme le cercle d'appui long s'il est ouvert."""
        if self._cercle is not None:
            try:
                self._cercle.destroy()
            except tk.TclError:
                pass
            self._cercle = None

    def _lire_systeme(self):
        """Releve periodique de l'etat du systeme : messages de branchement et
        rafraichissement des icones d'etat de la page courante."""
        try:
            while True:
                genre, nom, present = self.systeme.evenements.get_nowait()
                if genre == "manette":
                    self.bandeau("Manette %s : %s" % ("branchée" if present else "débranchée", nom))
                else:
                    self.bandeau("Stockage %s : %s" % ("branché" if present else "retiré", nom))
        except queue.Empty:
            pass
        page = self.page
        if hasattr(page, "maj_statuts"):
            page.maj_statuts()
        self.after(2000, self._lire_systeme)

    def commande(self, c):
        """Aiguille une commande de manette vers l'element qui a la main : menu rapide, panneau d'accessibilite, clavier virtuel, puis page courante."""
        if c == "GUIDE":
            if self._menu is not None:
                self.fermer_menu()
            else:
                self.ouvrir_menu()
            return
        if self._menu is not None:
            self._menu.commande(c)
            return
        if self._acces is not None:
            self._acces.commande(c)
            return
        if self._clavier is not None:
            self._clavier.commande(c)
            return
        p = self.page
        if hasattr(p, "commande"):
            p.commande(c)
            return
        # sous-pages de reglages : lignes choisies au haut / bas, A pour valider
        if self._liste_courante and c in ("haut", "bas", "A"):
            cv, lignes, etat = self._liste_courante
            if not lignes or not cv.winfo_exists():
                return
            if c == "A":
                if etat[0] >= 0:
                    self.jouer_son("select")
                    lignes[etat[0]][1]()
                return
            etat[0] = max(0, min(len(lignes) - 1, etat[0] + (1 if c == "bas" else -1)))
            cv.delete("sel_or")
            bb = cv.bbox(lignes[etat[0]][0])
            if bb:
                neon(cv, bb[0] + 2, bb[1] + 2, bb[2] - 2, bb[3] - 2, self.px(8), T["or"], halo=0, w=3, tags="sel_or")
                cv.yview_moveto(max(0, (bb[1] - 20) / max(1, float(cv.cget("scrollregion").split()[3]))))
            self.jouer_son("hover")
        elif c == "B":
            self.montrer(PageReglages)

    def ouvrir_menu(self):
        self.fermer_clavier()
        self.fermer_acces()
        self._menu = MenuRapide(self)
        self.jouer_son("select")

    def ouvrir_menu_alim(self):
        """Ouvre le menu rapide directement sur le choix Eteindre / Redemarrer."""
        if self._menu is None:
            self.ouvrir_menu()
        if self._menu is not None:
            self._menu._ouvrir_alim()

    def fermer_menu(self):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
            self._menu = None

    def revenir(self):
        """Ramene Omni au premier plan (fin de partie, menu rapide)."""
        self.en_arriere_plan = False
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass
        if self._bandeau is not None:
            try:
                self._bandeau.destroy()
            except Exception:
                pass
            self._bandeau = None

    def ouvrir_launcher(self, pid):
        """Ouvre le launcher d'une plateforme dans le journal de suivi, apres verification d'Internet et anti-double-ouverture (30 s)."""
        if not DEMO and not plateforme_presente(pid):
            return
        if not DEMO and (pid in LAUNCHERS or (pid == "steam" and steam_racine() is None)):
            probleme = diagnostic_internet()
            if probleme:
                self.bandeau(probleme)
                return
        # une preparation en cours : on renvoie au journal plutot qu'a un refus sec
        inst = self.installs.get(pid)
        if inst and inst["etat"] == "encours":
            self.montrer(PageTerminal, pid=pid, premiere=True)
            return
        # un seul lancement a la fois : plusieurs appuis ne rouvrent pas le launcher
        dernier = getattr(self, "_ouvertures", {}).get(pid, 0)
        if time.time() - dernier < 30:
            self.bandeau("%s est déjà en train de s'ouvrir, patiente." % PLAT[pid]["nom"])
            self.passer_derriere()
            return
        self._ouvertures = getattr(self, "_ouvertures", {})
        self._ouvertures[pid] = time.time()
        self.jouer_son("valid")
        if DEMO:
            return
        demarrer_installation(self, PLAT[pid], self.joueur_actif,
                              fonction=lambda pr, q=pid: ouverture_surveillee(q, pr),
                              titre="Ouverture de " + PLAT[pid]["nom"])
        self.montrer(PageTerminal, pid=pid, premiere=True)

    def passer_derriere(self):
        """Omni s'efface derriere le launcher ou le jeu : leurs fenetres (y compris
        celle de mise a jour de Steam) ne doivent jamais rester cachees derriere."""
        self.en_arriere_plan = True
        try:
            self.attributes("-topmost", False)
            self.after(700, self.lower)
            self.after(2500, lambda: self.en_arriere_plan and self.lower())
        except Exception:
            pass

    def bandeau(self, texte):
        """Rappel discret par-dessus le launcher, quelques secondes."""
        if self._bandeau is not None:
            try:
                self._bandeau.destroy()
            except Exception:
                pass
        b = tk.Toplevel(self)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        w = self.px(860)
        h = self.px(54) if self.police(16).measure(texte) < w - self.px(40) else self.px(84)
        b.geometry("%dx%d+%d+%d" % (w, h, (self.W - w) // 2, self.px(16)))
        cv = tk.Canvas(b, width=w, height=h, bg=T["violet"], highlightthickness=2, highlightbackground=T["or"])
        cv.pack()
        cv.create_text(w / 2, h / 2, text=texte, fill=T["text"], font=self.police(16), width=w - self.px(40),
                       justify="center")
        self._bandeau = b
        self.after(7000, lambda: b.winfo_exists() and b.destroy())

    # ----- clavier virtuel -----
    def _focus_champ(self, e):
        self.cible_saisie = e.widget
        if self._clavier is not None:
            self._clavier.maj_statut()

    def manette_presente(self):
        return bool(getattr(self.manette, "devs", {}))

    def toggle_clavier(self):
        """Montre ou cache le clavier virtuel (celui de la page s'il en a un)."""
        if getattr(self.page, "clavier_integre", False):
            # l'ecran a son propre clavier : l'icone le montre ou le cache
            self.page.basculer_clavier()
            return
        if self._clavier is not None:
            self.fermer_clavier()
            return
        self.fermer_acces()
        self._clavier = ClavierIntegre(self, self)
        self._clavier.place(relx=0.5, rely=1.0, anchor="s", y=-self.px(12))
        self._clavier.lift()

    def fermer_clavier(self):
        if self._clavier is not None:
            try:
                self._clavier.destroy()
            except Exception:
                pass
            self._clavier = None

    # ----- panneau accessibilite rapide -----
    def toggle_acces(self):
        """Montre ou cache le panneau d'accessibilite rapide."""
        if self._acces is not None:
            self.fermer_acces()
            return
        self.fermer_clavier()
        self._acces = PanneauAccessibilite(self, self, compact=True)
        self._acces.place(relx=1.0, x=-self.px(30), y=self.px(92), anchor="ne")
        self._acces.lift()

    def fermer_acces(self):
        if self._acces is not None:
            try:
                self._acces.destroy()
            except Exception:
                pass
            self._acces = None


def champ(parent, app, largeur, nom, show=""):
    """Champ de texte a la charte ; nom = libelle rappele par le clavier virtuel."""
    e = tk.Entry(parent, font=app.police(18), bg=T["tuile"], fg=T["text"], insertbackground=T["mag"],
                 relief="flat", bd=0, width=largeur, show=show, highlightthickness=app.px(2),
                 highlightbackground=mel(T["cyan"], T["bg"], 0.55), highlightcolor=T["cyan"])
    e.nom_champ = nom
    return e


# ===========================================================================
# Clavier virtuel (fiable sous openbox : Frame posee sur la fenetre, pas Toplevel)
# ===========================================================================
class ClavierIntegre(tk.Frame):
    """Clavier virtuel pilotable a la manette, pose sur la fenetre (un Toplevel est peu fiable sous openbox)."""
    LETTRES = {
        "AZERTY": ["azertyuiop", "qsdfghjklm", "wxcvbn"],
        "QWERTY": ["qwertyuiop", "asdfghjkl", "zxcvbnm"],
    }
    SYMBOLES = ["@#&_-+=*/%", "()[]!?.,;:", "€$£'\"<>|~^"]
    ACCENTS = ["éèêëàâä", "çùûüôöîï", "ÉÈÀÇ"]

    def __init__(self, parent, app, integre=False, compact=False):
        """Cree le clavier ; integre=True pour un clavier propre a une page, compact=True pour une version basse."""
        self.compact = compact
        super().__init__(parent, bg=T["panel"], highlightthickness=app.px(2),
                         highlightbackground=T["cyan"], padx=app.px(12), pady=app.px(8))
        self.app = app
        self.integre = integre
        self.maj = False
        self.mode = "AZERTY"
        self.nav = not integre      # le clavier flottant se pilote d'office a la manette
        self.pos = [1, 0]
        self._build()

    def _cible(self):
        """Champ de texte qui recoit la saisie, ou None s'il n'existe plus."""
        w = self.app.cible_saisie
        try:
            if w is not None and w.winfo_exists():
                return w
        except Exception:
            pass
        return None

    def maj_statut(self):
        c = self._cible()
        if c is not None:
            self.statut.configure(text="Écrit dans : " + getattr(c, "nom_champ", "champ de texte"), fg=T["cyan"])
        else:
            self.statut.configure(text="Touche d'abord une zone de texte", fg=T["amber"])

    def _touche(self, parent, texte, action, largeur=3, couleur=None, actif=False):
        """Cree une touche cliquable et l'enregistre dans la rangee courante (pour la navigation a la manette)."""
        a = self.app
        fond = T["mag"] if actif else (couleur or T["tuile"])
        enc = T["bg"] if (actif or couleur) else T["text"]
        b = tk.Label(parent, text=texte, font=a.police(15 if self.compact else 18, True), fg=enc, bg=fond, width=largeur,
                     pady=a.px(3 if self.compact else 6), cursor="hand2", highlightthickness=1,
                     highlightbackground=mel(T["cyan"], T["bg"], 0.5))
        b.pack(side="left", padx=a.px(3), pady=a.px(3))
        b.bind("<Enter>", lambda e: b.configure(bg=T["sel"] if fond == T["tuile"] else mel(fond, "#ffffff", 0.2)))
        b.bind("<Leave>", lambda e: b.configure(bg=fond))
        b.bind("<Button-1>", lambda e: action())
        b.action = action
        self._rang.append(b)
        return b

    def _build(self):
        """Construit toute la disposition : barre de modes, rangees de touches, barre d'espace. Appelee a chaque changement de mode ou de majuscule."""
        a = self.app
        for w in self.winfo_children():
            w.destroy()
        self.grille = []
        rang_modes = []
        barre = tk.Frame(self, bg=T["panel"])
        barre.pack(fill="x", pady=(0, a.px(4)))
        ic = tk.Canvas(barre, width=a.px(40), height=a.px(30), bg=T["panel"], highlightthickness=0)
        ic.pack(side="left")
        ico_clavier(ic, a.px(20), a.px(15), a.px(32), T["cyan"])
        self.statut = tk.Label(barre, text="", font=a.police(13, True), bg=T["panel"])
        self.statut.pack(side="left", padx=a.px(8))
        self.maj_statut()
        if not self.integre:
            fermer = NeonBouton(barre, a, icone="fermer", commande=a.fermer_clavier, hauteur=a.px(36),
                                couleur=T["danger"], infobulle="Fermer le clavier")
            fermer.pack(side="right")
            fermer.action = a.fermer_clavier
        for m, lib in [("ACCENTS", "éàç"), ("SYMBOLES", "?123"), ("QWERTY", "QWERTY"), ("AZERTY", "AZERTY")]:
            lb = tk.Label(barre, text=lib, font=a.police(12, True), padx=a.px(10), pady=a.px(4), cursor="hand2",
                          fg=T["bg"] if m == self.mode else T["text2"],
                          bg=T["mag"] if m == self.mode else T["tuile"])
            lb.pack(side="right", padx=a.px(3))
            lb.bind("<Button-1>", lambda e, mm=m: self._mode(mm))
            lb.action = lambda mm=m: self._mode(mm)
            rang_modes.insert(0, lb)
        if not self.integre:
            rang_modes.append(fermer)
        self.grille.append(rang_modes)

        rangs = []
        if self.mode in self.LETTRES:
            rangs = ["1234567890"] + self.LETTRES[self.mode]
        elif self.mode == "SYMBOLES":
            rangs = ["1234567890"] + self.SYMBOLES
        else:
            rangs = self.ACCENTS
        for i, rang in enumerate(rangs):
            fr = tk.Frame(self, bg=T["panel"])
            fr.pack()
            self._rang = []
            self.grille.append(self._rang)
            dernier = i == len(rangs) - 1
            if dernier and self.mode in self.LETTRES:
                self._touche(fr, "\u21e7", self._maj_toggle, largeur=4, actif=self.maj)
            for ch in rang:
                aff = ch.upper() if (self.maj and self.mode in self.LETTRES) else ch
                self._touche(fr, aff, lambda c=aff: self._tap(c))
            if dernier:
                self._touche(fr, "\u232b", self._effacer, largeur=4, couleur=T["dim"])
        bas = tk.Frame(self, bg=T["panel"])
        bas.pack(pady=(a.px(2), 0))
        self._rang = []
        self.grille.append(self._rang)
        self._touche(bas, "Espace", lambda: self._tap(" "), largeur=18, couleur=T["dim"])
        self._touche(bas, "Valider \u21b5", self._entree, largeur=10, couleur=T["ok"])
        self.pos[0] = max(0, min(self.pos[0], len(self.grille) - 1))
        self.pos[1] = max(0, min(self.pos[1], len(self.grille[self.pos[0]]) - 1))
        self._surligner()

    # ----- pilotage manette / fleches -----
    def set_nav(self, actif):
        self.nav = actif
        self._surligner()

    def _surligner(self):
        """Entoure d'or la touche choisie a la manette."""
        for r, rang in enumerate(self.grille):
            for c, w in enumerate(rang):
                try:
                    if self.nav and [r, c] == self.pos:
                        w.configure(highlightthickness=3, highlightbackground=T["or"])
                    else:
                        w.configure(highlightthickness=1 if isinstance(w, tk.Label) else 0,
                                    highlightbackground=mel(T["cyan"], T["bg"], 0.5))
                except Exception:
                    pass

    def commande(self, c):
        """Retourne "sortie_haut" quand on remonte au-dessus du clavier integre."""
        r, k = self.pos
        if c in ("gauche", "droite"):
            n = len(self.grille[r])
            self.pos[1] = (k + (1 if c == "droite" else -1)) % n
        elif c in ("haut", "bas"):
            r2 = r + (1 if c == "bas" else -1)
            if r2 < 0:
                if self.integre:
                    return "sortie_haut"
                r2 = 0
            if r2 >= len(self.grille):
                r2 = len(self.grille) - 1
            ancien, nouveau = self.grille[r], self.grille[r2]
            k2 = round(k * (len(nouveau) - 1) / max(1, len(ancien) - 1))
            self.pos = [r2, max(0, min(k2, len(nouveau) - 1))]
        elif c == "A":
            w = self.grille[r][k]
            self.app.jouer_son("select")
            w.action()
            return None
        elif c == "X":
            self._effacer()
        elif c == "Y":
            self._maj_toggle()
            return None
        elif c == "B" and not self.integre:
            self.app.fermer_clavier()
            return None
        if self.winfo_exists():
            self._surligner()
        return None

    def _mode(self, m):
        self.mode = m
        self._build()

    def _maj_toggle(self):
        self.maj = not self.maj
        self._build()

    def _tap(self, c):
        """Ecrit un caractere dans le champ cible ; la majuscule ne dure que pour une lettre."""
        w = self._cible()
        if w is None:
            self.maj_statut()
            return
        w.insert("insert", c)
        w.focus_set()
        if self.maj:        # majuscule le temps d'une lettre, comme sur un telephone
            self.maj = False
            self._build()

    def _effacer(self):
        w = self._cible()
        if w is not None:
            p = w.index("insert")
            if p > 0:
                w.delete(p - 1)
            w.focus_set()

    def _entree(self):
        w = self._cible()
        if w is not None:
            w.event_generate("<Return>")


# ===========================================================================
# Accessibilite : panneau visuel (rapide depuis l'en-tete, ou page complete)
# ===========================================================================
class PanneauAccessibilite(tk.Frame):
    """Taille de l'affichage, couleurs (daltonisme), contraste, sons. Chaque joueur garde ses choix."""
    TAILLES = [(1.0, "Normal"), (1.2, "Grand"), (1.4, "Très grand")]
    COULEURS = [("aucun", "Normales"), ("deuteranopie", "Rouge / vert"), ("tritanopie", "Bleu / jaune")]

    def __init__(self, parent, app, compact=False):
        """Construit le panneau ; compact=True pour la version rapide ouverte depuis l'en-tete."""
        super().__init__(parent, bg=T["panel"], highlightthickness=app.pxo(2) if compact else 0,
                         highlightbackground=T["cyan"], padx=app.pxo(20), pady=app.pxo(14))
        self.app = app
        a = app
        r = a.reglages
        self.options = []
        tete = tk.Frame(self, bg=T["panel"])
        tete.pack(fill="x")
        ic = tk.Canvas(tete, width=a.pxo(40), height=a.pxo(40), bg=T["panel"], highlightthickness=0)
        ic.pack(side="left")
        ico_acces(ic, a.pxo(20), a.pxo(20), a.pxo(34), T["cyan"])
        tk.Label(tete, text="Accessibilité", font=a.police_o(20, True), fg=T["text"], bg=T["panel"]).pack(side="left", padx=a.pxo(10))
        if compact:
            NeonBouton(tete, a, icone="fermer", commande=a.fermer_acces, hauteur=a.pxo(36),
                       couleur=T["danger"], infobulle="Fermer").pack(side="right")

        self._titre("Taille de l'affichage")
        ligne = tk.Frame(self, bg=T["panel"]); ligne.pack(anchor="w")
        for i, (z, lib) in enumerate(self.TAILLES):
            self._tuile_taille(ligne, z, lib, i, abs(r.get("zoom", 1.0) - z) < 0.01)

        self._titre("Couleurs")
        ligne = tk.Frame(self, bg=T["panel"]); ligne.pack(anchor="w")
        for cle, lib in self.COULEURS:
            self._tuile_couleur(ligne, cle, lib, r.get("dalton", "aucun") == cle)

        ligne = tk.Frame(self, bg=T["panel"]); ligne.pack(anchor="w", pady=(a.pxo(14), 0))
        self._interrupteur(ligne, "Contraste renforcé", "contraste", r.get("contraste", False))
        self._interrupteur(ligne, "Sons de l'interface", "sons", r.get("sons", True))
        self.pos = min(getattr(app, "_acces_pos", 0), len(self.options) - 1)
        self._surligner()

    def _surligner(self):
        for i, (w, act) in enumerate(self.options):
            w.configure(highlightthickness=self.app.pxo(3) if i == self.pos else 0, highlightbackground=T["or"])

    def commande(self, c):
        """Navigation a la manette entre les options ; A valide, B ferme."""
        if c in ("gauche", "haut", "droite", "bas"):
            self.pos = (self.pos + (1 if c in ("droite", "bas") else -1)) % len(self.options)
            self.app.jouer_son("hover")
            self._surligner()
        elif c == "A":
            self.app._acces_pos = self.pos
            self.options[self.pos][1]()
        elif c == "B":
            self.app.fermer_acces()
            return "B"

    def _titre(self, t):
        a = self.app
        tk.Label(self, text=t, font=a.police_o(13, True), fg=T["dim"], bg=T["panel"]).pack(anchor="w", pady=(a.pxo(14), a.pxo(4)))

    def _tuile_taille(self, parent, z, lib, i, choisi):
        """Tuile de choix de la taille de l'affichage."""
        a = self.app
        w, h = a.pxo(120), a.pxo(96)
        cv = tk.Canvas(parent, width=w + a.pxo(12), height=h + a.pxo(12), bg=T["panel"], highlightthickness=0, cursor="hand2")
        cv.pack(side="left", padx=a.pxo(2))
        m = a.pxo(6)
        col = T["cyan"] if choisi else mel(T["cyan"], T["bg"], 0.6)
        neon(cv, m, m, m + w, m + h, a.pxo(8), col, fill=T["sel"] if choisi else T["tuile"], halo=2 if choisi else 0)
        cv.create_text(m + w / 2, m + h * 0.42, text="A", fill=T["text"],
                       font=(FONT_NAME, -int(a.pxo(20) * (1 + i * 0.45)), "bold"))
        cv.create_text(m + w / 2, m + h * 0.82, text=lib, fill=T["cyan"] if choisi else T["dim"], font=a.police_o(12, True))
        cv.bind("<Button-1>", lambda e: (a.jouer_son("valid"), a.set_reglage("zoom", z)))
        self.options.append((cv, lambda: (a.jouer_son("valid"), a.set_reglage("zoom", z))))

    def _tuile_couleur(self, parent, cle, lib, choisi):
        """Tuile de choix de la palette de couleurs."""
        a = self.app
        w, h = a.pxo(120), a.pxo(70)
        cv = tk.Canvas(parent, width=w + a.pxo(12), height=h + a.pxo(12), bg=T["panel"], highlightthickness=0, cursor="hand2")
        cv.pack(side="left", padx=a.pxo(2))
        m = a.pxo(6)
        col = T["cyan"] if choisi else mel(T["cyan"], T["bg"], 0.6)
        neon(cv, m, m, m + w, m + h, a.pxo(8), col, fill=T["sel"] if choisi else T["tuile"], halo=2 if choisi else 0)
        pal = dict(PALETTE_BASE); pal.update(PALETTES_DALTON[cle])
        for k, c in enumerate([pal["mag"], pal["cyan"], pal["ok"]]):
            x = m + w / 2 + (k - 1) * a.pxo(26)
            cv.create_oval(x - a.pxo(9), m + a.pxo(14), x + a.pxo(9), m + a.pxo(32), fill=c, outline="")
        cv.create_text(m + w / 2, m + h * 0.76, text=lib, fill=T["cyan"] if choisi else T["dim"], font=a.police_o(11, True))
        cv.bind("<Button-1>", lambda e: (a.jouer_son("valid"), a.set_reglage("dalton", cle)))
        self.options.append((cv, lambda: (a.jouer_son("valid"), a.set_reglage("dalton", cle))))

    def _interrupteur(self, parent, lib, cle, val):
        """Interrupteur (contraste, sons) cliquable."""
        a = self.app
        fr = tk.Frame(parent, bg=T["panel"], cursor="hand2")
        fr.pack(side="left", padx=(0, a.pxo(24)))
        w, h = a.pxo(58), a.pxo(30)
        cv = tk.Canvas(fr, width=w + 4, height=h + 4, bg=T["panel"], highlightthickness=0)
        cv.pack(side="left")
        col = T["ok"] if val else T["dim"]
        rrect(cv, 2, 2, 2 + w, 2 + h, h / 2, fill=mel(col, T["bg"], 0.55), outline=col, width=2)
        kx = 2 + (w - h / 2 - a.pxo(2) if val else h / 2 + a.pxo(2))
        cv.create_oval(kx - h * 0.36, 2 + h * 0.14, kx + h * 0.36, 2 + h * 0.86, fill=col, outline="")
        t = tk.Label(fr, text=lib, font=a.police_o(14, True), fg=T["text"], bg=T["panel"])
        t.pack(side="left", padx=a.pxo(8))
        for wdg in (fr, cv, t):
            wdg.bind("<Button-1>", lambda e: (a.jouer_son("valid"), a.set_reglage(cle, not val)))
        self.options.append((fr, lambda: (a.jouer_son("valid"), a.set_reglage(cle, not val))))


def cadre_defilant(parent, app, w, h, fond=None, pad=None):
    """Panneau a liseré neon contenant une zone defilante (listes de la maquette)."""
    fond = fond or T["panel"]
    m = app.px(10)
    cadre = tk.Canvas(parent, width=w + 2 * m, height=h + 2 * m, bg=T["bg"], highlightthickness=0)
    neon(cadre, m, m, m + w, m + h, app.px(10), mel(T["cyan"], T["bg"], 0.35), fill=fond, halo=2, w=app.epais())
    pad = app.px(18) if pad is None else pad
    zone = ZoneDefilante(cadre, app, w - 2 * pad - app.px(22), h - 2 * pad, bg=fond)
    cadre.create_window(m + pad, m + pad, window=zone, anchor="nw")
    return cadre, zone


def tronquer(texte, police, largeur):
    if police.measure(texte) <= largeur:
        return texte
    while texte and police.measure(texte + "…") > largeur:
        texte = texte[:-1]
    return texte + "…"


# ===========================================================================
# Page : installation d'une plateforme avec suivi clair jusqu'au bout.
# L'installation tourne dans un fil separe et continue si on quitte la page ;
# son etat vit dans app.installs, donc on peut revenir la suivre.
# ===========================================================================
def _chrono(depart):
    """Temps ecoule depuis le debut de l'operation, au format +mm:ss."""
    d = int(max(0, time.time() - depart))
    return "+%02d:%02d" % (d // 60, d % 60)


def demarrer_installation(app, plat, profil, fonction=None, titre=None):
    """Lance une installation (ou la premiere ouverture de Steam) dans un fil.
    Son etat et son journal lisible vivent dans app.installs[pid]."""
    pid = plat["id"]
    if app.installs.get(pid, {}).get("etat") == "encours":
        return
    etat = {"etat": "encours", "pct": 0, "msg": "Préparation...", "debut": time.time(), "erreur": "",
            "journal": [], "indetermine": False, "titre": titre or ("Installation de " + plat["nom"]),
            "fonction": fonction, "titre_court": titre}
    app.installs[pid] = etat

    def prog(pct, msg):
        """Rapporte l'avancement d'une operation : pct < 0 = total inconnu (barre animee). Tient le journal lisible, en mettant a jour la ligne chiffree au lieu d'en empiler dix."""
        if int(pct) < 0:
            etat["indetermine"] = True        # total inconnu : barre animee
        else:
            etat["indetermine"] = False
            etat["pct"] = max(etat["pct"], min(100, int(pct)))
        etat["msg"] = msg
        j = etat["journal"]
        # une progression chiffree met a jour sa ligne au lieu d'en empiler dix
        if msg and j and j[-1][0] == "encours" and ":" in msg and j[-1][1].split(":")[0] == msg.split(":")[0] \
                and any(ch.isdigit() for ch in msg):
            j[-1] = ("encours", msg, j[-1][2])
            return
        if msg and (not j or j[-1][1] != msg):
            # l'etape precedente est terminee : on la coche
            if j and j[-1][0] == "encours":
                j[-1] = ("ok", j[-1][1], j[-1][2])
            j.append(("encours", msg, _chrono(etat["debut"])))
            del j[:-200]

    def travail():
        """Corps du fil : execute l'operation, coche le journal, puis ajoute la plateforme au profil si elle a reussi."""
        ok, msg = (fonction or (lambda pr: plateforme_installer(pid, pr)))(prog)
        j = etat["journal"]
        if j and j[-1][0] == "encours":
            j[-1] = ("ok" if ok else "ko", j[-1][1], j[-1][2])
        j.append(("ok" if ok else "ko", "Terminé avec succès" if ok else (msg or "Échec"), _chrono(etat["debut"])))
        if ok:
            if pid not in profil["plateformes"]:
                profil["plateformes"].append(pid)
            profil["plat_sel"] = pid
            sauver_profils(app.profils)
            etat.update(etat="fini", pct=100, msg="Terminé.")
        else:
            etat.update(etat="echec", erreur=msg or "L'installation n'a pas abouti.")

    threading.Thread(target=travail, daemon=True).start()


# ===========================================================================
# Reglages
# ===========================================================================
def page_titre(page, app, titre, sous=None, sous_couleur=None):
    app.entete(page, "barre").pack()
    tk.Label(page, text=titre, font=app.police(30, True), fg=T["text"], bg=T["bg"]).pack()
    if sous:
        tk.Label(page, text=sous, font=app.police(16), fg=sous_couleur or T["dim"], bg=T["bg"]).pack(pady=(0, app.px(12)))


def liste_neon(parent, app, elements, largeur, hauteur):
    """Liste de lignes neon cliquables : (texte, texte_droite, choisi, action)."""
    cadre, zone = cadre_defilant(parent, app, largeur, hauteur)
    cv = zone.cv
    w = int(cv["width"]) - app.px(12)
    y = app.px(6)
    h = app.px(58)
    lignes = []
    app._liste_courante = (cv, lignes, [-1])
    for i, (txt, droite, choisi, action) in enumerate(elements):
        t = "l%d" % i
        if choisi:
            c = neon(cv, app.px(6), y, app.px(6) + w, y + h, app.px(8), T["ok"], fill=T["sel"], halo=2, tags=t)
        else:
            c = rrect(cv, app.px(6), y, app.px(6) + w, y + h, app.px(8), fill=T["tuile"],
                      outline=mel(T["cyan"], T["bg"], 0.6), width=1, tags=t)
        cv.create_text(app.px(26), y + h / 2, text=tronquer(txt, app.police(16, True), w * 0.72), anchor="w",
                       fill=T["ok"] if choisi else T["text"], font=app.police(16, True), tags=t)
        if droite:
            cv.create_text(app.px(6) + w - app.px(18), y + h / 2, text=droite, anchor="e", fill=T["cyan"],
                           font=app.police(14), tags=t)
        if action:
            lignes.append((t, action))
            cv.tag_bind(t, "<Button-1>", lambda e, f=action: (app.jouer_son("select"), f()))
            cv.tag_bind(t, "<Enter>", lambda e, cc=c, ch=choisi: (cv.configure(cursor="hand2"),
                                                                    None if ch else cv.itemconfigure(cc, outline=T["cyan"])))
            cv.tag_bind(t, "<Leave>", lambda e, cc=c, ch=choisi: (cv.configure(cursor=""),
                                                                    None if ch else cv.itemconfigure(cc, outline=mel(T["cyan"], T["bg"], 0.6))))
        y += h + app.px(10)
    zone.set_contenu(y)
    return cadre


def bouton_retour(page, app, cible=None):
    NeonBouton(page, app, "Retour", cible or (lambda: app.montrer(PageReglages)), icone="retour",
               couleur=T["dim"]).pack(pady=(app.px(16), 0))


class PageReseau(tk.Frame):
    """Reglages > Reseau : liste des reseaux Wi-Fi, connexion."""
    def __init__(self, parent, app):
        """Construit la page et lance une premiere recherche de reseaux."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        actuel = reseau_actuel()
        page_titre(self, a, "Réseau", "Connecté à : %s" % actuel if actuel else "Non connecté",
                   T["ok"] if actuel else T["amber"])
        self.zone = tk.Frame(self, bg=T["bg"]); self.zone.pack()
        barre = tk.Frame(self, bg=T["bg"]); barre.pack()
        NeonBouton(barre, a, "Retour", lambda: a.montrer(PageReglages), icone="retour", couleur=T["dim"]).pack(side="left", padx=a.px(6))
        NeonBouton(barre, a, "Rechercher", self.rafraichir, couleur=T["cyan"]).pack(side="left", padx=a.px(6))
        self.rafraichir()

    def rafraichir(self):
        """Relance la recherche de reseaux Wi-Fi et redessine la liste."""
        a = self.app
        for w in self.zone.winfo_children():
            w.destroy()
        attente = tk.Label(self.zone, text="Recherche des réseaux...", font=a.police(16), fg=T["cyan"], bg=T["bg"])
        attente.pack(pady=a.px(20))
        self.update_idletasks()
        reseaux = wifi_lister()
        attente.destroy()
        if not reseaux:
            tk.Label(self.zone, text="Aucun réseau Wi-Fi trouvé.\nLe câble réseau se connecte tout seul.",
                     font=a.police(16), fg=T["dim"], bg=T["bg"], justify="center").pack(pady=a.px(30))
            return
        actuel = reseau_actuel()
        elements = [(("\U0001F512 " if r["securise"] else "") + r["ssid"], "%s %%" % r["signal"], r["ssid"] == actuel,
                     (lambda rr=r: self.connecter(rr))) for r in reseaux[:15]]
        liste_neon(self.zone, a, elements, min(a.px(720), a.W - a.px(100)),
                   a.H - a.px(96) - a.px(250)).pack()

    def connecter(self, res):
        if res["securise"]:
            self.app.montrer(PageMotDePasse, ssid=res["ssid"])
        else:
            wifi_connecter(res["ssid"])
            self.app.montrer(PageReseau)


class PageMotDePasse(tk.Frame):
    """Saisie du mot de passe d'un reseau Wi-Fi avec clavier integre."""
    def __init__(self, parent, app, ssid=""):
        """Construit le champ, les boutons et le clavier a l'ecran."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        self.ssid = ssid
        page_titre(self, a, "Mot de passe Wi-Fi", "Réseau : " + ssid, T["cyan"])
        ligne = tk.Frame(self, bg=T["bg"]); ligne.pack()
        self.entry = champ(ligne, a, 26, "Mot de passe Wi-Fi")
        self.entry.pack(side="left", ipady=a.px(8))
        self.entry.bind("<Return>", lambda e: self.connecter())
        self.entry.focus_set()
        a.cible_saisie = self.entry
        self.msg = tk.Label(self, text="", font=a.police(15, True), fg=T["danger"], bg=T["bg"])
        self.msg.pack(pady=a.px(6))
        bas = tk.Frame(self, bg=T["bg"]); bas.pack()
        NeonBouton(bas, a, "Retour", lambda: a.montrer(PageReseau), icone="retour", couleur=T["dim"]).pack(side="left", padx=a.px(6))
        NeonBouton(bas, a, "Se connecter", self.connecter, couleur=T["ok"], plein=True, son="valid").pack(side="left", padx=a.px(6))
        # clavier integre a la page (pratique a la manette)
        self.clavier_integre = True
        self.clavier = ClavierIntegre(self, a, integre=True)
        self.clavier.set_nav(True)
        self.clavier_visible = True
        self.clavier.pack(pady=(a.px(14), 0))

    def basculer_clavier(self):
        self.clavier_visible = not self.clavier_visible
        if self.clavier_visible:
            self.clavier.pack(pady=(self.app.px(14), 0))
        else:
            self.clavier.pack_forget()

    def commande(self, c):
        if c == "B":
            self.app.montrer(PageReseau)
        else:
            self.clavier.commande(c)

    def connecter(self):
        self.msg.configure(text="Connexion...", fg=T["cyan"])
        self.update_idletasks()
        if wifi_connecter(self.ssid, self.entry.get()):
            self.app.montrer(PageReseau)
        else:
            self.msg.configure(text="La connexion a échoué. Vérifie le mot de passe.", fg=T["danger"])


class PageAffichage(tk.Frame):
    """Reglages > Affichage : choix de la resolution."""
    def __init__(self, parent, app):
        """Liste les resolutions disponibles et marque l'actuelle."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        self.sortie = affichage_sortie()
        actuelle = resolution_actuelle()
        page_titre(self, a, "Affichage", "Résolution actuelle : %s" % (actuelle or "inconnue"), T["cyan"])
        res = resolutions_dispo()
        if not res:
            tk.Label(self, text="Impossible de lister les résolutions.", font=a.police(16), fg=T["dim"], bg=T["bg"]).pack(pady=a.px(30))
        else:
            elements = [(m, "", m == actuelle, (lambda mm=m: self.appliquer(mm))) for m in res[:20]]
            liste_neon(self, a, elements, a.px(460), a.H - a.px(96) - a.px(230)).pack()
        bouton_retour(self, a)

    def appliquer(self, mode):
        if self.sortie:
            appliquer_resolution(self.sortie, mode)
        self.app._appliquer_reglages()
        self.app.W, self.app.H = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
        self.app.montrer(PageAffichage)


class PageAudio(tk.Frame):
    """Reglages > Audio : choix de la sortie du son."""
    def __init__(self, parent, app):
        """Liste les sorties audio et marque la sortie par defaut."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        page_titre(self, a, "Sortie audio", "Choisis où sort le son.")
        active = audio_sortie_active()
        sorties = audio_sorties()
        if not sorties:
            tk.Label(self, text="Aucune sortie audio détectée.", font=a.police(16), fg=T["dim"], bg=T["bg"]).pack(pady=a.px(30))
        else:
            elements = [(s["desc"], "", s["nom"] == active, (lambda n=s["nom"]: self.definir(n))) for s in sorties]
            liste_neon(self, a, elements, min(a.px(760), a.W - a.px(100)), a.H - a.px(96) - a.px(230)).pack()
        self.msg = tk.Label(self, text="", font=a.police(13), fg=T["dim"], bg=T["bg"])
        self.msg.pack(pady=(a.px(8), 0))
        barre = tk.Frame(self, bg=T["bg"]); barre.pack()
        NeonBouton(barre, a, "Tester le son", self.tester, couleur=T["cyan"]).pack(side="left", padx=a.px(6))
        NeonBouton(barre, a, "Retour", lambda: a.montrer(PageReglages), icone="retour",
                   couleur=T["dim"]).pack(side="left", padx=a.px(6))

    def definir(self, nom):
        audio_definir_sortie(nom)
        self.app.jouer_son("valid")
        self.app.montrer(PageAudio)

    def tester(self):
        self.msg.configure(text="Si tu n'entends rien, vérifie la sortie choisie ci-dessus.", fg=T["dim"])
        self.app.jouer_son("valid")


class PageStockage(tk.Frame):
    """Reglages > Stockage : place libre et occupation par plateforme."""
    def __init__(self, parent, app):
        """Dessine la jauge globale et lance le calcul des tailles en arriere-plan."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        total, utilise, libre, pct, cible = espace_disque()
        page_titre(self, a, "Stockage", "%s Go libres sur %s Go" % (libre, total),
                   T["ok"] if pct < 75 else (T["amber"] if pct < 90 else T["danger"]))
        W = a.px(640)
        self.cv = tk.Canvas(self, width=W + a.px(40), height=a.px(420), bg=T["bg"], highlightthickness=0)
        self.cv.pack()
        cv = self.cv
        coul = T["ok"] if pct < 75 else (T["amber"] if pct < 90 else T["danger"])
        x0, y = a.px(20), a.px(16)
        rrect(cv, x0, y, x0 + W, y + a.px(34), a.px(17), fill=T["panel2"], outline=mel(coul, T["bg"], 0.5), width=1)
        neon(cv, x0, y, x0 + max(a.px(34), W * pct / 100), y + a.px(34), a.px(17), coul, fill=coul, halo=2, w=1)
        cv.create_text(x0 + W / 2, y + a.px(17), text="%d %% utilisé" % pct, fill=T["text"], font=a.police(15, True))
        cv.create_text(x0, y + a.px(66), anchor="w", fill=T["dim"], font=a.police(14, True), text="\u2009".join("PAR PLATEFORME"))
        self.y0 = y + a.px(90)
        self.lignes = {}
        plats = [p for p in PLATEFORMES if plateforme_presente(p["id"])]
        if not plats:
            cv.create_text(x0, self.y0 + a.px(20), anchor="w", fill=T["dim"], font=a.police(15),
                           text="Aucune plateforme installée pour l'instant.")
        for i, p in enumerate(plats):
            yy = self.y0 + i * a.px(52)
            pastille(cv, x0, yy, a.px(40), p)
            cv.create_text(x0 + a.px(56), yy + a.px(20), anchor="w", text=p["nom"], fill=T["text"], font=a.police(16, True))
            self.lignes[p["id"]] = cv.create_text(x0 + W, yy + a.px(20), anchor="e", text="calcul...",
                                                  fill=T["cyan"], font=a.police(15))
        tk.Label(self, text="Les jeux et sauvegardes sont sur une partie du disque à part :\n"
                            "les mises à jour de la console n'y touchent jamais.",
                 font=a.police(13), fg=T["dim"], bg=T["bg"], justify="center").pack()
        bouton_retour(self, a)
        self.tailles = {}
        threading.Thread(target=self._calculer, args=([p["id"] for p in plats],), daemon=True).start()
        self.after(500, self._afficher)

    def _calculer(self, ids):
        chemins = {"steam": [os.path.join(steam_racine() or "/nonexistent", "steamapps")],
                   "gog": dossiers_gog(), "emu": dossiers_roms()}
        for pid in ids:
            c = [x for x in chemins.get(pid, [prefixe(pid)]) if os.path.exists(x)]
            self.tailles[pid] = taille_dossiers(c) if not DEMO else [42, 8, 1, 15, 0, 0][[p["id"] for p in PLATEFORMES].index(pid)] * 1024 ** 3

    def _afficher(self):
        """Met a jour les tailles au fur et a mesure que le calcul avance."""
        if not self.winfo_exists():
            return
        for pid, item in self.lignes.items():
            if pid in self.tailles:
                o = self.tailles[pid]
                txt = "%.1f Go" % (o / 1024 ** 3) if o >= 1024 ** 3 else "%d Mo" % (o // 1048576)
                self.cv.itemconfigure(item, text=txt)
        if len(self.tailles) < len(self.lignes):
            self.after(500, self._afficher)


class PageAccessibilite(tk.Frame):
    """Page complete d'accessibilite (le meme panneau que le raccourci de l'en-tete)."""
    def __init__(self, parent, app):
        """Insere le panneau dans un cadre et relie la manette."""
        super().__init__(parent, bg=T["bg"])
        self.app = a = app
        a.entete(self, "barre").pack()
        cadre = tk.Frame(self, bg=T["panel"], highlightthickness=a.px(2), highlightbackground=mel(T["cyan"], T["bg"], 0.35))
        cadre.pack(pady=(a.px(10), 0))
        self.panneau = PanneauAccessibilite(cadre, a)
        self.panneau.pack()
        self.commande = lambda c: self.app.montrer(PageReglages) if c == "B" else self.panneau.commande(c)
        tk.Label(self, text="Chaque joueur garde ses propres réglages.", font=a.police(14),
                 fg=T["dim"], bg=T["bg"]).pack(pady=(a.px(12), 0))
        bouton_retour(self, a)


# ===========================================================================
# V3 : ergonomie console (maquettes « carrousel », « statut des plateformes »,
# « bibliotheque unifiee »). Base synthwave magenta / cyan, OR pour ce qui est
# selectionne, touches neon. Tout se pilote a la manette, au clavier ou a la souris.
# ===========================================================================
BOUTONS_MANETTE = {"A": "#3ddc84", "B": "#ff4d6d", "X": "#4d7cff", "Y": "#ffc53d"}
# Ce qu'on affiche dans les aides selon la marque de la derniere manette utilisee.
# Les commandes restent positionnelles : A = bouton du bas, B = droite, X = gauche, Y = haut.
AIDES_MARQUE = {
    "xbox":     {"A": ("A", "#3ddc84"), "B": ("B", "#ff4d6d"), "X": ("X", "#4d7cff"), "Y": ("Y", "#ffc53d")},
    "playstation": {"A": ("✕", "#7fb2ff"), "B": ("○", "#ff5a6e"), "X": ("□", "#ff8fd8"), "Y": ("△", "#3ddcb4")},
    "nintendo": {"A": ("B", "#d0c9e8"), "B": ("A", "#d0c9e8"), "X": ("Y", "#d0c9e8"), "Y": ("X", "#d0c9e8")},
}
AIDES_MARQUE["generique"] = AIDES_MARQUE["xbox"]
VENDEURS = {0x045e: "xbox", 0x054c: "playstation", 0x057e: "nintendo"}


def image_fond(W, H):
    """Fond violet nuit traverse de rayons lumineux (magenta, cyan, or), floute.
    Calcule une fois puis garde sur le disque."""
    if not PIL_OK:
        return None
    cle = "%dx%d_%s%s%s" % (W, H, T["mag"][1:], T["cyan"][1:], T["or"][1:])
    chemin = os.path.join(CACHE_DIR, "fond_%s.png" % cle)
    if os.path.isfile(chemin):
        try:
            return Image.open(chemin).convert("RGB")
        except Exception:
            pass
    from PIL import ImageFilter
    base = Image.new("RGB", (W, H), hex_rgb(T["bg"]))
    calque = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(calque)
    cx, cy = W / 2, H * 0.42
    R = math.hypot(W, H)
    couleurs = [T["mag"], T["or"], T["cyan"], T["mag"], T["or"], "#9d3cff"]
    for k in range(34):
        a = k * 2 * math.pi / 34 + ((k * 7919) % 100) / 400.0
        ouv = 0.018 + ((k * 104729) % 50) / 1400.0
        col = hex_rgb(couleurs[k % len(couleurs)])
        alpha = 38 + (k * 31) % 60
        pts = [(cx, cy), (cx + R * math.cos(a - ouv), cy + R * math.sin(a - ouv)),
               (cx + R * math.cos(a + ouv), cy + R * math.sin(a + ouv))]
        d.polygon(pts, fill=col + (alpha,))
    calque = calque.filter(ImageFilter.GaussianBlur(max(6, H // 45)))
    lueur = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lueur).ellipse([cx - W * 0.28, cy - H * 0.30, cx + W * 0.28, cy + H * 0.30],
                                  fill=hex_rgb(mel(T["mag"], T["bg"], 0.55)) + (90,))
    lueur = lueur.filter(ImageFilter.GaussianBlur(H // 8))
    base = Image.alpha_composite(base.convert("RGBA"), lueur)
    base = Image.alpha_composite(base, calque)
    # vignette : bords plus sombres pour que les panneaux ressortent
    masque = Image.new("L", (W, H), 0)
    ImageDraw.Draw(masque).ellipse([-W * 0.15, -H * 0.25, W * 1.15, H * 1.2], fill=255)
    masque = masque.filter(ImageFilter.GaussianBlur(H // 6))
    sombre = Image.new("RGBA", (W, H), hex_rgb(T["bg"]) + (255,))
    base = Image.composite(base, sombre, masque).convert("RGB")
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        base.save(chemin)
    except Exception:
        pass
    return base


RATIO_CARTE = 0.77     # largeur / hauteur d'une carte des planches


def carte_img(planche, ligne, colonne, haut, estompe=False):
    """La carte ENTIERE, telle que dessinee : aucun cercle ni cadre par-dessus.
    La mise en valeur (lueur, liseré) se dessine AUTOUR, jamais sur l'illustration."""
    if not PIL_OK:
        return None
    larg = int(haut * RATIO_CARTE)
    cle = ("entiere", planche, ligne, colonne, larg, haut, estompe, T["bg"])
    if cle in _cache_img:
        return _cache_img[cle]
    c = _case_carte(planche, ligne, colonne)
    if c is None:
        return None
    img = c.convert("RGB").resize((larg, haut), Image.LANCZOS)
    if estompe:
        img = Image.blend(img, Image.new("RGB", img.size, hex_rgb(T["bg"])), 0.45)
    ph = ImageTk.PhotoImage(img)
    _cache_img[cle] = ph
    return ph


def dessiner_carte(cv, x, y, haut, planche, ligne, colonne, niveau=0, tags=None, img_refs=None):
    """Carte centree en (x, y). niveau 0 = mise en avant (lueur or autour),
    1 = voisine, 2 = lointaine (estompee). Renvoie la boite de la carte."""
    larg = int(haut * RATIO_CARTE)
    x0, y0, x1, y1 = x - larg / 2, y - haut / 2, x + larg / 2, y + haut / 2
    ph = carte_img(planche, ligne, colonne, int(haut), estompe=niveau == 2)
    m = max(3, int(haut * 0.02))
    if niveau == 0:
        neon(cv, x0 - m, y0 - m, x1 + m, y1 + m, m * 2, T["or"], halo=3, w=max(2, m // 2 + 1), tags=tags)
    else:
        rrect(cv, x0 - 2, y0 - 2, x1 + 2, y1 + 2, 4, fill="",
              outline=mel(T["or"], T["bg"], 0.45 if niveau == 1 else 0.75), width=1, tags=tags)
    if ph is not None:
        if img_refs is not None:
            img_refs.append(ph)
        cv.create_image(x, y, image=ph, tags=tags)
    return (x0, y0, x1, y1)


# ----- icones supplementaires -----
def ico_manette(cv, cx, cy, s, col, tags=None):
    """Icone de manette, dessinee."""
    lw = max(2, s / 14)
    rrect(cv, cx - s * 0.44, cy - s * 0.22, cx + s * 0.44, cy + s * 0.26, s * 0.2, outline=col, fill="", width=lw, tags=tags)
    cv.create_line(cx - s * 0.30, cy, cx - s * 0.12, cy, fill=col, width=lw, tags=tags)
    cv.create_line(cx - s * 0.21, cy - s * 0.09, cx - s * 0.21, cy + s * 0.09, fill=col, width=lw, tags=tags)
    for dx, dy in [(0.2, -0.05), (0.3, 0.05)]:
        r = s * 0.045
        cv.create_oval(cx + s * dx - r, cy + s * dy - r, cx + s * dx + r, cy + s * dy + r, fill=col, outline="", tags=tags)


def ico_horloge(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 14)
    r = s * 0.38
    cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=lw, tags=tags)
    cv.create_line(cx, cy, cx, cy - r * 0.62, fill=col, width=lw, capstyle="round", tags=tags)
    cv.create_line(cx, cy, cx + r * 0.45, cy + r * 0.25, fill=col, width=lw, capstyle="round", tags=tags)


def ico_etoile(cv, cx, cy, s, col, tags=None, plein=True):
    pts = []
    for k in range(10):
        r = s * (0.42 if k % 2 == 0 else 0.18)
        a = -math.pi / 2 + k * math.pi / 5
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    cv.create_polygon(pts, fill=col if plein else "", outline=col, width=max(1, s / 16), tags=tags)


def ico_loupe(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 10)
    r = s * 0.24
    cv.create_oval(cx - r - s * 0.08, cy - r - s * 0.08, cx + r - s * 0.08, cy + r - s * 0.08, outline=col, width=lw, tags=tags)
    cv.create_line(cx + s * 0.08, cy + s * 0.08, cx + s * 0.34, cy + s * 0.34, fill=col, width=lw, capstyle="round", tags=tags)


def ico_tri(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    for k, l in enumerate([0.62, 0.44, 0.26]):
        y = cy - s * 0.2 + k * s * 0.2
        cv.create_line(cx - s * 0.32, y, cx - s * 0.32 + s * l, y, fill=col, width=lw, capstyle="round", tags=tags)


def ico_wifi(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    for k, r in enumerate([0.42, 0.28, 0.14]):
        cv.create_arc(cx - s * r, cy - s * r + s * 0.2, cx + s * r, cy + s * r + s * 0.2, start=45, extent=90,
                      style="arc", outline=col, width=lw, tags=tags)
    cv.create_oval(cx - s * 0.04, cy + s * 0.16, cx + s * 0.04, cy + s * 0.24, fill=col, outline="", tags=tags)


def ico_ecran(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    rrect(cv, cx - s * 0.4, cy - s * 0.28, cx + s * 0.4, cy + s * 0.18, s * 0.05, outline=col, fill="", width=lw, tags=tags)
    cv.create_line(cx - s * 0.16, cy + s * 0.34, cx + s * 0.16, cy + s * 0.34, fill=col, width=lw, tags=tags)
    cv.create_line(cx, cy + s * 0.18, cx, cy + s * 0.34, fill=col, width=lw, tags=tags)


def ico_son(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    cv.create_polygon(cx - s * 0.36, cy - s * 0.1, cx - s * 0.2, cy - s * 0.1, cx, cy - s * 0.3, cx, cy + s * 0.3,
                      cx - s * 0.2, cy + s * 0.1, cx - s * 0.36, cy + s * 0.1, fill=col, outline="", tags=tags)
    for r in (0.18, 0.32):
        cv.create_arc(cx - s * r, cy - s * r, cx + s * r, cy + s * r, start=-45, extent=90, style="arc",
                      outline=col, width=lw, tags=tags)


def ico_disque(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    rrect(cv, cx - s * 0.38, cy - s * 0.26, cx + s * 0.38, cy + s * 0.26, s * 0.06, outline=col, fill="", width=lw, tags=tags)
    cv.create_line(cx - s * 0.38, cy + s * 0.04, cx + s * 0.38, cy + s * 0.04, fill=col, width=lw, tags=tags)
    cv.create_oval(cx + s * 0.2, cy + s * 0.1, cx + s * 0.28, cy + s * 0.18, fill=col, outline="", tags=tags)


def ico_lune(cv, cx, cy, s, col, tags=None):
    r = s * 0.34
    cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=60, extent=240, style="chord", fill=col, outline="", tags=tags)
    cv.create_oval(cx - r * 0.35, cy - r * 1.05, cx + r * 1.2, cy + r * 0.5, fill=T["tuile"], outline="", tags=tags)


def ico_bouclier(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    cv.create_polygon(cx, cy - s * 0.38, cx + s * 0.32, cy - s * 0.24, cx + s * 0.28, cy + s * 0.1, cx, cy + s * 0.38,
                      cx - s * 0.28, cy + s * 0.1, cx - s * 0.32, cy - s * 0.24, outline=col, fill="", width=lw,
                      joinstyle="round", tags=tags)
    cv.create_line(cx - s * 0.12, cy, cx - s * 0.02, cy + s * 0.1, cx + s * 0.14, cy - s * 0.1, fill=col, width=lw,
                   capstyle="round", tags=tags)


def ico_bluetooth(cv, cx, cy, s, col, tags=None):
    lw = max(2, s / 12)
    cv.create_line(cx - s * 0.18, cy - s * 0.16, cx + s * 0.16, cy + s * 0.14, cx, cy + s * 0.34, cx, cy - s * 0.34,
                   cx + s * 0.16, cy - s * 0.14, cx - s * 0.18, cy + s * 0.16, fill=col, width=lw,
                   joinstyle="round", tags=tags)


def ico_rj45(cv, cx, cy, s, col, tags=None):
    """Prise reseau (cable)."""
    lw = max(2, s / 12)
    rrect(cv, cx - s * 0.34, cy - s * 0.26, cx + s * 0.34, cy + s * 0.22, s * 0.05, outline=col, fill="", width=lw, tags=tags)
    for k in range(4):
        x = cx - s * 0.2 + k * s * 0.133
        cv.create_line(x, cy - s * 0.06, x, cy + s * 0.1, fill=col, width=max(1, lw * 0.8), tags=tags)
    cv.create_line(cx - s * 0.12, cy + s * 0.22, cx - s * 0.12, cy + s * 0.34, cx + s * 0.12, cy + s * 0.34,
                   cx + s * 0.12, cy + s * 0.22, fill=col, width=lw, tags=tags)


ICONES.update({"rj45": ico_rj45, "manette": ico_manette, "horloge": ico_horloge, "etoile": ico_etoile, "loupe": ico_loupe,
               "tri": ico_tri, "wifi": ico_wifi, "ecran": ico_ecran, "son": ico_son, "disque": ico_disque,
               "lune": ico_lune, "bouclier": ico_bouclier, "bluetooth": ico_bluetooth})


def duree_lisible(sec):
    """Temps de jeu en clair : « Jamais lance », « 12 min », « 3.5 heures »."""
    sec = int(sec or 0)
    if sec <= 0:
        return "Jamais lancé"
    if sec < 3600:
        return "%d min" % max(1, sec // 60)
    h = sec / 3600.0
    return "%d heure%s" % (h, "s" if h >= 2 else "") if h >= 10 else "%.1f heures" % h


def quand_lisible(ts):
    """Date de derniere session en clair : « Aujourd'hui », « Hier », « Avant-hier »..."""
    if not ts:
        return "Jamais"
    jours = int((time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) - ts) // 86400) + 1
    if time.time() - ts < 3600 * 3:
        return il_y_a(ts).capitalize()
    if jours <= 0:
        return "Aujourd'hui"
    if jours == 1:
        return "Hier"
    if jours == 2:
        return "Avant-hier"
    return il_y_a(ts).capitalize()


# ===========================================================================
# Etat du systeme : reseau, Bluetooth, peripheriques branches. Un fil interroge
# le systeme toutes les 2 s ; l'interface lit le resultat sans jamais attendre.
# ===========================================================================
def lire_octets_interface(interface):
    """(octets recus, octets emis) d'une interface reseau, lus dans /sys. (0, 0) si absente."""
    try:
        base = "/sys/class/net/%s/statistics/" % interface
        with open(base + "rx_bytes") as f:
            rx = int(f.read())
        with open(base + "tx_bytes") as f:
            tx = int(f.read())
        return rx, tx
    except (OSError, ValueError):
        return 0, 0


def interface_active():
    """(type, interface) de la connexion reseau en service : « ethernet » ou « wifi »,
    ("aucun", "") sans connexion. Le cable est prefere au Wi-Fi."""
    trouvees = []
    r = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], timeout=4)
    if r is not None and r.returncode == 0:
        for ligne in r.stdout.splitlines():
            champs = ligne.split(":")
            if len(champs) >= 3 and champs[2] == "connected" and champs[1] in ("ethernet", "wifi"):
                trouvees.append((champs[1], champs[0]))
    else:       # NetworkManager absent : on lit l'etat des interfaces
        for chemin in sorted(glob.glob("/sys/class/net/*/operstate")):
            interface = chemin.split("/")[4]
            try:
                with open(chemin) as f:
                    actif = f.read().strip() == "up"
            except OSError:
                continue
            if actif and interface != "lo":
                sans_fil = os.path.isdir("/sys/class/net/%s/wireless" % interface)
                trouvees.append(("wifi" if sans_fil else "ethernet", interface))
    trouvees.sort(key=lambda t: t[0] != "ethernet")
    return trouvees[0] if trouvees else ("aucun", "")


def etat_bluetooth():
    """« absent » (aucune puce), « eteint », « actif » ou « connecte » (au moins un appareil)."""
    r = _run(["bluetoothctl", "show"], timeout=4)
    if r is None or r.returncode != 0 or "Powered" not in r.stdout:
        return "absent"
    if "Powered: yes" not in r.stdout:
        return "eteint"
    c = _run(["bluetoothctl", "devices", "Connected"], timeout=4)
    return "connecte" if c is not None and c.returncode == 0 and c.stdout.strip() else "actif"


def peripheriques_branches():
    """{nom: genre} des manettes/volants et des cles ou disques amovibles branches.
    genre vaut « manette » ou « stockage »."""
    trouves = {}
    try:
        with open("/proc/bus/input/devices", errors="replace") as f:
            blocs = f.read().split("\n\n")
    except OSError:
        blocs = []
    for bloc in blocs:
        nom = re.search(r'Name="([^"]*)"', bloc)
        gestion = re.search(r"Handlers=(.*)", bloc)
        if nom and gestion and any(h.startswith("js") for h in gestion.group(1).split()):
            trouves[nom.group(1)] = "manette"
    r = _run(["lsblk", "-dnr", "-o", "NAME,RM,TYPE,SIZE,MODEL"], timeout=4)
    if r is not None and r.returncode == 0:
        for ligne in r.stdout.splitlines():
            champs = ligne.split(" ", 4)
            if len(champs) >= 4 and champs[1] == "1" and champs[2] == "disk":
                modele = champs[4].replace("\\x20", " ").strip() if len(champs) > 4 else ""
                trouves["%s (%s)" % (modele or champs[0], champs[3])] = "stockage"
    return trouves


def debit_lisible(octets_par_s):
    """1500000 -> « 1.4 Mo/s » ; 800 -> « 0 Ko/s »."""
    if octets_par_s >= 1048576:
        return "%.1f Mo/s" % (octets_par_s / 1048576.0)
    return "%d Ko/s" % (octets_par_s / 1024)


class EtatSysteme(threading.Thread):
    """Interroge reseau, Bluetooth et peripheriques toutes les 2 s, en arriere-plan.

    `etat` est lu par l'interface ; `evenements` recoit (genre, texte) quand un
    peripherique est branche ou debranche. Le premier releve est silencieux :
    ce qui est deja branche au demarrage n'est pas un evenement."""

    def __init__(self):
        super().__init__(daemon=True)
        self.etat = {"reseau": "aucun", "interface": "", "bas": 0.0, "haut": 0.0, "bt": "absent"}
        self.evenements = queue.Queue()
        self._precedent = None      # (horodatage, rx, tx)
        self._connus = None

    def run(self):
        """Boucle de releve : jamais d'exception qui arrete le fil."""
        while True:
            try:
                self.relever()
            except Exception:
                pass
            time.sleep(2)

    def relever(self):
        """Un releve complet. Separe de run() pour etre appelable seul."""
        if DEMO:
            self.etat.update(reseau="wifi", interface="demo", bas=1.4 * 1048576, haut=0.2 * 1048576, bt="connecte")
            return
        genre, interface = interface_active()
        maintenant = time.time()
        rx, tx = lire_octets_interface(interface) if interface else (0, 0)
        bas = haut = 0.0
        if self._precedent and interface == self.etat["interface"] and maintenant > self._precedent[0]:
            dt = maintenant - self._precedent[0]
            bas, haut = max(0, rx - self._precedent[1]) / dt, max(0, tx - self._precedent[2]) / dt
        self._precedent = (maintenant, rx, tx)
        self.etat.update(reseau=genre, interface=interface, bas=bas, haut=haut, bt=etat_bluetooth())
        actuels = peripheriques_branches()
        if self._connus is not None:
            for nom, g in actuels.items():
                if nom not in self._connus:
                    self.evenements.put((g, nom, True))
            for nom, g in self._connus.items():
                if nom not in actuels:
                    self.evenements.put((g, nom, False))
        self._connus = actuels


# ===========================================================================
# Manettes : lecture directe des peripheriques (python3-evdev). Les commandes
# passent par une file, l'interface les lit toutes les 30 ms.
# ===========================================================================
class Manette(threading.Thread):
    """Fil de lecture des manettes (python3-evdev). Traduit les boutons en commandes, avec repetition de la direction, et transmet appui/relachement de Guide et Select+Start."""
    def __init__(self, file):
        super().__init__(daemon=True)
        self.file = file
        self.devs = {}
        self.etat = {}
        self.marque = "xbox"

    def _scanner(self, evdev):
        """Detecte les nouvelles manettes (avec un bouton A) et note leur marque pour l'affichage des aides."""
        e = evdev.ecodes
        for chemin in evdev.list_devices():
            if chemin in self.devs:
                continue
            try:
                d = evdev.InputDevice(chemin)
                touches = d.capabilities().get(e.EV_KEY, [])
                if e.BTN_SOUTH in touches or e.BTN_A in touches or e.BTN_1 in touches:
                    self.devs[chemin] = d
                    marque = VENDEURS.get(d.info.vendor, "generique")
                    if "wii" in d.name.lower() or "nintendo" in d.name.lower() or "joy-con" in d.name.lower():
                        marque = "nintendo"
                    # xpad (Xbox) remonte le bouton de gauche en BTN_X (0x133) et celui du haut en
                    # BTN_Y (0x134) ; les pilotes recents (Sony, Nintendo) l'inverse : on remet dans l'ordre.
                    legacy = marque in ("xbox", "generique")
                    self.etat[chemin] = {"dir": None, "suivant": 0, "hat": [0, 0], "stick": [0.0, 0.0],
                                         "marque": marque, "legacy": legacy, "clavier": [0, 0]}
            except Exception:
                pass

    def _pousser(self, c):
        self.file.put(c)

    def _appui_special(self, st, e, ev):
        """Bouton Guide, Select et Start : appui ET relachement sont transmis.

        L'interface mesure la duree : appui long = menu Omni (cercle qui se
        remplit). Les manettes sans bouton central utilisent Select + Start
        maintenus ensemble, qui produisent les memes evenements (COMBO_*)."""
        tenus = st.setdefault("tenus", set())
        if ev.value:
            tenus.add(ev.code)
        else:
            tenus.discard(ev.code)
        if ev.code == e.BTN_MODE:
            self._pousser("GUIDE_BAS" if ev.value else "GUIDE_HAUT")
            return
        combo = e.BTN_SELECT in tenus and e.BTN_START in tenus
        if combo != st.get("combo", False):
            st["combo"] = combo
            self._pousser("COMBO_BAS" if combo else "COMBO_HAUT")
        elif ev.value and not combo:
            self._pousser("START" if ev.code == e.BTN_START else "SELECT")

    def run(self):
        """Boucle de lecture : scanne les manettes toutes les 3 s, lit leurs evenements et pousse les commandes dans la file de l'interface."""
        try:
            import evdev
            import select
        except Exception:
            return      # pas de python3-evdev : clavier et souris seulement
        e = evdev.ecodes
        boutons = {e.BTN_SOUTH: "A", e.BTN_EAST: "B", e.BTN_TL: "LB", e.BTN_TR: "RB", e.BTN_MODE: "GUIDE",
                   e.BTN_START: "START", e.BTN_SELECT: "SELECT",
                   # Wiimote tenue a l'horizontale : 2 = valider, 1 = retour, + / - = menus
                   e.BTN_2: "A", e.BTN_1: "B", e.KEY_NEXT: "START", e.KEY_PREVIOUS: "SELECT"}
        croix_clavier = {e.KEY_LEFT: (0, -1), e.KEY_RIGHT: (0, 1), e.KEY_UP: (1, -1), e.KEY_DOWN: (1, 1)}
        dernier_scan = 0
        while True:
            now = time.time()
            if now - dernier_scan > 3:
                self._scanner(evdev)
                dernier_scan = now
            if not self.devs:
                time.sleep(0.5)
                continue
            try:
                prets, _, _ = select.select(list(self.devs.values()), [], [], 0.05)
            except Exception:
                prets = []
            for d in prets:
                st = self.etat[d.path]
                try:
                    for ev in d.read():
                        if ev.type == e.EV_KEY and ev.code in croix_clavier:
                            axe, sens = croix_clavier[ev.code]
                            st["hat"][axe] = sens if ev.value else 0
                        elif ev.type == e.EV_KEY and ev.code in (e.BTN_MODE, e.BTN_SELECT, e.BTN_START) \
                                and ev.value in (0, 1):
                            self._appui_special(st, e, ev)
                        elif ev.type == e.EV_KEY and ev.value == 1:
                            nom = boutons.get(ev.code)
                            if ev.code == 0x133:
                                nom = "X" if st["legacy"] else "Y"
                            elif ev.code == 0x134:
                                nom = "Y" if st["legacy"] else "X"
                            if nom:
                                self.marque = st["marque"]
                                self._pousser(nom)
                        elif ev.type == e.EV_ABS:
                            if ev.code == e.ABS_HAT0X:
                                st["hat"][0] = ev.value
                            elif ev.code == e.ABS_HAT0Y:
                                st["hat"][1] = ev.value
                            elif ev.code in (e.ABS_X, e.ABS_Y):
                                info = d.absinfo(ev.code)
                                milieu = (info.max + info.min) / 2.0
                                v = (ev.value - milieu) / max(1.0, (info.max - info.min) / 2.0)
                                st["stick"][0 if ev.code == e.ABS_X else 1] = v
                except OSError:
                    self.devs.pop(d.path, None)
                    continue
                hx, hy = st["hat"]
                sx, sy = st["stick"]
                direction = None
                if hx or hy:
                    direction = ("gauche" if hx < 0 else "droite") if hx else ("haut" if hy < 0 else "bas")
                elif max(abs(sx), abs(sy)) > 0.55:
                    direction = ("gauche" if sx < 0 else "droite") if abs(sx) > abs(sy) else ("haut" if sy < 0 else "bas")
                if direction != st["dir"]:
                    st["dir"] = direction
                    if direction:
                        self._pousser(direction)
                        st["suivant"] = now + 0.40
            # repetition quand on maintient la direction
            for st in self.etat.values():
                if st["dir"] and now >= st["suivant"]:
                    self._pousser(st["dir"])
                    st["suivant"] = now + 0.13


# ===========================================================================
# Temps de jeu : Omni compte lui-meme (cahier des charges)
# ===========================================================================
class SuiviJeux:
    """Temps de jeu : Omni compte lui-meme les sessions, et referme le launcher quand le joueur quitte le jeu."""
    def __init__(self, app):
        self.app = app
        self.sessions = []
        app.after(10000, self._tic)

    def stats(self, profil, jeu_id):
        return profil.setdefault("jeux", {}).setdefault(jeu_id, {})

    def demarrer(self, jeu, profil, proc):
        st = self.stats(profil, jeu["id"])
        st["derniere"] = time.time()
        profil["derniere_activite"] = time.time()
        sauver_profils(self.app.profils)
        self.sessions.append({"jeu": jeu, "profil": profil, "proc": proc, "debut": time.time(), "vu": False})

    def _steam_actif(self, appid):
        """Vrai si un processus de Steam porte l'AppId du jeu."""
        motif = ("AppId=%s" % appid).encode()
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    with open("/proc/%s/cmdline" % pid, "rb") as f:
                        if motif in f.read():
                            return True
                except Exception:
                    pass
        return False

    def _vivant(self, s):
        """Vrai si la session de jeu tourne encore (Steam : le jeu est cherche dans les processus, avec 2 minutes de grace au lancement)."""
        if s["jeu"]["plateforme"] == "steam":
            if self._steam_actif(s["jeu"]["lancement"].get("appid", "?")):
                s["vu"] = True
                return True
            return not s["vu"] and time.time() - s["debut"] < 120
        p = s["proc"]
        return hasattr(p, "poll") and p.poll() is None

    def _tic(self):
        """Toutes les 10 s : cloture les sessions terminees, ajoute leur duree et ramene Omni devant."""
        for s in list(self.sessions):
            if not self._vivant(s):
                duree = time.time() - s["debut"]
                if s["jeu"]["plateforme"] == "steam" and not s["vu"]:
                    duree = 0
                st = self.stats(s["profil"], s["jeu"]["id"])
                st["temps"] = st.get("temps", 0) + duree
                st["derniere"] = time.time()
                self.sessions.remove(s)
                sauver_profils(self.app.profils)
                # le joueur a quitte le jeu : son launcher part avec, retour au menu Omni
                if PLAT.get(s["jeu"]["plateforme"], {}).get("id") in (["steam"] + list(LAUNCHERS)):
                    fermer_launcher(s["jeu"]["plateforme"])
                self.app.revenir()
        self.app.after(10000, self._tic)


# ===========================================================================
# Base des ecrans : une seule toile (fond a rayons visible partout), elements
# dessines, focus « or » deplace a la manette / aux fleches / a la souris.
# ===========================================================================
class PageBase(tk.Canvas):
    """Base de tous les ecrans console : une toile, un fond a rayons, des elements dessines, un focus « or » deplace a la manette, au clavier ou a la souris."""
    titre = ""
    avec_badge = True

    def __init__(self, parent, app):
        """Cree la toile et branche la molette de la souris."""
        super().__init__(parent, width=app.W, height=app.H, bg=T["bg"], highlightthickness=0)
        self.app = app
        self.foc = {}
        self.ordre = []
        self.focus_id = None
        self._imgs = []
        self.bind("<Button-4>", lambda e: self.defiler(-1))
        self.bind("<Button-5>", lambda e: self.defiler(1))
        self.bind("<MouseWheel>", lambda e: self.defiler(-1 if e.delta > 0 else 1))

    # ----- a redefinir par chaque ecran -----
    def dessiner(self):
        pass

    def aides(self):
        return [("A", "Choisir"), ("B", "Retour")]

    def retour(self):
        pass

    def action_x(self):
        pass

    def action_y(self):
        pass

    def onglet(self, sens):
        pass

    def defiler(self, sens):
        pass

    def nav_speciale(self, d):
        return False

    def bord(self, d):
        pass

    def saisie_active(self):
        return True

    # ----- mecanique commune -----
    def img(self, ph):
        if ph is not None:
            self._imgs.append(ph)
        return ph

    def redessiner(self):
        """Efface et redessine tout l'ecran, puis replace l'anneau de focus."""
        self.delete("all")
        self.foc, self.ordre, self._imgs = {}, [], []
        self._fond()
        self.dessiner()
        self._entete()
        self._aides()
        if self.focus_id not in self.foc:
            self.focus_id = self.focus_defaut()
        self._anneau()

    def focus_defaut(self):
        return self.ordre[0] if self.ordre else None

    def _fond(self):
        """Fond a rayons, soleil, nom de la console et titre de la page."""
        a = self.app
        ph = a.fond_image()
        if ph is not None:
            self.create_image(0, 0, image=ph, anchor="nw")
        soleil(self, a.px(30), a.px(24), a.px(30), a.px(26))
        self.create_text(a.px(72), a.px(37), text="OMNI", anchor="w", fill=T["mag"], font=a.police(17, True))
        if self.titre:
            self.create_text(a.W / 2 + 2, a.px(50) + 2, text=self.titre, fill=mel(T["mag"], T["bg"], 0.35),
                             font=a.police(29))
            self.create_text(a.W / 2, a.px(50), text=self.titre, fill=T["text"], font=a.police(29))

    def _entete(self):
        """Badge du joueur et icones (clavier, accessibilite, reglages), puis icones d'etat."""
        a = self.app
        s = a.px(48)
        x = a.W - a.px(30)
        y = a.px(24)
        j = a.joueur_actif
        if j is not None and self.avec_badge:
            nom = tronquer(j["nom"], a.police(15, True), a.px(150))
            lb = a.police(15, True).measure(nom) + a.px(72)
            x0 = x - lb
            rrect(self, x0, y, x, y + s, s / 2, fill=T["violet"], outline=mel(T["or"], T["bg"], 0.35), width=2, tags="ico_badge")
            av = self.img(carte_img(j["planche"], j["ligne"], j["colonne"], s - a.px(8)))
            if av:
                self.create_image(x0 + s / 2, y + s / 2, image=av, tags="ico_badge")
            self.create_text(x0 + s + a.px(6), y + s / 2, text=nom, anchor="w", fill=T["text"],
                             font=a.police(15, True), tags="ico_badge")
            self.focusable("ico_badge", (x0, y, x, y + s), lambda: a.montrer(PageSelection), tag="ico_badge")
            x = x0 - a.px(12)
        icones = [("clavier", a.toggle_clavier), ("acces", a.toggle_acces)]
        if j is not None:
            icones.append(("reglages", lambda: a.montrer(PageReglages)))
        for nom, cmd in reversed(icones):
            x0 = x - s
            tag = "ico_" + nom
            self.create_oval(x0, y, x, y + s, fill=T["violet"], outline=T["cyan"], width=round(2 * TRAIT[0]), tags=tag)
            ICONES[nom](self, x0 + s / 2, y + s / 2, s * 0.58, T["cyan"], tags=tag)
            self.focusable(tag, (x0, y, x, y + s), cmd, tag=tag)
            x = x0 - a.px(10)
        self._x_statut = x
        self._statuts()

    def maj_statuts(self):
        """Redessine seulement les icones d'etat (appele toutes les 2 s)."""
        if hasattr(self, "_x_statut"):
            self._statuts()

    def _statuts(self):
        """Icones d'etat a gauche des boutons de l'en-tete : reseau (cable, Wi-Fi
        ou coupe) avec les debits en temps reel, et Bluetooth."""
        a = self.app
        etat = a.systeme.etat
        self.delete("statut")
        s = a.px(48)
        y = a.px(24)
        x = self._x_statut
        bt = etat["bt"]
        couleur_bt = {"connecte": T["ok"], "actif": T["cyan"]}.get(bt, T["dim"])
        x0 = x - s
        self.create_oval(x0, y, x, y + s, fill=T["violet"], outline=couleur_bt, width=round(2 * TRAIT[0]), tags="statut")
        ICONES["bluetooth"](self, x0 + s / 2, y + s / 2, s * 0.58, couleur_bt, tags="statut")
        if bt in ("absent", "eteint"):
            self.create_line(x0 + s * 0.28, y + s * 0.72, x0 + s * 0.72, y + s * 0.28, fill=T["dim"],
                             width=round(2 * TRAIT[0]), tags="statut")
        x = x0 - a.px(10)
        reseau = etat["reseau"]
        couleur = T["ok"] if reseau != "aucun" else T["amber"]
        x0 = x - s
        self.create_oval(x0, y, x, y + s, fill=T["violet"], outline=couleur, width=round(2 * TRAIT[0]), tags="statut")
        ICONES["rj45" if reseau == "ethernet" else "wifi"](self, x0 + s / 2, y + s / 2, s * 0.58, couleur, tags="statut")
        if reseau == "aucun":
            self.create_line(x0 + s * 0.28, y + s * 0.72, x0 + s * 0.72, y + s * 0.28, fill=T["amber"],
                             width=round(2 * TRAIT[0]), tags="statut")
        else:
            texte = "\u2193 %s   \u2191 %s" % (debit_lisible(etat["bas"]), debit_lisible(etat["haut"]))
            # sous les icones, pas a cote : le titre de la page est centre et leur serait superpose
            self.create_text(self._x_statut, y + s + a.px(14), text=texte, anchor="e", fill=T["text2"],
                             font=a.police(12), tags="statut")

    def _aides(self):
        """Aides de boutons en bas a droite, aux symboles de la marque de manette utilisee en dernier."""
        a = self.app
        y = a.H - a.px(38)
        x = a.W - a.px(40)
        for bouton, texte in reversed(self.aides()):
            f = a.police(15)
            x -= f.measure(texte)
            self.create_text(x, y, text=texte, anchor="w", fill=T["text"], font=f)
            x -= a.px(10)
            r = a.px(15)
            if bouton in BOUTONS_MANETTE:
                lettre, col = AIDES_MARQUE.get(a.marque_manette(), AIDES_MARQUE["xbox"])[bouton]
                self.create_oval(x - 2 * r, y - r, x, y + r, outline=col, width=round(2 * TRAIT[0]), fill=T["bg"])
                self.create_text(x - r, y, text=lettre, fill=col, font=a.police(14, True))
                x -= 2 * r + a.px(30)
            else:
                self.create_text(x, y, text=bouton, anchor="e", fill=T["cyan"], font=a.police(15, True))
                x -= a.police(15, True).measure(bouton) + a.px(30)

    def focusable(self, fid, bbox, action=None, tag=None, anneau=True):
        self.foc[fid] = {"bbox": bbox, "action": action, "anneau": anneau}
        self.ordre.append(fid)
        if tag:
            self.tag_bind(tag, "<Enter>", lambda e: (self.configure(cursor="hand2"), self.focaliser(fid, souris=True)))
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
            self.tag_bind(tag, "<Button-1>", lambda e: self.cliquer(fid))

    def _anneau(self):
        """Dessine l'anneau d'or autour de l'element qui a le focus."""
        self.delete("anneau")
        f = self.foc.get(self.focus_id)
        if not f or not f["anneau"]:
            return
        a = self.app
        x0, y0, x1, y1 = f["bbox"]
        m = a.px(4)
        neon(self, x0 - m, y0 - m, x1 + m, y1 + m, a.px(12), T["or"], halo=3, w=3, tags="anneau")
        self.itemconfigure("anneau", state="disabled")
        self.tag_raise("anneau")

    def focaliser(self, fid, souris=False):
        """Donne le focus a un element (avec un son de survol quand c'est a la manette)."""
        if fid == self.focus_id or fid not in self.foc:
            return
        ancien = self.focus_id
        self.focus_id = fid
        if not souris:
            self.app.jouer_son("hover")
        self.sur_focus(ancien, fid)

    def sur_focus(self, ancien, nouveau):
        self._anneau()

    def cliquer(self, fid):
        self.focaliser(fid, souris=True)
        self.activer()

    def activer(self):
        f = self.foc.get(self.focus_id)
        if f and f["action"]:
            self.app.jouer_son("select")
            f["action"]()

    def deplacer(self, d):
        """Deplace le focus vers l'element le plus proche dans la direction demandee."""
        if self.nav_speciale(d):
            return
        f = self.foc.get(self.focus_id)
        if f is None:
            if self.ordre:
                self.focaliser(self.ordre[0])
            return
        vx, vy = {"gauche": (-1, 0), "droite": (1, 0), "haut": (0, -1), "bas": (0, 1)}[d]
        x0, y0, x1, y1 = f["bbox"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        meilleur, score_min = None, None
        for fid, g in self.foc.items():
            if fid == self.focus_id:
                continue
            gx0, gy0, gx1, gy1 = g["bbox"]
            gx, gy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
            prim = (gx - cx) * vx + (gy - cy) * vy
            if prim <= 4:
                continue
            sec = abs((gx - cx) * vy) + abs((gy - cy) * vx)
            score = prim + 2.5 * sec
            if score_min is None or score < score_min:
                meilleur, score_min = fid, score
        if meilleur:
            self.focaliser(meilleur)
        else:
            self.bord(d)

    def commande(self, c):
        """Aiguille une commande de manette vers l'action de la page : deplacement, A, B, X, Y, onglets."""
        if c in ("haut", "bas", "gauche", "droite"):
            self.deplacer(c)
        elif c == "A":
            self.activer()
        elif c == "B":
            self.retour()
        elif c == "X":
            self.action_x()
        elif c == "Y":
            self.action_y()
        elif c in ("LB", "RB"):
            self.onglet(-1 if c == "LB" else 1)
        elif c == "START":
            self.app.toggle_acces()

    # ----- petits elements dessines -----
    def bouton_or(self, fid, x, y, w, h, texte, action, plein=False, couleur=None):
        """Bouton dore dessine, focalisable."""
        a = self.app
        col = couleur or T["or"]
        tag = "b_" + fid
        rrect(self, x, y, x + w, y + h, a.px(6), fill=col if plein else T["violet"], outline=col, width=2, tags=tag)
        self.create_text(x + w / 2, y + h / 2, text=texte, fill=T["bg"] if plein else col,
                         font=a.police(13, True), tags=tag)
        self.focusable(fid, (x, y, x + w, y + h), action, tag=tag)

    def panneau(self, x0, y0, x1, y1, lueur=False):
        a = self.app
        if lueur:
            neon(self, x0, y0, x1, y1, a.px(12), T["or"], fill=T["violet"], halo=3, w=2)
        else:
            neon(self, x0, y0, x1, y1, a.px(12), mel(T["cyan"], T["bg"], 0.45), fill=T["violet"], halo=1, w=1)

    def pilule(self, x, y, texte, col, plein=False, anchor="w"):
        """Etiquette arrondie (statut, niveau...). Renvoie sa largeur."""
        a = self.app
        f = a.police(11, True)
        w = f.measure(texte) + a.px(16)
        h = a.px(22)
        if anchor == "center":
            x -= w / 2
        rrect(self, x, y, x + w, y + h, h / 2, fill=col if plein else T["bg"], outline=col, width=1)
        self.create_text(x + w / 2, y + h / 2, text=texte, fill=T["bg"] if plein else col, font=f)
        return w


# ===========================================================================
# Ecran « Qui joue ? » : carrousel (profil central agrandi, orbite d'or)
# ===========================================================================
class PageSelection(PageBase):
    """Ecran « Qui joue ? » : carrousel de profils, le profil central agrandi."""
    titre = "QUI JOUE ?"
    avec_badge = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        app.joueur_actif = None
        self.items = sorted(app.profils, key=lambda p: -(p.get("derniere_activite") or 0)) + [None]
        self.idx = 0
        self.focus_id = "carte"
        self.redessiner()

    def _dims(self, d):
        a = self.app
        return {0: (a.px(380), a.px(440)), 1: (a.px(240), a.px(320)), 2: (a.px(200), a.px(270))}[abs(d)]

    def dessiner(self):
        """Dessine les profils voisins puis le profil central et les chevrons."""
        a = self.app
        cx, cy = a.W / 2, a.H * 0.50
        for d in (-2, 2, -1, 1, 0):
            i = self.idx + d
            if not 0 <= i < len(self.items):
                continue
            off = {0: 0, 1: a.px(345), 2: a.px(590)}[abs(d)] * (1 if d > 0 else -1)
            self._carte(i, cx + off, cy, d)
        # chevrons
        w, h = self._dims(0)
        for sens in (-1, 1):
            x = cx + sens * (w / 2 + a.px(26))
            if 0 <= self.idx + sens < len(self.items):
                t = "chev%d" % sens
                self.create_line(x - sens * a.px(8), cy - a.px(18), x + sens * a.px(8), cy, x - sens * a.px(8),
                                 cy + a.px(18), fill=T["or"], width=round(3 * TRAIT[0]), capstyle="round", joinstyle="round", tags=t)
                self.tag_bind(t, "<Button-1>", lambda e, s_=sens: self._aller(s_))

    def _carte(self, i, x, y, d):
        """Dessine une carte du carrousel (profil ou « ajouter ») selon son rang par rapport au centre."""
        a = self.app
        w, h = self._dims(d)
        x0, y0, x1, y1 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
        tag = "c%d" % i
        prof = self.items[i]
        if d == 0:
            neon(self, x0, y0, x1, y1, a.px(14), mel(T["or"], "#ffffff", 0.1), fill=T["violet"], halo=3, w=2, tags=tag)
        else:
            rrect(self, x0, y0, x1, y1, a.px(12), fill=mel(T["violet"], T["bg"], 0.35 if abs(d) == 2 else 0.1),
                  outline=mel(T["or"], T["bg"], 0.45 if abs(d) == 1 else 0.7), width=2, tags=tag)
        if prof is None:
            ico_plus(self, x, y - h * 0.10, w * 0.32, T["or"] if abs(d) < 2 else mel(T["or"], T["bg"], 0.4), tags=tag)
            self.create_text(x, y + h * 0.22, text="AJOUTER UN\nNOUVEAU PROFIL", justify="center",
                             fill=T["or"] if abs(d) < 2 else T["dim"], font=a.police(17 if d == 0 else 13, True), tags=tag)
        else:
            if d == 0:
                dessiner_carte(self, x, y - a.px(62), a.px(250), prof["planche"], prof["ligne"], prof["colonne"],
                               0, tags=tag, img_refs=self._imgs)
                self.create_text(x, y + h * 0.22, text=tronquer(prof["nom"], a.police(25), w - a.px(30)),
                                 fill=T["text"], font=a.police(25), tags=tag)
                ligne = y + h * 0.31
                self.pilule(x, ligne, "NIVEAU %s  ·  DERNIÈRE PARTIE : %s" % (
                    prof.get("niveau", 1), il_y_a(prof.get("derniere_activite")).upper()), T["or"], anchor="center")
                plats = [PLAT[p] for p in prof.get("plateformes", []) if p in PLAT]
                ps = a.px(30)
                total = len(plats) * (ps + a.px(6)) - a.px(6)
                for k, pl in enumerate(plats):
                    pastille(self, x - total / 2 + k * (ps + a.px(6)), ligne + a.px(32), ps, pl, tags=tag)
            else:
                dessiner_carte(self, x, y - h * 0.09, a.px(200 if abs(d) == 1 else 165), prof["planche"],
                               prof["ligne"], prof["colonne"], abs(d), tags=tag, img_refs=self._imgs)
                self.create_text(x, y + h * 0.39, text=tronquer(prof["nom"], a.police(18), w - a.px(20)),
                                 fill=T["text2"] if abs(d) == 1 else T["dim"], font=a.police(18), tags=tag)
        if d == 0:
            self.focusable("carte", (x0, y0, x1, y1), self._choisir, anneau=False)
            self.tag_bind(tag, "<Button-1>", lambda e: self.cliquer("carte"))
        else:
            self.tag_bind(tag, "<Button-1>", lambda e, dd=d: self._aller(dd))
        self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))

    def _aller(self, d):
        n = max(0, min(len(self.items) - 1, self.idx + d))
        if n != self.idx:
            self.idx = n
            self.app.jouer_son("hover")
            self.focus_id = "carte"
            self.redessiner()

    def nav_speciale(self, d):
        if self.focus_id == "carte" and d in ("gauche", "droite"):
            self._aller(-1 if d == "gauche" else 1)
            return True
        return False

    def defiler(self, sens):
        self._aller(sens)

    def onglet(self, sens):
        self._aller(sens)

    def _choisir(self):
        """Valide le profil central : il devient le joueur actif et la bibliotheque s'ouvre."""
        prof = self.items[self.idx]
        a = self.app
        if prof is None:
            a.montrer(PageProfil)
            return
        a.jouer_son("valid")
        prof["derniere_activite"] = time.time()
        sauver_profils(a.profils)
        a.choisir_joueur(prof)
        a.montrer(PageBibliotheque)

    def action_x(self):
        if self.focus_id == "carte" and self.items[self.idx] is not None:
            self.app.montrer(PageProfil, profil=self.items[self.idx])

    def aides(self):
        if self.items[self.idx] is None:
            return [("\u25c0 \u25b6", "Parcourir"), ("A", "Créer")]
        return [("\u25c0 \u25b6", "Parcourir"), ("A", "Jouer"), ("X", "Modifier")]


# ===========================================================================
# Creation / modification d'un joueur : carrousel de cartes + clavier ouvert
# ===========================================================================
class PageProfil(PageBase):
    """Creation ou modification d'un joueur : carrousel de cartes, nom, clavier a l'ecran."""
    avec_badge = False
    clavier_integre = True

    def __init__(self, parent, app, profil=None):
        """Prepare le champ de nom et le clavier ; le clavier est ouvert d'office si une manette est branchee."""
        super().__init__(parent, app)
        self.profil = profil
        self.titre = "MODIFIER LE PROFIL" if profil else ("BIENVENUE !" if not app.profils else "NOUVEAU JOUEUR")
        app.joueur_actif = None
        self.cartes = toutes_les_cartes()
        self.idx = 0
        if profil:
            cle = (profil["planche"], profil["ligne"], profil["colonne"])
            self.idx = self.cartes.index(cle) if cle in self.cartes else 0
        self.msg = ""
        self.confirm = 0
        self.entry = tk.Entry(self, font=app.police(22), bg=T["violet"], fg=T["text"], insertbackground=T["or"],
                              relief="flat", bd=0, width=22, justify="center", highlightthickness=app.px(2),
                              highlightbackground=T["or"], highlightcolor=T["or"])
        self.entry.nom_champ = "Nom du joueur"
        if profil:
            self.entry.insert(0, profil["nom"])
        self.entry.bind("<Return>", lambda e: self.valider())
        self.clavier = ClavierIntegre(self, app, integre=True, compact=True)
        # a la manette le clavier est ouvert d'office ; au clavier physique il gene
        self.clavier_visible = app.manette_presente()
        self.focus_id = "avatar"
        self.redessiner()
        self.entry.focus_set()
        app.cible_saisie = self.entry
        self.clavier.maj_statut()

    def dessiner(self):
        """Dessine la bande de cartes, le champ de nom, le clavier et le bouton de suppression."""
        a = self.app
        cx = a.W / 2
        x0, y0, x1, y1 = cx - a.px(470), a.px(84), cx + a.px(470), a.px(372)
        self.panneau(x0, y0, x1, y1, lueur=self.focus_id == "avatar")
        ay = y0 + a.px(112)
        # bande de cartes : la choisie au centre, trois de chaque cote
        pas = [0, a.px(150), a.px(265), a.px(365)]
        hauteurs = [a.px(196), a.px(150), a.px(124), a.px(100)]
        for d in (3, 2, 1):
            for sens in (-1, 1):
                j = (self.idx + sens * d) % len(self.cartes)
                t = "bande%d" % (sens * d)
                dessiner_carte(self, cx + sens * pas[d], ay, hauteurs[d], *self.cartes[j],
                               niveau=1 if d == 1 else 2, tags=t, img_refs=self._imgs)
                self.tag_bind(t, "<Button-1>", lambda e, k=sens * d: self._carte(k))
                self.tag_bind(t, "<Enter>", lambda e: self.configure(cursor="hand2"))
                self.tag_bind(t, "<Leave>", lambda e: self.configure(cursor=""))
        dessiner_carte(self, cx, ay, hauteurs[0], *self.cartes[self.idx], niveau=0, tags="av", img_refs=self._imgs)
        for sens in (-1, 1):
            x = cx + sens * a.px(445)
            t = "chev%d" % sens
            self.create_line(x - sens * a.px(8), ay - a.px(18), x + sens * a.px(8), ay, x - sens * a.px(8), ay + a.px(18),
                             fill=T["or"], width=round(3 * TRAIT[0]), capstyle="round", joinstyle="round", tags=t)
            self.tag_bind(t, "<Button-1>", lambda e, s_=sens: self._carte(s_))
        self.create_text(x1 - a.px(16), y0 + a.px(14), text="%d / %d" % (self.idx + 1, len(self.cartes)), anchor="ne",
                         fill=T["dim"], font=a.police(11, True))
        self.focusable("avatar", (x0, y0, x1, y0 + a.px(222)), None, anneau=False)
        self.create_text(cx, y1 - a.px(56), text="TON NOM", fill=T["or"], font=a.police(12, True))
        self.create_window(cx, y1 - a.px(26), window=self.entry)
        if self.msg:
            self.create_text(cx, y1 + a.px(12), text=self.msg, fill=T["amber"], font=a.police(14, True))
        if self.clavier_visible:
            self.clavier.set_nav(self.focus_id == "clavier")
            self.create_window(cx, y1 + a.px(26), window=self.clavier, anchor="n")
            self.update_idletasks()
            kh = self.clavier.winfo_reqheight()
            kw = self.clavier.winfo_reqwidth()
            self.focusable("clavier", (cx - kw / 2, y1 + a.px(26), cx + kw / 2, y1 + a.px(26) + kh), None, anneau=False)
        else:
            self.create_text(cx, y1 + a.px(40), text="Clavier à l'écran : icône en haut à droite",
                             fill=T["dim"], font=a.police(13))
        if self.profil:
            txt = "CONFIRMER LA SUPPRESSION" if time.time() < self.confirm else "SUPPRIMER CE PROFIL"
            self.bouton_or("suppr", a.px(40), a.H - a.px(62), a.px(250), a.px(40), txt, self._supprimer, couleur=T["danger"])

    def basculer_clavier(self):
        self.clavier_visible = not self.clavier_visible
        if not self.clavier_visible and self.focus_id == "clavier":
            self.focus_id = "avatar"
        self.redessiner()

    def _carte(self, sens):
        self.idx = (self.idx + sens) % len(self.cartes)
        self.app.jouer_son("hover")
        self.redessiner()

    def nav_speciale(self, d):
        """Navigation propre a la page : gauche/droite change de carte, bas descend vers le clavier."""
        if self.focus_id == "avatar" and d in ("gauche", "droite"):
            self._carte(-1 if d == "gauche" else 1)
            return True
        if self.focus_id == "avatar" and d == "bas" and not self.clavier_visible:
            self.basculer_clavier()
            self.focus_id = "clavier"
            self.redessiner()
            return True
        if self.focus_id == "avatar" and d == "bas":
            self.focus_id = "clavier"
            self.redessiner()
            return True
        if self.focus_id == "clavier":
            if self.clavier.commande(d) == "sortie_haut":
                self.focus_id = "avatar"
                self.redessiner()
            return True
        return False

    def saisie_active(self):
        return self.focus_id == "clavier"

    def commande(self, c):
        """Commandes de manette de la page (A ouvre le clavier, Y tire une carte au hasard)."""
        if self.focus_id == "clavier" and c in ("A", "X", "Y"):
            self.clavier.commande(c)
            return
        if self.focus_id == "avatar" and c == "A":
            self.clavier_visible = True
            self.focus_id = "clavier"
            self.redessiner()
            return
        if c == "Y" and self.focus_id == "avatar":
            self.idx = random.randrange(len(self.cartes))
            self.redessiner()
            return
        PageBase.commande(self, c)

    def aides(self):
        if self.focus_id == "clavier":
            return [("A", "Touche"), ("X", "Effacer"), ("Y", "Majuscule"), ("B", "Retour")]
        return [("\u25c0 \u25b6", "Changer de carte"), ("Y", "Au hasard"), ("A", "Choisir"), ("B", "Retour")]

    def retour(self):
        a = self.app
        if a.profils:
            a.montrer(PageSelection)

    def valider(self):
        """Enregistre le profil (nouveau ou modifie) apres controle du nom."""
        a = self.app
        nom = self.entry.get().strip()
        if not nom:
            self.msg = "Écris d'abord ton nom."
            self.focus_id = "clavier"
            self.redessiner()
            return
        if any(p["nom"].lower() == nom.lower() and p is not self.profil for p in a.profils):
            self.msg = "Ce nom est déjà pris."
            self.redessiner()
            return
        pl, r, c = self.cartes[self.idx]
        a.jouer_son("valid")
        if self.profil:
            self.profil.update(nom=nom, planche=pl, ligne=r, colonne=c)
            sauver_profils(a.profils)
            a.montrer(PageSelection)
            return
        prof = {"id": uuid.uuid4().hex[:8], "nom": nom, "planche": pl, "ligne": r, "colonne": c, "niveau": 1,
                "derniere_activite": time.time(), "plateformes": [], "migre": True, "jeux": {}}
        a.profils.append(prof)
        sauver_profils(a.profils)
        a.choisir_joueur(prof)
        a.montrer(PageBibliotheque)

    def _supprimer(self):
        """Supprime le profil apres une seconde confirmation dans les 4 secondes."""
        a = self.app
        if time.time() < self.confirm:
            a.profils[:] = [p for p in a.profils if p is not self.profil]
            sauver_profils(a.profils)
            a.montrer(PageSelection if a.profils else PageProfil)
        else:
            self.confirm = time.time() + 4
            self.redessiner()
            self.after(4100, lambda: self.winfo_exists() and self.redessiner())


# ===========================================================================
# Plateformes : liste avec statut + panneau de detail
# ===========================================================================
DESCRIPTIONS = {
    "integree": "Intégrée à Omni : tes jeux s'affichent ici et se lancent directement.",
    "deleguee": "Launcher officiel : il tourne en coulisse pendant tes parties. Ouvre-le pour ton compte, tes achats ou installer un jeu.",
}


class PagePlateformes(PageBase):
    """Liste des plateformes avec leur statut, boutons d'action et panneau de detail."""
    titre = "PLATEFORMES"

    def __init__(self, parent, app, plat=None):
        """Prepare la page et lance la surveillance des installations."""
        super().__init__(parent, app)
        self.j = app.joueur_actif
        self.haut = 0
        self.sel = plat.get("id") if isinstance(plat, dict) else plat
        self._compte = {}
        self._compte_t = 0
        self.redessiner()
        self.after(700, self._veille)

    def _comptes(self):
        if time.time() - self._compte_t > 5:
            self._compte = {p["id"]: len(jeux_de(p["id"])) if plateforme_presente(p["id"]) else 0 for p in PLATEFORMES}
            self._compte_t = time.time()
        return self._compte

    def _etat(self, pid):
        """(etat, libelle, couleur) d'une plateforme : en cours, echec, pret ou pas installe."""
        a = self.app
        inst = a.installs.get(pid)
        if inst and inst["etat"] == "encours":
            return "encours", "INSTALLATION EN COURS (%d %%)" % inst["pct"], T["cyan"]
        if inst and inst["etat"] == "echec":
            return "echec", "ÉCHEC DE L'INSTALLATION", T["danger"]
        if plateforme_presente(pid):
            if pid == "steam" and steam_connecte():
                return "ok", "PRÊT · COMPTE CONNECTÉ", T["ok"]
            return "ok", "PRÊT", T["ok"]
        return "absent", "PAS INSTALLÉ" + (" (300 Mo À TÉLÉCHARGER)" if pid == "steam" else ""), T["dim"]

    def dessiner(self):
        """Dessine la colonne de plateformes (avec defilement) et le panneau de detail."""
        a = self.app
        lx0, ly0 = a.px(60), a.px(100)
        lx1, ly1 = int(a.W * 0.56), a.H - a.px(80)
        self.panneau(lx0, ly0, lx1, ly1)
        RH, G = a.px(84), a.px(10)
        visibles = max(1, (ly1 - ly0 - a.px(20) + G) // (RH + G))
        ids = [p["id"] for p in PLATEFORMES]
        if self.sel is None:
            self.sel = ids[0]
        k = ids.index(self.sel) if self.sel in ids else 0
        if k < self.haut:
            self.haut = k
        if k >= self.haut + visibles:
            self.haut = k - visibles + 1
        y = ly0 + a.px(12)
        dans = self.j.get("plateformes", []) if self.j else []
        for p in PLATEFORMES[self.haut:self.haut + visibles]:
            pid = p["id"]
            etat, lib, col = self._etat(pid)
            x0, x1 = lx0 + a.px(12), lx1 - a.px(12)
            choisi = pid == self.sel
            rrect(self, x0, y, x1, y + RH, a.px(10), fill=mel(T["violet"], T["mag"], 0.10) if choisi else T["tuile"],
                  outline=T["or"] if choisi else mel(T["cyan"], T["bg"], 0.7), width=2 if choisi else 1, tags="r_" + pid)
            pastille(self, x0 + a.px(14), y + a.px(15), a.px(54), p, tags="r_" + pid)
            self.create_text(x0 + a.px(84), y + a.px(26), text=p["nom"], anchor="w", fill=T["text"],
                             font=a.police(18), tags="r_" + pid)
            self.pilule(x0 + a.px(84), y + a.px(44), lib, col, plein=etat == "ok" and col == T["ok"])
            if etat == "encours":
                inst = a.installs[pid]
                bw = a.px(210)
                rrect(self, x0 + a.px(84), y + a.px(72), x0 + a.px(84) + bw, y + a.px(78), a.px(3), fill=T["panel2"], outline="")
                rrect(self, x0 + a.px(84), y + a.px(72), x0 + a.px(84) + bw * inst["pct"] / 100, y + a.px(78), a.px(3),
                      fill=T["cyan"], outline="")
            elif etat == "ok":
                self.create_text(x1 - a.px(200), y + a.px(26), anchor="e", fill=T["cyan"] if pid in dans else T["dim"],
                                 font=a.police(12, True), text="DANS TON PROFIL" if pid in dans else "")
            # boutons de la ligne
            bh = a.px(30)
            boutons = []
            if etat == "absent" or etat == "echec":
                boutons = [("INSTALLER" if etat == "absent" else "RÉESSAYER", lambda q=p: self._installer(q))]
            elif etat == "ok":
                if pid in dans:
                    boutons = [("BIBLIOTHÈQUE", lambda q=pid: self.app.montrer(PageBibliotheque, filtre=q))]
                    if pid != "gog" and pid != "emu":
                        boutons.append(("OUVRIR", lambda q=pid: self.app.ouvrir_launcher(q)))
                else:
                    boutons = [("AJOUTER À MON PROFIL", lambda q=pid: self._ajouter(q))]
            if not boutons:
                self.focusable("l_" + pid, (x0, y, x1, y + RH), lambda q=pid: self.app.montrer(PageTerminal, pid=q),
                               tag="r_" + pid, anneau=False)
            bw = max([a.px(150)] + [a.police(13, True).measure(t) + a.px(26) for t, _ in boutons])
            bx = x1 - a.px(14) - bw
            for n, (txt, act) in enumerate(boutons):
                by = y + a.px(10) + n * (bh + a.px(6)) if len(boutons) > 1 else y + (RH - bh) / 2
                self.bouton_or("%s_%d" % (pid, n), bx, by, bw, bh, txt, act)
            y += RH + G
        if self.haut > 0:
            self.create_text((lx0 + lx1) / 2, ly0 + a.px(6), text="\u25b2", fill=T["or"], font=a.police(10))
        if self.haut + visibles < len(PLATEFORMES):
            self.create_text((lx0 + lx1) / 2, ly1 - a.px(6), text="\u25bc", fill=T["or"], font=a.police(10))
        self._detail(lx1 + a.px(30), ly0, a.W - a.px(60), ly1)

    def _detail(self, x0, y0, x1, y1):
        """Panneau de droite : description, statut, progression et nombre de jeux."""
        a = self.app
        p = PLAT[self.sel]
        self.panneau(x0, y0, x1, y1, lueur=True)
        cx = (x0 + x1) / 2
        pastille(self, cx - a.px(60), y0 + a.px(30), a.px(120), p)
        self.create_text(cx, y0 + a.px(185), text=p["nom"], fill=T["or"], font=a.police(24))
        self.create_line(x0 + a.px(40), y0 + a.px(212), x1 - a.px(40), y0 + a.px(212), fill=mel(T["or"], T["bg"], 0.5))
        self.create_text(cx, y0 + a.px(250), text=DESCRIPTIONS[p["type"]], fill=T["text2"], font=a.police(14),
                         width=x1 - x0 - a.px(60), justify="center")
        etat, lib, col = self._etat(p["id"])
        y = y0 + a.px(320)
        self.create_text(cx, y, text="Statut : " + lib.capitalize(), fill=col, font=a.police(15, True))
        inst = a.installs.get(p["id"])
        if etat == "encours":
            bx0, bx1 = x0 + a.px(40), x1 - a.px(40)
            rrect(self, bx0, y + a.px(26), bx1, y + a.px(44), a.px(9), fill=T["panel2"], outline=mel(T["cyan"], T["bg"], 0.5))
            if inst["pct"]:
                neon(self, bx0, y + a.px(26), bx0 + max(a.px(18), (bx1 - bx0) * inst["pct"] / 100), y + a.px(44),
                     a.px(9), T["cyan"], fill=T["cyan"], halo=2, w=1)
            ecoule = int(time.time() - inst["debut"])
            points = "." * (1 + int(time.time() * 2) % 3)
            self.create_text(cx, y + a.px(70), text=inst["msg"].rstrip(".") + points, fill=T["text"], font=a.police(14))
            self.create_text(cx, y + a.px(96), text="Depuis %d min %02d s. Ne pas éteindre la console." % (ecoule // 60, ecoule % 60),
                             fill=T["dim"], font=a.police(12))
        elif etat == "echec":
            self.create_text(cx, y + a.px(40), text=inst["erreur"], fill=T["text2"], font=a.police(13),
                             width=x1 - x0 - a.px(60), justify="center")
        elif etat == "ok":
            if p["id"] in ("steam", "emu"):
                self.create_text(cx, y + a.px(30), text="Livré avec la console : rien à télécharger.",
                                 fill=T["dim"], font=a.police(12))
            n = self._comptes().get(p["id"], 0)
            self.create_text(cx, y + a.px(56), text="%d %s installé%s" % (n, p["unite"] if n != 1 else p["unite"].rstrip("s"),
                                                                         "s" if n > 1 else ""),
                             fill=T["text2"], font=a.police(14))
        if p["type"] == "deleguee":
            self.pilule(cx, y1 - a.px(46), "COMPATIBILITÉ VARIABLE", T["amber"], anchor="center")

    def sur_focus(self, ancien, nouveau):
        """Selectionne la plateforme dont une ligne ou un bouton vient de prendre le focus."""
        pid = nouveau.split("_")[0] if nouveau and not nouveau.startswith("ico") else None
        if nouveau and nouveau.startswith("l_"):
            pid = nouveau[2:]
        if pid in PLAT and pid != self.sel:
            self.sel = pid
            self.redessiner()
        else:
            self._anneau()

    def focus_defaut(self):
        for fid in self.ordre:
            if fid.startswith(self.sel + "_") or fid == "l_" + self.sel:
                return fid
        return self.ordre[0] if self.ordre else None

    def bord(self, d):
        """Au bord de la liste, change de plateforme selectionnee."""
        ids = [p["id"] for p in PLATEFORMES]
        k = ids.index(self.sel)
        if d in ("bas", "haut"):
            k2 = k + (1 if d == "bas" else -1)
            if 0 <= k2 < len(ids):
                self.sel = ids[k2]
                self.focus_id = None
                self.redessiner()

    def defiler(self, sens):
        self.bord("bas" if sens > 0 else "haut")

    def _installer(self, p):
        demarrer_installation(self.app, p, self.j)
        self.app.montrer(PageTerminal, pid=p["id"])

    def _ajouter(self, pid):
        if pid not in self.j["plateformes"]:
            self.j["plateformes"].append(pid)
            sauver_profils(self.app.profils)
        self.app.jouer_son("valid")
        self.redessiner()

    def action_x(self):
        # retirer du profil (sans desinstaller pour les autres joueurs)
        if self.sel in self.j.get("plateformes", []):
            self.j["plateformes"].remove(self.sel)
            sauver_profils(self.app.profils)
            self.redessiner()

    def retour(self):
        self.app.montrer(PageBibliotheque)

    def aides(self):
        base = [("A", "Choisir")]
        if self.sel in self.j.get("plateformes", []):
            base.append(("X", "Retirer de mon profil"))
        return base + [("B", "Bibliothèque")]

    def _veille(self):
        """Toutes les 700 ms : redessine tant qu'une installation avance ou vient de finir."""
        if not self.winfo_exists():
            return
        a = self.app
        if any(i["etat"] == "encours" for i in a.installs.values()) or \
                any(i["etat"] == "fini" for i in a.installs.values()):
            for pid, i in list(a.installs.items()):
                if i["etat"] == "fini":
                    a.installs.pop(pid, None)
                    a.jouer_son("valid")
            self._compte_t = 0
            self.redessiner()
        self.after(700, self._veille)


# ===========================================================================
# Bibliotheque unifiee : filtres, recherche, tri, jaquettes, fiche du jeu
# ===========================================================================
TRIS = [("titre", "TITRE"), ("recents", "RÉCENTS"), ("temps", "TEMPS DE JEU")]


class PageBibliotheque(PageBase):
    """Bibliotheque unifiee : filtres, recherche, tri, jaquettes, fiche du jeu."""
    titre = "BIBLIOTHÈQUE"

    def __init__(self, parent, app, filtre=None):
        """Charge les jeux du profil et complete les jaquettes Steam en arriere-plan."""
        super().__init__(parent, app)
        self.j = app.joueur_actif
        self.filtre = filtre or self.j.get("filtre", "tous")
        self.tri = self.j.get("tri", "titre")
        self.haut = 0
        self.fhaut = 0
        self.lancement = {}
        self.var_recherche = tk.StringVar()
        self.var_recherche.trace_add("write", lambda *x: self._planifier_filtre())
        self.recherche = tk.Entry(self, textvariable=self.var_recherche, font=app.police(14), bg=T["violet"], fg=T["text"], insertbackground=T["or"],
                                  relief="flat", bd=0, width=18, highlightthickness=1,
                                  highlightbackground=mel(T["cyan"], T["bg"], 0.5), highlightcolor=T["or"])
        self.recherche.nom_champ = "Rechercher un jeu"
        self.recherche.bind("<Return>", lambda e: (self.focus_set(), self._premier_jeu()))
        self._tous = []
        self._charger()
        self.focus_id = "j0" if self.liste else "f_" + self.filtre
        self.redessiner()
        self.after(5000, self._veille)
        if not DEMO and "steam" in self.j.get("plateformes", []):
            self._completer_infos_steam()

    # ----- donnees -----
    def _charger(self):
        """Relit les jeux de chaque plateforme du profil."""
        jeux = []
        for pid in self.j.get("plateformes", []):
            if pid in PLAT and plateforme_presente(pid):
                jeux += jeux_de(pid)
        self._tous = jeux
        self._sig = tuple((g["id"], g["etat"], g["progression"]) for g in jeux)
        self._filtrer()

    def _stats(self, jeu):
        return self.j.setdefault("jeux", {}).get(jeu["id"], {})

    def _filtrer(self):
        """Applique filtre, recherche et tri a la liste affichee."""
        f = self.filtre
        liste = list(self._tous)
        if f == "recents":
            liste = [g for g in liste if self._stats(g).get("derniere")]
        elif f == "favoris":
            liste = [g for g in liste if self._stats(g).get("favori")]
        elif f in PLAT:
            liste = [g for g in liste if g["plateforme"] == f]
        q = self.recherche.get().strip().lower() if hasattr(self, "recherche") else ""
        if q:
            liste = [g for g in liste if q in g["titre"].lower()]
        if f == "recents" or self.tri == "recents":
            liste.sort(key=lambda g: -(self._stats(g).get("derniere") or 0))
        elif self.tri == "temps":
            liste.sort(key=lambda g: -(self._stats(g).get("temps") or 0))
        else:
            liste.sort(key=lambda g: g["titre"].lower())
        self.liste = liste

    def _planifier_filtre(self):
        if getattr(self, "_filtre_prevu", None):
            self.after_cancel(self._filtre_prevu)
        self._filtre_prevu = self.after(250, self._rafraichir_liste)

    def _rafraichir_liste(self):
        self._filtre_prevu = None
        self._filtrer()
        self.haut = 0
        self.redessiner()

    def filtres(self):
        """Filtres proposes : tous, recents, favoris, une entree par plateforme du profil, gerer."""
        f = [("tous", "TOUS LES JEUX", "manette"), ("recents", "RÉCEMMENT JOUÉS", "horloge"),
             ("favoris", "FAVORIS", "etoile")]
        for pid in self.j.get("plateformes", []):
            if pid in PLAT:
                f.append((pid, PLAT[pid]["nom"].upper(), None))
        f.append(("gerer", "AJOUTER / GÉRER", "plus"))
        return f

    # ----- dessin -----
    def _geo(self):
        """Geometrie de la grille : zone, taille des tuiles, colonnes et lignes visibles."""
        a = self.app
        gx0, gy0 = a.px(60) + a.px(310) + a.px(34), a.px(150)
        gx1, gy1 = a.W - a.px(60), a.H - a.px(78)
        TW, TH, G = a.px(160), a.px(208), a.px(18)
        ncol = max(1, (gx1 - gx0 + G) // (TW + G))
        nrow = max(1, (gy1 - gy0 + G) // (TH + G))
        return gx0, gy0, gx1, gy1, TW, TH, G, ncol, nrow

    def dessiner(self):
        self._colonne()
        self._grille()

    def _colonne(self):
        """Colonne de filtres a gauche (avec defilement quand elle ne tient pas)."""
        a = self.app
        x0, y0, x1, y1 = a.px(60), a.px(100), a.px(60) + a.px(310), a.H - a.px(78)
        self.panneau(x0, y0, x1, y1)
        self.create_text(x0 + a.px(18), y0 + a.px(24), text="FILTRES", anchor="w", fill=T["or"], font=a.police(13, True))
        IH, G = a.px(50), a.px(8)
        items = self.filtres()
        visibles = max(1, (y1 - y0 - a.px(56) + G) // (IH + G))
        fid = self.focus_id or ""
        if fid.startswith("f_"):
            k = [i[0] for i in items].index(fid[2:]) if fid[2:] in [i[0] for i in items] else 0
            if k < self.fhaut:
                self.fhaut = k
            if k >= self.fhaut + visibles:
                self.fhaut = k - visibles + 1
        y = y0 + a.px(46)
        for cle, lib, ico in items[self.fhaut:self.fhaut + visibles]:
            tag = "tf_" + cle
            actif = cle == self.filtre
            rrect(self, x0 + a.px(12), y, x1 - a.px(12), y + IH, a.px(8),
                  fill=mel(T["violet"], T["mag"], 0.12) if actif else T["tuile"],
                  outline=T["or"] if actif else mel(T["cyan"], T["bg"], 0.75), width=2 if actif else 1, tags=tag)
            if ico:
                ICONES[ico](self, x0 + a.px(38), y + IH / 2, a.px(26), T["or"] if actif else T["cyan"], tags=tag)
            else:
                pastille(self, x0 + a.px(24), y + a.px(10), IH - a.px(20), PLAT[cle], tags=tag)
            self.create_text(x0 + a.px(62), y + IH / 2, text=tronquer(lib, a.police(14), a.px(200)), anchor="w",
                             fill=T["or"] if actif else T["text"], font=a.police(14), tags=tag)
            if cle in PLAT:
                n = len([g for g in self._tous if g["plateforme"] == cle])
                self.create_text(x1 - a.px(24), y + IH / 2, text=str(n), anchor="e", fill=T["dim"], font=a.police(12), tags=tag)
            act = (lambda: self.app.montrer(PagePlateformes)) if cle == "gerer" else (lambda c=cle: self._choisir_filtre(c))
            self.focusable("f_" + cle, (x0 + a.px(12), y, x1 - a.px(12), y + IH), act, tag=tag)
            y += IH + G

    def _entete_grille(self):
        """Titre de la liste, tri et champ de recherche."""
        a = self.app
        gx0, gy0, gx1 = self._geo()[:3]
        lib = dict((c, l) for c, l, i in self.filtres()).get(self.filtre, "")
        self.create_text(gx0, a.px(118), text="%s  ·  %d" % (lib, len(self.liste)), anchor="w", fill=T["dim"], font=a.police(13, True))
        # recherche
        rw = a.px(250)
        rx = gx1 - rw
        ico_loupe(self, rx - a.px(18), a.px(118), a.px(22), T["cyan"])
        self.create_window(rx, a.px(118), window=self.recherche, anchor="w", width=rw, height=a.px(34))
        self.focusable("recherche", (rx, a.px(101), gx1, a.px(135)), self._ouvrir_recherche, anneau=True)
        # tri
        tlib = "TRI : " + dict(TRIS)[self.tri]
        tw = a.police(12, True).measure(tlib) + a.px(44)
        tx = rx - a.px(40) - tw
        rrect(self, tx, a.px(101), tx + tw, a.px(135), a.px(6), fill=T["violet"], outline=mel(T["cyan"], T["bg"], 0.5), tags="tri")
        ico_tri(self, tx + a.px(18), a.px(118), a.px(20), T["cyan"], tags="tri")
        self.create_text(tx + a.px(32), a.px(118), text=tlib, anchor="w", fill=T["text"], font=a.police(12, True), tags="tri")
        self.focusable("tri", (tx, a.px(101), tx + tw, a.px(135)), self._changer_tri, tag="tri")

    def _grille(self):
        """Grille de jaquettes, ou le message adapte quand il n'y a rien a montrer."""
        a = self.app
        gx0, gy0, gx1, gy1, TW, TH, G, ncol, nrow = self._geo()
        self._entete_grille()
        if not self.j.get("plateformes"):
            self._vide("Ajoute ta première plateforme", "Steam, GOG, Epic, EA... Tes jeux installés apparaîtront ici.",
                       "AJOUTER UNE PLATEFORME", lambda: a.montrer(PagePlateformes))
            return
        if not self.liste:
            txt = {"favoris": "Aucun favori pour l'instant. Appuie sur X sur un jeu pour l'ajouter.",
                   "recents": "Aucune partie jouée pour l'instant."}.get(self.filtre, "Aucun jeu installé ici pour l'instant.")
            if self.var_recherche.get().strip():
                self._vide("Aucun résultat", "Aucun jeu ne correspond à « %s »." % self.var_recherche.get().strip(), None, None)
                return
            if self.filtre == "gog":
                self._vide("Aucun jeu GOG pour l'instant",
                           "GOG n'a pas de launcher sous Linux : dépose les installateurs achetés sur gog.com "
                           "dans le dossier Jeux/GOG de la console, ils apparaîtront ici tout seuls.", None, None)
                return
            if self.filtre == "emu":
                self._vide("Aucune ROM pour l'instant",
                           "Dépose tes fichiers de jeux dans le dossier Jeux/ROMs de la console : Omni reconnaît "
                           "la console d'origine à l'extension et les affiche ici.", None, None)
                return
            if self.filtre in PLAT and self.filtre not in ("gog", "emu"):
                self._vide("Rien à afficher", txt + " Ouvre le launcher pour en installer.", "OUVRIR " + PLAT[self.filtre]["nom"].upper(),
                           lambda: a.ouvrir_launcher(self.filtre))
            else:
                self._vide("Rien à afficher", txt, None, None)
            return
        fid = self.focus_id or ""
        if fid.startswith("j"):
            k = int(fid[1:])
            row = k // ncol
            if row < self.haut:
                self.haut = row
            if row >= self.haut + nrow:
                self.haut = row - nrow + 1
        debut = self.haut * ncol
        focus_jeu = None
        for k in range(debut, min(len(self.liste), debut + ncol * nrow)):
            jeu = self.liste[k]
            x = gx0 + (k % ncol) * (TW + G)
            y = gy0 + (k // ncol - self.haut) * (TH + G)
            tag = "tj%d" % k
            img = self.img(jaquette_image(jeu, TW, TH, self._fichier_jaquette(jeu)))
            rrect(self, x - 1, y - 1, x + TW + 1, y + TH + 1, a.px(8), fill=T["tuile"], outline=mel(T["cyan"], T["bg"], 0.55), tags=tag)
            if img:
                self.create_image(x, y, image=img, anchor="nw", tags=tag)
            pastille(self, x + a.px(8), y + a.px(8), a.px(28), PLAT[jeu["plateforme"]], tags=tag)
            if self._stats(jeu).get("favori"):
                ico_etoile(self, x + TW - a.px(20), y + a.px(22), a.px(24), T["or"], tags=tag)
            if jeu["etat"] == "telechargement":
                self.create_rectangle(x, y + TH - a.px(40), x + TW, y + TH, fill=T["bg"], outline="", stipple="gray50", tags=tag)
                rrect(self, x + a.px(10), y + TH - a.px(20), x + TW - a.px(10), y + TH - a.px(12), a.px(3), fill=T["panel2"], outline="", tags=tag)
                if jeu["progression"]:
                    rrect(self, x + a.px(10), y + TH - a.px(20), x + a.px(10) + (TW - a.px(20)) * jeu["progression"] / 100,
                          y + TH - a.px(12), a.px(3), fill=T["cyan"], outline="", tags=tag)
                self.create_text(x + TW / 2, y + TH - a.px(30), text="TÉLÉCHARGEMENT %d %%" % jeu["progression"],
                                 fill=T["cyan"], font=a.police(10, True), tags=tag)
            elif not jeu.get("jaquette") and not self._fichier_jaquette(jeu):
                self.create_rectangle(x, y + TH - a.px(46), x + TW, y + TH, fill=T["bg"], outline="", stipple="gray50", tags=tag)
                self.create_text(x + a.px(10), y + TH - a.px(24), text=tronquer(jeu["titre"], a.police(13, True), TW - a.px(20)),
                                 anchor="w", fill=T["text"], font=a.police(13, True), tags=tag)
            self.focusable("j%d" % k, (x, y, x + TW, y + TH), lambda g=jeu: self.lancer(g), tag=tag)
            if fid == "j%d" % k:
                focus_jeu = (jeu, x, y)
        if self.haut > 0:
            self.create_text((gx0 + gx1) / 2, gy0 - a.px(8), text="\u25b2", fill=T["or"], font=a.police(10))
        if (self.haut + nrow) * ncol < len(self.liste):
            self.create_text((gx0 + gx1) / 2, gy1 + a.px(6), text="\u25bc", fill=T["or"], font=a.police(10))
        if focus_jeu:
            self._fiche(*focus_jeu)

    def _fiche(self, jeu, tx, ty):
        """Fiche du jeu sous la tuile qui a le focus : temps de jeu, derniere session, lancer, favori."""
        a = self.app
        gx0, gy0, gx1, gy1, TW, TH, G, ncol, nrow = self._geo()
        FW, FH = a.px(250), a.px(270)
        fx = min(max(tx, gx0), gx1 - FW)
        fy = ty + TH + a.px(14)
        if fy + FH > a.H - a.px(60):
            fy = ty - FH - a.px(14)
        if fy < a.px(95):
            # pas la place dessus ni dessous : a cote
            fy = min(ty, a.H - a.px(60) - FH)
            fx = tx + TW + a.px(14) if tx + TW + a.px(14) + FW < a.W - a.px(20) else tx - FW - a.px(14)
        neon(self, fx, fy, fx + FW, fy + FH, a.px(10), T["or"], fill=T["violet"], halo=2, w=2, tags="fiche")
        st = self._stats(jeu)
        champs = [("TITRE", jeu["titre"]), ("PLATEFORME", PLAT[jeu["plateforme"]]["nom"]),
                  ("TEMPS DE JEU", duree_lisible(st.get("temps"))), ("DERNIÈRE SESSION", quand_lisible(st.get("derniere")))]
        y = fy + a.px(16)
        for lib, val in champs:
            self.create_text(fx + a.px(16), y, text=lib, anchor="nw", fill=T["or"], font=a.police(11, True), tags="fiche")
            self.create_text(fx + a.px(16), y + a.px(16), text=tronquer(val, a.police(14), FW - a.px(32)), anchor="nw",
                             fill=T["text"], font=a.police(14), tags="fiche")
            y += a.px(44)
        lance = self.lancement.get(jeu["id"], 0) > time.time()
        bw = FW - a.px(32)
        for n, (txt, bouton, act) in enumerate([("LANCEMENT..." if lance else "LANCER", "A", lambda: self.lancer(jeu)),
                                                ("RETIRER DES FAVORIS" if st.get("favori") else "AJOUTER AUX FAVORIS", "X",
                                                 lambda: self._favori(jeu))]):
            by = fy + FH - a.px(78) + n * a.px(38)
            t = "fb%d" % n
            rrect(self, fx + a.px(16), by, fx + a.px(16) + bw, by + a.px(30), a.px(6),
                  fill=T["or"] if (n == 0 and lance) else T["violet"], outline=T["or"], width=1, tags=("fiche", t))
            self.create_text(fx + a.px(16) + bw / 2 - a.px(10), by + a.px(15), text=txt,
                             fill=T["bg"] if (n == 0 and lance) else T["or"], font=a.police(12, True), tags=("fiche", t))
            lettre, col = AIDES_MARQUE.get(a.marque_manette(), AIDES_MARQUE["xbox"])[bouton]
            self.create_oval(fx + bw - a.px(4), by + a.px(5), fx + bw + a.px(16), by + a.px(25), outline=col, width=1, tags=("fiche", t))
            self.create_text(fx + bw + a.px(6), by + a.px(15), text=lettre, fill=col, font=a.police(10, True), tags=("fiche", t))
            self.tag_bind(t, "<Button-1>", lambda e, f=act: f())

    def _vide(self, titre, texte, lib, cmd):
        """Message d'accueil quand la liste est vide, avec un bouton d'action si utile."""
        a = self.app
        gx0, gy0, gx1, gy1 = self._geo()[:4]
        cx = (gx0 + gx1) / 2
        self.create_text(cx, gy0 + a.px(120), text=titre, fill=T["text"], font=a.police(24))
        self.create_text(cx, gy0 + a.px(165), text=texte, fill=T["dim"], font=a.police(15), width=gx1 - gx0 - a.px(80),
                         justify="center")
        if lib:
            w = a.police(14, True).measure(lib) + a.px(60)
            self.bouton_or("vide", cx - w / 2, gy0 + a.px(215), w, a.px(46), lib, cmd, plein=True)

    def _fichier_jaquette(self, jeu):
        if jeu["plateforme"] != "steam" or DEMO:
            return jeu.get("jaquette")
        c = os.path.join(CACHE_DIR, self.j.get("id", "x"), "steam_%s.jpg" % jeu["lancement"].get("appid", ""))
        return jeu.get("jaquette") or (c if os.path.isfile(c) else None)

    # ----- navigation -----
    def focus_defaut(self):
        if self.liste:
            return "j%d" % (self.haut * self._geo()[7])
        return "f_" + self.filtre if ("f_" + self.filtre) in self.foc else (self.ordre[0] if self.ordre else None)

    def sur_focus(self, ancien, nouveau):
        if (ancien or "").startswith(("j", "f_")) or (nouveau or "").startswith(("j", "f_")):
            self.redessiner()
        else:
            self._anneau()

    def nav_speciale(self, d):
        """Navigation entre colonne de filtres, tuiles, tri et recherche."""
        fid = self.focus_id or ""
        ncol = self._geo()[7]
        n = len(self.liste)
        if fid.startswith("j"):
            k = int(fid[1:])
            if d == "droite" and k % ncol < ncol - 1 and k + 1 < n:
                self.focaliser("j%d" % (k + 1))
            elif d == "gauche":
                if k % ncol > 0:
                    self.focaliser("j%d" % (k - 1))
                else:
                    self._vers_filtre()
            elif d == "bas":
                if k + ncol < n:
                    self._aller_jeu(k + ncol)
                elif k // ncol < (n - 1) // ncol:
                    self._aller_jeu(n - 1)
            elif d == "haut":
                if k >= ncol:
                    self._aller_jeu(k - ncol)
                else:
                    self.focaliser("tri")
            return True
        if fid.startswith("f_") and d == "droite":
            self._premier_jeu()
            return True
        if fid.startswith("f_") and d in ("haut", "bas"):
            items = [i[0] for i in self.filtres()]
            k = items.index(fid[2:]) + (1 if d == "bas" else -1)
            if 0 <= k < len(items):
                self.focus_id = "f_" + items[k]
                self.app.jouer_son("hover")
                self.redessiner()
            elif d == "haut":
                self.focaliser(self.ordre[-1] if self.ordre else fid)
            return True
        if fid in ("tri", "recherche") and d == "bas":
            self._premier_jeu()
            return True
        return False

    def _aller_jeu(self, k):
        self.focus_id = "j%d" % k
        self.app.jouer_son("hover")
        self.redessiner()

    def _premier_jeu(self):
        if self.liste:
            self._aller_jeu(self.haut * self._geo()[7])

    def _vers_filtre(self):
        self.focus_id = "f_" + self.filtre
        self.app.jouer_son("hover")
        self.redessiner()

    def defiler(self, sens):
        """Fait defiler la grille d'une ligne."""
        ncol, nrow = self._geo()[7], self._geo()[8]
        maxh = max(0, (len(self.liste) - 1) // ncol - nrow + 1)
        self.haut = max(0, min(maxh, self.haut + sens))
        if (self.focus_id or "").startswith("j"):
            k = int(self.focus_id[1:])
            row = k // ncol
            if row < self.haut or row >= self.haut + nrow:
                self.focus_id = "j%d" % min(len(self.liste) - 1, self.haut * ncol + k % ncol)
        self.redessiner()

    def _choisir_filtre(self, cle):
        """Active un filtre et le retient dans le profil."""
        self.filtre = cle
        self.j["filtre"] = cle
        sauver_profils(self.app.profils)
        self._filtrer()
        self.haut = 0
        self.focus_id = "j0" if self.liste else "f_" + cle
        self.redessiner()

    def onglet(self, sens):
        items = [i[0] for i in self.filtres() if i[0] != "gerer"]
        k = (items.index(self.filtre) + sens) % len(items) if self.filtre in items else 0
        self._choisir_filtre(items[k])

    def _changer_tri(self):
        cles = [t[0] for t in TRIS]
        self.tri = cles[(cles.index(self.tri) + 1) % len(cles)]
        self.j["tri"] = self.tri
        sauver_profils(self.app.profils)
        self._filtrer()
        self.redessiner()

    def _ouvrir_recherche(self):
        self.recherche.focus_set()
        self.app.cible_saisie = self.recherche
        if self.app._clavier is None:
            self.app.toggle_clavier()

    def action_x(self):
        fid = self.focus_id or ""
        if fid.startswith("j"):
            self._favori(self.liste[int(fid[1:])])
        elif fid.startswith("f_") and fid[2:] in PLAT:
            self.app.ouvrir_launcher(fid[2:])

    def action_y(self):
        self._vers_filtre()

    def retour(self):
        if (self.focus_id or "").startswith("j"):
            self._vers_filtre()
        else:
            self.app.montrer(PageSelection)

    def aides(self):
        fid = self.focus_id or ""
        if fid.startswith("j"):
            return [("Y", "Filtres"), ("X", "Favori"), ("A", "Jouer")]
        if fid.startswith("f_") and fid[2:] in PLAT and fid[2:] not in ("gog", "emu"):
            return [("A", "Filtrer"), ("X", "Ouvrir le launcher"), ("B", "Changer de joueur")]
        return [("A", "Choisir"), ("B", "Changer de joueur")]

    # ----- actions -----
    def _favori(self, jeu):
        """Ajoute ou retire un jeu des favoris du profil."""
        st = self.j.setdefault("jeux", {}).setdefault(jeu["id"], {})
        st["favori"] = not st.get("favori")
        sauver_profils(self.app.profils)
        self.app.jouer_son("select")
        if self.filtre == "favoris":
            self._filtrer()
        self.redessiner()

    def lancer(self, jeu):
        """Lance un jeu (une fois toutes les 8 s), demarre son suivi et efface Omni derriere lui."""
        a = self.app
        if jeu["etat"] != "installe" or self.lancement.get(jeu["id"], 0) > time.time():
            return
        a.jouer_son("valid")
        self.lancement[jeu["id"]] = time.time() + 8
        self.redessiner()
        proc = lancer_jeu(jeu)
        a.suivi.demarrer(jeu, self.j, proc)
        if not DEMO:
            a.passer_derriere()
        self.after(8200, lambda: self.winfo_exists() and self.redessiner())

    def _veille(self):
        """Toutes les 5 s : recharge la liste si un jeu est apparu ou a change d'etat."""
        if not self.winfo_exists():
            return
        ancien = self._sig
        jeux = []
        for pid in self.j.get("plateformes", []):
            if pid in PLAT and plateforme_presente(pid):
                jeux += jeux_de(pid)
        if tuple((g["id"], g["etat"], g["progression"]) for g in jeux) != ancien:
            self._charger()
            self.redessiner()
        self.after(5000, self._veille)

    def _completer_infos_steam(self):
        """Telecharge en arriere-plan les jaquettes Steam manquantes."""
        cache = os.path.join(CACHE_DIR, self.j.get("id", "x"))
        manquants = [g["lancement"]["appid"] for g in self._tous if g["plateforme"] == "steam"
                     and not os.path.isfile(os.path.join(cache, "steam_%s.jpg" % g["lancement"]["appid"]))]
        if not manquants:
            return
        fini = []

        def travail():
            for appid in manquants:
                steam_infos_distantes(appid, cache)
            fini.append(1)
        threading.Thread(target=travail, daemon=True).start()

        def attendre():
            """Attend la fin du telechargement des jaquettes, puis redessine."""
            if not self.winfo_exists():
                return
            if fini:
                _cache_img.clear()
                self.redessiner()
            else:
                self.after(800, attendre)
        self.after(800, attendre)


# ===========================================================================
# Reglages : panneau sobre (fond uni, cahier des charges), pilotable manette
# ===========================================================================
class PageReglages(PageBase):
    """Menu des reglages : une tuile par rubrique, « Bientot » pour celles pas encore faites."""
    titre = "RÉGLAGES"

    def _fond(self):
        a = self.app
        self.configure(bg=T["bg"])
        self.create_text(a.W / 2, a.px(50), text=self.titre, fill=T["text"], font=a.police(29))

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.redessiner()

    def dessiner(self):
        """Dessine les tuiles de rubriques en grille."""
        a = self.app
        rubriques = [
            ("Réseau", "Wi-Fi et câble", "wifi", PageReseau),
            ("Affichage", "Résolution de l'écran", "ecran", PageAffichage),
            ("Audio", "Sortie du son", "son", PageAudio),
            ("Stockage", "Place disponible", "disque", PageStockage),
            ("Accessibilité", "Taille, couleurs, contraste", "acces", PageAccessibilite),
            ("Plateformes", "Installer, ajouter, retirer", "manette", PagePlateformes),
            ("Bluetooth", "Manettes, Joy-Con, casques", "bluetooth", None),
            ("Veille", "Test de mise en veille", "lune", None),
            ("Contrôle parental", "Âge et temps de jeu", "bouclier", None),
            ("Système", "Mises à jour automatiques", "reglages", None),
            ("Alimentation", "Éteindre ou redémarrer", "alim", a.ouvrir_menu_alim),
        ]
        W, H, G = a.px(270), a.px(118), a.px(22)
        ncol = max(2, min(5, (a.W - a.px(100) + G) // (W + G)))
        total = ncol * (W + G) - G
        x0 = (a.W - total) / 2
        for i, (titre, desc, ico, page) in enumerate(rubriques):
            x = x0 + (i % ncol) * (W + G)
            y = a.px(110) + (i // ncol) * (H + G)
            t = "rg%d" % i
            col = T["cyan"] if page else mel(T["dim"], T["bg"], 0.3)
            rrect(self, x, y, x + W, y + H, a.px(10), fill=T["tuile"], outline=col, width=2 if page else 1, tags=t)
            ICONES[ico](self, x + a.px(38), y + a.px(40), a.px(34), col, tags=t)
            self.create_text(x + a.px(70), y + a.px(40), text=titre, anchor="w", fill=T["text"] if page else T["dim"],
                             font=a.police(16, True), tags=t)
            self.create_text(x + a.px(20), y + a.px(84), text=desc, anchor="w", fill=T["dim"], font=a.police(12), tags=t)
            if not page:
                self.pilule(x + W - a.px(88), y + a.px(12), "BIENTÔT", T["dim"])
            self.focusable(t, (x, y, x + W, y + H), (lambda pg=page: a.montrer(pg) if isinstance(pg, type) else pg()) if page else None, tag=t)

    def retour(self):
        self.app.retour_reglages()


# ===========================================================================
# Menu rapide (bouton Guide) : par-dessus tout, meme pendant un jeu
# ===========================================================================
class MenuRapide(tk.Toplevel):
    """Menu lateral du bouton Guide, par-dessus tout, meme pendant un jeu."""
    def __init__(self, app):
        """Construit la liste d'entrees selon le contexte (jeu en cours, launcher ouvert)."""
        super().__init__(app)
        self.app = a = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        W, H = a.px(420), a.H
        self.geometry("%dx%d+0+0" % (W, H))
        self.cv = tk.Canvas(self, width=W, height=H, bg=T["violet"], highlightthickness=0)
        self.cv.pack()
        self.entrees = []
        self.alim = False                       # True : sous-menu Eteindre / Redemarrer
        self._construire()
        self.pos = 0
        self._dessiner()
        self.focus_force()

    def _construire(self):
        """Remplit la liste d'entrees : menu principal, ou sous-menu d'alimentation."""
        app = self.app
        if self.alim:
            self.entrees = [("Éteindre la console", "alim", lambda: self._alimentation("eteindre")),
                            ("Redémarrer", "redem", lambda: self._alimentation("redemarrer")),
                            ("Annuler", "retour", self._fin_alim)]
            return
        self.entrees = []
        if app.suivi.sessions:
            self.entrees.append(("Quitter le jeu", "fermer", self._quitter_jeu))
        elif not DEMO and any(_run(["pgrep", "-x", n], timeout=3) is not None
                              and _run(["pgrep", "-x", n], timeout=3).returncode == 0
                              for n in ("steam", "umu-run", "wine")):
            self.entrees.append(("Fermer le launcher", "fermer", self._fermer_launcher))
        self.entrees += [("Bibliothèque", "manette", self._bibli), ("Changer de joueur", "joueurs", self._joueurs),
                        ("Réglages", "reglages", self._reglages), ("Clavier", "clavier", self._clavier),
                        ("Accessibilité", "acces", self._acces), ("Éteindre", "alim", self._ouvrir_alim)]

    def _ouvrir_alim(self):
        """Passe au sous-menu d'alimentation (evite un arret par megarde)."""
        self.alim, self.pos = True, 0
        self._construire()
        self._dessiner()

    def _fin_alim(self):
        """Revient au menu principal, selection sur « Éteindre »."""
        self.alim = False
        self._construire()
        self.pos = len(self.entrees) - 1
        self._dessiner()

    def _alimentation(self, intention):
        """Demande l'arret ou le redemarrage au guichet (root), puis affiche l'attente."""
        cv, a = self.cv, self.app
        cv.delete("all")
        cv.create_text(a.px(30), a.H / 2, anchor="w", fill=T["text"], font=a.police(18),
                       text="Extinction en cours..." if intention == "eteindre" else "Redémarrage en cours...")
        cv.update_idletasks()
        if DEMO:
            return
        r = _run(["sudo", "-n", SERVICE_INSTALL, intention], timeout=30)
        if r is None or r.returncode != 0:
            # sans guichet (systeme de test), repli direct : fonctionne si la session a les droits
            _run(["systemctl", "poweroff" if intention == "eteindre" else "reboot"], timeout=30)

    def _dessiner(self):
        """Dessine les entrees et la selection."""
        a, cv = self.app, self.cv
        cv.delete("all")
        W = int(cv["width"])
        cv.create_line(W - 2, 0, W - 2, a.H, fill=T["or"], width=3)
        soleil(cv, a.px(30), a.px(30), a.px(36), a.px(30))
        cv.create_text(a.px(80), a.px(45), text="OMNI", anchor="w", fill=T["mag"], font=a.police(20, True))
        j = a.joueur_actif
        if j:
            cv.create_text(a.px(30), a.px(95), text="Joueur : " + j["nom"], anchor="w", fill=T["text2"], font=a.police(14))
        y = a.px(140)
        for i, (lib, ico, act) in enumerate(self.entrees):
            t = "m%d" % i
            sel = i == self.pos
            if sel:
                neon(cv, a.px(20), y, W - a.px(24), y + a.px(58), a.px(10), T["or"], fill=mel(T["violet"], T["mag"], 0.12), halo=2, tags=t)
            else:
                rrect(cv, a.px(20), y, W - a.px(24), y + a.px(58), a.px(10), fill=T["tuile"], outline="", tags=t)
            ICONES[ico](cv, a.px(52), y + a.px(29), a.px(28), T["or"] if sel else T["cyan"], tags=t)
            cv.create_text(a.px(84), y + a.px(29), text=lib, anchor="w", fill=T["text"], font=a.police(17), tags=t)
            cv.tag_bind(t, "<Enter>", lambda e, k=i: self._aller(k))
            cv.tag_bind(t, "<Button-1>", lambda e, k=i: (self._aller(k), self.commande("A")))
            y += a.px(70)
        cv.create_text(a.px(30), a.H - a.px(40), text="Guide ou B pour fermer", anchor="w", fill=T["dim"], font=a.police(13))

    def _aller(self, k):
        if k != self.pos:
            self.pos = k
            self._dessiner()

    def commande(self, c):
        """Navigation haut/bas, A valide, B ou Guide ferment."""
        if c in ("haut", "bas"):
            self._aller((self.pos + (1 if c == "bas" else -1)) % len(self.entrees))
            self.app.jouer_son("hover")
        elif c == "A":
            self.app.jouer_son("select")
            self.entrees[self.pos][2]()
        elif c in ("B", "GUIDE"):
            if self.alim and c == "B":
                self._fin_alim()
            else:
                self.app.fermer_menu()

    def _retour_omni(self):
        self.app.fermer_menu()
        self.app.revenir()

    def _fermer_launcher(self):
        """Sortie de secours : un launcher reste devant sans repondre."""
        arreter_steam()
        for pid in LAUNCHERS:
            fermer_launcher(pid)
        self._retour_omni()

    def _quitter_jeu(self):
        """Ferme le jeu en cours et son launcher, puis ramene a la bibliotheque."""
        for sess in list(self.app.suivi.sessions):
            p = sess["proc"]
            try:
                if hasattr(p, "terminate"):
                    p.terminate()
            except Exception:
                pass
            fermer_launcher(sess["jeu"]["plateforme"])
        self._bibli()

    def _bibli(self):
        self._retour_omni()
        if self.app.joueur_actif:
            self.app.montrer(PageBibliotheque)

    def _joueurs(self):
        self._retour_omni()
        self.app.montrer(PageSelection)

    def _reglages(self):
        self._retour_omni()
        self.app.montrer(PageReglages)

    def _clavier(self):
        self._retour_omni()
        self.app.toggle_clavier()

    def _acces(self):
        self._retour_omni()
        self.app.toggle_acces()


# ===========================================================================
# Journal d'installation : un faux terminal aux couleurs d'Omni, qui ne montre
# que des etapes compréhensibles (jamais la sortie brute des outils Linux).
# ===========================================================================
class PageTerminal(PageBase):
    """Journal d'installation facon terminal : etapes comprehensibles, jamais la sortie brute d'un outil (sauf a la demande)."""
    def __init__(self, parent, app, pid="steam", premiere=False):
        """Prepare la page pour la plateforme `pid` ; premiere=True pour la premiere ouverture d'un launcher."""
        super().__init__(parent, app)
        self.pid = pid
        self.brut = False
        self.premiere = premiere
        self._fini_vu = False
        inst = app.installs.get(pid)
        self.titre = (inst or {}).get("titre", "Installation de " + PLAT[pid]["nom"]).upper()
        self.redessiner()
        self.after(400, self._tic)

    def dessiner(self):
        """Dessine la fenetre de journal puis le pied (barre, resultat, boutons)."""
        a = self.app
        inst = a.installs.get(self.pid)
        x0, y0, x1, y1 = a.px(110), a.px(100), a.W - a.px(110), a.H - a.px(200)
        neon(self, x0, y0, x1, y1, a.px(10), mel(T["cyan"], T["bg"], 0.3), fill="#07010f", halo=2, w=2)
        # barre de titre facon terminal
        self.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y0 + a.px(34), fill=T["violet"], outline="")
        for k, c in enumerate((T["mag"], T["or"], T["cyan"])):
            r = a.px(6)
            cx = x0 + a.px(20) + k * a.px(20)
            self.create_oval(cx - r, y0 + a.px(18) - r, cx + r, y0 + a.px(18) + r, fill=c, outline="")
        depart = time.strftime("%H:%M", time.localtime(inst["debut"])) if inst else ""
        self.create_text((x0 + x1) / 2, y0 + a.px(18), fill=T["dim"], font=a.police_mono(12),
                         text="omni %s · journal · %s%s" % (OMNI_VERSION, PLAT[self.pid]["nom"].lower(),
                                                            "  ·  démarré à " + depart if depart else ""))
        if inst is None:
            self.create_text(x0 + a.px(24), y0 + a.px(60), anchor="w", fill=T["dim"], font=a.police_mono(15),
                             text="$ aucune installation en cours pour " + PLAT[self.pid]["nom"])
            self.bouton_or("retour", a.W / 2 - a.px(90), a.H - a.px(150), a.px(180), a.px(44), "RETOUR", self.retour)
            return
        if self.brut:
            self._journal_brut(x0, y0, x1, y1)
        else:
            self._journal_omni(x0, y0, x1, y1, inst)
        self._pied(inst, y1)

    def _journal_brut(self, x0, y0, x1, y1):
        """La sortie telle quelle du programme, pour comprendre un echec."""
        a = self.app
        f = a.police_mono(12)
        lh = f.metrics("linespace") + a.px(3)
        places = max(1, int((y1 - y0 - a.px(60)) // lh))
        lignes = ["(pas de journal : l'échec est survenu avant le lancement du programme,",
                  " la raison est dans le résumé)"]
        recent = None
        for nom in ("%s.log" % self.pid, "%s-install.log" % self.pid):
            chemin = os.path.join(DOSSIER_JOURNAUX, nom)
            if os.path.isfile(chemin) and (recent is None or os.path.getmtime(chemin) > os.path.getmtime(recent)):
                recent = chemin
        if recent:
            try:
                with open(recent, errors="replace") as fh:
                    lignes = [l.rstrip() for l in fh.read().split("\n") if l.strip()][-places:]
            except Exception:
                lignes = ["(journal illisible)"]
            if len(lignes) <= 1:
                lignes += ["", "Le programme n'a rien écrit dans ce journal.",
                           "Cela arrive quand il s'arrête avant de démarrer vraiment,",
                           "ou quand le système lui refuse une autorisation.",
                           "Le résumé, au-dessus, donne la raison."]
        self.create_text(x0 + a.px(20), y0 + a.px(44), anchor="w", fill=T["dim"], font=f,
                         text=recent or "")
        y = y0 + a.px(64)
        for ligne in lignes:
            col = T["danger"] if any(m in ligne.lower() for m in MOTS_ERREUR) else T["text2"]
            self.create_text(x0 + a.px(20), y, anchor="w", text=tronquer(ligne, f, x1 - x0 - a.px(40)),
                             fill=col, font=f)
            y += lh

    def _journal_omni(self, x0, y0, x1, y1, inst):
        """Lignes du journal lisible, les plus recentes en bas."""
        a = self.app
        # lignes du journal (les plus recentes en bas)
        f = a.police_mono(15)
        lh = f.metrics("linespace") + a.px(6)
        places = max(1, int((y1 - y0 - a.px(60)) // lh))
        lignes = inst["journal"][-places:]
        y = y0 + a.px(52)
        rotation = "|/-\\"[int(time.time() * 4) % 4]
        for etat, texte, heure in lignes:
            sym, col = {"ok": ("\u2713", T["ok"]), "ko": ("\u2717", T["danger"]),
                        "encours": (rotation, T["cyan"])}[etat]
            self.create_text(x0 + a.px(20), y, anchor="w", text=heure, fill=mel(T["dim"], T["bg"], 0.2), font=f)
            self.create_text(x0 + a.px(20) + f.measure("+00:00  "), y, anchor="w", text=sym, fill=col, font=f)
            self.create_text(x0 + a.px(20) + f.measure("+00:00  ✓ "), y, anchor="w",
                             text=tronquer(texte, f, x1 - x0 - a.px(40) - f.measure("+00:00  ✓ ")),
                             fill=T["text"] if etat != "ko" else T["danger"], font=f)
            y += lh
        if inst["etat"] == "encours" and int(time.time() * 2) % 2 == 0:
            self.create_text(x0 + a.px(20), y, anchor="w", text="_", fill=T["cyan"], font=f)

    def _pied(self, inst, y1):
        """Barre de progression, resume du resultat et boutons selon l'etat."""
        a = self.app
        x0, x1 = a.px(110), a.W - a.px(110)
        # barre et resultat
        by = y1 + a.px(26)
        col = {"encours": T["cyan"], "fini": T["ok"], "echec": T["danger"]}[inst["etat"]]
        bx0, bx1 = x0, x1
        rrect(self, bx0, by, bx1, by + a.px(18), a.px(9), fill=T["panel2"], outline=mel(col, T["bg"], 0.5), width=1)
        if inst["etat"] == "encours" and inst.get("indetermine"):
            larg = (bx1 - bx0) * 0.22
            x = bx0 + ((time.time() * 120) % ((bx1 - bx0) + larg)) - larg
            neon(self, max(bx0, x), by, min(bx1, x + larg), by + a.px(18), a.px(9), col, fill=col, halo=2, w=1)
        elif inst["pct"]:
            neon(self, bx0, by, bx0 + max(a.px(18), (bx1 - bx0) * inst["pct"] / 100), by + a.px(18), a.px(9), col,
                 fill=col, halo=2, w=1)
        ecoule = int(time.time() - inst["debut"])
        if inst["etat"] == "encours":
            res = "En cours depuis %d min %02d s. Tu peux revenir au menu, ça continue." % (ecoule // 60, ecoule % 60)
        elif inst["etat"] == "fini":
            res = "Terminé : %s est prêt." % PLAT[self.pid]["nom"]
            if self.pid == "steam":
                res += " La connexion à ton compte se fait dans Steam, quand tu veux."
        else:
            res = "Échec : " + inst["erreur"]
        self.create_text(bx0, by + a.px(40), anchor="w", text=res, fill=col, font=a.police(15, True),
                         width=bx1 - bx0 - a.px(80))
        self.create_text(bx1, by + a.px(40), anchor="e", fill=col, font=a.police(18, True),
                         text="..." if (inst["etat"] == "encours" and inst.get("indetermine")) else "%d %%" % inst["pct"])
        # boutons
        bw, bh = a.px(200), a.px(44)
        yb = a.H - a.px(110)
        if inst["etat"] == "fini":
            self.bouton_or("fini", a.W / 2 - bw / 2, yb, bw, bh, "TERMINÉ", self._terminer, plein=True)
        elif inst["etat"] == "echec":
            self.bouton_or("retour", a.W / 2 - bw * 1.5 - a.px(14), yb, bw, bh, "RETOUR", self.retour)
            self.bouton_or("details", a.W / 2 - bw / 2, yb, bw, bh,
                           "JOURNAL BRUT" if not self.brut else "REVENIR AU RÉSUMÉ", self._basculer_brut)
            self.bouton_or("reessayer", a.W / 2 + bw / 2 + a.px(14), yb, bw, bh, "RÉESSAYER",
                           self._reessayer, plein=True)
        else:
            self.bouton_or("retour", a.W / 2 - bw / 2, yb, bw, bh, "RETOUR AU MENU", self.retour)

    def focus_defaut(self):
        for f in ("fini", "reessayer", "retour"):
            if f in self.foc:
                return f
        return super().focus_defaut()

    def aides(self):
        return [("A", "Choisir"), ("B", "Retour")]

    def _tic(self):
        """Redessine tant que l'operation avance et reagit a sa fin."""
        if not self.winfo_exists():
            return
        inst = self.app.installs.get(self.pid)
        self.redessiner()
        if inst and inst["etat"] == "fini" and not self._fini_vu:
            self._fini_vu = True
            self.app.jouer_son("valid")
            if not self.premiere:
                # apres une installation, Omni doit etre devant, pas derriere
                self.app.revenir()
            if self.premiere:
                # Steam est prêt : il passe devant, Omni s'efface
                self.after(1500, self._terminer)
        self.after(200 if inst and inst["etat"] == "encours" else 1500, self._tic)

    def _terminer(self):
        """Ferme le journal : retour aux plateformes (premiere ouverture) ou a la bibliotheque."""
        a = self.app
        a.installs.pop(self.pid, None)
        if self.premiere:
            a.montrer(PagePlateformes, plat=self.pid)
            a.passer_derriere()
            a.bandeau("%s est ouvert. Bouton Guide : menu Omni." % PLAT[self.pid]["nom"])
        else:
            a.montrer(PageBibliotheque, filtre=self.pid)

    def _basculer_brut(self):
        self.brut = not self.brut
        self.redessiner()

    def _reessayer(self):
        a = self.app
        ancien = a.installs.pop(self.pid, None) or {}
        demarrer_installation(a, PLAT[self.pid], a.joueur_actif,
                              fonction=ancien.get("fonction"), titre=ancien.get("titre_court"))
        self.redessiner()

    def retour(self):
        inst = self.app.installs.get(self.pid)
        if inst and inst["etat"] == "echec":
            self.app.installs.pop(self.pid, None)
        self.app.montrer(PagePlateformes, plat=self.pid)


# anciens noms encore utilises par les sous-pages de reglages
PageAccueil = PageBibliotheque
PageGalerie = PageProfil
PageConfirmInstall = PagePlateformes


if __name__ == "__main__":
    OmniConsole().mainloop()
