# Interface française

Cette version modifiée de LightCraft 0.4.0 ajoute Français au menu Retouche → Langue et à Réglages → Général → Langue de l’interface. Le choix est enregistré dans les préférences. Le code de langue est `fr` ; `fr-FR`, `fr-CA` et `fr_FR.UTF-8` sont reconnus.

Les textes fixes sont dans `crates/ui-egui/locales/fr.json` et les messages contenant des variables dans `fr-formats.json`. Les clés anglaises sont conservées. Le français utilise Inter, déjà présent dans le logiciel. Les noms de fichiers, les noms saisis par l’utilisateur, les identifiants de commande et les métadonnées restent intacts.

La traduction couvre tous les textes des catalogues existants, ainsi que des textes supplémentaires dans les crédits et les boîtes de dialogue. Les notes de version affichées dans Nouveautés sont dans `docs/whats-new-fr.md`. Les dates utilisent les noms français des mois et l’ordre jour, mois, année. Les diagnostics techniques produits par les bibliothèques, les protocoles, la console et la documentation développeur peuvent rester en anglais.

Validation : `cargo test --release --locked -p lightcraft-ui-egui i18n::tests`. Le test français vérifie le menu, les formats, les dates, la persistance du choix et le rendu de Mes photos et Toutes les photos. Le test commun vérifie les catalogues et les caractères disponibles dans les polices.

Modification locale du 9 octobre 2026, fondée sur le tag `v0.4.0`, commit `2472021091a28eb93a05947cfc9b941d3911543a`. Cette compilation est une version modifiée non officielle.
