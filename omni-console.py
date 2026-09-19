#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Console - Interface joueurs
=================================
Cartes de profil = illustrations steampunk extraites de planches (sprite sheet).
Le profil stocke la position (planche, ligne, colonne) ; la carte est extraite
a la volee et habillee d'un cadre neon anime + nom. Aucune authentification.

Ecrans : Selection joueur -> Galerie de cartes / creation -> Accueil (bibliotheque).
"""

import tkinter as tk
from tkinter import font as tkfont
import json
import os

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    PIL_OK = True
except Exception:
    PIL_OK = False

# ---------------------------------------------------------------------------
# Charte Omni
# ---------------------------------------------------------------------------
COL_BG      = "#0d0221"
COL_PANEL   = "#1a0a3a"
COL_MAGENTA = "#ff2e97"
COL_CYAN    = "#2de2e6"
COL_TEXT    = "#f5f5ff"
COL_DIM     = "#8a7fb5"
COL_OK      = "#3ddc84"
FONT_NAME = "DejaVu Sans"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARTES_DIR = os.path.join(BASE_DIR, "cartes")
OMNI_DIR = os.path.expanduser("~/.omni")
PROFILS_FILE = os.path.join(OMNI_DIR, "profils.json")

# ---------------------------------------------------------------------------
# Definition des planches (sprite sheets) : fichier, colonnes, lignes
# ---------------------------------------------------------------------------
PLANCHES = {
    "planche1": {"fichier": "planche1.jpg", "cols": 5, "rows": 3},
    "planche2": {"fichier": "planche2.jpg", "cols": 4, "rows": 3},
    "planche3": {"fichier": "planche3.jpg", "cols": 5, "rows": 3},
    "planche4": {"fichier": "planche4.jpg", "cols": 4, "rows": 3},
}

# Cache des planches ouvertes (PIL) et des cartes extraites (PhotoImage)
_planches_pil = {}
_cache_cartes = {}


def _ouvrir_planche(nom):
    if nom in _planches_pil:
        return _planches_pil[nom]
    p = PLANCHES.get(nom)
    if not p:
        return None
    chemin = os.path.join(CARTES_DIR, p["fichier"])
    try:
        img = Image.open(chemin).convert("RGBA")
        _planches_pil[nom] = img
        return img
    except Exception:
        return None


def extraire_carte(planche, ligne, colonne, larg, haut):
    """Retourne une PIL Image de la carte (planche, ligne, colonne) redimensionnee."""
    img = _ouvrir_planche(planche)
    if img is None:
        return None
    p = PLANCHES[planche]
    W, H = img.size
    cw, ch = W // p["cols"], H // p["rows"]
    # petite marge pour eviter les bords des cartes voisines
    mx, my = int(cw * 0.03), int(ch * 0.03)
    x0 = colonne * cw + mx
    y0 = ligne * ch + my
    x1 = (colonne + 1) * cw - mx
    y1 = (ligne + 1) * ch - my
    carte = img.crop((x0, y0, x1, y1)).resize((larg, haut))
    return carte


def carte_avec_cadre(planche, ligne, colonne, larg, haut, couleur_neon="#ff2e97",
                     nom=None, actif=False):
    """Compose une carte avec cadre neon + nom, retourne une PhotoImage tk."""
    if not PIL_OK:
        return None
    carte = extraire_carte(planche, ligne, colonne, larg, haut)
    if carte is None:
        return None
    marge = 14
    nom_h = 46 if nom else 0
    W = larg + 2 * marge
    H = haut + 2 * marge + nom_h
    canvas = Image.new("RGBA", (W, H), (13, 2, 33, 255))
    draw = ImageDraw.Draw(canvas)
    r, g, b = tuple(int(couleur_neon[i:i+2], 16) for i in (1, 3, 5))
    # halo neon
    for off, alpha in [(6, 50), (4, 110), (2, 180), (0, 255)]:
        draw.rectangle([marge-off, marge-off, marge+larg+off, marge+haut+off],
                       outline=(r, g, b, alpha), width=3)
    canvas.paste(carte, (marge, marge), carte)
    # liseré cyan interieur
    draw.rectangle([marge+3, marge+3, marge+larg-3, marge+haut-3],
                   outline=(45, 226, 230, 200), width=2)
    # anneau actif
    if actif:
        draw.rectangle([2, 2, W-2, H-2], outline=(45, 226, 230, 255), width=4)
    # nom
    if nom:
        try:
            fnt = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                     max(18, int(haut*0.09)))
        except Exception:
            fnt = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), nom, font=fnt)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw)//2, marge + haut + 6), nom, fill=(245, 245, 255, 255), font=fnt)
        draw.line([(W//2-40, H-8), (W//2+40, H-8)], fill=(r, g, b, 255), width=3)
    return ImageTk.PhotoImage(canvas)


# ---------------------------------------------------------------------------
# Profils
# ---------------------------------------------------------------------------
def charger_profils():
    try:
        with open(PROFILS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def sauver_profils(profils):
    os.makedirs(OMNI_DIR, exist_ok=True)
    try:
        with open(PROFILS_FILE, "w") as f:
            json.dump(profils, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


COULEURS_NEON = ["#ff2e97", "#2de2e6", "#ff9e2c", "#3ddc84", "#9d3cff", "#4d7cff"]


def toutes_les_cartes():
    """Liste (planche, ligne, colonne) de toutes les cartes disponibles."""
    cartes = []
    for nom, p in PLANCHES.items():
        for r in range(p["rows"]):
            for c in range(p["cols"]):
                cartes.append((nom, r, c))
    return cartes


# ===========================================================================
# Application
# ===========================================================================
class OmniConsole(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Omni Console")
        self.configure(bg=COL_BG)
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        self.f_titre    = tkfont.Font(family=FONT_NAME, size=36, weight="bold")
        self.f_soustitre= tkfont.Font(family=FONT_NAME, size=17)
        self.f_normal   = tkfont.Font(family=FONT_NAME, size=14)
        self.f_petit    = tkfont.Font(family=FONT_NAME, size=11)

        self.profils = charger_profils()
        self.joueur_actif = None
        self._img_refs = []  # garder les references aux PhotoImage

        self.container = tk.Frame(self, bg=COL_BG)
        self.container.pack(fill="both", expand=True)
        self.page = None

        self.afficher_banniere()
        self.montrer(PageSelection if self.profils else PageGalerie)

    def afficher_banniere(self):
        b = tk.Frame(self, bg=COL_BG, height=84)
        b.pack(fill="x", side="top"); b.pack_propagate(False)
        s = tk.Canvas(b, width=64, height=64, bg=COL_BG, highlightthickness=0)
        s.place(x=36, y=12)
        for i, c in enumerate(["#ff9e2c", "#ff7e3d", "#ff5e5e", "#ff487f", "#ff3690", "#ff2e97"]):
            s.create_rectangle(6, 8+i*8, 58, 13+i*8, fill=c, outline="")
        tk.Label(b, text="OMNI CONSOLE", font=self.f_titre, fg=COL_MAGENTA, bg=COL_BG).place(x=115, y=18)
        tk.Frame(b, bg=COL_CYAN, height=3).place(x=117, y=66, width=360)

    def montrer(self, PageClass, **kw):
        if self.page is not None:
            self.page.destroy()
        self._img_refs = []
        wrap = tk.Frame(self.container, bg=COL_BG)
        wrap.pack(fill="both", expand=True)
        wrap.grid_rowconfigure(0, weight=1); wrap.grid_columnconfigure(0, weight=1)
        self.page = wrap
        PageClass(wrap, self, **kw).grid(row=0, column=0)

    def garder(self, img):
        self._img_refs.append(img)
        return img


def bouton(parent, texte, commande, couleur=COL_CYAN, largeur=16):
    b = tk.Label(parent, text=texte, font=(FONT_NAME, 14, "bold"),
                 fg=COL_BG, bg=couleur, width=largeur, pady=10, cursor="hand2")
    b.bind("<Button-1>", lambda e: commande())
    b.bind("<Enter>", lambda e: b.configure(bg=COL_MAGENTA, fg=COL_TEXT))
    b.bind("<Leave>", lambda e: b.configure(bg=couleur, fg=COL_BG))
    return b


# ===========================================================================
# Page : Selection d'un joueur existant
# ===========================================================================
class PageSelection(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        tk.Label(self, text="Qui joue ?", font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack(pady=(0, 4))
        tk.Label(self, text="Choisissez votre profil ou ajoutez un joueur.",
                 font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(pady=(0, 20))
        grille = tk.Frame(self, bg=COL_BG); grille.pack()
        LW, LH = 150, 200
        col = 0
        for prof in app.profils:
            img = carte_avec_cadre(prof["planche"], prof["ligne"], prof["colonne"],
                                   LW, LH, prof.get("couleur", "#ff2e97"), prof["nom"])
            if img:
                app.garder(img)
                lbl = tk.Label(grille, image=img, bg=COL_BG, cursor="hand2")
                lbl.grid(row=0, column=col, padx=12, pady=10)
                lbl.bind("<Button-1>", lambda e, p=prof: self.choisir(p))
            col += 1
        # Tuile ajouter
        cv = tk.Canvas(grille, width=LW+28, height=LH+46, bg=COL_PANEL, highlightthickness=0, cursor="hand2")
        cv.grid(row=0, column=col, padx=12, pady=10)
        cv.create_rectangle(4, 4, LW+24, LH+42, outline=COL_CYAN, width=2)
        cv.create_oval((LW+28)/2-28, (LH+46)/2-40, (LW+28)/2+28, (LH+46)/2+16, outline=COL_CYAN, width=3)
        cv.create_text((LW+28)/2, (LH+46)/2-12, text="+", font=(FONT_NAME, 36, "bold"), fill=COL_CYAN)
        cv.create_text((LW+28)/2, (LH+46)/2+44, text="Ajouter", font=(FONT_NAME, 13), fill=COL_CYAN)
        cv.bind("<Button-1>", lambda e: app.montrer(PageGalerie))

    def choisir(self, prof):
        self.app.joueur_actif = prof
        self.app.montrer(PageAccueil)


# ===========================================================================
# Page : Galerie de cartes + creation
# ===========================================================================
class PageGalerie(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        self.carte_sel = None      # (planche, ligne, colonne)
        self.couleur = COULEURS_NEON[0]

        premier = len(app.profils) == 0
        tk.Label(self, text="Bienvenue !" if premier else "Nouvelle carte",
                 font=app.f_titre, fg=COL_TEXT, bg=COL_BG).pack(pady=(0, 2))
        tk.Label(self, text="Choisissez votre carte de joueur.",
                 font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(pady=(0, 12))

        corps = tk.Frame(self, bg=COL_BG); corps.pack(fill="both", expand=True)

        # Galerie scrollable a gauche
        gauche = tk.Frame(corps, bg=COL_BG)
        gauche.pack(side="left", padx=(0, 20))
        canvas = tk.Canvas(gauche, bg=COL_BG, highlightthickness=0, width=720, height=430)
        scroll = tk.Scrollbar(gauche, orient="vertical", command=canvas.yview)
        self.grille = tk.Frame(canvas, bg=COL_BG)
        self.grille.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.grille, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        # molette
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        self.vignettes = {}
        cartes = toutes_les_cartes()
        CW, CH = 100, 133
        ncol = 6
        for i, (pl, r, c) in enumerate(cartes):
            img = carte_avec_cadre(pl, r, c, CW, CH, self.couleur)
            if not img:
                continue
            app.garder(img)
            lbl = tk.Label(self.grille, image=img, bg=COL_BG, cursor="hand2")
            lbl.grid(row=i // ncol, column=i % ncol, padx=4, pady=4)
            lbl.bind("<Button-1>", lambda e, key=(pl, r, c): self.selectionner(key))
            self.vignettes[(pl, r, c)] = lbl
        # Panneau droit : apercu + nom + couleur + valider
        droite = tk.Frame(corps, bg=COL_BG); droite.pack(side="left")
        self.apercu = tk.Label(droite, bg=COL_BG); self.apercu.pack()
        tk.Label(droite, text="Nom", font=app.f_normal, fg=COL_CYAN, bg=COL_BG).pack(anchor="w", pady=(14, 0))
        self.entry = tk.Entry(droite, font=app.f_soustitre, bg=COL_PANEL, fg=COL_TEXT,
                              insertbackground=COL_MAGENTA, relief="flat", width=16)
        self.entry.pack(pady=(6, 12), ipady=6)
        self.entry.bind("<KeyRelease>", lambda e: self.maj_apercu())
        self.entry.focus_set()
        tk.Label(droite, text="Couleur du cadre", font=app.f_normal, fg=COL_CYAN, bg=COL_BG).pack(anchor="w")
        lig = tk.Frame(droite, bg=COL_BG); lig.pack(anchor="w", pady=(6, 14))
        for hexa in COULEURS_NEON:
            cc = tk.Canvas(lig, width=28, height=28, bg=COL_BG, highlightthickness=0, cursor="hand2")
            self._past(cc, hexa, hexa == self.couleur); cc.pack(side="left", padx=3)
            cc.bind("<Button-1>", lambda e, h=hexa, lg=lig: self.set_couleur(h, lg))
        bas = tk.Frame(droite, bg=COL_BG); bas.pack(pady=(6, 0))
        if not premier:
            bouton(bas, "Retour", lambda: app.montrer(PageSelection),
                   couleur=COL_DIM, largeur=10).pack(side="left", padx=6)
        bouton(bas, "Valider", self.valider, couleur=COL_OK, largeur=12).pack(side="left", padx=6)

        # Selection par defaut (maintenant que entry et apercu existent)
        cartes_dispo = toutes_les_cartes()
        if cartes_dispo:
            self.selectionner(cartes_dispo[0])

    def _past(self, canvas, couleur, actif):
        canvas.delete("all")
        if actif: canvas.create_oval(1, 1, 27, 27, outline=COL_CYAN, width=2)
        canvas.create_oval(4, 4, 24, 24, fill=couleur, outline="")

    def set_couleur(self, hexa, lig):
        self.couleur = hexa
        for wc, h in zip([w for w in lig.winfo_children() if isinstance(w, tk.Canvas)], COULEURS_NEON):
            self._past(wc, h, h == hexa)
        self.maj_apercu()

    def selectionner(self, key):
        # remettre l'ancienne vignette normale, marquer la nouvelle
        self.carte_sel = key
        self.maj_apercu()

    def maj_apercu(self):
        if not self.carte_sel:
            return
        pl, r, c = self.carte_sel
        nom = self.entry.get().strip() or "Joueur"
        img = carte_avec_cadre(pl, r, c, 210, 280, self.couleur, nom, actif=True)
        if img:
            self.app.garder(img)
            self.apercu.configure(image=img)
            self.apercu.image = img

    def valider(self):
        if not self.carte_sel:
            return
        pl, r, c = self.carte_sel
        nom = self.entry.get().strip() or "Joueur"
        self.app.profils.append({"nom": nom, "planche": pl, "ligne": r, "colonne": c,
                                 "couleur": self.couleur})
        sauver_profils(self.app.profils)
        self.app.montrer(PageSelection)


# ===========================================================================
# Page : Accueil du joueur (bibliotheque a venir)
# ===========================================================================
class PageAccueil(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL_BG)
        self.app = app
        j = app.joueur_actif
        haut = tk.Frame(self, bg=COL_BG); haut.pack(pady=(0, 20))
        img = carte_avec_cadre(j["planche"], j["ligne"], j["colonne"], 90, 120,
                               j.get("couleur", "#ff2e97"), j["nom"])
        if img:
            app.garder(img)
            tk.Label(haut, image=img, bg=COL_BG).pack(side="left", padx=(0, 20))
        tk.Label(haut, text=f"Bonjour {j['nom']}", font=app.f_titre,
                 fg=COL_TEXT, bg=COL_BG).pack(side="left")

        tk.Label(self, text="Votre bibliotheque de jeux apparaitra ici.",
                 font=app.f_soustitre, fg=COL_DIM, bg=COL_BG).pack(pady=(0, 8))
        tk.Label(self, text="(Bibliotheque et plateformes : prochaine etape)",
                 font=app.f_petit, fg=COL_DIM, bg=COL_BG).pack(pady=(0, 24))
        bouton(self, "Changer de joueur", lambda: app.montrer(PageSelection),
               couleur=COL_CYAN, largeur=18).pack()


if __name__ == "__main__":
    OmniConsole().mainloop()
