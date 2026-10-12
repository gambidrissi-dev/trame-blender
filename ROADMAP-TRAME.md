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
| 4 | Poteau : 1 clic + section/hauteur | |
| 5 | Toit : contour + type (plat, 1 pan, 2 pans, 4 pans), pente, épaisseur | |
| 6 | Escalier : 2 clics (départ, direction) + largeur, hauteur à franchir | |
| 7 | Porte : sens et côté d'ouverture ; raccord des murs accrochés à un mur existant | |
| 8 | Saisie de la longueur au clavier pendant le tracé | |
| 9 | Étages : panneau, étage actif, ajouter un étage, hauteur des murs = hauteur d'étage | |
| 10 | Écran Trame : panneau « Trame » (outils, étages, 3D), boîte à outils réduite aux outils d'archi | |
| 11 | Vue 3D dans une fenêtre à part (un bouton) | |
| 12 | Coupe : 2 clics → vue en coupe | |
| 13 | Enregistrer / ouvrir en IFC depuis le panneau Trame | |
| 14 | Test « maison R+1 » de bout en bout + publication | |

## Hors périmètre de cette mission
Cotation, nomenclatures, mise en page de planches, rendu de plan hachuré par matériau en temps réel
(les murs coupés hachurés existent dans les dessins SVG de Bonsai, pas encore dans la vue).
