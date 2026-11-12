# Déclaration d'utilisation de l'intelligence artificielle générative

## Déclaration DDIA

**Outil d'intelligence artificielle :** Claude Opus 5.5 (claude-opus-5-5) par Claude Code d'Anthropic, utilisé le 11 novembre 2026. L'outil peut produire du code ou des analyses erronés, et ses résultats ont été testés et validés par une personne.

**Conceptualisation :** L'IAG a proposé d'exécuter le convertisseur de MiseEnWeb dans le navigateur, avec Pyodide, et de publier la page sur GitHub Pages. Le besoin, offrir l'outil aux étudiants sans installation, ainsi que les choix finaux ont été déterminés par l'auteur du projet.

**Méthodologie :** L'IAG a vérifié la faisabilité de l'approche avant de la proposer, en convertissant les documents d'exemple dans Pyodide et en comparant le résultat à celui du programme de bureau. Elle a proposé des méthodes de vérification : tests automatisés dans le navigateur et audit d'accessibilité.

**Exécution :** L'IAG a rédigé le code TypeScript, HTML et CSS de la page, le pont Python entre la page et le convertisseur, le *service worker* et les scripts de préparation. Elle a exécuté les tests et l'audit d'accessibilité, puis corrigé les défauts relevés. L'auteur a utilisé la page dans le navigateur, relevé ce qui ne convenait pas et corrigé des propositions de l'IAG.

**Visualisation :** L'IAG a adapté le style graphique du site des Bibliothèques (dépôt `bibweb`) à la page, en s'aidant de la base de connaissances UI/UX Pro Max. Elle a produit l'image de partage, les icônes de l'application et les captures d'écran, à partir du logo existant et selon les indications de l'auteur.

**Rédaction - Révision et édition :** L'IAG a rédigé les textes de la page, les conseils de correction affichés aux étudiants, le README et une ébauche de la présente déclaration, révisés par l'auteur.

**Administration du projet :** L'IAG a repéré les licences des composants inclus dans la page, sans que cela constitue un avis juridique.

**Confidentialité et sécurité :** La page convertit les documents dans le navigateur, sans les envoyer à un serveur. Aucun document d'étudiant n'est inclus dans le dépôt : les tests ont utilisé les documents fictifs du dépôt et un document fictif créé pour l'occasion.

## Répartition du travail

**Mon travail :**

- définir le besoin : permettre aux étudiants d'utiliser MiseEnWeb sans installation;
- choisir l'approche, l'hébergement et le style graphique, celui du site des Bibliothèques;
- utiliser la page dans le navigateur et demander les améliorations : vocabulaire accessible aux
  étudiants, aperçu avec vérification, installation comme application, référencement, animations;
- corriger des propositions de l'IAG : retrait des pastilles de la bannière, du volet « Options
  avancées » pour une seule option, de la barre de chargement séparée et de l'animation des cartes
  au survol; reformulation de l'explication sur le texte de remplacement des images; thème clair
  par défaut; couleur et position du logo et du nom de l'outil;
- valider chaque étape par l'examen du résultat.

**Le travail de l'IAG (Claude) :**

- vérifier la faisabilité de l'approche et proposer l'architecture;
- rédiger le code de la page, le pont Python, le *service worker* et les scripts;
- produire l'image de partage, les icônes et les captures d'écran;
- exécuter les tests dans le navigateur et l'audit d'accessibilité, et corriger les défauts relevés;
- rédiger le README et la présente ébauche de déclaration.

## Outils et programmes utilisés

**Intelligence artificielle générative**

| Outil | Usage |
|---|---|
| Claude Opus 5.5, par Claude Code (Anthropic) | Accompagnement, rédaction du code, production des images, tests, explications |
| UI/UX Pro Max (2.13.0), extension de Claude Code | Recommandations de design et d'expérience utilisateur |

**Langage et bibliothèques intégrés à la page**

| Outil | Version | Licence | Usage |
|---|---|---|---|
| Pyodide | 314.0.7 (Python 3.14.2) | MPL-2.0 | Python dans le navigateur |
| Convertisseur MiseEnWeb (`docx2html`) | inclus dans le dépôt | MIT | Conversion des documents |
| Mammoth | 1.13.0 | BSD-2-Clause | Conversion du Word en HTML |
| python-docx | 1.2.0 | MIT | Lecture des documents Word |
| Beautiful Soup (beautifulsoup4) | 4.14.3 | MIT | Traitement du HTML |
| PyYAML | 6.0.3 | MIT | Lecture des profils |
| lxml | 6.1.3 | BSD-3-Clause | Dépendance indirecte |
| cobble | 0.1.4 | BSD-2-Clause | Dépendance indirecte |
| soupsieve | 2.8.3 | MIT | Dépendance indirecte |
| typing_extensions | 4.15.0 | PSF-2.0 | Dépendance indirecte |
| Figtree (Fontsource) | 5.3.0 | OFL-1.1 | Police de l'interface |
| Lora (Fontsource) | 5.3.0 | OFL-1.1 | Police des textes d'introduction |
| Phosphor Icons | 2.1.1 | MIT | Icônes |

**Outils de développement**

| Outil | Version | Usage |
|---|---|---|
| Node.js et npm | 22.22.3 et 10.9.8 | Exécution des scripts, installation des paquets |
| Vite | 8.3.5 | Construction du site |
| TypeScript | 7.0.2 | Vérification du code |
| Playwright | 1.64.1 | Tests automatisés dans le navigateur, captures d'écran |
| axe-core | 4.14.0 | Audit d'accessibilité (WCAG 2.2 AA) |
| Google Chrome | 157 | Tests et vérification du rendu |
| Git | 2.54.0 | Suivi des versions |
| GitHub et GitHub Pages | s. o. | Hébergement du dépôt et publication de la page |
| Visual Studio Code | s. o. | Éditeur de code |
| macOS | 27.0 | Système d'exploitation |

**Sources consultées**

- Site des Bibliothèques de l'Université de Montréal, dépôt `bibweb` : jetons de design, logo,
  favoricône et système d'animation, repris dans la page.
- W3C. *Web Content Accessibility Guidelines (WCAG) 2.2*. <https://www.w3.org/TR/WCAG22/>
- Déclaration rédigée avec le générateur DDIA des bibliothèques de l'Université de Montréal, fondé sur
  le modèle de Kari D. Weaver (Université de Waterloo). <https://bibudem.github.io/ddia/>
