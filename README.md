# MiseEnWeb, version web

Convertit des documents Word (`.docx`) en pages web accessibles, directement dans le navigateur.
Rien à installer, et les documents ne quittent jamais l'ordinateur.

Le convertisseur est celui du dépôt [`miseenweb`](https://github.com/bibudem/miseenweb). Il tourne
dans la page grâce à [Pyodide](https://pyodide.org) (Python en WebAssembly).

## Démarrer

Node 22.12 ou plus récent.

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # site statique dans dist/
```

Au premier lancement, Pyodide et les bibliothèques Python (16 Mo) sont téléchargés dans
`public/pyodide/`.

## Organisation

- `index.html` et `src/` : la page, son style et le worker qui fait tourner Python.
- `python/pont.py` : le lien entre la page et le convertisseur.
- `python/docx2html/`, `profils/`, `gabarits/` : copies du dépôt `miseenweb`, à ne pas modifier.

## Mettre à jour le convertisseur

Après un changement dans le dépôt `miseenweb` :

```sh
npm run synchroniser
```

## Publier

Chaque poussée sur `main` publie le site sur GitHub Pages. Pour l'activer une fois : **Settings**,
**Pages**, puis **Source** : **GitHub Actions**.

## Licence

© Les bibliothèques de l'Université de Montréal. Code sous licence MIT, documentation et logo de
MiseEnWeb sous CC BY 4.0. Les logos et le favicon des Bibliothèques ne sont couverts par aucune de ces
licences. Le détail, avec les composants tiers, est dans [`LICENCES.md`](LICENCES.md).

L'utilisation de l'intelligence artificielle générative est décrite dans
[`DECLARATION-IA.md`](DECLARATION-IA.md).
