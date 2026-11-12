/// <reference lib="webworker" />
// Fait tourner le convertisseur Python (Pyodide) hors du fil principal :
// la page reste fluide pendant le chargement et la conversion.

import type { PyodideAPI } from 'pyodide'
import type { Demande, Evenement } from './protocole'

declare const self: DedicatedWorkerGlobalScope

// Le code Python, les profils et les gabarits sont intégrés au script lors de la construction
const sources = import.meta.glob('../python/**/*.{py,yaml,yml,html}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const RACINE_PYODIDE = new URL(`${import.meta.env.BASE_URL}pyodide/`, self.location.origin).href
// Dossier de la version de Pyodide, donné par le manifeste
let BASE = ''

interface Manifeste {
  pyodide: string
  paquets: string[]
  roues: string[]
  fichiers: { nom: string; taille: number }[]
}

const emettre = (evenement: Evenement, transfert: Transferable[] = []) => self.postMessage(evenement, transfert)

let python: PyodideAPI
let pont: any

// Télécharge d'abord tous les fichiers en mesurant la progression. Pyodide les redemande
// ensuite : ils viennent alors du cache du navigateur (ou du service worker), sans attente.
async function precharger(manifeste: Manifeste): Promise<Map<string, ArrayBuffer>> {
  const total = manifeste.fichiers.reduce((somme, f) => somme + f.taille, 0)
  let fait = 0
  let dernier = 0
  const signaler = () => {
    const maintenant = performance.now()
    if (maintenant - dernier > 100 || fait === total) {
      dernier = maintenant
      emettre({ type: 'telechargement', fait, total })
    }
  }
  const contenus = new Map<string, ArrayBuffer>()
  await Promise.all(
    manifeste.fichiers.map(async ({ nom }) => {
      const reponse = await fetch(`${BASE}${nom}`)
      if (!reponse.ok || !reponse.body) throw new Error(`Fichier introuvable : ${nom}`)
      const morceaux: Uint8Array[] = []
      const lecteur = reponse.body.getReader()
      for (;;) {
        const { done, value } = await lecteur.read()
        if (done) break
        morceaux.push(value)
        fait += value.byteLength
        signaler()
      }
      if (manifeste.roues.includes(nom)) contenus.set(nom, await new Blob(morceaux as BlobPart[]).arrayBuffer())
    }),
  )
  emettre({ type: 'telechargement', fait: total, total })
  return contenus
}

async function demarrer(): Promise<void> {
  const manifeste: Manifeste = await (await fetch(`${RACINE_PYODIDE}manifeste.json`, { cache: 'no-cache' })).json()
  BASE = `${RACINE_PYODIDE}${manifeste.pyodide}/`
  const roues = await precharger(manifeste)

  emettre({ type: 'etat', etape: 'python', texte: 'Démarrage…' })
  const { loadPyodide } = await import(/* @vite-ignore */ `${BASE}pyodide.mjs`)
  python = (await loadPyodide({ indexURL: BASE })) as PyodideAPI

  emettre({ type: 'etat', etape: 'bibliotheques', texte: 'Chargement des bibliothèques de conversion…' })
  const sitePackages: string = python.runPython('import site; site.getsitepackages()[0]')
  await python.loadPackage(manifeste.paquets, { messageCallback: () => {} })
  for (const [, octets] of roues) python.unpackArchive(octets, 'wheel', { extractDir: sitePackages })

  for (const [chemin, contenu] of Object.entries(sources)) {
    const destination = `/app/${chemin.replace('../python/', '')}`
    python.FS.mkdirTree(destination.slice(0, destination.lastIndexOf('/')))
    python.FS.writeFile(destination, contenu)
  }
  python.FS.mkdirTree('/entree')
  python.runPython('import sys; sys.path.insert(0, "/app")')
  pont = python.pyimport('pont')

  emettre({ type: 'pret', catalogue: JSON.parse(pont.catalogue()) })
}

async function traiter(demande: Demande): Promise<unknown> {
  switch (demande.action) {
    case 'deposer': {
      python.FS.writeFile(`/entree/${demande.nom}`, new Uint8Array(demande.octets))
      pont.lire(demande.nom)
      return
    }
    case 'analyser':
      return demande.documents.map(({ nom, profil }) => ({ nom, ...JSON.parse(pont.analyser(nom, demande.revue, profil)) }))
    case 'oublier':
      pont.oublier(demande.nom)
      return
    case 'convertir': {
      const documents = python.toPy(demande.documents)
      const journal = (texte: string) => emettre({ type: 'progression', ...JSON.parse(texte) })
      try {
        return JSON.parse(pont.convertir(documents, demande.revue, journal))
      } finally {
        documents.destroy()
      }
    }
    case 'archive': {
      const proxy = pont.archive()
      const octets: Uint8Array = proxy.toJs()
      proxy.destroy()
      return octets.buffer
    }
    case 'apercu':
      return pont.apercu(demande.nom)
    case 'rapport':
      return pont.rapport()
  }
}

const pret = demarrer().catch((erreur: unknown) => {
  emettre({ type: 'echec', texte: String(erreur) })
  throw erreur
})

self.addEventListener('message', async ({ data }: MessageEvent<Demande>) => {
  try {
    await pret
    const resultat = await traiter(data)
    const transfert = resultat instanceof ArrayBuffer ? [resultat] : []
    emettre({ type: 'reponse', id: data.id, resultat }, transfert)
  } catch (erreur) {
    emettre({ type: 'reponse', id: data.id, erreur: String(erreur) })
  }
})
