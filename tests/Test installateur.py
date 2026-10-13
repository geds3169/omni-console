"""Tests de l'installateur : fonctions pures, fichiers de localisation, garde-fous.
Aucun disque ni ecran requis (la logique est separee de l'interface)."""
import importlib.util, os, sys, tempfile, unittest

SPEC = importlib.util.spec_from_file_location("inst", os.path.join(os.path.dirname(__file__), "..", "omni-installer.py"))
inst = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inst)
GO = 1024 ** 3


def _lister_exemple(octets):
    """lister_disques() avec un seul disque de `octets` octets (lsblk simule)."""
    ancien = inst._sortie
    try:
        inst._sortie = lambda cmd: 'NAME="vda" SIZE="%d" MODEL="" TYPE="disk" RM="0" RO="0"' % octets
        return inst.lister_disques()
    finally:
        inst._sortie = ancien


inst.lister_disques_exemple = _lister_exemple


class TestPlan(unittest.TestCase):
    def test_trop_petit(self):
        with self.assertRaises(inst.ErreurInstall):
            inst.plan_partitions(12 * GO, 0)

    def test_bornes_systeme(self):
        # taille du systeme inconnue : minimum 16 Go, systeme = moitie du disque entre 10 et 30 Gio
        self.assertEqual(inst.plan_partitions(16 * GO, 0)["sys_fin"], "10GiB")
        self.assertEqual(inst.plan_partitions(24 * GO, 0)["sys_fin"], "12GiB")
        self.assertEqual(inst.plan_partitions(40 * GO, 0)["sys_fin"], "20GiB")
        self.assertEqual(inst.plan_partitions(2000 * GO, 0)["sys_fin"], "30GiB")

    def test_disque_de_test_20_go_accepte(self):
        # regression : un seuil fixe de 24 Go verrouillait le disque de test de l'atelier
        for go in (16, 18, 20, 21):
            inst.plan_partitions(go * GO, 0)
        self.assertFalse(inst.lister_disques_exemple(20 * GO)[0]["petit"])

    def test_systeme_mesure(self):
        # systeme de 8 Gio : disque minimum = 8 x 1,3 + 4 = 14,4 Gio ; la partition lui laisse 30 % de marge
        self.assertLess(inst.disque_minimal_octets(8 * GO), 15 * GO)
        self.assertEqual(inst.plan_partitions(16 * GO, 8 * GO)["sys_fin"], "11GiB")
        with self.assertRaises(inst.ErreurInstall):
            inst.plan_partitions(14 * GO, 8 * GO)        # 14 < 14,4
        self.assertEqual(inst.plan_partitions(100 * GO, 8 * GO)["sys_fin"], "30GiB")

    def test_toujours_de_la_place_pour_les_jeux(self):
        for go in (16, 20, 30, 100):
            fin = int(inst.plan_partitions(go * GO, 8 * GO)["sys_fin"].replace("GiB", ""))
            self.assertGreaterEqual(go - fin, 3)

    def test_nom_partition(self):
        self.assertEqual(inst.nom_partition("/dev/sda", 3), "/dev/sda3")
        self.assertEqual(inst.nom_partition("/dev/nvme0n1", 3), "/dev/nvme0n1p3")
        self.assertEqual(inst.nom_partition("/dev/mmcblk0", 2), "/dev/mmcblk0p2")
        self.assertEqual(inst.nom_partition("/dev/vda", 4), "/dev/vda4")


class TestLocalisation(unittest.TestCase):
    def fichiers(self, **choix):
        base = {"clavier": "fr", "code_langue": "fr", "fuseau": "Europe/Paris"}
        base.update(choix)
        return inst.fichiers_localisation(base)

    def test_clavier_fr_ecrit_trois_fois(self):
        f = self.fichiers()
        self.assertIn('XKBLAYOUT="fr"', f["/etc/default/keyboard"])
        self.assertEqual(f["/etc/vconsole.conf"], "KEYMAP=fr\n")
        self.assertIn('"XkbLayout" "fr"', f["/etc/X11/xorg.conf.d/00-keyboard.conf"])

    def test_suisse_romand(self):
        f = self.fichiers(clavier="ch", code_langue="fr")
        self.assertEqual(f["/etc/vconsole.conf"], "KEYMAP=fr_CH\n")
        self.assertIn('XKBVARIANT="fr"', f["/etc/default/keyboard"])

    def test_portugais(self):
        f = self.fichiers(clavier="pt", code_langue="pt")
        self.assertEqual(f["/etc/vconsole.conf"], "KEYMAP=pt-latin1\n")
        self.assertEqual(f["/etc/default/locale"], "LANG=pt_PT.UTF-8\n")

    def test_ecriture_et_fuseau(self):
        with tempfile.TemporaryDirectory() as cible:
            os.makedirs(cible + "/usr/share/zoneinfo/Europe")
            open(cible + "/usr/share/zoneinfo/Europe/Paris", "w").close()
            os.makedirs(cible + "/etc/systemd/system")
            os.symlink("/dev/null", cible + "/etc/systemd/system/console-setup.service")
            os.symlink("/dev/null", cible + "/etc/systemd/system/autre.service")
            inst.ecrire_localisation(cible, {"clavier": "fr", "code_langue": "fr", "fuseau": "Europe/Paris"})
            self.assertEqual(os.readlink(cible + "/etc/localtime"), "/usr/share/zoneinfo/Europe/Paris")
            self.assertEqual(open(cible + "/etc/timezone").read(), "Europe/Paris\n")
            self.assertFalse(os.path.lexists(cible + "/etc/systemd/system/console-setup.service"))
            self.assertTrue(os.path.islink(cible + "/etc/systemd/system/autre.service"))  # seuls les services voulus

    def test_fuseau_inconnu_retombe_sur_utc(self):
        with tempfile.TemporaryDirectory() as cible:
            os.makedirs(cible + "/usr/share/zoneinfo")
            open(cible + "/usr/share/zoneinfo/UTC", "w").close()
            inst.ecrire_localisation(cible, {"clavier": "fr", "code_langue": "fr", "fuseau": "Mars/Olympus"})
            self.assertEqual(os.readlink(cible + "/etc/localtime"), "/usr/share/zoneinfo/UTC")
            self.assertEqual(open(cible + "/etc/timezone").read(), "UTC\n")


class TestGrub(unittest.TestCase):
    def test_sans_serie(self):
        c = inst.contenu_grub_defaut({})
        self.assertIn('quiet splash loglevel=0"', c)
        self.assertNotIn("ttyS0", c)
        self.assertIn("GRUB_TIMEOUT_STYLE=hidden", c)

    def test_avec_serie(self):
        c = inst.contenu_grub_defaut({"CONSOLE_SERIE": "1"})
        self.assertIn("console=tty0 console=ttyS0,115200", c)
        self.assertIn("plymouth.ignore-serial-consoles", c)
        # l'ordre compte : la derniere console declaree devient /dev/console
        self.assertLess(c.index("console=tty0"), c.index("console=ttyS0"))

    def test_theme(self):
        c = inst.contenu_grub_defaut({}, theme=True)
        self.assertIn("GRUB_THEME=/boot/grub/themes/omni/theme.txt", c)
        self.assertNotIn("GRUB_THEME", inst.contenu_grub_defaut({}, theme=False))


class TestOutils(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        inst.JOURNAL_INSTALL = os.path.join(self.tmp.name, "install.log")
        inst.ETAT_INSTALL = os.path.join(self.tmp.name, "install.etat")

    def tearDown(self):
        self.tmp.cleanup()

    def test_options_image(self):
        p = os.path.join(self.tmp.name, "opt.conf")
        open(p, "w").write("# commentaire\nCONSOLE_SERIE=1\n\nAUTRE = x\n")
        self.assertEqual(inst.lire_options_image(p), {"CONSOLE_SERIE": "1", "AUTRE": "x"})
        self.assertEqual(inst.lire_options_image(p + ".absent"), {})

    def test_lancer_journalise_et_echoue(self):
        inst.lancer(["true"])
        with self.assertRaises(inst.ErreurInstall):
            inst.lancer(["false"])
        self.assertIsNone(inst.lancer(["commande-inexistante-omni"], tolerant=True))
        self.assertEqual(inst.lancer(["false"], tolerant=True).returncode, 1)
        j = open(inst.JOURNAL_INSTALL).read()
        self.assertIn("$ false", j)
        self.assertIn("code de retour 1", j)

    def test_groupes_existants(self):
        with tempfile.TemporaryDirectory() as c:
            os.makedirs(c + "/etc")
            open(c + "/etc/group", "w").write("audio:x:29:\nvideo:x:44:\n")
            self.assertEqual(inst.groupes_existants(c, ("audio", "bluetooth", "video")), ["audio", "video"])

    def test_musique_cherchee_au_meme_endroit_que_le_build(self):
        with tempfile.TemporaryDirectory() as d:
            ancien = inst.DOSSIERS_MUSIQUE
            try:
                inst.DOSSIERS_MUSIQUE = (d + "/musique", d)
                self.assertEqual(inst.chercher_musique(), "")
                os.makedirs(d + "/musique")
                open(d + "/musique/a.ogg", "w").close()
                self.assertTrue(inst.chercher_musique().endswith("musique/a.ogg"))
            finally:
                inst.DOSSIERS_MUSIQUE = ancien

    def test_pas_de_disque_invente(self):
        # lsblk absent ou en echec : aucun disque (et surtout pas un faux /dev/sda)
        ancien = inst._sortie
        try:
            inst._sortie = lambda cmd: ""
            self.assertEqual(inst.lister_disques(), [])
        finally:
            inst._sortie = ancien

    def test_lister_disques_filtre(self):
        sortie = ('NAME="sda" SIZE="500107862016" MODEL="Samsung SSD" TYPE="disk" RM="0" RO="0"\n'
                  'NAME="sdb" SIZE="16000000000" MODEL="Cle USB" TYPE="disk" RM="1" RO="0"\n'
                  'NAME="loop0" SIZE="1000000000" MODEL="" TYPE="loop" RM="0" RO="1"\n'
                  'NAME="sr0" SIZE="2600000000" MODEL="DVD" TYPE="rom" RM="1" RO="0"\n'
                  'NAME="sdc" SIZE="1000000000" MODEL="Minuscule" TYPE="disk" RM="0" RO="0"\n')
        ancien = inst._sortie
        try:
            inst._sortie = lambda cmd: sortie
            d = inst.lister_disques()
        finally:
            inst._sortie = ancien
        self.assertEqual([x["chemin"] for x in d], ["/dev/sda", "/dev/sdb"])
        self.assertFalse(d[0]["petit"])
        self.assertTrue(d[1]["petit"])      # 16 Go : liste mais non selectionnable
        self.assertTrue(d[1]["amovible"])


class TestGardeFous(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        inst.JOURNAL_INSTALL = os.path.join(self.tmp.name, "install.log")

    def tearDown(self):
        self.tmp.cleanup()

    def test_support_de_demarrage_refuse(self):
        i = inst.Installation({}, {"/dev/null"}, lambda *a: None, cible=self.tmp.name)
        with self.assertRaises(inst.ErreurInstall) as e:
            i.garde_fous("/dev/null")
        self.assertIn("support de demarrage", str(e.exception))

    def test_disque_invalide_refuse(self):
        i = inst.Installation({}, set(), lambda *a: None, cible=self.tmp.name)
        for mauvais in ("", "sda", "/etc/passwd-inexistant", "/dev/disque-qui-n-existe-pas"):
            with self.assertRaises(inst.ErreurInstall):
                i.garde_fous(mauvais)

    def test_fichier_session_absent_est_une_image_incomplete(self):
        i = inst.Installation({}, set(), lambda *a: None, cible=self.tmp.name)
        ancien = inst.DOSSIER_SYSTEME
        try:
            inst.DOSSIER_SYSTEME = self.tmp.name + "/vide"
            with self.assertRaises(inst.ErreurInstall):
                i.poser_fichier_systeme("omni-console.service", "/x/y", 0o644)
        finally:
            inst.DOSSIER_SYSTEME = ancien

    def test_poser_fichier_systeme(self):
        src = self.tmp.name + "/src"
        os.makedirs(src)
        open(src + "/f", "w").write("contenu")
        ancien = inst.DOSSIER_SYSTEME
        try:
            inst.DOSSIER_SYSTEME = src
            cible = self.tmp.name + "/cible"
            i = inst.Installation({}, set(), lambda *a: None, cible=cible)
            i.poser_fichier_systeme("f", "/a/b/f", 0o755)
            self.assertEqual(open(cible + "/a/b/f").read(), "contenu")
            self.assertEqual(os.stat(cible + "/a/b/f").st_mode & 0o777, 0o755)
        finally:
            inst.DOSSIER_SYSTEME = ancien

    def test_etapes_croissantes(self):
        pcts = [p for _, p in inst.Installation.ETAPES]
        self.assertEqual(pcts, sorted(pcts))
        self.assertEqual(pcts[-1], 100)
        recu = []
        i = inst.Installation({}, set(), lambda *a: recu.append(a), cible=self.tmp.name)
        inst.ETAT_INSTALL = self.tmp.name + "/etat"
        for cle, _ in inst.Installation.ETAPES:
            i.etape(cle)
        self.assertEqual([r[1] for r in recu], [c for c, _ in inst.Installation.ETAPES])
        self.assertEqual([r[0] for r in recu], sorted(r[0] for r in recu))


class TestTraductions(unittest.TestCase):
    def test_toutes_les_cles_dans_toutes_les_langues(self):
        reference = set(inst.T["fr"])
        for lg, textes in inst.T.items():
            self.assertEqual(set(textes) ^ reference, set(), "cles differentes en %s" % lg)
        # toutes les etapes ont un libelle
        for lg in inst.T:
            for cle, _ in inst.Installation.ETAPES:
                self.assertIn(cle, inst.T[lg], "%s : libelle absent pour l'etape %s" % (lg, cle))

    def test_slides_meme_nombre(self):
        n = len(inst.T["fr"]["slides"])
        for lg in inst.T:
            self.assertEqual(len(inst.T[lg]["slides"]), n)


class TestArret(unittest.TestCase):
    """L'arret doit etre tenace : paliers dans l'ordre, demontage et sync avant."""

    def test_paliers(self):
        appels, pauses = [], []
        vrai = (inst.lancer, inst.time.sleep, inst.journaliser)
        inst.lancer = lambda cmd, **kw: appels.append(cmd)
        inst.time.sleep = lambda n: pauses.append(n)
        inst.journaliser = lambda t: None
        try:
            inst.arreter_machine("reboot")
        finally:
            inst.lancer, inst.time.sleep, inst.journaliser = vrai
        self.assertEqual(appels[0], ["sync"])
        self.assertIn(["umount", "-R", "-l", "/target"], appels)
        systemctl = [c for c in appels if c[0] == "systemctl"]
        self.assertEqual(systemctl, [["systemctl", "--no-block", "reboot"], ["systemctl", "-f", "reboot"],
                                     ["systemctl", "-ff", "reboot"]])
        self.assertEqual(len(pauses), 3)

    def test_mode_invalide(self):
        with self.assertRaises(KeyError):
            inst.arreter_machine("n'importe quoi")


if __name__ == "__main__":
    unittest.main(verbosity=1)
