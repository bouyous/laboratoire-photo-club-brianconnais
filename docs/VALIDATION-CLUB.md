# Validation de la distribution club 0.5.0

Essais effectués le 13 octobre 2026 sur **un ordinateur Windows x64**. Une installation séparée
sert à tester l’installateur, sans remplacer LightCraft installé ni utiliser la bibliothèque personnelle.
Le rapport final de la Release complète cette fiche avec l’installation et la désinstallation.

## Contrôles du code et des exécutables

La suite Rust complète couvre 1 073 tests réussis, avec les contrôles de formatage, Clippy,
parité des commandes, couches, attributions d’assets et compilation WASM.
Les exécutables de distribution sont compilés pour x86_64-pc-windows-msvc avec CRT statique.
La ressource Windows et la fenêtre utilisent le logo fourni ; la fenêtre À propos a été inspectée.

## Bibliothèque et application autonome

- Premier lancement en français, catalogue vide sans photos de démonstration.
- Import de JPEG et de TIFF float32, création d’un album et notation.
- Réglage d’exposition, export JPEG aux dimensions attendues.
- Fermeture puis réouverture : photos, album, notes et développement conservés.
- Réduction du bruit et suppression masquée réelles, ajout des deux TIFF dérivés au catalogue.
- Nouvelle réouverture : cinq photos présentes, dont les deux résultats IA.
- Annulation du travail IA ; l’interface reste accessible pendant les calculs.
- SHA-256 des originaux inchangés ; aucun fichier du dossier d’application modifié par les essais.
- Chemins avec espaces et accents, dossier courant distinct de l’installation.
- Aucun Python externe dans PATH, aucune référence à l’ancien projet PhotoLabPro pour l’exécution.

## Qualité IA : témoins synthétiques reproductibles

Test CPU avec le moteur gelé autonome, images float32 320 × 256 :
NAFNet réduit l’erreur quadratique moyenne du bruit ajouté de 0,00122808 à 0,00003548.
La suppression LaMa élimine le rectangle rouge témoin ; les pixels de la zone témoin extérieure
au masque sont rigoureusement identiques. Ce résultat ne prouve pas la qualité sur toutes les photos.
Les essais intégrés ont également utilisé DirectML pour le débruitage et la reprise CPU pour LaMa.

## Poussières et RAW

La recherche de poussières ne corrige rien avant sélection explicite. Les tests incluent
bruit ponctuel, détails texturés/colorés, tache faible et interpolation sur fond dégradé.
Lors d’un essai privé sur NEF fourni par l’utilisateur, le détecteur a proposé 11 zones au lieu
des 60 anciennes. Ce sont des propositions, pas des poussières confirmées. L’annulation a rendu
l’image identique et la correction testée n’a modifié aucun pixel hors de sa zone.
Les photographies personnelles de cet essai ne sont pas distribuées.
Le NEF compressé testé a été ouvert depuis son JPEG intégré ; le rendu des données RAW complètes
de cette variante n’est pas encore disponible. Cette limite est affichée/documentée par LightCraft.

## Portée et limites

Windows 10/11 x64 ciblés ; la machine de test ne remplace pas des essais sur plusieurs matériels
ni une machine virtuelle Windows vierge. Bibliothèque et IA fonctionnent avec leurs dépendances
embarquées, mais les pilotes graphiques et les ressources matérielles varient.
L’affichage requiert DirectX 12 ; l’IA possède un chemin CPU. Préproduction, sans signature commerciale.
Conserver des sauvegardes, vérifier les résultats de suppression et valider les taches proposées.

## Installateur réellement testé

Le paquet EXE final a été installé dans un dossier séparé avec espaces et accents.
Les essais de bibliothèque et d’IA ci-dessus ont été rejoués depuis cet exécutable installé.
Désinstallation réussie : application retirée, les 38 fichiers de photos, catalogue, préférences
et résultats du test ont gardé leur SHA-256. Aucun redémarrage Windows requis.
Les chiffres et empreintes de l’exécutable sont dans VALIDATION-PhotoLab-Club-0.5.0.json.
