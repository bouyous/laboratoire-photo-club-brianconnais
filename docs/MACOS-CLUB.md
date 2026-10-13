# Laboratoire du Photo Club Briançonnais — macOS

Deux paquets de préproduction sont préparés : **Apple Silicon (M1 et suivants), macOS 14+**,
et **Intel, macOS 13+**. Choisir selon « À propos de ce Mac ».
Ouvrir le DMG, glisser l’application dans Applications, puis la lancer depuis ce dossier.
Python et les modèles IA sont embarqués ; aucun Python à installer et traitements hors ligne.
La première version Mac utilise le CPU pour l’IA. Les calculs peuvent être longs ; le test rapide
et l’annulation restent disponibles. 8 Go de RAM au minimum recommandé, 16 Go pour de grandes photos.

Les préférences et TIFF IA sont enregistrés dans
`~/Library/Application Support/LaboratoirePhotoClub`, jamais dans le bundle d’application.
La bibliothèque est dans `~/Pictures/PhotoLab Club Library` par défaut, ou dans le dossier choisi.
Le nom historique de ce répertoire est conservé pour la compatibilité du catalogue.
Retirer l’application conserve ces données. Conserver des sauvegardes de ses photos et du catalogue.

## Signature et validation

Les builds initiaux ont une **signature ad hoc, sans certificat Developer ID ni notarisation Apple**.
Ce n’est pas une application certifiée par Apple. macOS peut bloquer le premier lancement.
Ne pas désactiver Gatekeeper globalement. Télécharger depuis ce dépôt et vérifier le SHA-256.
Si vous choisissez de faire confiance à cette préproduction, consulter les instructions Apple :
https://support.apple.com/fr-fr/102445. Un certificat du distributeur et une notarisation
pourront être ajoutés ultérieurement ; aucun identifiant Apple n’est inclus dans les sources.

Les tests des builds sont exécutés sur les Mac virtuels GitHub (un environnement par architecture).
Ils ne remplacent pas des essais sur les machines des membres. Le rapport accompagnant chaque
paquet précise ce qui a réellement été vérifié. Les limites RAW et poussières restent celles
de la version Windows : certains NEF compressés utilisent le JPEG intégré ; vérifier les taches
proposées et les résultats de suppression IA.

OpenCV est construit depuis ses sources Apache, sans FFmpeg/x264 ni interfaces vidéo : les
wheels Mac ordinaires embarquent des bibliothèques exclues par les règles du projet.
ONNX Runtime est 1.24.4 sur ARM et 1.23.2 sur Intel, dernière série retenue avec un wheel Intel.
Licences du code, polices, poids et dépendances conservées dans le bundle.
