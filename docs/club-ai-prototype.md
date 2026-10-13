# Prototype IA du club photo

Modification locale du 9 octobre 2026, fondée sur LightCraft 0.4.0 et son interface française.
Le panneau **IA — PhotoLab Club** ajoute le débruitage de PhotoLabPro et la suppression par LaMa.
Le logiciel stable installé n’est pas remplacé. Le prototype possède ses propres préférences.

Le débruitage propose Confort (NAFNet), Qualité (SCUNet), Extrême et Automatique, avec une intensité.
La suppression utilise un pinceau sur l’image, un masque rouge, l’annulation du dernier trait et
l’effacement du masque. Le résultat est une nouvelle photo TIFF, consultable via Afficher le résultat.
Afficher l’original revient à la photo source. Un changement de photo ou de géométrie efface le masque
pour éviter un effacement au mauvais endroit. Le masque n’est pas encore sauvegardé entre sessions.

## Architecture et précision

Le rendu courant, avec ses réglages, est exporté par le moteur Rust en TIFF RGB linéaire float32,
avec les primaires sRGB et le profil ICC linéaire correspondant. Le processus Python local charge
`AIManager` de PhotoLabPro, ses fonctions de transfert, son analyse du bruit et ONNX Runtime.
La profondeur float32 et le profil ICC sont conservés. Les données originales du capteur ne sont pas
modifiées ; il s’agit d’un traitement du rendu, pas d’un débruitage avant dématriçage. Le résultat
intègre les réglages actuels et reste indépendant du RAW d’origine.

La tâche s’exécute hors du fil de l’interface. L’annulation termine le processus enfant ; un échec
du moteur natif permet une nouvelle tentative sur CPU. Les fichiers de résultats sont vérifiés avant
leur adoption. Ils restent dans des dossiers de tâches distincts, sans écraser un résultat précédent.

Le pont LaMa corrige deux problèmes du chemin hérité : la variante OpenCV attend BGR tandis que
PhotoLab traite RGB ; les petites images sont complétées en répétant les pixels du bord au lieu de
refléter un objet à supprimer hors de son masque. Les pixels masqués sont neutralisés à l’entrée
du modèle. La vérification doit porter sur la disparition de l’objet et les pixels non masqués,
pas simplement sur une différence quelconque du résultat.

Le détecteur de poussière compare désormais la persistance d’une tache à deux échelles pour rejeter
les fluctuations ponctuelles de bruit. Un test de régression produit 60 faux positifs dans le
détecteur d’origine et aucun avec le correctif, tout en conservant les trois taches floues connues.
Cela ne certifie pas encore le détecteur sur toutes les scènes photographiques.

## Configuration et distribution

`ai-runtime.json`, à côté de l’exécutable, contient les chemins du Python existant, du script
`ai-worker.py`, du code PhotoLab, des modèles et du dossier des résultats. Ce prototype réutilise
les composants installés sur l’ordinateur de développement. Une version autonome pour les machines
du club nécessitera de livrer le moteur IA et ses licences, de vérifier les conversions et poids
exacts des modèles, puis de tester les matériels cibles. Aucun poids n’est distribué dans ce prototype.
L’exception au produit entièrement Rust concerne seulement ce moteur IA externe explicitement
demandé par l’utilisateur. Les RAW et la bibliothèque restent gérés par LightCraft.

Les modèles NAFNet et SCUNet et la variante OpenCV de LaMa disposent de licences permissives,
mais la provenance des conversions ONNX employées doit également être conservée lors de la livraison.
Les licences du logiciel et les restrictions sur les marques ArtCraft restent applicables.

Références :
- https://github.com/megvii-research/NAFNet/blob/main/LICENSE
- https://github.com/cszn/SCUNet/blob/main/LICENSE
- https://huggingface.co/opencv/inpainting_lama/blob/main/README.md
- https://huggingface.co/opencv/inpainting_lama/blob/main/lama.py
