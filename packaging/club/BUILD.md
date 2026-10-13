# Recompiler la distribution Windows du club

Les sources Rust restent en version de base 0.4.0 ; la distribution club est 0.5.1.
Windows 10/11 x64, Rust (MSVC), Visual Studio Build Tools C++, Python 3.12 x64,
Git et Inno Setup 6.7.3 sont nécessaires **pour construire**, pas pour utiliser l’application.

1. Cloner ce dépôt et `https://github.com/storytold/craft-fonts` à côté (vérifier les licences OFL).
2. Créer un environnement Python 3.12. Installer les versions de `ai/requirements-build.txt`.
3. Préparer `models/` en téléchargeant les fichiers listés dans `models-manifest.json`.
   NAFNet vient du membre `denoise-nafnet/model.onnx` de l’archive `.dtmodel` indiquée.
   Vérifier tous les SHA-256 et joindre les licences ; ne pas inclure les autres modèles PhotoLabPro.
4. Exécuter `packaging/club/build.ps1 -Python <python.exe> -Models <dossier> -Iscc <ISCC.exe>`.
   Le script contrôle les modèles et utilise les licences archivées dans `packaging/club/licences/`.
5. Lancer l’installateur dans un dossier de test séparé. Vérifier catalogue/import/réouverture,
   débruitage, suppression masquée et désinstallation avant chaque nouvelle publication.

`cargo xtask ci` est le contrôle Rust complet (fmt, clippy, tests, parité, couches, assets, WASM).
Les modèles et exécutables ne vont pas dans Git : joindre les livrables aux Releases.
Mettre à jour README, NOTICE, MODIFICATIONS-CLUB.md, manifeste et version d’installateur pour un nouveau fork.
La signature Authenticode requiert un certificat du distributeur ; la présente version n’en utilise pas.
