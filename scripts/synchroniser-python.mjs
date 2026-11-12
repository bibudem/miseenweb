// Copie dans python/ le convertisseur du dépôt miseenweb : le code, les profils et les gabarits.
// Le dépôt miseenweb reste la seule source : on n'édite pas ces copies, on les resynchronise.
//
//   npm run synchroniser                     # dépôt voisin ../miseenweb
//   npm run synchroniser -- /chemin/miseenweb
//
// L'interface tkinter, le menu du Terminal et la ligne de commande ne sont pas copiés :
// ils n'ont pas de sens dans un navigateur.

import { cp, mkdir, readdir, rm, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const racine = join(dirname(fileURLToPath(import.meta.url)), '..')
const depot = resolve(process.argv[2] ?? join(racine, '..', 'miseenweb'))
const cible = join(racine, 'python')

const MODULES = [
  '__init__.py',
  'conversion.py',
  'diagnostic.py',
  'images_emf.py',
  'normalisation.py',
  'pied_page.py',
  'pipeline.py',
  'post_traitement.py',
  'profils.py',
  'rapport.py',
]

if (!existsSync(join(depot, 'docx2html'))) {
  console.error(`Dépôt miseenweb introuvable : ${depot}`)
  process.exit(1)
}

for (const dossier of ['docx2html', 'profils', 'gabarits']) {
  await rm(join(cible, dossier), { recursive: true, force: true })
}
await mkdir(join(cible, 'docx2html'), { recursive: true })
for (const module of MODULES) {
  await cp(join(depot, 'docx2html', module), join(cible, 'docx2html', module))
}
for (const dossier of ['profils', 'gabarits']) {
  await cp(join(depot, dossier), join(cible, dossier), { recursive: true })
}

// Les documents d'exemple, pour le bouton « Essayer avec des exemples »
const exemples = join(racine, 'public', 'exemples')
await rm(exemples, { recursive: true, force: true })
await mkdir(exemples, { recursive: true })
const nomsExemples = (await readdir(join(depot, 'exemples'))).filter((n) => n.endsWith('.docx') && !n.startsWith('~$'))
for (const nom of nomsExemples) await cp(join(depot, 'exemples', nom), join(exemples, nom))
await writeFile(join(exemples, 'liste.json'), JSON.stringify(nomsExemples.sort()))

// Note la version d'origine, pour savoir quel état du convertisseur la page embarque
let commit = 'inconnu'
try {
  commit = execFileSync('git', ['-C', depot, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim()
} catch {}
await writeFile(join(cible, 'ORIGINE.txt'), `Copié du dépôt miseenweb, commit ${commit}.\nNe pas modifier : lancer « npm run synchroniser ».\n`)

const profils = await readdir(join(cible, 'profils'))
console.log(`Convertisseur copié depuis ${depot} (commit ${commit}) : ${MODULES.length} modules, ${profils.length} profils.`)
