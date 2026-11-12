// Prépare public/pyodide/ : Pyodide et toutes les bibliothèques Python du convertisseur,
// servis avec la page. Aucun fichier n'est demandé à un autre site quand la page est utilisée.
//
// - Le cœur de Pyodide vient du paquet npm « pyodide ».
// - lxml, PyYAML, Beautiful Soup et leurs dépendances, compilés pour le navigateur,
//   viennent de la distribution officielle de Pyodide. Leur empreinte SHA-256 est vérifiée
//   avec le fichier pyodide-lock.json du paquet npm.
// - Mammoth, cobble et python-docx, écrits en Python pur, viennent de PyPI. Leur empreinte
//   est fixée ci-dessous.
//
// Les fichiers vont dans public/pyodide/<version>/ : leur adresse change avec la version,
// ce qui permet au service worker de les garder sans jamais servir une version périmée.
// public/pyodide/manifeste.json indique la version et la liste des fichiers.
// Les fichiers déjà présents et intacts ne sont pas téléchargés de nouveau.

import { createHash } from 'node:crypto'
import { copyFile, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const racine = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(racine, 'node_modules', 'pyodide')
const dossierPyodide = join(racine, 'public', 'pyodide')

// Paquets de la distribution Pyodide dont le convertisseur a besoin (les dépendances suivent)
const PAQUETS_PYODIDE = ['lxml', 'pyyaml', 'beautifulsoup4']

// Paquets en Python pur, pris sur PyPI. Mêmes versions que l'exécutable Windows.
const ROUES_PYPI = [
  {
    fichier: 'mammoth-1.13.0-py2.py3-none-any.whl',
    sha256: 'dd7629fa9d0a5e82207b3f481a9dcb8308fb43f6206258e062f11121efba9991',
    url: 'https://files.pythonhosted.org/packages/af/2a/47d72b27689f3c7cd1d270dd1d4699df2fe3b78b2f293b6b08f565548a45/mammoth-1.13.0-py2.py3-none-any.whl',
  },
  {
    fichier: 'cobble-0.1.4-py3-none-any.whl',
    sha256: '36c91b1655e599fd428e2b95fdd5f0da1ca2e9f1abb0bc871dec21a0e78a2b44',
    url: 'https://files.pythonhosted.org/packages/d5/e1/3714a2f371985215c219c2a70953d38e3eed81ef165aed061d21de0e998b/cobble-0.1.4-py3-none-any.whl',
  },
  {
    fichier: 'python_docx-1.2.0-py3-none-any.whl',
    sha256: '3fd478f3250fbbbfd3b94fe1e985955737c145627498896a8a6bf81f4baf66c7',
    url: 'https://files.pythonhosted.org/packages/d0/00/1e03a4989fa5795da308cd774f05b704ace555a70f9bf9d3be057b680bcf/python_docx-1.2.0-py3-none-any.whl',
  },
]

const CŒUR = ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']

const empreinte = (octets) => createHash('sha256').update(octets).digest('hex')

async function telecharger(url, chemin, sha256) {
  if (existsSync(chemin) && empreinte(await readFile(chemin)) === sha256) return false
  const reponse = await fetch(url)
  if (!reponse.ok) throw new Error(`Téléchargement impossible (${reponse.status}) : ${url}`)
  const octets = Buffer.from(await reponse.arrayBuffer())
  if (empreinte(octets) !== sha256) throw new Error(`Empreinte SHA-256 inattendue : ${url}`)
  await writeFile(chemin, octets)
  return true
}

const version = JSON.parse(await readFile(join(source, 'package.json'), 'utf8')).version
const destination = join(dossierPyodide, version)
await mkdir(destination, { recursive: true })

// Retire les fichiers d'une version précédente
for (const nom of await readdir(dossierPyodide)) {
  if (nom !== version && nom !== 'manifeste.json') await rm(join(dossierPyodide, nom), { recursive: true, force: true })
}

// 1. Cœur de Pyodide
for (const nom of CŒUR) await copyFile(join(source, nom), join(destination, nom))
const verrou = JSON.parse(await readFile(join(source, 'pyodide-lock.json'), 'utf8'))

// 2. Paquets compilés, avec leurs dépendances
const aPrendre = new Set()
const ajouter = (nom) => {
  if (aPrendre.has(nom)) return
  const paquet = verrou.packages[nom]
  if (!paquet) throw new Error(`Paquet absent de pyodide-lock.json : ${nom}`)
  aPrendre.add(nom)
  paquet.depends.forEach(ajouter)
}
PAQUETS_PYODIDE.forEach(ajouter)

let nouveaux = 0
for (const nom of aPrendre) {
  const { file_name: fichier, sha256 } = verrou.packages[nom]
  const url = `https://cdn.jsdelivr.net/pyodide/v${version}/full/${fichier}`
  if (await telecharger(url, join(destination, fichier), sha256)) nouveaux++
}

// 3. Paquets en Python pur
for (const roue of ROUES_PYPI) {
  if (await telecharger(roue.url, join(destination, roue.fichier), roue.sha256)) nouveaux++
}

// 4. Manifeste : lu par le worker (paquets à charger, roues à décompresser, fichiers à précharger
//    avec leur taille pour la barre de progression) et par le service worker (fichiers à garder)
const noms = [...CŒUR, ...[...aPrendre].map((n) => verrou.packages[n].file_name), ...ROUES_PYPI.map((r) => r.fichier)]
const fichiers = await Promise.all(noms.map(async (nom) => ({ nom, taille: (await stat(join(destination, nom))).size })))
await writeFile(
  join(dossierPyodide, 'manifeste.json'),
  JSON.stringify({ pyodide: version, paquets: PAQUETS_PYODIDE, roues: ROUES_PYPI.map((r) => r.fichier), fichiers }, null, 2),
)

const mo = (fichiers.reduce((s, f) => s + f.taille, 0) / 1024 / 1024).toFixed(1)
console.log(`Pyodide ${version} prêt dans public/pyodide/${version}/ (${fichiers.length} fichiers, ${mo} Mo, ${nouveaux} téléchargé(s)).`)
