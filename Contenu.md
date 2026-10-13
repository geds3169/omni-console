# Contenu de l'archive

Projet Omni Console, archive du 6 octobre 2026 (révision après audit).

## Documents de cadrage
| Fichier | Rôle |
|---|---|
| `CAHIER-DES-CHARGES.md` | Ce que le projet doit être, et ce qu'il refuse d'être |
| `ETAT-DU-PROJET.md` | Document de reprise : ce qui marche, ce qui casse, les pièges, les commandes |
| `ROADMAP.md` | Suite des travaux |
| `CONTENU.md` | Ce fichier |

## Code
| Fichier | Rôle | Empreinte MD5 |
|---|---|---|
| `omni-build.sh` | Construction de l'ISO | `b8bfb7ef4455f3da5bbb69de75696c15` |
| `omni-installer.py` | Installateur graphique | `31e41bad174a6c9cc63796fd87aa79a4` |
| `omni-console.py` | Interface joueurs, lancement des plateformes | `56ce892526bee3741cea1ba2d5852f89` |

## Contrôle
| Fichier | Rôle |
|---|---|
| `controle.sh` | Syntaxe, analyse statique, tests, interface sous écran virtuel, empreintes |
| `tests/` | Tests utilisés par `controle.sh` |

## Ressources
- `cartes/` — quatre planches steampunk 2304x1792
- `concepts/` — recherches graphiques, planches Firefly, exemple de cadre néon, tuile SVG par plateforme
- `sons/` — `omni-hover`, `omni-select`, `omni-valid` et la musique `pont_de_verre_instru.ogg`
- `plymouth/` — fond, éclairs, `omni.plymouth` et deux variantes de `omni.script`, thème non encore intégré au build

## Pièces de travail
- `journaux/epic-install.log` — le journal qui contient les deux fautes Proton du 6 octobre, point de reprise
- `journaux/omni-build.log` — trace d'un build
- `outils/OVMF_VARS.fd` — variables UEFI pour les essais en machine virtuelle
- `versions-precedentes/` — états antérieurs des trois fichiers, à ne consulter qu'en cas de régression

## Absent
L'ISO produite, trop volumineuse. Elle se reconstruit avec `sudo ./omni-build.sh --clean-all`.
