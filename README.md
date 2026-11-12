# MiseEnWeb, version web

Convertit des documents Word (`.docx`) en pages web accessibles, directement dans le navigateur.
Aucune installation n'est requise, et les documents ne quittent jamais l'ordinateur.

Le convertisseur est écrit en Python. [Pyodide](https://pyodide.org) l'exécute dans le navigateur.

## Démarrer

Requiert Node 22.12 ou une version plus récente.

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # site statique dans dist/
```

Au premier lancement, Pyodide et les bibliothèques Python (16 Mo) sont téléchargés dans
`public/pyodide/`.

## Organisation

- `index.html` et `src/` : la page, son style et le *worker* qui exécute Python.
- `python/pont.py` : le lien entre la page et le convertisseur.
- `python/docx2html/`, `profils/`, `gabarits/` : le convertisseur, ses profils et ses gabarits.

## Publier

Le site est publié sur GitHub Pages à chaque envoi (`git push`) sur la branche `main`. La publication
s'active une seule fois, dans les réglages du dépôt : **Settings**, **Pages**, puis **Source** :
**GitHub Actions**.

## Licence

© Les bibliothèques de l'Université de Montréal. Code sous licence MIT, documentation et logo de
MiseEnWeb sous CC BY 4.0. Les logos et la favoricône des Bibliothèques ne sont couverts par aucune de ces
licences. Le détail, y compris les composants tiers, figure dans [`LICENCES.md`](LICENCES.md).

L'utilisation de l'intelligence artificielle générative est décrite dans
[`DECLARATION-IA.md`](DECLARATION-IA.md).
