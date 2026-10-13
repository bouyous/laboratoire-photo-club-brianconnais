# Modifications de PhotoLab Club Briançonnais

Version de distribution 0.5.0, 13 octobre 2026, basée sur LightCraft v0.4.0
(2472021091a28eb93a05947cfc9b941d3911543a). Aucun parrainage du projet d’origine.

1. Français : catalogue complet de chaînes fixes et formatées, menus, dates, crédits et dialogues.
2. PhotoLabPro : pont IA isolé, NAFNet/SCUNet, suppression LaMa au pinceau, masque normalisé,
   conservation float32/ICC, correction BGR et remplissage des bords, annulation et reprise CPU.
3. Poussières du capteur : propositions multiscales, rejet bruit/texture/chromatisme,
   sélection explicite sans correction automatique, interpolation locale et annulation groupée.
4. Distribution : logo fourni par le club, retrait des marques graphiques ArtCraft,
   préférences séparées, bibliothèque distincte, français par défaut, moteur IA autonome,
   modèles embarqués et installateur par utilisateur avec désinstallation conservant les données.

La bibliothèque, le rendu, les curseurs et les fonctions de développement viennent principalement
du projet LightCraft. L’IA réemploie les modules PhotoLabPro, sans reprendre son ancienne interface,
son décodeur RAW ou les SDK externes. Les poids des modèles sont inchangés.

Fichiers modifiés par rapport au tag d’origine (les ajouts de distribution sont dans ai/, assets/club/,
packaging/club/ et les documents *CLUB.md) :

- `AGENTS.md`
- `NOTICE`
- `README.md`
- `ROADMAP.md`
- `apps/lightcraft/build.rs`
- `apps/lightcraft/src/main.rs`
- `assets/ATTRIBUTION.md`
- `crates/develop/src/settings.rs`
- `crates/engine/src/cmd/masks.rs`
- `crates/engine/src/library.rs`
- `crates/engine/src/tests_import.rs`
- `crates/pipeline/src/dust.rs`
- `crates/pipeline/src/spots.rs`
- `crates/ui-egui/locales/fr-formats.json`
- `crates/ui-egui/locales/fr.json`
- `crates/ui-egui/locales/ja-formats.json`
- `crates/ui-egui/locales/pt-br-formats.json`
- `crates/ui-egui/locales/zh-hans-formats.json`
- `crates/ui-egui/locales/zh-hant-formats.json`
- `crates/ui-egui/src/control.rs`
- `crates/ui-egui/src/credits.rs`
- `crates/ui-egui/src/i18n.rs`
- `crates/ui-egui/src/lib.rs`
- `crates/ui-egui/src/links.rs`
- `crates/ui-egui/src/menus.rs`
- `crates/ui-egui/src/panels/detail.rs`
- `crates/ui-egui/src/panels/dialogs.rs`
- `crates/ui-egui/src/panels/edit.rs`
- `crates/ui-egui/src/panels/left.rs`
- `crates/ui-egui/src/panels/masking.rs`
- `crates/ui-egui/src/panels/people.rs`
- `crates/ui-egui/src/panels/right.rs`
- `crates/ui-egui/src/panels/settings.rs`
- `crates/ui-egui/src/panels/strip.rs`
- `crates/ui-egui/src/panels/topbar.rs`
- `crates/ui-egui/src/state.rs`
- `docs/localization-fr.md`
- `docs/localization.md`
- `docs/parity.md`
- `docs/whats-new-fr.md`
- `crates/pipeline/examples/dust_report.rs`
- `crates/ui-egui/src/ai.rs`
- `crates/ui-egui/src/dust_review.rs`
- `docs/LICENCES-CLUB.md`
- `docs/UPSTREAM-README.md`
- `docs/club-ai-prototype.md`
- `docs/dust-review.md`

## Mise à jour 0.5.1 — 13 octobre 2026

Le nom public devient **Laboratoire du Photo Club Briançonnais**, à la demande du responsable,
après identification de DxO PhotoLab dans le même domaine. Aucun lien avec DxO.
Fenêtre, À propos, installateur, raccourcis, liens et messages de bibliothèque sont renommés.
Les crédits et licences conservent LightCraft et PhotoLabPro pour identifier l’origine du code.
Le format du catalogue, les variables techniques, l’identifiant de l’installateur et les anciens
répertoires de données restent compatibles : une mise à jour retrouve la bibliothèque existante.
Les poids des modèles et le moteur IA embarqué sont inchangés.
