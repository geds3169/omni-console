"""Fumee de l'interface (mode demo, ecran virtuel) : pages, icones d'etat, appui long, chemins pfx."""
import importlib.util, os, sys, time, tempfile
os.environ["OMNI_DEMO"] = "1"
home = tempfile.mkdtemp(); os.environ["HOME"] = home
spec = importlib.util.spec_from_file_location("con", os.path.join(os.path.dirname(__file__), "..", "omni-console.py"))
con = importlib.util.module_from_spec(spec); spec.loader.exec_module(con)
SORTIE = os.environ.get("SORTIE", home)

# --- fonctions pures ---
assert con.debit_lisible(1572864) == "1.5 Mo/s" and con.debit_lisible(2048) == "2 Ko/s"
con.PROFIL_COURANT["id"] = "p1"
assert con.racine_wine("epic").endswith("/launchers/epic/pfx")
d = con.dossier_installation("epic"); assert os.path.isdir(d) and os.path.isabs(d) and d != "/"
env = con.env_proton("epic")
assert env["STEAM_COMPAT_INSTALL_PATH"] == d and os.path.isdir(env["STEAM_COMPAT_INSTALL_PATH"])
os.environ["STEAM_COMPAT_INSTALL_PATH"] = ""        # une valeur heritee vide ne doit pas gagner
assert con.env_proton("epic")["STEAM_COMPAT_INSTALL_PATH"] == d
assert con.chemin_windows("/a/b/c.msi") == "Z:\\a\\b\\c.msi"
v = con.strategies_installation("epic", "/x/EpicInstaller.msi")
assert [n for n, _ in v][0].startswith("msiexec") and v[-1][0] == "msi direct", v
assert all(a[0] != "wine" and "/files/bin/wine" not in a[0] for _, a in v)       # plus de binaire wine donne a umu
assert v[0][1][1:] == ["/i", "Z:\\x\\EpicInstaller.msi", "/qn"]
con.noter_recette("epic", "msiexec, chemin du systeme")
assert con.strategies_installation("epic", "/x/E.msi")[0][0] == "msiexec, chemin du systeme"    # recette memorisee en premier
assert con.strategies_installation("ea", "/x/EA.exe")[0][1] == ["/x/EA.exe", "/quiet"]
assert con.LAUNCHERS["ubisoft"]["proton"] == "ubisoft"
attendu = "ubisoft" if os.path.isfile("/opt/omni/proton-ubisoft/toolmanifest.vdf") else "defaut"   # repli si non installe
assert con.variante_proton("ubisoft") == attendu
# jeux Epic : le manifeste est cherche DANS pfx
man = os.path.join(con.racine_wine("epic"), "drive_c/ProgramData/Epic/EpicGamesLauncher/Data/Manifests")
os.makedirs(man); open(man + "/a.item", "w").write('{"AppName":"X","DisplayName":"Jeu test","bIsApplication":true}')
con.DEMO = False
assert [j["titre"] for j in con.jeux_epic()] == ["Jeu test"]
con.DEMO = True

# --- interface ---
app = con.OmniConsole()
def pump(t):
    fin = time.time() + t
    while time.time() < fin: app.update(); time.sleep(0.02)
def photo(n): pump(0.4); os.system("import -window root %s/%s.png" % (SORTIE, n))
pump(0.8)
app.profils[:] = [{"id": "p1", "nom": "Alex", "planche": "planche1", "ligne": 0, "colonne": 0, "niveau": 3,
                   "derniere_activite": time.time(), "plateformes": ["steam", "epic"], "jeux": {}}]
app.choisir_joueur(app.profils[0]); app.montrer(con.PageBibliotheque)
app.systeme.relever(); pump(0.5); photo("c1_bibliotheque")
assert app.systeme.etat["reseau"] == "wifi"

# appui court hors jeu : ouvre le menu
app.en_arriere_plan = False
app.file_manette.put("GUIDE_BAS"); pump(0.1); app.file_manette.put("GUIDE_HAUT"); pump(0.3)
assert app._menu is not None, "appui court hors jeu"
app.fermer_menu()
# appui long : cercle puis menu
app.file_manette.put("GUIDE_BAS"); pump(0.5)
assert app._cercle is not None, "le cercle doit apparaitre"
photo("c2_cercle")
pump(0.6)
assert app._menu is not None and app._cercle is None, "menu ouvert apres l'appui long"
app.file_manette.put("GUIDE_HAUT"); pump(0.2)
photo("c3_menu")
# appui sur Guide, menu ouvert : ferme
app.file_manette.put("GUIDE_BAS"); pump(0.2); app.file_manette.put("GUIDE_HAUT"); pump(0.2)
assert app._menu is None
# dans un jeu : un appui court ne fait rien ; un appui long ouvre le menu
app.en_arriere_plan = True
app.file_manette.put("GUIDE_BAS"); pump(0.1); app.file_manette.put("GUIDE_HAUT"); pump(0.3)
assert app._menu is None, "appui court dans un jeu : reserve a Steam"
app.file_manette.put("COMBO_BAS"); pump(1.2)
assert app._menu is not None, "Select+Start maintenus"
app.file_manette.put("COMBO_HAUT"); pump(0.2); app.fermer_menu(); app.en_arriere_plan = False

# evenements de branchement
app.systeme.evenements.put(("manette", "Xbox Wireless Controller", True)); pump(2.5)
photo("c4_branchement")
app.montrer(con.PageSelection); pump(0.4)
app.choisir_joueur(app.profils[0])
for page in (con.PagePlateformes, con.PageReglages, con.PageStockage, con.PageReseau, con.PageAudio, con.PageAccessibilite):
    app.montrer(page); pump(0.4)
app.montrer(con.PageSelection); photo("c5_selection")
# menu d'alimentation : sous-menu, annulation, tuile des reglages
app.ouvrir_menu(); pump(0.2); m = app._menu
assert m.entrees[-1][0] == "Éteindre"
m.pos = len(m.entrees) - 1; m.commande("A"); pump(0.2)
assert m.alim and [e[0] for e in m.entrees] == ["Éteindre la console", "Redémarrer", "Annuler"]
photo("c6_alimentation")
m.commande("B"); assert not m.alim and m.pos == len(m.entrees) - 1
app.fermer_menu(); app.ouvrir_menu_alim(); pump(0.2); assert app._menu.alim; app.fermer_menu()
print("GUI CONSOLE OK")
app.destroy()
