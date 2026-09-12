#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Console - Installateur graphique
=====================================
Installateur maison qui remplace debian-installer.

Deroule :
  1. Localisation : langue, pays, fuseau horaire, clavier
  2. Choix du disque cible (avec garde-fou : affichage, choix explicite,
     confirmation avant tout formatage)
  3. Installation en arriere-plan PENDANT qu'un diaporama de presentation
     de la console defile (facon Windows/Ubuntu), avec barre de progression
     et journal.
  4. Fin : inviter a retirer la cle et redemarrer.

Aucune authentification. Pas de mode live. L'ISO demarre directement
sur cet installateur.

Cette version est un SQUELETTE FONCTIONNEL : la navigation, les pages et
le diaporama marchent. Le partitionnement/formatage reel et la copie du
systeme sont isoles dans des fonctions clairement marquees, non actives
tant qu'on ne les a pas validees ensemble (securite : operation
destructrice).
"""

import tkinter as tk
from tkinter import font as tkfont
import subprocess
import threading
import time
import os

# ---------------------------------------------------------------------------
# Charte graphique Omni (synthwave / outrun)
# ---------------------------------------------------------------------------
COL_BG       = "#0d0221"   # violet nuit (fond principal)
COL_PANEL    = "#1a0a3a"   # panneau legerement plus clair
COL_MAGENTA  = "#ff2e97"   # magenta (titres, accents)
COL_CYAN     = "#2de2e6"   # cyan (boutons, soulignements)
COL_TEXT     = "#f5f5ff"   # texte clair
COL_DIM      = "#8a7fb5"   # texte attenue
COL_AMBER    = "#ff9e2c"   # ambre (barre soleil)
COL_DANGER   = "#ff4d4d"   # rouge (avertissements)
COL_OK       = "#3ddc84"   # vert (succes)

FONT_NAME = "DejaVu Sans"

# ---------------------------------------------------------------------------
# Donnees de localisation (simplifiees ; a etoffer)
# ---------------------------------------------------------------------------
LANGUES = [
    ("Francais",  "fr", "fr", "Europe/Paris"),
    ("English",   "en", "us", "America/New_York"),
    ("Deutsch",   "de", "de", "Europe/Berlin"),
    ("Portugues", "pt", "pt", "Europe/Lisbon"),
]

# Pays -> fuseau propose (echantillon ; a etoffer)
PAYS_FUSEAUX = {
    "France":     "Europe/Paris",
    "Belgique":   "Europe/Brussels",
    "Suisse":     "Europe/Zurich",
    "Canada":     "America/Montreal",
    "USA":        "America/New_York",
    "Allemagne":  "Europe/Berlin",
    "Portugal":   "Europe/Lisbon",
    "Bresil":     "America/Sao_Paulo",
}

# Dispositions clavier proposees (echantillon)
CLAVIERS = ["fr", "us", "de", "pt", "be", "ch"]


class OmniInstaller(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Omni Console - Installateur")
        self.configure(bg=COL_BG)
        # Plein ecran.
        self.attributes("-fullscreen", True)
        # Echappatoire de developpement : Echap quitte le plein ecran.
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        # Polices.
        self.f_titre  = tkfont.Font(family=FONT_NAME, size=34, weight="bold")
        self.f_soustitre = tkfont.Font(family=FONT_NAME, size=18)
        self.f_normal = tkfont.Font(family=FONT_NAME, size=14)
        self.f_petit  = tkfont.Font(family=FONT_NAME, size=11)
        self.f_mono   = tkfont.Font(family="DejaVu Sans Mono", size=11)

        # Choix de l'utilisateur, collectes au fil des pages.
        self.choix = {
            "langue": None, "code_langue": None, "clavier": None,
            "pays": None, "fuseau": None, "disque": None,
        }

        # Conteneur des pages.
        self.container = tk.Frame(self, bg=COL_BG)
        self.container.pack(fill="both", expand=True)

        self.page_actuelle = None
        self.afficher_banniere()
        self.montrer_page(PageLangue)

    # -- Banniere Omni en haut (soleil + titre) --------------------------
    def afficher_banniere(self):
        banniere = tk.Frame(self, bg=COL_BG, height=90)
        banniere.pack(fill="x", side="top")
        banniere.pack_propagate(False)
        # Soleil : six barres degradees ambre -> magenta.
        soleil = tk.Canvas(banniere, width=70, height=70, bg=COL_BG,
                           highlightthickness=0)
        soleil.place(x=40, y=12)
        couleurs = ["#ff9e2c", "#ff7e3d", "#ff5e5e", "#ff487f",
                    "#ff3690", "#ff2e97"]
        for i, c in enumerate(couleurs):
            y = 8 + i * 9
            soleil.create_rectangle(6, y, 64, y + 6, fill=c, outline="")
        # Titre.
        titre = tk.Label(banniere, text="OMNI CONSOLE", font=self.f_titre,
                         fg=COL_MAGENTA, bg=COL_BG)
        titre.place(x=125, y=22)
        # Soulignement cyan.
        ligne = tk.Frame(banniere, bg=COL_CYAN, height=3)
        ligne.place(x=127, y=70, width=360)

    # -- Navigation entre pages ------------------------------------------
    def montrer_page(self, PageClass):
        if self.page_actuelle is not None:
            self.page_actuelle.destroy()
        self.page_actuelle = PageClass(self.container, self)
        self.page_actuelle.pack(fill="both", expand=True, padx=60, pady=20)


# ===========================================================================
# Composants reutilisables
# ===========================================================================
def bouton(parent, texte, commande, couleur=COL_CYAN, largeur=18):
    b = tk.Label(parent, text=texte, font=("DejaVu Sans", 14, "bold"),
                 fg=COL_BG, bg=couleur, width=largeur, pady=10,
                 cursor="hand2")
    b.bind("<Button-1>", lambda e: commande())
    # Effet survol.
    def entrer(e): b.configure(bg=COL_MAGENTA, fg=COL_TEXT)
    def sortir(e): b.configure(bg=couleur, fg=COL_BG)
    b.bind("<Enter>", entrer)
    b.bind("<Leave>", sortir)
    return b


# ===========================================================================
# Page 1 : Langue / Pays / Fuseau / Clavier
# ===========================================================================
class PageLangue(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app

        tk.Label(self, text="Bienvenue", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 4))
        tk.Label(self, text="Choisissez votre langue et votre region.",
                 font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(
                 anchor="w", pady=(0, 24))

        corps = tk.Frame(self, bg=COL_BG)
        corps.pack(fill="both", expand=True)

        # Colonne langue.
        col_l = tk.Frame(corps, bg=COL_BG)
        col_l.pack(side="left", fill="y", padx=(0, 40))
        tk.Label(col_l, text="Langue", font=app.f_normal,
                 fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        self.var_langue = tk.StringVar(value=LANGUES[0][0])
        for nom, code, clav, fuseau in LANGUES:
            tk.Radiobutton(col_l, text=nom, variable=self.var_langue,
                           value=nom, font=app.f_normal, fg=COL_TEXT,
                           bg=COL_BG, selectcolor=COL_PANEL,
                           activebackground=COL_BG, activeforeground=COL_MAGENTA,
                           anchor="w", width=16, command=self.langue_choisie
                           ).pack(anchor="w")

        # Colonne pays.
        col_p = tk.Frame(corps, bg=COL_BG)
        col_p.pack(side="left", fill="y", padx=(0, 40))
        tk.Label(col_p, text="Pays", font=app.f_normal,
                 fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        self.var_pays = tk.StringVar(value="France")
        for pays in PAYS_FUSEAUX:
            tk.Radiobutton(col_p, text=pays, variable=self.var_pays,
                           value=pays, font=app.f_normal, fg=COL_TEXT,
                           bg=COL_BG, selectcolor=COL_PANEL,
                           activebackground=COL_BG, activeforeground=COL_MAGENTA,
                           anchor="w", width=14).pack(anchor="w")

        # Colonne clavier.
        col_c = tk.Frame(corps, bg=COL_BG)
        col_c.pack(side="left", fill="y")
        tk.Label(col_c, text="Clavier", font=app.f_normal,
                 fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(0, 8))
        self.var_clavier = tk.StringVar(value="fr")
        for clav in CLAVIERS:
            tk.Radiobutton(col_c, text=clav.upper(), variable=self.var_clavier,
                           value=clav, font=app.f_normal, fg=COL_TEXT,
                           bg=COL_BG, selectcolor=COL_PANEL,
                           activebackground=COL_BG, activeforeground=COL_MAGENTA,
                           anchor="w", width=8).pack(anchor="w")

        # Bouton suivant.
        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=20)
        bouton(bas, "Suivant  \u25B6", self.suivant).pack(side="right")

    def langue_choisie(self):
        # Quand on change de langue, proposer clavier et fuseau coherents.
        for nom, code, clav, fuseau in LANGUES:
            if nom == self.var_langue.get():
                self.var_clavier.set(clav)
                break

    def suivant(self):
        nom = self.var_langue.get()
        code = next(c for n, c, k, f in LANGUES if n == nom)
        self.app.choix["langue"] = nom
        self.app.choix["code_langue"] = code
        self.app.choix["pays"] = self.var_pays.get()
        self.app.choix["fuseau"] = PAYS_FUSEAUX[self.var_pays.get()]
        self.app.choix["clavier"] = self.var_clavier.get()
        self.app.montrer_page(PageDisque)


# ===========================================================================
# Page 2 : Choix du disque (avec garde-fou)
# ===========================================================================
class PageDisque(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.var_disque = tk.StringVar(value="")

        tk.Label(self, text="Disque d'installation", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 4))
        tk.Label(self, text="Choisissez le disque ou installer Omni Console.",
                 font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(
                 anchor="w", pady=(0, 20))

        # Avertissement.
        avert = tk.Label(self,
            text="\u26A0  Le disque choisi sera entierement efface.",
            font=app.f_normal, fg=COL_DANGER, bg=COL_BG)
        avert.pack(anchor="w", pady=(0, 16))

        # Liste des disques detectes.
        self.zone = tk.Frame(self, bg=COL_BG)
        self.zone.pack(fill="both", expand=True)
        self.charger_disques()

        # Boutons.
        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=20)
        bouton(bas, "\u25C0  Retour", self.retour, couleur=COL_DIM,
               largeur=14).pack(side="left")
        self.btn_suivant = bouton(bas, "Suivant  \u25B6", self.suivant)
        self.btn_suivant.pack(side="right")

    def charger_disques(self):
        for w in self.zone.winfo_children():
            w.destroy()
        disques = self.detecter_disques()
        if not disques:
            tk.Label(self.zone, text="Aucun disque detecte.",
                     font=self.app.f_normal, fg=COL_DIM, bg=COL_BG).pack(
                     anchor="w")
            return
        for d in disques:
            cadre = tk.Frame(self.zone, bg=COL_PANEL, padx=16, pady=12)
            cadre.pack(fill="x", pady=6)
            rb = tk.Radiobutton(cadre, variable=self.var_disque,
                                value=d["chemin"], bg=COL_PANEL,
                                selectcolor=COL_BG, activebackground=COL_PANEL)
            rb.pack(side="left", padx=(0, 12))
            info = tk.Frame(cadre, bg=COL_PANEL)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=f"{d['chemin']}  \u2014  {d['taille']}",
                     font=("DejaVu Sans", 14, "bold"), fg=COL_TEXT,
                     bg=COL_PANEL, anchor="w").pack(anchor="w")
            tk.Label(info, text=d["modele"], font=self.app.f_petit,
                     fg=COL_DIM, bg=COL_PANEL, anchor="w").pack(anchor="w")

    def detecter_disques(self):
        """
        Detecte les VRAIS disques d'installation via lsblk.
        Ecarte : zram (memoire compressee), loop (fichiers montes), rom
        (lecteurs optiques), et tout disque trop petit (< 8 Go) qui ne
        peut pas accueillir le systeme. On lit aussi la colonne RM pour
        signaler l'USB amovible (souvent la cle d'installation elle-meme).
        """
        disques = []
        try:
            sortie = subprocess.run(
                ["lsblk", "-dbn", "-o", "NAME,SIZE,MODEL,TYPE,RM,RO"],
                capture_output=True, text=True, timeout=10).stdout
            for ligne in sortie.strip().split("\n"):
                parts = ligne.split(None, 5)
                if len(parts) < 4:
                    continue
                nom, taille_o, type_ = parts[0], parts[1], parts[3]
                modele = parts[2] if parts[2] != "" else "Disque"
                amovible = (len(parts) >= 5 and parts[4] == "1")
                lecture_seule = (len(parts) >= 6 and parts[5] == "1")
                # Ne garder que les vrais disques.
                if type_ != "disk":
                    continue
                # Ecarter zram et loop par leur nom.
                if nom.startswith(("zram", "loop", "sr")):
                    continue
                if lecture_seule:
                    continue
                # Taille en octets ; ecarter les disques < 8 Go.
                try:
                    o = int(taille_o)
                except ValueError:
                    continue
                if o < 8 * 1024 * 1024 * 1024:
                    continue
                disques.append({
                    "chemin": f"/dev/{nom}",
                    "taille": self._taille_lisible(o),
                    "modele": modele + ("  (USB amovible)" if amovible else ""),
                    "amovible": amovible,
                })
        except Exception:
            # Hors systeme reel (ex. test) : disques fictifs.
            disques = [
                {"chemin": "/dev/sda", "taille": "240 Go", "modele": "Disque A (test)", "amovible": False},
                {"chemin": "/dev/sdb", "taille": "1 To",   "modele": "Disque B (test)", "amovible": False},
            ]
        return disques

    @staticmethod
    def _taille_lisible(octets):
        for unite, seuil in [("To", 1024**4), ("Go", 1024**3), ("Mo", 1024**2)]:
            if octets >= seuil:
                return f"{octets / seuil:.0f} {unite}"
        return f"{octets} o"

    def retour(self):
        self.app.montrer_page(PageLangue)

    def suivant(self):
        if not self.var_disque.get():
            # Rien choisi : signaler.
            self.btn_suivant.configure(bg=COL_DANGER)
            self.after(300, lambda: self.btn_suivant.configure(bg=COL_CYAN))
            return
        self.app.choix["disque"] = self.var_disque.get()
        self.app.montrer_page(PageConfirmation)


# ===========================================================================
# Page 3 : Confirmation avant formatage (garde-fou destructif)
# ===========================================================================
class PageConfirmation(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app

        tk.Label(self, text="Confirmation", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 20))

        d = app.choix["disque"]
        msg = (f"Omni Console va etre installe sur {d}.\n\n"
               f"TOUT le contenu de ce disque sera efface definitivement.\n"
               f"Cette action est irreversible.")
        tk.Label(self, text=msg, font=app.f_soustitre, fg=COL_TEXT,
                 bg=COL_BG, justify="left").pack(anchor="w", pady=(0, 30))

        # Recapitulatif des choix.
        recap = tk.Frame(self, bg=COL_PANEL, padx=20, pady=16)
        recap.pack(fill="x", pady=(0, 20))
        for label, cle in [("Langue", "langue"), ("Pays", "pays"),
                           ("Fuseau horaire", "fuseau"), ("Clavier", "clavier"),
                           ("Disque", "disque")]:
            l = tk.Frame(recap, bg=COL_PANEL)
            l.pack(fill="x", pady=2)
            tk.Label(l, text=f"{label} :", font=app.f_normal, fg=COL_CYAN,
                     bg=COL_PANEL, width=16, anchor="w").pack(side="left")
            tk.Label(l, text=str(app.choix[cle]), font=app.f_normal,
                     fg=COL_TEXT, bg=COL_PANEL, anchor="w").pack(side="left")

        bas = tk.Frame(self, bg=COL_BG)
        bas.pack(fill="x", side="bottom", pady=20)
        bouton(bas, "\u25C0  Retour", lambda: app.montrer_page(PageDisque),
               couleur=COL_DIM, largeur=14).pack(side="left")
        bouton(bas, "Effacer et installer", self.installer,
               couleur=COL_DANGER, largeur=22).pack(side="right")

    def installer(self):
        self.app.montrer_page(PageInstallation)


# ===========================================================================
# Page 4 : Installation + diaporama de presentation
# ===========================================================================
# Diaporama : pour l'instant, images bidon A, B, C... (placeholders).
DIAPO = [
    ("A", "Bibliotheque unifiee",
     "Tous vos jeux Steam, Epic, GOG au meme endroit."),
    ("B", "Plusieurs joueurs",
     "Chaque joueur son profil, ses sauvegardes, son temps de jeu."),
    ("C", "Manettes et Joy-Con",
     "Branchez, appuyez, jouez. Sans configuration."),
    ("D", "Mises a jour automatiques",
     "La console s'entretient toute seule."),
    ("E", "Controle parental",
     "Classification par age et limites de temps par profil."),
    ("F", "Accessibilite",
     "Filtres daltoniens, texte agrandi, jeu a une main."),
    ("G", "SSD portable",
     "Emportez vos jeux et votre profil chez un ami."),
    ("H", "Restauration simple",
     "Un souci ? Retour a la derniere version qui marchait."),
]


class PageInstallation(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.index_diapo = 0
        self.installation_finie = False

        tk.Label(self, text="Installation en cours", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack(anchor="w", pady=(0, 20))

        # Zone diaporama (grande, au centre).
        self.diapo_cadre = tk.Frame(self, bg=COL_PANEL, height=340)
        self.diapo_cadre.pack(fill="x", pady=(0, 20))
        self.diapo_cadre.pack_propagate(False)

        # Grande "image" bidon (lettre dans un cadre colore).
        self.img_label = tk.Label(self.diapo_cadre, text="A",
            font=("DejaVu Sans", 120, "bold"), fg=COL_MAGENTA, bg=COL_PANEL)
        self.img_label.pack(pady=(20, 0))
        self.diapo_titre = tk.Label(self.diapo_cadre, text="",
            font=("DejaVu Sans", 22, "bold"), fg=COL_CYAN, bg=COL_PANEL)
        self.diapo_titre.pack()
        self.diapo_desc = tk.Label(self.diapo_cadre, text="",
            font=app.f_soustitre, fg=COL_TEXT, bg=COL_PANEL)
        self.diapo_desc.pack(pady=(6, 0))

        # Barre de progression.
        prog_cadre = tk.Frame(self, bg=COL_BG)
        prog_cadre.pack(fill="x", pady=(0, 8))
        self.canvas_prog = tk.Canvas(prog_cadre, height=22, bg=COL_PANEL,
                                     highlightthickness=0)
        self.canvas_prog.pack(fill="x")
        self.barre = self.canvas_prog.create_rectangle(0, 0, 0, 22,
                                                       fill=COL_CYAN, outline="")
        self.label_pct = tk.Label(self, text="0 %", font=app.f_petit,
                                  fg=COL_DIM, bg=COL_BG)
        self.label_pct.pack(anchor="e")

        # Journal (quelques lignes).
        self.journal = tk.Label(self, text="", font=app.f_mono,
                                fg=COL_DIM, bg=COL_BG, anchor="w",
                                justify="left")
        self.journal.pack(anchor="w", pady=(10, 0))

        # Lancer le diaporama et l'installation.
        self.tourner_diapo()
        threading.Thread(target=self.executer_installation, daemon=True).start()

    def tourner_diapo(self):
        lettre, titre, desc = DIAPO[self.index_diapo % len(DIAPO)]
        self.img_label.configure(text=lettre)
        self.diapo_titre.configure(text=titre)
        self.diapo_desc.configure(text=desc)
        self.index_diapo += 1
        if not self.installation_finie:
            self.after(4000, self.tourner_diapo)

    def maj_progression(self, pct, message):
        largeur = self.canvas_prog.winfo_width()
        self.canvas_prog.coords(self.barre, 0, 0, largeur * pct / 100, 22)
        self.label_pct.configure(text=f"{pct} %")
        self.journal.configure(text=message)

    def executer_installation(self):
        """
        Installation reelle. POUR L'INSTANT : SIMULATION seulement.
        Les etapes destructrices (partitionnement, formatage, copie) sont
        des fonctions separees, NON ACTIVEES tant qu'on ne les a pas
        validees ensemble. Ici on simule la progression.
        """
        etapes = [
            (10, "Preparation du disque..."),
            (25, "Partitionnement..."),
            (40, "Formatage..."),
            (60, "Copie du systeme Omni..."),
            (80, "Installation du demarrage..."),
            (95, "Application des reglages..."),
            (100, "Installation terminee."),
        ]
        for pct, msg in etapes:
            time.sleep(2.5)
            self.after(0, self.maj_progression, pct, msg)
        self.installation_finie = True
        self.after(1500, lambda: self.app.montrer_page(PageFin))


# ===========================================================================
# Page 5 : Fin
# ===========================================================================
class PageFin(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app

        tk.Label(self, text="\u2713", font=("DejaVu Sans", 80, "bold"),
                 fg=COL_OK, bg=COL_BG).pack(pady=(60, 10))
        tk.Label(self, text="Installation terminee", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack()
        tk.Label(self,
            text="Retirez la cle USB, puis redemarrez la console.",
            font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(pady=(10, 40))

        bouton(self, "Redemarrer", self.redemarrer,
               couleur=COL_OK, largeur=20).pack()

    def redemarrer(self):
        # En condition reelle : subprocess.run(["reboot"])
        # Ici (test), on quitte simplement.
        self.app.destroy()


if __name__ == "__main__":
    app = OmniInstaller()
    app.mainloop()
