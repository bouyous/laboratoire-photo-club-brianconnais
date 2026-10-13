# Poussières du capteur : propositions et retouche locale

Correctif du 9 octobre 2026, validé sur le NEF et le JPEG _DSC2312 fournis par l’utilisateur.
Le besoin concerne uniquement les taches du capteur ; les saletés du sujet doivent rester intactes.

La détection précédente saturait sa limite de 60 résultats. Elle sélectionnait des motifs du
support et des détails des feuilles, puis appliquait immédiatement des retouches. La recherche
de zone source et la correction de tonalité pouvaient produire des anneaux et des motifs copiés.

Le nouveau détecteur recherche plusieurs tailles, vérifie la symétrie du profil sombre,
l’atténuation neutre des couleurs, la régularité du fond et sa texture fine. Les petits points
de bruit, les détails colorés et les bords tronqués sont filtrés. Le seuil peut être assoupli
uniquement sur les fonds particulièrement réguliers pour préserver les taches faibles.
Le score est relatif ; il n’est pas une probabilité calibrée qu’un motif soit une poussière.

**Rechercher les poussières** ne modifie aucun pixel. Les cercles jaunes sont des propositions,
toutes décochées. Cocher les vraies taches, puis **Corriger les sélectionnées**. Les motifs
neutres et flous du support restent parfois indistinguables d’une tache du capteur sur une seule
image. Une photo de référence uniforme ou plusieurs prises du même capteur seraient nécessaires
pour confirmer automatiquement leur origine. Aucun motif ambigu n’est retouché par défaut.

La correction de poussière reconstruit le fond depuis le voisinage immédiat : plan de couleur
et interpolation normalisée de son résidu. Elle ne copie pas de texture depuis une zone éloignée.
Les pixels hors du disque restent intacts ; les corrections sélectionnées sont un seul pas d’annulation.
La propriété `Spot.dust` est rétrocompatible à la lecture ; les lecteurs plus anciens ignorent
ce drapeau et le décalage source nul préserve alors leurs pixels au lieu de créer une autre retouche.

L’API `spot.findDust` retourne les propositions par défaut (`add:false`). `add:true` reste une
application explicite pour les scripts. `spot.applyDust` reçoit la liste validée. L’interface
utilise `dust.scan` en arrière-plan, `dust.select`, `dust.apply` et `dust.clear`.

Sur le rendu du NEF fourni : 60 anciens résultats contre 11 nouvelles propositions au réglage 50.
La recherche laisse le rendu strictement identique. L’application d’une seule microtache de fond
modifie 150 pixels et aucun en dehors de la zone visée ; l’annulation restaure exactement le rendu.
Cela ne signifie pas que les 11 propositions sont 11 poussières confirmées.

Le Nikon compressé utilisé est actuellement ouvert depuis son JPEG intégré par LightCraft ;
le décodage RAW complet de ce fichier reste une limitation distincte. Les deux fichiers fournis
sont inchangés. Les anciennes retouches déjà exportées dans le JPEG ne peuvent pas être annulées
par ce correctif : refaire l’essai depuis le NEF, ou annuler les anciennes retouches dans leur session.
