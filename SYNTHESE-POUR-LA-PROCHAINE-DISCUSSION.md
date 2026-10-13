# Omni Console : synthèse pour la prochaine discussion (6 octobre 2026, mise à jour)

## Où sont les fichiers
Tout est dans le dossier Google Drive « Omni Console » : les trois fichiers de code, controle.sh, tests/, cartes/, sons/, omni-plymouth-theme/, OVMF_VARS.fd, ETAT-DU-PROJET.md (document de reprise complet, section 9 = révision du 6 octobre) et CONTENU.md. Le même projet est dans /home/geds/mon-projet/ sur l'atelier.

Attention : sur le Drive, omni-installer.py est encore l'ancienne version. La version corrigée est celle de l'empreinte ci-dessous, à vérifier avec md5sum dans /home/geds/mon-projet/.

Empreintes MD5 attendues :
- omni-build.sh : b8bfb7ef4455f3da5bbb69de75696c15
- omni-installer.py : 6d480eeb4bc820f03331fe64e2e0441a (l'ancienne 31e41bad... est périmée)
- omni-console.py : 56ce892526bee3741cea1ba2d5852f89

## Contexte
Projet Omni Console : une ISO Ubuntu 24.04 qui transforme un PC en console de salon. L'atelier est une VM sur ma machine perso. Elle sert à construire l'ISO et à la faire tourner dans une VM QEMU imbriquée, avec un disque disque-test.qcow2 et un accès TTY par console série. La musique d'installation est dans sons/. Le support BIOS/Legacy est secondaire : les jeux modernes avec anti-triche exigent en pratique UEFI.

Claude Code est installé sur l'atelier (6 octobre) : il peut lire le projet, lancer controle.sh et les builds, et lire les journaux. Règle : il demande mon accord avant tout sudo, toute suppression et tout build.

## Ce qui a été fait
Audit complet des trois fichiers, puis correction (détail dans ETAT-DU-PROJET.md, section 9).
- Build : plus de chemin en dur ni de copie silencieuse ratée, musique prise dans sons/, console série active d'office, locales générées, thème grub, script unique de pose de Proton avec une version dédiée à Ubisoft (GE-Proton10-10).
- Installateur : plus de faux disque, une seule installation possible, écran d'erreur, journal, clavier, fuseau et langue appliqués au système installé, grub pour UEFI et BIOS.
- Interface : lancement unifié des launchers Windows (trois voies pour le .msi d'Epic), chemins pfx corrigés, icônes réseau et Bluetooth avec débits, messages de branchement, appui long sur Guide ou Select + Start, commentaires ajoutés.
- Vérifié (par Claude, en bac à sable) : analyse statique propre, 27 tests de l'installateur, 27 contrôles du build dans un faux chroot, essais de l'interface sous écran virtuel, pose réelle de Proton et d'umu.

## Correctif du disque de test (6 octobre, après l'audit)
Le disque d'installation n'était plus sélectionnable : un seuil fixe de 24 Go verrouillait le disque de test de l'atelier. Il est remplacé par un minimum calculé d'après la taille réelle du système (casper/filesystem.size, écrite par le build) : taille du système + 30 % de marge + 4 Go pour les jeux, jamais moins de 12 Go, et 16 Go si la taille est inconnue. Un disque de 16 à 20 Go est accepté. Test ajouté (clic réel sur la ligne du disque). L'installateur vit dans l'ISO : un changement demande un nouveau build.

## À vérifier chez moi (non testé)
Un build complet, l'installation Epic (le journal epic-install.log dira quelle voie marche), l'appui long avec une vraie manette, l'installation en anglais avec omni-selftest.

## Où j'en suis
- Je termine le build puis j'installe sur disque-test.qcow2 et je fais un retour.
- L'atelier était à 96 % de disque (1,8 Go libres sur 45) : il faut au moins 25 Go libres. Nettoyage : démonter ce qui est resté monté, supprimer chroot, image et output de /root/omni-build en gardant cache-telechargements (Proton), puis build avec --clean-all.
- Les outils de controle.sh (shellcheck, pyflakes, xvfb, python3-tk, python3-evdev, imagemagick) ne sont pas obligatoires.

## Pas fait
Ligne « Menu Steam » pendant un jeu Steam, appairage Bluetooth, bibliothèque sur disque externe, pilote NVIDIA, snapshots, Secure Boot.
