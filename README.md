![MiseEnWeb, du document Word à la page web accessible. Les bibliothèques de l'Université de Montréal.](public/partage.jpg)

# MiseEnWeb

Convertit des documents Word (`.docx`) en pages web accessibles, directement dans le navigateur.
Aucune installation n'est requise, et les documents ne quittent jamais l'ordinateur.

Le convertisseur est écrit en Python. Pyodide l'exécute dans le navigateur.

## Démarrer

Requiert Node 22.12 ou une version plus récente.

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # site statique dans dist/
```

Au premier lancement, Pyodide et les bibliothèques Python (16 Mo) sont téléchargés dans
`public/pyodide/`.

## Structure

- `index.html` et `src/` : la page, son style et le worker qui exécute Python.
  - `src/assistant.ts` : l'assistant de création de profil.
  - `src/profil.ts` : l'ajout d'un profil à partir d'un fichier, et sa conservation dans le navigateur.
- `python/pont.py` : le lien entre la page et le convertisseur.
- `python/docx2html/`, `profils/`, `gabarits/` : le convertisseur, ses profils et ses gabarits.
  - `analyse.py` : relevé de ce que des documents ont en commun (styles, titres en gras, images).
  - `generateur.py` : écriture d'un profil d'après les réponses de l'assistant.
  - `validation.py` : vérification d'un profil, avec un message par erreur.
- `tests/` : les tests automatiques du convertisseur.

## Profils

Un profil contient les règles de conversion d'une publication : reconnaissance des documents, titres,
texte de remplacement des images, présentation de la page et des tableaux. C'est un fichier YAML.

- Les profils du site sont dans `python/profils/`. `defaut.yaml` sert d'exemple commenté.
- Dans la page, un profil s'ajoute à partir d'un fichier ou se crée avec l'assistant de création de
  profil. Il est validé, puis conservé dans le navigateur. Un seul profil ajouté à la fois.
- L'assistant compare les documents de la liste et pose ses questions en six écrans. Sans document,
  il en pose quatre : il règle alors la reconnaissance et la présentation seulement.

## Tester

Requiert Python 3. Les tests ont été exécutés avec Python 3.13.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Les tests créent leurs documents Word. Aucun document réel n'est conservé dans le répertoire GitHub.

## Publier

Le site est publié sur GitHub Pages à chaque envoi (`git push`) sur la branche `main`. La publication
s'active une seule fois, dans les réglages du répertoire GitHub : **Settings**, **Pages**, puis **Source** :
**GitHub Actions**.

## Licences

© 2026 Les bibliothèques de l'Université de Montréal

- **MIT** (fichier [`LICENSE`](LICENSE)) : le code, les profils, les gabarits et les exemples fictifs
  de `public/exemples/`.
- **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr)** : la documentation (`README.md`,
  `DECLARATION-IA.md`), le logo et les icônes de MiseEnWeb (`public/logo.svg`, `public/icone-*.png`),
  l'image de partage (`public/partage.jpg`) et les captures d'écran (`public/captures/`). Ces fichiers
  font exception au fichier `LICENSE` : la mention « associated documentation files » de la licence
  MIT ne s'y applique pas.
- **Exclus** : le logo des Bibliothèques (`public/logo-bib.svg`, `public/logo-bib-blanc.svg`) est une
  marque de l'Université de Montréal. Aucune de ces licences ne le couvre, y compris là où il apparaît
  dans l'image de partage et les captures d'écran. Un utilisateur qui réutilise ce code doit le
  retirer ou le remplacer.

Les composants tiers conservent leur propre licence, indiquée dans
[`DECLARATION-IA.md`](DECLARATION-IA.md). Ce document décrit aussi l'utilisation de l'intelligence
artificielle générative.
