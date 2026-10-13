# Trame — roadmap « Archicad-like »

Objectif : un archi qui connaît Archicad ouvre Trame et fait l'APS d'une maison sans formation :
murs, dalles, toit, portes, fenêtres, poteaux, escalier, plusieurs étages, plan, coupe, 3D, fichier IFC.

Principe de chaque outil : **on clique dans le plan, puis une fenêtre de réglages**, valeurs mémorisées,
types créés et nommés tout seuls. Blender et Bonsai restent le moteur, jamais l'interface.

## Définition de « terminé »
Un test automatique construit une maison R+1 (murs, dalles, toit, portes, fenêtres, poteau, escalier,
2 étages) uniquement avec les outils Trame, l'enregistre en IFC, la rouvre et retrouve tous les éléments.
Et un démarrage réel de Blender montre l'écran Trame prêt à dessiner.

## Étapes
| # | Étape | État |
|---|-------|------|
| 1 | Démarrage prêt à dessiner (projet, vue en plan, Outil Mur, français) | fait |
| 2 | Mur : 2 clics + réglages, enchaînement, fermeture, accroche aux extrémités | fait |
| 3 | Dalle, Porte, Fenêtre | fait |
| 4 | Poteau : 1 clic + section/hauteur | fait |
| 5 | Toit : contour + type (plat, 1 pan, 2 pans, 4 pans), pente, épaisseur | fait |
| 6 | Escalier : 2 clics (départ, direction) + largeur, hauteur à franchir | fait |
| 7 | Porte : sens et côté d'ouverture ; raccord des murs accrochés à un mur existant | fait |
| 8 | Saisie de la longueur au clavier pendant le tracé | fait |
| 9 | Étages : panneau, étage actif, ajouter un étage, hauteur des murs = hauteur d'étage | fait |
| 10 | Écran Trame : panneau « Trame » (outils, étages, 3D), boîte à outils réduite aux outils d'archi | fait |
| 11 | Vue 3D dans une fenêtre à part (un bouton) | fait |
| 12 | Coupe : 2 clics → vue en coupe | fait |
| 13 | Enregistrer / ouvrir en IFC depuis le panneau Trame | fait |
| 14 | Test « maison R+1 » de bout en bout + publication | fait |

## Suite
| # | Étape | État |
|---|-------|------|
| 15 | Cotation façon Archicad (points, puis placement de la ligne), cotes IFC « DIMENSION » | fait |
| 16 | Plan : fond blanc, murs/poteaux coupés hachurés par matériau, symboles de portes et fenêtres | fait |

## Phase 2 — fonctionnalités Archicad
| # | Étape | État |
|---|-------|------|
| 17 | Matériaux : créer un matériau (nom, famille de hachure, couleur 3D), le choisir dans les outils | fait |
| 18 | Calques : calques Archicad par défaut, chaque élément sur son calque, afficher/masquer/verrouiller | fait |
| 19 | Vision plan : trait noir sur blanc (vu en traits), étage inférieur en calque de fond, toit du dessus en pointillés | fait |
| 20 | Toiture : débord, toit tracé sur le contour des murs | fait |
| 21 | Escaliers : en L et en U avec palier | |
| 22 | Velux : fenêtre de toit posée dans le pan, toit percé | |
| 23 | Terrain : maillage à partir de points cotés (triangulation), en IFC | |
| 24 | IA : assistant Trame qui construit à partir d'une demande en français (API Claude) | |
| 25 | Tests de bout en bout étendus + publication | |

## Hors périmètre
Nomenclatures, mise en page de planches.
