"""Fumee de l'interface de l'installateur sous Xvfb : pages, installation simulee,
echec, redessin pendant l'installation (ne doit pas relancer le fil)."""
import importlib.util, os, sys, time, tempfile
spec = importlib.util.spec_from_file_location("inst", os.path.join(os.path.dirname(__file__), "..", "omni-installer.py"))
inst = importlib.util.module_from_spec(spec); spec.loader.exec_module(inst)
tmp = tempfile.mkdtemp()
inst.JOURNAL_INSTALL = tmp + "/install.log"; inst.ETAT_INSTALL = tmp + "/etat"
SORTIE = os.environ.get("SORTIE", tmp)

lancements = []
class FausseInstallation:
    ETAPES = inst.Installation.ETAPES
    mode = "ok"
    def __init__(self, choix, proteges, signaler, cible="/target"):
        self.signaler = signaler; lancements.append(1)
    def executer(self, disque):
        for cle, pct in self.ETAPES[:-1]:
            self.signaler(max(0, pct - 5), cle, "%.1f / 8.0 Go" % (pct / 12.0) if cle == "copy" else "")
            time.sleep(0.5)
        if FausseInstallation.mode == "echec":
            raise inst.ErreurInstall("mkfs.ext4 : /dev/vda3 est en cours d'utilisation")
inst.Installation = FausseInstallation
inst.lister_disques = lambda: [
    {"chemin": "/dev/vda", "octets": 64 * 1024**3, "taille": "64 Go", "modele": "Disque virtuel", "amovible": False, "petit": False},
    {"chemin": "/dev/sdb", "octets": 16 * 1024**3, "taille": "16 Go", "modele": "Cle USB  (USB)", "amovible": True, "petit": True}]
inst.disques_de_demarrage = lambda: set()
inst.lire_fuseaux = lambda: {"Europe": ["Paris", "Berlin"], "America": ["New_York"]}

app = inst.OmniInstaller()
def pump(t):
    fin = time.time() + t
    while time.time() < fin:
        app.update(); time.sleep(0.02)
def photo(nom):
    pump(0.3); os.system("import -window root %s/%s.png" % (SORTIE, nom))
pump(0.5); photo("01_langue")
app.montrer_page(inst.PageDisque); pump(0.3); photo("02_disque")
assert "/dev/sdb" not in app.page_actuelle.winfo_children()[0].marques if hasattr(app.page_actuelle.winfo_children()[0], "marques") else True
page = app.page_actuelle.winfo_children()[0]
assert "/dev/vda" in page.marques and "/dev/sdb" not in page.marques, "le disque trop petit doit etre non selectionnable"
page.choisir("/dev/vda"); app.choix["disque"] = "/dev/vda"; app.choix["fuseau"] = "Europe/Paris"
app.montrer_page(inst.PageConfirmation); photo("03_confirmation")

# installation reussie, avec redessin pendant l'installation
FausseInstallation.mode = "ok"
app.montrer_page(inst.PageInstallation); pump(1.2); photo("04_installation")
n = len(lancements)
app.regler_zoom(0.1); pump(0.3)          # redessine la page : ne doit PAS relancer l'installation
app._taille_connue = (0, 0); app._ecran_change(); pump(0.3)
assert len(lancements) == n == 1, "l'installation a ete relancee (%d)" % len(lancements)
app.regler_zoom(-0.1)
pump(5)
assert app.page_actuelle_classe is inst.PageFin, app.page_actuelle_classe
assert app.install is None
photo("05_fin")

# installation en echec
FausseInstallation.mode = "echec"; lancements.clear()
app.montrer_page(inst.PageInstallation); pump(5)
assert app.page_actuelle_classe is inst.PageErreur, app.page_actuelle_classe
assert app.install is None
photo("06_erreur")
# recommencer repart de zero
app.montrer_page(inst.PageLangue); app.montrer_page(inst.PageInstallation); pump(1)
assert len(lancements) == 2
print("GUI OK")
app.arreter_musique(); app.destroy()
