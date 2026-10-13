# Licences et redistribution — version club 0.5.0

La redistribution gratuite ou commerciale du code LightCraft est autorisée par MIT ou Apache-2.0,
à condition de conserver les avis applicables et fournir les licences. Nous conservons les deux textes,
le NOTICE d’origine et les attributions. Les modifications sont identifiées dans les fichiers et dans
MODIFICATIONS-CLUB.md. `crates/segment` conserve sa licence Apache-2.0 uniquement.

Origine vérifiée : https://github.com/storytold/lightcraft, tag v0.4.0,
commit 2472021091a28eb93a05947cfc9b941d3911543a. Les fichiers tiers conservent leurs licences.
Les modules du pont IA réemploient le PhotoLabPro développé pour le responsable de ce projet,
à sa demande ; les ajouts originaux sont distribués sous MIT OU Apache-2.0.
Aucun code de décodeur RAW tiers ou SDK Nikon n’a été incorporé dans le pont.

## Marques et logo

Les marques ArtCraft ne sont pas couvertes par MIT/Apache. Leur notice est conservée dans
docs/brand/LICENSE-brand.txt ; leurs fichiers graphiques ont été retirés du fork.
La référence textuelle à LightCraft identifie seulement l’origine du code.
Le logo Photo Club Briançonnais est le fichier fourni par le responsable pour cette application ;
voir assets/club/LICENSE-logo.txt. Aucune licence générale de marque n’est accordée.

## Modèles inclus

- NAFNet SIDD width-32 : Megvii Research, MIT ; export ONNX distribué par darktable-ai.
  https://github.com/megvii-research/NAFNet et
  https://github.com/darktable-org/darktable-ai/tree/master/models/denoise-nafnet.
  Seuls les poids ONNX sont repris, aucun code de darktable ou du convertisseur.
  Le texte NAFNet préserve également les avis BasicSR Apache-2.0.
- SCUNet real/15/50 : Kai Zhang et collaborateurs, Apache-2.0 ; exports ONNX Heliosoph.
  https://github.com/cszn/SCUNet et https://huggingface.co/Heliosoph/scunet-onnx.
- LaMa : export OpenCV inpainting_lama, Apache-2.0 ; origine ONNX Carve/LaMa-ONNX.
  https://huggingface.co/opencv/inpainting_lama. Correction du contrat BGR dans notre pont,
  poids inchangés. Les conditions Apache-2.0 sont indiquées dans la fiche de ce modèle.

Les fichiers, sources et SHA-256 exacts figurent dans packaging/club/models-manifest.json.
Ils sont distribués dans l’installateur, pas dans Git. SAM 3 n’est pas inclus et sa licence séparée
ne s’applique qu’à un téléchargement optionnel choisi par l’utilisateur.

## Moteur et dépendances

Python : PSF ; NumPy : BSD et avis OpenBLAS ; OpenCV : Apache-2.0 et avis de sa distribution ;
ONNX Runtime/DirectML : MIT et avis tiers ; tifffile : BSD ; psutil : BSD ;
PyInstaller : GPL avec exception explicite de distribution du bootloader, qui autorise la
distribution de programmes gelés sous leur propre licence. Le code applicatif ne devient pas GPL.
FFmpeg, imagecodecs, Qt, LibRaw et les autres composants de PhotoLabPro non utilisés sont exclus.
Les DLL de support Python et les runtimes Microsoft redistribuables sont inclus.
Les textes et inventaires de la distribution sont dans `licences/`, accessibles après installation.
La liste Rust couvre les dépendances et leurs avis, avec les licences des polices embarquées.

Pour redistribuer une version modifiée : garder les textes, avis et attributions applicables,
documenter ses propres changements, vérifier les licences des nouveaux modèles et bibliothèques,
et ne pas revendiquer le parrainage des auteurs d’origine. Les licences ne garantissent ni qualité
photographique ni fonctionnement ; voir les limites du README.

## Mise à jour 0.5.1 — 13 octobre 2026

Le nom public devient **Laboratoire du Photo Club Briançonnais**, à la demande du responsable,
après identification de DxO PhotoLab dans le même domaine. Aucun lien avec DxO.
Fenêtre, À propos, installateur, raccourcis, liens et messages de bibliothèque sont renommés.
Les crédits et licences conservent LightCraft et PhotoLabPro pour identifier l’origine du code.
Le format du catalogue, les variables techniques, l’identifiant de l’installateur et les anciens
répertoires de données restent compatibles : une mise à jour retrouve la bibliothèque existante.
Les poids des modèles et le moteur IA embarqué sont inchangés.
