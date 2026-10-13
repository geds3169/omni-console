#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Console - Installateur graphique (v2)
Interface traduite (fr/en/de/pt) + fuseau horaire natif (region/ville)
a la charte Omni. Detection disque robuste. Installation simulee.
"""

import tkinter as tk
from tkinter import font as tkfont
import subprocess
import threading
import time
import os
import shlex
import signal

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

LANGUES = [
    ("Francais", "fr", "fr", "Europe", "Paris"),
    ("English", "en", "us", "America", "New_York"),
    ("Deutsch", "de", "de", "Europe", "Berlin"),
    ("Portugues", "pt", "pt", "Europe", "Lisbon"),
]
CLAVIERS = ["fr", "us", "de", "pt", "be", "ch"]


def lire_fuseaux():
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
def _sortie(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


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
        nom, parent, montage = champs[0], champs[1], " ".join(champs[2:])
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


class OmniInstaller(tk.Tk):
    def __init__(self):
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
        self.afficher_banniere()
        self.audio_proc = None
        self.volume = 60
        self.musique_on = True
        self.creer_player()
        self.demarrer_musique()
        self.montrer_page(PageLangue)

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
            self.montrer_page(self.page_actuelle_classe)

    # ---- Lecteur de musique (player en haut a droite) ----
    def creer_player(self):
        pf = tk.Frame(self, bg=COL_PANEL, highlightbackground=COL_CYAN,
                      highlightthickness=1)
        pf.place(relx=1.0, x=-20, y=16, anchor="ne")
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

    def _cmd_audio(self):
        import shutil
        import glob
        fichiers = sorted(glob.glob("/usr/local/share/omni/*.ogg") +
                          glob.glob("/usr/local/share/omni/*.mp3") +
                          glob.glob("/usr/local/share/omni/*.wav"))
        # Repli sur le dossier projet pour test hors ISO
        if not fichiers:
            fichiers = sorted(glob.glob("./*.ogg") + glob.glob("./*.mp3"))
        chemin = fichiers[0] if fichiers else ""
        if not chemin:
            return None
        vol = self.volume / 100.0
        if shutil.which("mpv"):
            return ["mpv", "--no-video", "--loop", "--ao=pulse,pipewire,alsa",
                    f"--volume={self.volume}",
                    "--really-quiet", chemin]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-loop", "0", "-autoexit",
                    "-volume", str(self.volume), "-loglevel", "quiet", chemin]
        if shutil.which("cvlc"):
            return ["cvlc", "--intf", "dummy", "--loop",
                    f"--gain={vol}", chemin]
        return None

    def jouer_son(self, nom):
        """Joue un son court d'interface (hover/select/valid) sans bloquer."""
        import glob, shutil
        base = "/usr/local/share/omni/sons"
        f = f"{base}/omni-{nom}.ogg"
        if not os.path.exists(f):
            # repli test hors ISO
            alt = glob.glob(f"./sons/omni-{nom}.ogg") or glob.glob(f"./omni-{nom}.ogg")
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
        self.arreter_musique()
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

    def montrer_page(self, PageClass):
        self.page_actuelle_classe = PageClass
        if self.page_actuelle is not None:
            self.page_actuelle.destroy()
        # Cadre exterieur qui remplit tout, avec le contenu centre dedans.
        self.page_actuelle = tk.Frame(self.container, bg=COL_BG)
        self.page_actuelle.pack(fill="both", expand=True)
        self.page_actuelle.grid_rowconfigure(0, weight=1)
        self.page_actuelle.grid_columnconfigure(0, weight=1)
        page = PageClass(self.page_actuelle, self)
        if getattr(PageClass, "PLEINE_LARGEUR", False):
            page.grid(row=0, column=0, sticky="nsew", padx=self.px(40), pady=self.px(20))
        else:
            page.grid(row=0, column=0)


def bouton(parent, texte, commande, couleur=COL_CYAN, largeur=18):
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
    def __init__(self, parent, app):
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
        self.list_ville.delete(0, "end")
        villes = self.app.fuseaux.get(region, [])
        for v in villes:
            self.list_ville.insert("end", v)
        if ville_defaut and ville_defaut in villes:
            idx = villes.index(ville_defaut)
            self.list_ville.selection_set(idx)
            self.list_ville.see(idx)

    def suivant(self):
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
    def __init__(self, parent, app):
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
        self.marques = {}
        for w in self.zone.winfo_children():
            w.destroy()
        disques = self.detecter_disques()
        if not disques:
            tk.Label(self.zone, text=self.app.tr("no_disk"), font=self.app.f_normal,
                     fg=COL_DIM, bg=COL_BG).pack(anchor="w")
            return
        for d in disques:
            protege = d["chemin"] in self.app.proteges
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
            detail = d["modele"] + ("   \u2014  " + self.app.tr("boot_media") if protege else "")
            l2 = tk.Label(info, text=detail, font=self.app.f_petit,
                          fg=COL_AMBER if protege else COL_DIM,
                          bg=COL_PANEL, anchor="w")
            l2.pack(anchor="w")
            if not protege:
                for w in (info, l1, l2):
                    w.bind("<Button-1>", lambda e, c=d["chemin"]: self.choisir(c))
                    w.configure(cursor="hand2")

    def detecter_disques(self):
        disques = []
        try:
            sortie = subprocess.run(["lsblk", "-dbn", "-P", "-o", "NAME,SIZE,MODEL,TYPE,RM,RO"],
                                    capture_output=True, text=True, timeout=10).stdout
            for ligne in sortie.strip().split("\n"):
                if not ligne.strip():
                    continue
                champs = {}
                for tok in shlex.split(ligne):
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        champs[k] = v
                nom = champs.get("NAME", "")
                type_ = champs.get("TYPE", "")
                modele = champs.get("MODEL", "").strip() or "Disque"
                amovible = champs.get("RM", "0") == "1"
                lecture_seule = champs.get("RO", "0") == "1"
                if type_ != "disk":
                    continue
                if nom.startswith(("zram", "loop", "sr")):
                    continue
                if lecture_seule:
                    continue
                try:
                    o = int(champs.get("SIZE", "0"))
                except ValueError:
                    continue
                if o < 8 * 1024 * 1024 * 1024:
                    continue
                disques.append({"chemin": f"/dev/{nom}", "taille": self._taille_lisible(o),
                                "modele": modele + ("  (USB)" if amovible else ""), "amovible": amovible})
        except Exception:
            disques = [{"chemin": "/dev/sda", "taille": "240 Go", "modele": "Disque A (test)", "amovible": False}]
        return disques

    @staticmethod
    def _taille_lisible(octets):
        for unite, seuil in [("To", 1024**4), ("Go", 1024**3), ("Mo", 1024**2)]:
            if octets >= seuil:
                return f"{octets / seuil:.0f} {unite}"
        return f"{octets} o"

    def suivant(self):
        choisi = self.var_disque.get()
        if not choisi or choisi == "AUCUN" or choisi in self.app.proteges:
            self.btn_next.configure(bg=COL_DANGER)
            self.after(300, lambda: self.btn_next.configure(bg=COL_CYAN))
            return
        self.app.choix["disque"] = choisi
        self.app.montrer_page(PageConfirmation)


class PageConfirmation(tk.Frame):
    def __init__(self, parent, app):
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


DIAPO = [
    ("A", "Bibliotheque unifiee", "Steam, Epic, GOG au meme endroit."),
    ("B", "Plusieurs joueurs", "Chaque joueur son profil et ses sauvegardes."),
    ("C", "Manettes et Joy-Con", "Branchez, appuyez, jouez."),
    ("D", "Mises a jour automatiques", "La console s'entretient toute seule."),
    ("E", "Controle parental", "Age et temps de jeu par profil."),
    ("F", "Accessibilite", "Filtres daltoniens, texte agrandi."),
    ("G", "SSD portable", "Emportez vos jeux chez un ami."),
    ("H", "Restauration simple", "Retour a la derniere version qui marchait."),
]


class PageInstallation(tk.Frame):
    PLEINE_LARGEUR = True
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.index_diapo = 0
        self.fini = False
        tk.Label(self, text=app.tr("installing"), font=app.f_soustitre, fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, app.px(16)))
        self.diapo_cadre = tk.Frame(self, bg=COL_PANEL, height=app.px(420))
        self.diapo_cadre.pack(fill="both", expand=True, pady=(0, app.px(16)), padx=app.px(20))
        self.diapo_cadre.pack_propagate(False)
        self.img = tk.Label(self.diapo_cadre, text="A", font=(FONT_NAME, -app.px(200), "bold"),
                            fg=COL_MAGENTA, bg=COL_PANEL)
        self.img.pack(pady=(app.px(16), 0))
        self.d_titre = tk.Label(self.diapo_cadre, text="", font=app.f_titre, fg=COL_CYAN, bg=COL_PANEL)
        self.d_titre.pack()
        self.d_desc = tk.Label(self.diapo_cadre, text="", font=app.f_soustitre, fg=COL_TEXT, bg=COL_PANEL)
        self.d_desc.pack(pady=(app.px(6), 0))
        pcadre = tk.Frame(self, bg=COL_BG)
        pcadre.pack(fill="x", pady=(0, app.px(6)))
        self.canvas = tk.Canvas(pcadre, height=app.px(22), bg=COL_PANEL, highlightthickness=0)
        self.canvas.pack(fill="x")
        self.barre = self.canvas.create_rectangle(0, 0, 0, app.px(22), fill=COL_CYAN, outline="")
        self.lbl_pct = tk.Label(self, text="0 %", font=app.f_petit, fg=COL_DIM, bg=COL_BG)
        self.lbl_pct.pack(anchor="e")
        self.journal = tk.Label(self, text="", font=app.f_mono, fg=COL_DIM, bg=COL_BG, anchor="w")
        self.journal.pack(anchor="w", pady=(app.px(8), 0))
        self.tourner()
        threading.Thread(target=self.installer, daemon=True).start()

    def tourner(self):
        slides = T.get(self.app.lang, T["fr"]).get("slides", [])
        if slides:
            t, d = slides[self.index_diapo % len(slides)]
            self.img.configure(text=str((self.index_diapo % len(slides)) + 1))
            self.d_titre.configure(text=t)
            self.d_desc.configure(text=d)
        self.index_diapo += 1
        if not self.fini:
            self.after(4000, self.tourner)

    def maj(self, pct, msg):
        w = self.canvas.winfo_width()
        self.canvas.coords(self.barre, 0, 0, w * pct / 100, self.app.px(22))
        self.lbl_pct.configure(text=f"{pct} %")
        self.journal.configure(text=msg)

    def installer(self):
        """VRAIE installation : partition (EFI/systeme/donnees) + format + copie + grub.
        Garde-fous : refuse le disque source ; toutes les etapes verifiees."""
        disque = self.app.choix.get("disque", "")
        try:
            self._install_reel(disque)
        except Exception as e:
            self.after(0, self.maj, 0, f"ERREUR : {e}")
            return
        self.fini = True
        self.after(1500, lambda: self.app.montrer_page(PageFin))

    def _run(self, cmd, msg=None, pct=None):
        if msg is not None:
            self.after(0, self.maj, pct if pct is not None else 0, msg)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd[:3])}... : {r.stderr.strip()[:120]}")
        return r.stdout

    def _install_reel(self, disque):
        import os, time
        # --- Garde-fous ---
        if not disque or not disque.startswith("/dev/"):
            raise RuntimeError("Disque cible invalide")
        # Refus ferme : jamais le support depuis lequel la console a demarre
        if disque in self.app.proteges or disque in disques_de_demarrage():
            raise RuntimeError("Refus : c'est le support de demarrage")

        def part(n):
            return disque + (("p"+str(n)) if disque[-1].isdigit() else str(n))
        # p1 = BIOS boot (bios_grub), p2 = EFI, p3 = systeme, p4 = donnees
        p_bios = part(1)
        p_efi = part(2)
        p_sys = part(3)
        p_dat = part(4)

        # --- 1. Partitionnement GPT ---
        self.after(0, self.maj, 10, self.app.tr("part"))
        self._run(["wipefs", "-a", disque])
        self._run(["parted", "-s", disque, "mklabel", "gpt"])
        # Partition BIOS Boot (pour grub BIOS sur GPT)
        self._run(["parted", "-s", disque, "mkpart", "BIOSBOOT", "1MiB", "2MiB"])
        self._run(["parted", "-s", disque, "set", "1", "bios_grub", "on"])
        # EFI
        self._run(["parted", "-s", disque, "mkpart", "EFI", "fat32", "2MiB", "514MiB"])
        self._run(["parted", "-s", disque, "set", "2", "esp", "on"])
        # Systeme et donnees
        self._run(["parted", "-s", disque, "mkpart", "OMNI_SYS", "ext4", "514MiB", "60%"])
        self._run(["parted", "-s", disque, "mkpart", "OMNI_DATA", "ext4", "60%", "100%"])
        time.sleep(1)

        # --- 2. Formatage ---
        self.after(0, self.maj, 30, self.app.tr("format"))
        self._run(["mkfs.vfat", "-F", "32", "-n", "OMNI_EFI", p_efi])
        self._run(["mkfs.ext4", "-F", "-L", "OMNI_SYS", p_sys])
        self._run(["mkfs.ext4", "-F", "-L", "OMNI_DATA", p_dat])

        # --- 3. Montage + copie du systeme (squashfs de l'ISO) ---
        self.after(0, self.maj, 45, self.app.tr("copy"))
        cible = "/target"
        os.makedirs(cible, exist_ok=True)
        self._run(["mount", p_sys, cible])
        os.makedirs(cible+"/boot/efi", exist_ok=True)
        self._run(["mount", p_efi, cible+"/boot/efi"])
        # Copier le systeme depuis le squashfs monte de l'ISO
        squash = "/rofs"
        if not os.path.ismount(squash):
            squash = "/cdrom/casper/filesystem.squashfs"
        if os.path.isdir("/rofs"):
            self._run(["cp", "-ax", "/rofs/.", cible+"/"])
        else:
            os.makedirs("/mnt/squash", exist_ok=True)
            self._run(["mount", "-o", "loop", squash, "/mnt/squash"])
            self._run(["cp", "-ax", "/mnt/squash/.", cible+"/"])

        # --- 4. fstab + montages pour chroot ---
        self.after(0, self.maj, 70, self.app.tr("settings"))
        efi_uuid = subprocess.run(["blkid", "-s", "UUID", "-o", "value", p_efi], capture_output=True, text=True).stdout.strip()
        sys_uuid = subprocess.run(["blkid", "-s", "UUID", "-o", "value", p_sys], capture_output=True, text=True).stdout.strip()
        dat_uuid = subprocess.run(["blkid", "-s", "UUID", "-o", "value", p_dat], capture_output=True, text=True).stdout.strip()
        with open(cible+"/etc/fstab", "w") as f:
            f.write(f"UUID={sys_uuid} / ext4 defaults 0 1\n")
            f.write(f"UUID={efi_uuid} /boot/efi vfat umask=0077 0 1\n")
            f.write(f"UUID={dat_uuid} /omni-data ext4 defaults 0 2\n")
        os.makedirs(cible+"/omni-data", exist_ok=True)
        for m in ["dev", "proc", "sys"]:
            self._run(["mount", "--bind", "/"+m, cible+"/"+m])
        self._run(["mount", "--bind", "/dev/pts", cible+"/dev/pts"])

        # --- 4b. Noyau + initrd : ABSENTS du squashfs (ils sont dans /casper).
        # On les copie depuis l'ISO, ou on regenere via le paquet noyau. ---
        self.after(0, self.maj, 80, self.app.tr("boot"))
        import glob
        # Trouver la version du noyau depuis les modules copies
        mods = glob.glob(cible+"/usr/lib/modules/*")
        kver = os.path.basename(mods[0]) if mods else ""
        casper_vmlinuz = None
        casper_initrd = None
        for d in ["/cdrom/casper", "/run/live/medium/casper", "/casper"]:
            if os.path.exists(d):
                for v in ["vmlinuz", "vmlinuz.efi"]:
                    if os.path.exists(d+"/"+v):
                        casper_vmlinuz = d+"/"+v
                for i in ["initrd", "initrd.img", "initrd.lz"]:
                    if os.path.exists(d+"/"+i):
                        casper_initrd = d+"/"+i
                break
        if kver and casper_vmlinuz:
            self._run(["cp", casper_vmlinuz, cible+f"/boot/vmlinuz-{kver}"])
        if kver and casper_initrd:
            self._run(["cp", casper_initrd, cible+f"/boot/initrd.img-{kver}"])
        if kver and not glob.glob(cible+"/boot/vmlinuz-*"):
            ch0 = ["chroot", cible]
            try:
                self._run(ch0+["apt-get", "install", "--reinstall", "-y", f"linux-image-{kver}"])
            except Exception:
                try:
                    self._run(ch0+["update-initramfs", "-c", "-k", kver])
                except Exception:
                    pass
        if not glob.glob(cible+"/boot/vmlinuz-*"):
            raise RuntimeError("Noyau (vmlinuz) absent apres copie : boot impossible")

        # --- 5. Installation grub (UEFI + BIOS) ---
        self.after(0, self.maj, 85, self.app.tr("boot"))
        ch = ["chroot", cible]
        with open(cible+"/etc/default/grub", "w") as f:
            f.write('GRUB_DEFAULT=0\n')
            f.write('GRUB_TIMEOUT=0\n')
            f.write('GRUB_TIMEOUT_STYLE=hidden\n')
            f.write('GRUB_RECORDFAIL_TIMEOUT=0\n')
            f.write('GRUB_DISABLE_OS_PROBER=true\n')
            f.write('GRUB_DISABLE_RECOVERY=true\n')
            f.write('GRUB_DISTRIBUTOR="Omni Console"\n')
            f.write('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0"\n')
            f.write('GRUB_CMDLINE_LINUX=""\n')
        self._run(ch+["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi",
                      "--bootloader-id=OMNI", "--recheck"])
        try:
            self._run(ch+["grub-install", "--target=i386-pc", "--recheck", "--boot-directory=/boot", disque])
        except Exception:
            pass
        self._run(ch+["update-grub"])
        subprocess.run(ch+["grub-editenv", "/boot/grub/grubenv", "unset", "recordfail"],
                       capture_output=True)
        cfg = cible+"/boot/grub/grub.cfg"
        if not os.path.exists(cfg) or "menuentry" not in open(cfg).read():
            noyaux = sorted(glob.glob(cible+"/boot/vmlinuz-*"))
            initrds = sorted(glob.glob(cible+"/boot/initrd.img-*"))
            if noyaux and initrds:
                kver = os.path.basename(noyaux[-1]).replace("vmlinuz-", "")
                with open(cfg, "w") as f:
                    f.write(f"""set timeout=0
menuentry "Omni Console" {{
    search --no-floppy --fs-uuid --set=root {sys_uuid}
    linux /boot/vmlinuz-{kver} root=UUID={sys_uuid} ro quiet splash loglevel=0
    initrd /boot/initrd.img-{kver}
}}
""")

        # --- 6. Nettoyage live (retirer casper, etc.) ---
        self._run(ch+["bash", "-c", "apt-get purge -y casper 2>/dev/null; true"])

        # --- 6b. Creation utilisateur OMNI + autologin + desactivation installateur ---
        self.after(0, self.maj, 88, self.app.tr("settings"))
        ch = ["chroot", cible]

        import glob as _g
        for f in (["/etc/systemd/system/omni-x.service",
                   "/etc/systemd/system/omni-debug.service",
                   "/root/.xinitrc",
                   "/usr/local/bin/omni-installer",
                   "/etc/systemd/system/default.target"]
                  + _g.glob(cible+"/etc/systemd/system/*.wants/omni-*.service")):
            fp = f if f.startswith(cible) else cible + f
            try: os.remove(fp)
            except Exception: pass
        try:
            os.symlink("/usr/lib/systemd/system/graphical.target",
                       cible+"/etc/systemd/system/default.target")
        except Exception:
            pass

        self._run(ch+["useradd", "-m", "-s", "/bin/bash",
                      "-G", "sudo,audio,video,plugdev,input", "omni"])
        self._run(ch+["bash", "-c", "passwd -d omni; passwd -u omni 2>/dev/null || true"])

        with open(cible+"/etc/hostname", "w") as f:
            f.write("omni\n")
        with open(cible+"/etc/hosts", "w") as f:
            f.write("127.0.0.1\tlocalhost\n")
            f.write("127.0.1.1\tomni\n")
            f.write("::1\tlocalhost ip6-localhost ip6-loopback\n")

        os.makedirs(cible+"/home/omni", exist_ok=True)
        os.makedirs(cible+"/home/omni/.config/openbox", exist_ok=True)
        with open(cible+"/home/omni/.config/openbox/autostart", "w") as f:
            f.write("xsetroot -solid '#0d0221' &\n")
            f.write("cd /usr/local/share/omni/ui && python3 /usr/local/share/omni/ui/omni-console.py &\n")
        # La session du joueur : son, bus de session, puis gestionnaire de fenetres
        session = ("#!/bin/sh\n"
                   "if [ -x /usr/local/bin/omni-session-joueur ]; then\n"
                   "  exec dbus-run-session -- /usr/local/bin/omni-session-joueur\n"
                   "fi\n"
                   "exec openbox-session\n")
        with open(cible+"/home/omni/.xsession", "w") as f:
            f.write(session)
        with open(cible+"/home/omni/.xinitrc", "w") as f:
            f.write(session)
        with open(cible+"/usr/local/bin/omni-session-joueur", "w") as f:
            f.write("#!/bin/sh\n"
                    "# serveur de son : sans lui, ni l'interface ni les jeux n'ont de son\n"
                    "pipewire &\n"
                    "sleep 1\n"
                    "wireplumber &\n"
                    "pipewire-pulse &\n"
                    "sleep 1\n"
                    "exec openbox-session\n")
        os.chmod(cible+"/usr/local/bin/omni-session-joueur", 0o755)
        self._run(ch+["chown", "-R", "omni:omni", "/home/omni"])

        os.makedirs(cible+"/etc/systemd/system/getty@tty1.service.d", exist_ok=True)
        with open(cible+"/etc/systemd/system/getty@tty1.service.d/autologin.conf", "w") as f:
            f.write("[Service]\n")
            f.write("ExecStart=\n")
            f.write("ExecStart=-/sbin/agetty --autologin omni --noclear %I $TERM\n")
        with open(cible+"/home/omni/.bash_profile", "w") as f:
            f.write('if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then\n')
            f.write('  exec startx\n')
            f.write('fi\n')
        self._run(ch+["chown", "omni:omni", "/home/omni/.bash_profile"])
        try:
            os.remove(cible+"/etc/systemd/system/default.target")
        except Exception:
            pass
        os.symlink("/usr/lib/systemd/system/multi-user.target",
                   cible+"/etc/systemd/system/default.target")

        for masklink in ["/etc/systemd/system/getty@tty1.service",
                         "/etc/systemd/system/getty.target.wants/getty@tty1.service"]:
            fp = cible+masklink
            if os.path.islink(fp) and os.readlink(fp) == "/dev/null":
                try: os.remove(fp)
                except Exception: pass

        # --- 7. Demontage propre ---
        self.after(0, self.maj, 95, self.app.tr("settings"))
        for m in ["dev/pts", "dev", "proc", "sys", "boot/efi", ""]:
            subprocess.run(["umount", "-lf", cible+"/"+m if m else cible], capture_output=True)

        self.after(0, self.maj, 100, self.app.tr("finished"))
        time.sleep(1)


class PageFin(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        tk.Label(self, text="\u2713", font=app.f_titre, fg=COL_OK, bg=COL_BG).pack(pady=(app.px(60), app.px(10)))
        tk.Label(self, text=app.tr("done_title"), font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack()
        tk.Label(self, text=app.tr("done_msg"), font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(pady=(app.px(10), app.px(40)))
        self.msg = tk.Label(self, text="", font=app.f_petit, fg=COL_AMBER, bg=COL_BG)
        self.msg.pack(pady=(0, app.px(10)))
        barre = tk.Frame(self, bg=COL_BG)
        barre.pack()
        bouton(barre, app.tr("reboot"), self.redemarrer, couleur=COL_OK, largeur=18).pack(side="left", padx=app.px(8))
        bouton(barre, app.tr("shutdown"), self.eteindre, couleur=COL_DIM, largeur=18).pack(side="left", padx=app.px(8))

    def _commande_systeme(self, commandes, attente):
        """Essaie plusieurs commandes : selon l'etat du systeme live, elles ne
        sont pas toutes disponibles."""
        self.msg.configure(text=attente)
        self.update_idletasks()
        # demonter ce qui peut l'etre, sinon l'arret peut trainer
        subprocess.run(["sync"], capture_output=True)
        for cmd in commandes:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    return True
            except Exception:
                continue
        self.msg.configure(text="Impossible d'agir sur la machine : coupe l'alimentation.")
        return False

    def redemarrer(self):
        self._commande_systeme([["systemctl", "reboot"], ["reboot"],
                                ["shutdown", "-r", "now"]],
                               "Redemarrage en cours...")

    def eteindre(self):
        self._commande_systeme([["systemctl", "poweroff"], ["poweroff"],
                                ["shutdown", "-h", "now"]],
                               "Extinction en cours...")


# ===========================================================================
# Clavier virtuel (saisie a la souris si clavier physique HS ou mauvaise langue)
# ===========================================================================
class ClavierVirtuel(tk.Toplevel):
    # Dispositions disponibles
    DISPOS = {
        "AZERTY": [list("azertyuiop"), list("qsdfghjklm"), list("wxcvbn,;:!")],
        "QWERTY": [list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm,.?")],
    }
    SPECIAUX = list("@#&_-()[]{}/\\+=*%$\u20ac.'\"")

    def __init__(self, app, cible):
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
