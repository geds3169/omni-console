# OMNI CONSOLE — État du projet au 5 octobre 2026

Document de reprise : ce qui marche, ce qui ne marche pas, ce qui a été testé
et comment, pour continuer dans une nouvelle discussion sans rien reperdre.

---

## 1. Les trois fichiers du projet

| Fichier | Rôle | Empreinte MD5 |
|---|---|---|
| `omni-build.sh` | fabrication de l'ISO | `3b6cf8932d5d5b3ef711452592f6c4b8` |
| `omni-installer.py` | installateur graphique (dans l'ISO) | `31e41bad174a6c9cc63796fd87aa79a4` |
| `omni-console.py` | interface joueurs (dans l'ISO) | `51fe580cac026ddfc7a3788ee42bff75` |

Les trois doivent se trouver dans `/home/geds/mon-projet/` **avant** de lancer
un build. Vérification en une commande :

```
md5sum /home/geds/mon-projet/omni-*.{sh,py}
```

Base actuelle : **Ubuntu 24.04 (noble)**. Le cahier des charges vise 26.04, à
basculer quand elle sera disponible et éprouvée.

---

## 2. Ce qui fonctionne, vérifié en machine virtuelle

### Fabrication de l'ISO
- Build complet en **13 à 16 minutes**, ISO de 2,6 Go, BIOS et UEFI.
- Système de base, paquets et Proton **conservés en cache** entre deux builds :
  une coupure réseau ne coûte plus un build entier.
- Compression zstd : plus rapide à fabriquer, à installer et à démarrer.
- Mode `--verifier` : contrôle en deux minutes que tous les paquets et
  téléchargements sont disponibles, sans rien construire.
- Une seule fonction (`etape_chroot`) pour toutes les étapes lourdes : script
  déposé, délai maximum, journal séparé, lignes d'erreur affichées.

### Installation
- Partitionnement GPT quatre partitions, formatage, copie, amorçage.
- **Initramfs propre généré pour le système installé** (casper retiré d'abord),
  avec contrôle qu'il ne contient plus aucune trace du live.
- Partition de données montée pendant l'installation, dossiers créés et donnés
  au joueur (sans quoi tout est masqué au démarrage).
- Le support de démarrage est **protégé** : repéré par quatre méthodes, affiché
  avec un cadenas, impossible à sélectionner, et refusé même en forçant.
- Sélection de disque dessinée par Omni, deux états seulement, rien de coché au
  départ.
- Taille de l'interface suivant l'écran, réglable de 70 à 200 %.
- Session du joueur par **service systemd supervisé** (plus de chaîne
  getty → bash → startx). Si l'interface tombe, elle redémarre.
- Compte joueur **sans aucun privilège** : seul le guichet à intentions
  (`/usr/local/sbin/omni-plateforme`) peut agir en administrateur.
- Autodiagnostic `omni-selftest` installé (15 contrôles, critique/facultatif).

### Interface
- Profils par cartes steampunk, bibliothèque, plateformes, réglages,
  accessibilité, clavier à l'écran, menu rapide.
- Journal d'installation façon terminal : étapes horodatées, barre de
  progression, journal brut consultable, causes traduites en clair.
- Échelle 720p / 1080p / 4K vérifiée automatiquement à chaque livraison
  (16 parcours d'interface rejoués).

### Plateformes
- **Steam : installé, ouvert, fenêtre de connexion affichée.** Validé le
  5 octobre en machine virtuelle, sans accélération 3D.
- Émulateurs (RetroArch) et GOG : présents dès l'installation.
- Proton GE-Proton11-7 et umu embarqués dans l'image.

---

## 3. Ce qui ne fonctionne pas encore

### Epic Games — deux fautes identifiées le 6 octobre
Le correctif précédent (confier le `.msi` au wine de Proton) se retourne contre
nous. Journal complet dans `journaux/epic-install.log`.

**Faute 1, propre à Epic.** umu ne reçoit plus l'installateur mais le binaire
wine :
```
Proton: /opt/omni/proton/files/bin/wine
Proton: Executable is a unix path, launching with 'umu.exe'.
```
Proton voit un chemin unix, le passe par son shim `umu.exe`, et lance donc wine
à l'intérieur du préfixe. Rien ne s'installe, et le journal s'arrête sur
`fsync: up and running.` sans autre trace. La cible donnée à umu doit rester
l'installateur. Deux voies à départager par un essai réel, pas par déduction :
laisser umu recevoir le `.msi` tel quel, ou lui donner le chemin Windows complet
de msiexec dans le préfixe plus le `.msi` en lettre de lecteur — jamais le mot
`msiexec` seul, qui est ce que umu avait cherché côté hôte.

**Faute 2, commune à tous les launchers.**
```
Proton: Error: unable to use parent for game drive, path
```
Le chemin est vide après `path`. `STEAM_COMPAT_INSTALL_PATH` est posé sans
valeur, ou pointe sur un dossier qui n'existe pas encore au lancement. Proton
calcule la lettre de lecteur à partir du dossier parent : il lui faut un dossier
réel, absolu, créé avant l'appel, et pas la racine d'une partition. Un
sous-dossier de `/omni-data/cache/` convient.

**Conséquence sur l'architecture.** Une seule fonction de lancement partagée :
elle prépare le préfixe, crée le dossier d'installation, pose l'environnement
une fois pour toutes, et reçoit en paramètre l'installateur plus la version de
Proton. Chaque launcher ne fournit que ces deux informations, ce qui règle du
même coup le cas d'Ubisoft Connect qui demandera un GE-Proton plus ancien.

### EA App et Ubisoft Connect — non testés
Ubisoft Connect est connu pour ne pas s'installer avec les versions récentes de
GE-Proton (incident documenté chez GloriousEggroll et Lutris). Prévoir une
version de Proton différente pour ce launcher.

### Musique de l'installateur
Les sons de l'interface fonctionnent, la musique non. Le fichier
`pont_de_verre_instru.ogg` est désormais dans `sons/` de cette archive. Reste à
vérifier où `omni-build.sh` le copie et où `omni-installer.py` le cherche : les
deux chemins doivent coïncider.

### Console série absente de l'image
Il faut la remettre à la main après chaque installation. À activer d'office
dans le build : une console qu'on ne peut pas diagnostiquer sans démonter son
disque n'est pas réparable.

### Locale générée à chaud
À chaque lancement de conteneur, `en_US.UTF-8` est générée depuis zéro et
`pv-adverb` avertit que le démarrage serait plus rapide si la locale existait au
niveau du système. Sans gravité, mais quelques secondes gagnées à la produire
dans l'image.

### Points anciens toujours ouverts
- Clavier FR choisi à l'installation non appliqué au système installé.
- Plymouth Omni non intégré (Ubuntu encore visible au démarrage).
- Menu grub à cacher et habiller.

---

## 4. Décidé mais pas encore construit

- **Icônes réseau et Bluetooth** en haut à droite, avec débits en temps réel.
- **Carte d'état** quand on branche une manette, un volant, une clé, un disque.
- **Écran d'appairage** Bluetooth avec images (Joy-Con, Wiimote, manettes).
- **Appui long sur le bouton central** pour le menu Omni, cercle de progression,
  Select + Start maintenus en secours, ligne « Menu Steam » pendant un jeu Steam.
- **Bibliothèque sur disque externe** : disque adopté, jeux détectés où qu'ils
  soient, bibliothèque qui suit le joueur chez un ami.
- **Pilote NVIDIA** installé en arrière-plan après détection au démarrage.
- **Cliché avant mise à jour** et retour en arrière automatique après deux
  démarrages ratés.

---

## 5. Les pièges rencontrés, et leur cause réelle

À garder en tête : chacun a coûté des jours parce que le message d'erreur
désignait le mauvais coupable.

| Symptôme affiché | Cause réelle |
|---|---|
| « Steam now requires user namespaces » | l'outil d'isolation lancé par Omni (`setpriv --bounding-set`) refusait de s'exécuter, Steam n'était jamais lancé |
| `bwrap: Permission denied` (Epic) | Proton rangé sous `/usr`, que son conteneur refuse ; déplacé dans `/opt/omni/proton` |
| Steam « s'arrête avant la fin » | Steam se relance lui-même, le processus surveillé se termine normalement |
| Steam « n'affiche aucune fenêtre » | deux minutes d'attente, alors que le premier affichage sans 3D en demande dix |
| Installation bloquée 30 min | `/dev/pts` créé en double dans le chroot, la préconfiguration attendait un terminal |
| `Permission denied: /omni-data` | partition de données non montée pendant l'installation, donc préparée au mauvais endroit |
| Pas de son | serveur audio jamais démarré (pas de session utilisateur systemd) |
| Pas de réseau | NetworkManager ne gère que le Wi-Fi par défaut, le câble était ignoré |

**Leçon de méthode** : ne jamais croire un message d'erreur sur parole. Lire ce
que le programme écrit vraiment. Pour Steam, c'est dans
`~/.local/share/Steam/logs/console-linux.txt`, qu'Omni recopie désormais dans
son journal brut.

---

## 6. Commandes de travail

### Construire
```
sudo ./omni-build.sh --verifier     # contrôle sans rien construire (2 min)
sudo ./omni-build.sh --keep-base    # garde le système de base (rapide)
sudo ./omni-build.sh --clean-all    # repart de zéro
```

### Installer dans la VM de test
```
qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m 2G -machine type=q35,accel=kvm \
  -vga std -display gtk,gl=off,zoom-to-fit=on \
  -drive file=/home/geds/disque-test.qcow2,format=qcow2,if=virtio \
  -cdrom /root/omni-build/output/omni-console.iso -boot order=d \
  -nic user -audiodev pa,id=snd0 -device ich9-intel-hda -device hda-output,audiodev=snd0
```

### Remettre la console série (après chaque installation, VM éteinte)
```
sudo modprobe nbd max_part=8
sudo qemu-nbd --connect=/dev/nbd0 /home/geds/disque-test.qcow2
sudo mount /dev/nbd0p3 /mnt
sudo sed -i 's/quiet splash loglevel=0/quiet splash loglevel=0 console=tty0 console=ttyS0,115200/' /mnt/boot/grub/grub.cfg
sudo mkdir -p /mnt/etc/systemd/system/getty.target.wants
sudo ln -sf /usr/lib/systemd/system/serial-getty@.service /mnt/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service
sudo umount /mnt && sudo qemu-nbd --disconnect /dev/nbd0
```

### Tester
```
qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m 2G -machine type=q35,accel=kvm \
  -vga std -display gtk,gl=off,zoom-to-fit=on \
  -drive file=/home/geds/disque-test.qcow2,format=qcow2,if=virtio \
  -boot order=c,menu=off -nic user \
  -audiodev pa,id=snd0 -device ich9-intel-hda -device hda-output,audiodev=snd0 \
  -serial mon:stdio
```
Compte `omni`, sans mot de passe. Partition 3 = système, partition 4 = données.

### Remplacer un fichier sans reconstruire l'ISO (VM éteinte)
```
sudo modprobe nbd max_part=8
sudo qemu-nbd --connect=/dev/nbd0 /home/geds/disque-test.qcow2
sudo mount /dev/nbd0p3 /mnt
sudo cp /home/geds/mon-projet/omni-console.py /mnt/usr/local/share/omni/ui/omni-console.py
sudo md5sum /mnt/usr/local/share/omni/ui/omni-console.py
sudo umount /mnt && sudo qemu-nbd --disconnect /dev/nbd0
```

### Diagnostiquer depuis la console de la machine
```
omni-selftest                                   # contrôle de santé complet
tail -20 ~/.omni/journaux/steam.log             # journal Omni
tail -30 ~/.local/share/Steam/logs/console-linux.txt   # ce que Steam écrit vraiment
tail -30 ~/.omni/journaux/epic-install.log      # Proton, launchers Windows
ls -la /omni-data/                              # droits du dossier de données
```

### Mode démonstration (sans machine ni réseau)
```
OMNI_DEMO=1 python3 omni-console.py
```

---

## 7. Machine d'atelier : limites connues

3,4 Go de mémoire seulement, d'où les lenteurs. Ne jamais faire tourner la VM
de test pendant un build. Si la mémoire manque, le système tue des processus et
la fenêtre QEMU disparaît alors que la machine virtuelle continue.

Vérifier : `free -h` et `pgrep -af qemu-system`.

---

## 8. Arbitrages pris, et pourquoi

- **Launchers officiels sous Proton, pas Heroic ni Lutris.** Choix du cahier des
  charges : l'utilisateur ne doit jamais voir un outil tiers.
- **Proton plutôt qu'un Windows minimal.** Un Windows allégé ferait tourner plus
  de jeux, anti-triche compris, mais imposerait licences, pilotes à chasser,
  mises à jour subies, et exclurait les machines anciennes, qui sont justement
  la cible du projet.
- **Steam non embarqué dans l'ISO par défaut.** Le contrat d'abonnement de Valve
  limite la redistribution de son client. Option `STEAM_EMBARQUE=1` pour un
  usage personnel.
- **X11, pas Wayland.** Moins de surprises avec Steam et Proton.
- **Compte joueur sans sudo.** Les opérations privilégiées passent par un
  guichet qui n'accepte que des intentions connues.
- **Les anti-triche ne marcheront pas.** À afficher honnêtement sur les tuiles,
  pas à contourner.


---

## 9. Révision du 6 octobre 2026 (audit complet du code)

Les trois fichiers ont été relus ligne à ligne. `./controle.sh` rejoue 24 tests de
l'installateur, 27 contrôles des fonctions du build dans un faux chroot et deux
parcours d'interface sous écran virtuel. Aucun de ces contrôles ne remplace un essai
sur la machine : ce qui n'a pas pu être testé est marqué « à vérifier ».

### Corrigé
- **Musique** : le build la prend dans `sons/` (repli sur la racine du projet) et la dépose
  dans `/usr/local/share/omni/musique/`, que l'installateur lit. Les sons d'interface sont
  copiés une fois, `ui/sons` est un lien.
- **Chemins du projet** : plus de `/home/geds/mon-projet` en dur ; un fichier du projet absent
  arrête le build avec un message clair. Le thème Plymouth est cherché dans
  `omni-plymouth-theme/` ou `plymouth/`.
- **Console série** : active d'office (option `CONSOLE_SERIE`, 1 par défaut, à mettre à 0 pour
  une image de diffusion) : lien du getty dans l'image, arguments du noyau et `plymouth.ignore-serial-consoles`
  dans le grub installé. Plus de manipulation après installation.
- **Locales** : fr, en, de, pt générées dans l'image (plus de génération à chaud par Proton).
- **Clavier, fuseau, langue** choisis à l'installation : maintenant écrits dans le système
  installé (`/etc/default/keyboard`, `/etc/vconsole.conf`, configuration Xorg, `/etc/timezone`,
  `/etc/localtime`, `/etc/default/locale`) et les services de la console texte sont démasqués.
  **À vérifier** : installer en anglais et contrôler `omni-selftest`, qui teste désormais ces points.
- **Installateur** : plus de faux disque quand `lsblk` échoue ; refus d'un disque monté ; disque
  minimum 24 Go avec partition système de 16 à 30 Go ; 1 % réservé sur la partition de jeux ;
  un seul fil d'installation même si l'écran est redessiné ; écran d'erreur ; journal de chaque
  commande dans `/var/log/omni-installation.log` (copié dans le système installé) ; progression
  de copie mesurée ; grub installé pour UEFI et BIOS (le mode courant est obligatoire, l'autre
  facultatif, chargeur « amovible » en plus) ; thème grub aux couleurs d'Omni (menu toujours caché,
  Maj ou Échap l'affiche) ; groupes inexistants ignorés au lieu de faire échouer `useradd`.
- **Fichiers de session** (service, session du joueur, autostart, selftest) écrits une fois dans
  le build, copiés par l'installateur. L'interface écrit sa sortie dans `~/.omni/journaux/omni-console.log`.
- **Proton** : un seul script (`omni-poser-proton`) pour le build et pour la console ; version
  Ubisoft dédiée (`GE-Proton10-10`, intention `proton-ubisoft`) téléchargée à la demande ; le nom
  d'archive avec ou sans `-x86_64` est essayé. Testé en vrai : téléchargement, décompression, umu.
- **Launchers (Epic, EA, Ubisoft)** : une seule fonction de lancement (`lancer_umu`) ;
  `STEAM_COMPAT_INSTALL_PATH` est un dossier réel créé avant l'appel ; le binaire wine n'est plus
  donné à umu ; le `.msi` d'Epic est tenté par trois voies successives, contrôlées par la présence du
  launcher, la voie gagnante est retenue dans `~/.omni/recettes.json`. **À vérifier sur la machine** :
  c'est le journal `epic-install.log` qui dira quelle voie fonctionne.
- **Chemins `pfx`** : la détection des jeux Epic et le contrôle de fin d'installation cherchaient
  hors de `pfx`.
- Version de l'image : une seule source (`/etc/omni-version`, date du build + empreinte de l'interface).
- Le `pkill` du chroot ne vise plus que les processus de l'étape (il pouvait tuer ceux de l'atelier).

### Ajouté
- Icônes réseau (câble, Wi-Fi, coupé) et Bluetooth en haut à droite, débits en temps réel.
- Messages à l'écran quand une manette ou une clé/un disque est branché ou retiré.
- Appui long sur le bouton Guide (0,8 s, cercle qui se remplit) ou Select + Start maintenus :
  menu Omni, même par-dessus un jeu. Appui court : menu seulement quand Omni est devant.
  **À vérifier avec une vraie manette.**
- Commentaires ajoutés sur toutes les classes et fonctions non triviales.

### Reste à faire
- Ligne « Menu Steam » dans le menu pendant un jeu Steam ; écran d'appairage Bluetooth ;
  bibliothèque sur disque externe ; pilote NVIDIA en arrière-plan ; cliché avant mise à jour.
- Secure Boot (grub signé + shim) : non fait, non testable ici. Les machines BIOS restent prises en
  charge par l'installateur, mais les jeux récents avec anti-triche exigent en pratique UEFI.

## 10. Révision du 8 octobre 2026 : arrêt de la machine
- Installateur : l'arrêt et le redémarrage de fin d'installation passent par `arreter_machine()` (paliers : `systemctl --no-block`, `-f`, `-ff`, puis sysrq), après démontage de `/target`. Cause probable de l'ancien blocage : l'arrêt propre restait suspendu dans la session live. À confirmer sur la VM de test.
- Console : entrée « Éteindre » dans le menu Guide (sous-menu Éteindre / Redémarrer / Annuler) et tuile « Alimentation » dans les Réglages. Nouvelles intentions `eteindre` et `redemarrer` dans `omni-plateforme` (le joueur n'a pas de sudo général).
- Tests : 29 tests installateur, intention du guichet vérifiée dans `test_build.sh`, sous-menu vérifié dans `gui_console.py`.
