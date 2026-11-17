# Déclaration d'utilisation de l'intelligence artificielle générative

## Déclaration DDIA

**Outils d'intelligence artificielle :** Claude Opus 5.5 (claude-opus-5-5), utilisé le 11 novembre 2026, et Claude Fable 5.2 (claude-fable-5-2), utilisé du 13 au 17 novembre 2026, par Claude Code d'Anthropic. Ces outils peuvent produire du code ou des analyses erronés, et leurs résultats ont été testés et validés par une personne.

**Conceptualisation :** L'IAG a proposé d'exécuter le convertisseur de MiseEnWeb dans le navigateur, avec Pyodide, et de publier la page sur GitHub Pages. Le besoin, offrir l'outil aux utilisateurs sans installation, ainsi que les choix finaux ont été déterminés par l'auteur du projet. L'auteur a conçu la suite du projet : rendre les publications autonomes par des profils qu'elles créent elles-mêmes, offrir un assistant qui part de leurs documents, puis permettre la création d'un profil sans document, et faire de MiseEnWeb un outil général, pour toute publication. L'IAG a proposé des façons de réaliser ces idées, entre lesquelles l'auteur a choisi.

**Méthodologie :** L'IAG a vérifié la faisabilité de l'approche avant de la proposer, en convertissant les documents d'exemple dans Pyodide et en comparant le résultat à celui du programme de bureau. Elle a proposé des méthodes de vérification : tests automatisés dans le navigateur, audit d'accessibilité et contrôle d'intégrité, qui compare le texte du document Word à celui de la page produite. Pour les articles de la revue Science infirmière et pratiques en santé, l'IAG a analysé la structure des documents (styles, tableaux, images, couleurs) sans en lire le texte.

**Exécution :** L'IAG a rédigé le code TypeScript, HTML et CSS de la page, le pont Python entre la page et le convertisseur, le service worker et les scripts de préparation. Elle a exécuté les tests et l'audit d'accessibilité, puis corrigé les défauts relevés. À la suite des tests de la revue, elle a modifié le convertisseur : tableaux selon l'APA, tableaux larges, couleur des bandeaux, ordre du résumé et des mots-clés, sens d'écriture, puces, retraits et contrôle d'intégrité. Les 16 et 17 novembre, elle a rédigé les tests automatiques du convertisseur, la présentation des tableaux et de la page choisie par le profil, la validation d'un profil, l'analyse de documents d'exemple, le générateur de profil et l'assistant de création de profil. Elle a revu l'interface d'après les pages du système de design Primer, lues à la demande de l'auteur. L'auteur a utilisé la page dans le navigateur, relevé ce qui ne convenait pas et corrigé des propositions de l'IAG.

**Visualisation :** L'IAG a adapté le style graphique du site des Bibliothèques (répertoire GitHub `bibweb`) à la page, en s'aidant de la base de connaissances UI/UX Pro Max. Elle a produit l'image de partage, les icônes de l'application et les captures d'écran, à partir du logo existant et selon les indications de l'auteur. L'auteur a dirigé la conception de l'interface des 16 et 17 novembre : il a demandé qu'elle suive les principes de Primer, défini la hiérarchie des écrans de l'assistant et de l'accueil, la section « Paramètres de conversion », la présentation distincte des contenus tirés des documents et le rôle des couleurs. L'IAG a réalisé ces demandes et proposé des dispositions.

**Rédaction - Révision et édition :** L'IAG a rédigé les textes de la page, les conseils de correction affichés aux utilisateurs, le README et une ébauche de la présente déclaration, révisés par l'auteur. L'auteur a choisi la terminologie et rédigé lui-même plusieurs textes de l'interface : intitulés des sections et des boutons, consignes de l'assistant, aide des paramètres de conversion. Il a fixé les règles de rédaction que l'IAG applique.

**Administration du projet :** L'IAG a repéré les licences des composants inclus dans la page, sans que cela constitue un avis juridique.

**Confidentialité et sécurité :** La page convertit les documents dans le navigateur, sans les envoyer à un serveur. Aucun document d'utilisateur n'est inclus dans le répertoire GitHub. Les tests ont utilisé les documents fictifs du répertoire GitHub, un document fictif créé pour l'occasion et trois articles de la revue. Ces articles sont restés sur l'ordinateur de l'auteur, dans un dossier exclu du répertoire GitHub. L'IAG en a analysé la structure, sans en lire ni en afficher le texte.

## Répartition du travail

**Mon travail :**

- définir le besoin : permettre l'utilisation de MiseEnWeb sans installation;
- choisir l'approche, l'hébergement et le style graphique, celui du site des Bibliothèques;
- utiliser la page dans le navigateur et demander les améliorations : vocabulaire accessible aux
  utilisateurs, aperçu avec vérification, installation comme application, référencement, animations;
- corriger des propositions de l'IAG : retrait des pastilles de la bannière, du volet « Options
  avancées » pour une seule option, de la barre de chargement séparée et de l'animation des cartes
  au survol; reformulation de l'explication sur le texte de remplacement des images; thème clair
  par défaut; couleur et position du logo et du nom de l'outil;
- tester la conversion des articles de la revue, en trois tours, et relever les défauts;
- décider des règles : application stricte de l'APA aux tableaux, alignement des en-têtes selon leur colonne, vocabulaire et ton des messages;
- concevoir le plan des profils en libre-service : une publication crée son profil elle-même, et
  l'entrée au catalogue commun reste soumise à une approbation;
- concevoir l'assistant de création de profil : son point de départ, les documents de la publication,
  puis la création d'un profil sans document;
- choisir, à chaque étape, entre les approches proposées : présentation des tableaux par options,
  un seul gabarit, reconnaissance par l'ISSN seul, un profil ajouté à la fois, assistant dans la page;
- fournir les guides de style servant de sources aux présentations de tableaux;
- décider que l'outil vise toute publication, et remplacer « revue » par « publication » dans les textes;
- demander que l'interface suive les principes de Primer, et que l'IAG en lise les pages avant de proposer;
- diriger la conception de l'interface, écran par écran : titres, intitulés, consignes, ordre des
  éléments, mise en évidence des nombres relevés, tableau des regroupements, section « Paramètres
  de conversion », liste des documents sur une ligne;
- rédiger des textes de l'interface et fixer la terminologie et les règles de rédaction;
- corriger des propositions de l'IAG : intitulés et libellés des boutons, textes trop longs, pastilles
  sans contexte, couleur jaune lue comme une alerte, vert des étapes faites, icônes, boutons
  présentés comme des hyperliens, liste des documents trop haute;
- relever des défauts à l'essai : menu des règles mal réglé au démarrage, titres longs absents du
  relevé, ISSN refusé au dernier écran seulement, choix de départ du titre de l'article;
- valider chaque étape par l'examen du résultat, et écrire chaque commit.

**Le travail de l'IAG (Claude) :**

- vérifier la faisabilité de l'approche et proposer l'architecture;
- rédiger le code de la page, le pont Python, le service worker et les scripts;
- modifier le convertisseur à la suite des tests de la revue;
- produire l'image de partage, les icônes et les captures d'écran;
- exécuter les tests dans le navigateur et l'audit d'accessibilité, et corriger les défauts relevés;
- rédiger les tests automatiques, la validation d'un profil, l'analyse des documents, le générateur
  de profil et l'assistant de création de profil;
- lire les pages de Primer et rapporter ce qu'elles énoncent et n'énoncent pas;
- proposer des façons de réaliser les idées de l'auteur, avec leurs avantages et leurs
  inconvénients, et signaler ses propres erreurs;
- vérifier par programme la conversion des articles de la revue avec un profil créé par l'assistant,
  sans en afficher le texte;
- rédiger le README et la présente ébauche de déclaration.

## Outils et programmes utilisés

**Intelligence artificielle générative**

| Outil | Usage |
|---|---|
| Claude Opus 5.5, par Claude Code (Anthropic) | Accompagnement, rédaction du code, production des images, tests, explications |
| Claude Fable 5.2, par Claude Code (Anthropic) | Accompagnement, modification du convertisseur et de l'interface, tests automatiques, assistant de création de profil, explications |
| UI/UX Pro Max (2.13.0), extension de Claude Code | Recommandations de design et d'expérience utilisateur |

**Langage et bibliothèques intégrés à la page**

| Outil | Version | Licence | Usage |
|---|---|---|---|
| Pyodide | 314.0.7 (Python 3.14.2) | MPL-2.0 | Python dans le navigateur |
| Convertisseur MiseEnWeb (`docx2html`) | inclus dans le répertoire GitHub | MIT | Conversion des documents |
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
| pytest | 9.2.0 | Tests automatiques du convertisseur |
| Playwright | 1.64.1 | Tests automatisés dans le navigateur, captures d'écran |
| axe-core | 4.14.0 | Audit d'accessibilité (WCAG 2.2 AA) |
| Google Chrome | 157 | Tests et vérification du rendu |
| Git | 2.54.0 | Suivi des versions |
| GitHub et GitHub Pages | s. o. | Hébergement du répertoire GitHub et publication de la page |
| Visual Studio Code | s. o. | Éditeur de code |
| macOS | 27.0 | Système d'exploitation |

**Sources consultées**

- Site des Bibliothèques de l'Université de Montréal, répertoire GitHub `bibweb` : jetons de design, logo
  et système d'animation, repris dans la page.
- W3C. *Web Content Accessibility Guidelines (WCAG) 2.2*. <https://www.w3.org/TR/WCAG22/>
- American Psychological Association. « Table setup » (APA, 7e édition) : présentation des tableaux.
- University of Chicago Press. *The Chicago Manual of Style*, 18e édition, paragraphes 3.48 à 3.89 : présentation des tableaux.
- GitHub. Primer, <https://primer.style/> : formulaires, groupe de boutons radio, boutons, tableau de données, liste d'actions, typographie, usage des couleurs, contenu. Principes repris : action principale unique, fenêtre de confirmation, libellés courts, boutons actifs, messages reliés à leur champ.
- Office québécois de la langue française. Grand dictionnaire terminologique, et Gouvernement du Canada, glossaire de l'accessibilité : vocabulaire.
- Déclaration rédigée avec le générateur DDIA des bibliothèques de l'Université de Montréal, fondé sur
  le modèle de Kari D. Weaver (Université de Waterloo). <https://bibudem.github.io/ddia/>
