// Logique de la page : dépôt des documents, type de chaque document, conversion, résultats,
// aperçu avec vérification. Le travail Python se fait dans le worker (worker.ts) ; ce fichier
// ne touche qu'à l'interface.

import '@fontsource-variable/figtree/wght.css'
import '@fontsource-variable/lora/wght.css'
import './styles/jetons.css'
import './styles/page.css'
import './styles/animations.css'
// Révélations au défilement, comme sur le site des Bibliothèques
import './animations'

import type { Analyse, Catalogue, DemandeSansId, Evenement, Remarque, Resultat } from './protocole'

// ---- Icônes Phosphor, intégrées au script ----
const icones = import.meta.glob(
  '/node_modules/@phosphor-icons/core/assets/regular/{arrow-counter-clockwise,arrow-right,arrow-square-out,caret-down,check-circle,copy,download-simple,eye,file-doc,file-zip,folder-simple,info,lightning,list-checks,lock-simple,moon,shield-check,sliders-horizontal,sparkle,sun,trash,tree-structure,upload-simple,warning,x,x-circle}.svg',
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>

const icone = (nom: string) => icones[`/node_modules/@phosphor-icons/core/assets/regular/${nom}.svg`] ?? ''

// Icônes en gras, pour les symboles qui doivent rester lisibles en petit (menu ⋮ des navigateurs)
const iconesGras = import.meta.glob('/node_modules/@phosphor-icons/core/assets/bold/dots-three-vertical-bold.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function placerIcones(racine: ParentNode = document): void {
  for (const el of racine.querySelectorAll<HTMLElement>('[data-icone]')) {
    if (!el.firstElementChild) el.innerHTML = icone(el.dataset.icone!)
  }
  for (const el of racine.querySelectorAll<HTMLElement>('[data-icone-gras]')) {
    const svg = iconesGras[`/node_modules/@phosphor-icons/core/assets/bold/${el.dataset.iconeGras}-bold.svg`]
    if (svg && !el.firstElementChild) el.innerHTML = svg
  }
}

// ---- Éléments de la page ----
const $ = <T extends Element>(selecteur: string) => document.querySelector<T>(selecteur)!

const etat = $<HTMLElement>('.etat-moteur')
const texteEtat = $<HTMLElement>('[data-texte-etat]')
const carteOutil = $<HTMLElement>('.carte-outil')
const depot = $<HTMLElement>('[data-depot]')
const entreeFichiers = $<HTMLInputElement>('[data-entree-fichiers]')
const entreeDossier = $<HTMLInputElement>('[data-entree-dossier]')
const menuRevue = $<HTMLSelectElement>('#revue')
const blocListe = $<HTMLElement>('[data-bloc-liste]')
const listeFichiers = $<HTMLUListElement>('[data-fichiers]')
const compte = $<HTMLElement>('[data-compte]')
const annonce = $<HTMLElement>('[data-annonce]')
const boutonConvertir = $<HTMLButtonElement>('[data-convertir]')
const libelleConvertir = $<HTMLElement>('[data-libelle-convertir]')
const blocProgression = $<HTMLElement>('[data-progression]')
const texteProgression = $<HTMLElement>('[data-texte-progression]')
const barreProgression = $<HTMLProgressElement>('[data-progression] progress')
const blocResultats = $<HTMLElement>('[data-resultats]')
const titreResultats = $<HTMLElement>('#titre-resultats')
const bilan = $<HTMLUListElement>('[data-bilan]')
const aideResultats = $<HTMLElement>('[data-aide-resultats]')
const listeResultats = $<HTMLUListElement>('[data-liste-resultats]')
const lienPrincipal = $<HTMLAnchorElement>('[data-telecharger-principal]')
const libellePrincipal = $<HTMLElement>('[data-libelle-telecharger]')
const lienZip = $<HTMLAnchorElement>('[data-telecharger-zip]')
const lienRapport = $<HTMLAnchorElement>('[data-rapport]')
const dialogue = $<HTMLDialogElement>('[data-apercu]')
const titreApercu = $<HTMLElement>('[data-titre-apercu]')
const cadre = $<HTMLIFrameElement>('[data-cadre]')
const lienPage = $<HTMLAnchorElement>('[data-telecharger-page]')
const sectionVerifier = $<HTMLElement>('[data-section-verifier]')
const listePoints = $<HTMLUListElement>('[data-points]')
const comptePoints = $<HTMLElement>('[data-compte-verifier]')
const listePlan = $<HTMLOListElement>('[data-plan]')
const toast = $<HTMLElement>('[data-toast]')

const AUTO = '__auto__'
const AUTRE_DOCUMENT = ''

// ---- État ----
interface Depose {
  nom: string
  taille: number
  profil: string          // choisi à la main, ou '' pour la détection automatique
  analyse?: Analyse
}

const documents = new Map<string, Depose>()
let catalogue: Catalogue = { revues: [], profils: [] }
let pret = false
let enCours = false
let resultats: Resultat[] = []
let recupere = true       // faux tant que les résultats n'ont été ni téléchargés ni copiés
const urls: string[] = []
let pageOuverte: { resultat: Resultat; html: string } | null = null

// ---- Petits outils ----
function element<K extends keyof HTMLElementTagNameMap>(balise: K, classe = '', texte = ''): HTMLElementTagNameMap[K] {
  const el = document.createElement(balise)
  if (classe) el.className = classe
  if (texte) el.textContent = texte
  return el
}

function avecIcone(el: HTMLElement, nom: string, texte: string): HTMLElement {
  el.innerHTML = `<span class="icone" aria-hidden="true">${icone(nom)}</span>`
  el.append(texte)
  return el
}

const pluriel = (n: number, un: string, plusieurs: string) => `${n} ${n > 1 ? plusieurs : un}`

function annoncer(texte: string): void {
  annonce.textContent = texte
}

let minuterieToast = 0
function afficherToast(texte: string): void {
  toast.textContent = texte
  toast.hidden = false
  clearTimeout(minuterieToast)
  minuterieToast = window.setTimeout(() => (toast.hidden = true), 3500)
}

function urlObjet(contenu: BlobPart, type: string): string {
  const url = URL.createObjectURL(new Blob([contenu], { type }))
  urls.push(url)
  return url
}

function liberer(): void {
  urls.splice(0).forEach((u) => URL.revokeObjectURL(u))
}

// ---- Worker : demandes avec réponse ----
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
const enAttente = new Map<number, { resoudre: (v: any) => void; rejeter: (e: Error) => void }>()
let compteur = 0

function demander<T = unknown>(demande: DemandeSansId, transfert: Transferable[] = []): Promise<T> {
  const id = ++compteur
  return new Promise<T>((resoudre, rejeter) => {
    enAttente.set(id, { resoudre, rejeter })
    worker.postMessage({ ...demande, id }, transfert)
  })
}

const mo = (octets: number) => (octets / 1024 / 1024).toFixed(1).replace('.', ',')

worker.addEventListener('message', ({ data }: MessageEvent<Evenement>) => {
  switch (data.type) {
    // La pastille se remplit pendant le chargement : le téléchargement compte pour 70 %,
    // le démarrage de Python mène à 80 %, les bibliothèques à 92 %, puis elle passe au vert.
    case 'telechargement': {
      const pourcent = (data.fait / data.total) * 100
      texteEtat.textContent = `Téléchargement du convertisseur : ${Math.round(pourcent)} % (${mo(data.fait)} sur ${mo(data.total)} Mo)`
      etat.style.setProperty('--avancement', `${pourcent * 0.7}%`)
      break
    }
    case 'etat':
      texteEtat.textContent = data.texte
      etat.style.setProperty('--avancement', data.etape === 'python' ? '80%' : '92%')
      break
    case 'pret':
      etat.style.setProperty('--avancement', '100%')
      demarre(data.catalogue)
      break
    case 'echec':
      etat.dataset.etat = 'echec'
      texteEtat.textContent = 'Le convertisseur n’a pas pu démarrer. Rechargez la page, ou essayez un navigateur récent.'
      console.error(data.texte)
      break
    case 'progression':
      texteProgression.textContent = `Conversion de « ${data.fichier} » (${data.rang} sur ${data.total})…`
      barreProgression.max = data.total
      barreProgression.value = data.rang - 1
      break
    case 'reponse': {
      const attente = enAttente.get(data.id)
      enAttente.delete(data.id)
      if (data.erreur) attente?.rejeter(new Error(data.erreur))
      else attente?.resoudre(data.resultat)
      break
    }
  }
})

worker.addEventListener('error', () => {
  etat.dataset.etat = 'echec'
  texteEtat.textContent = 'Votre navigateur ne peut pas faire tourner le convertisseur. Essayez une version récente de Chrome, Edge, Firefox ou Safari.'
})

function demarre(donnees: Catalogue): void {
  catalogue = donnees
  pret = true
  etat.dataset.etat = 'pret'
  texteEtat.textContent = 'Convertisseur prêt'
  menuRevue.replaceChildren(
    new Option('Détection automatique (recommandé)', AUTO),
    ...catalogue.revues.map((r) => new Option(r.nom, r.nom)),
    new Option('Aucune revue : document général', AUTRE_DOCUMENT),
  )
  menuRevue.disabled = false
  void analyser()
}

// ---- Ajout des documents ----
async function ajouter(fichiers: File[]): Promise<void> {
  const retenus: File[] = []
  const remarques: string[] = []
  for (const fichier of fichiers) {
    const nom = fichier.name
    const minuscule = nom.toLowerCase()
    if (nom.startsWith('~$')) remarques.push(`« ${nom} » est un fichier temporaire de Word : il est ignoré.`)
    else if (minuscule.endsWith('.doc'))
      remarques.push(`« ${nom} » est dans l’ancien format .doc. Ouvrez-le dans Word et enregistrez-le en .docx.`)
    else if (!minuscule.endsWith('.docx')) remarques.push(`« ${nom} » n’est pas un document Word : il est ignoré.`)
    else if (documents.has(nom) || retenus.some((f) => f.name === nom))
      remarques.push(`« ${nom} » est déjà dans la liste. Deux documents de même nom donneraient la même page.`)
    else retenus.push(fichier)
  }
  if (retenus.length) remarques.unshift(`${pluriel(retenus.length, 'document ajouté', 'documents ajoutés')}.`)
  annoncer(remarques.join(' '))
  if (!retenus.length) return

  for (const f of retenus) documents.set(f.name, { nom: f.name, taille: f.size, profil: '' })
  afficherListe()
  await Promise.all(
    retenus.map(async (fichier) => {
      const octets = await fichier.arrayBuffer()
      await demander({ action: 'deposer', nom: fichier.name, octets }, [octets])
    }),
  )
  await analyser()
}

async function ajouterExemples(): Promise<void> {
  const base = import.meta.env.BASE_URL
  const noms: string[] = await (await fetch(`${base}exemples/liste.json`)).json()
  const fichiers = await Promise.all(
    noms.map(async (nom) => new File([await (await fetch(`${base}exemples/${nom}`)).blob()], nom)),
  )
  await ajouter(fichiers)
}

const demandesProfils = () => [...documents.values()].map((d) => ({ nom: d.nom, profil: d.profil }))

async function analyser(): Promise<void> {
  if (!pret || !documents.size) return afficherListe()
  const analyses = await demander<Analyse[]>({ action: 'analyser', documents: demandesProfils(), revue: menuRevue.value })
  for (const analyse of analyses) {
    const depose = documents.get(analyse.nom)
    if (depose) depose.analyse = analyse
  }
  afficherListe()
}

function tailleLisible(octets: number): string {
  return octets < 1024 * 1024 ? `${Math.max(1, Math.round(octets / 1024))} ko` : `${mo(octets)} Mo`
}

// Menu du type de document : détection automatique, puis types généraux, puis revues
function menuType(doc: Depose): HTMLSelectElement {
  const menu = element('select', 'type-document')
  menu.dataset.nom = doc.nom
  menu.setAttribute('aria-label', `Type de document pour ${doc.nom}`)
  const auto = doc.profil ? 'Détection automatique' : `Automatique : ${doc.analyse?.libelle ?? '…'}`
  menu.append(new Option(auto, ''))
  const groupes = new Map<string, HTMLOptGroupElement>()
  for (const p of catalogue.profils) {
    const titre = p.revue || 'Types de document'
    if (!groupes.has(titre)) {
      const groupe = element('optgroup')
      groupe.label = titre
      groupes.set(titre, groupe)
      menu.append(groupe)
    }
    // Dans le groupe d'une revue, le nom de la revue est déjà dit
    const texte = p.revue ? p.libelle.replace(`${p.revue} : `, '').replace(/^./, (c) => c.toUpperCase()) : p.libelle
    groupes.get(titre)!.append(new Option(texte, p.nom))
  }
  menu.value = doc.profil
  menu.addEventListener('change', () => {
    doc.profil = menu.value
    void analyser()
  })
  return menu
}

// Moment où chaque document est apparu : seule une ligne récente s'anime. Quand la liste est
// redessinée pendant son animation (fin de l'analyse), l'animation reprend là où elle en était,
// grâce à un délai négatif, au lieu de recommencer.
const apparitions = new Map<string, number>()
const DUREE_APPARITION = 400 + 5 * 50

function afficherListe(): void {
  // Garder le focus sur le menu d'un document quand la liste est redessinée
  const focus = (document.activeElement as HTMLElement | null)?.dataset?.nom

  for (const nom of apparitions.keys()) if (!documents.has(nom)) apparitions.delete(nom)
  const maintenant = performance.now()
  let rangNouveau = 0
  blocListe.hidden = documents.size === 0
  compte.textContent = `(${documents.size})`
  listeFichiers.replaceChildren(
    ...[...documents.values()].map((doc) => {
      const ligne = element('li', 'fichier')
      if (!apparitions.has(doc.nom)) apparitions.set(doc.nom, maintenant + Math.min(rangNouveau++, 5) * 50)
      const ecoule = maintenant - apparitions.get(doc.nom)!
      if (ecoule < DUREE_APPARITION) {
        ligne.toggleAttribute('data-nouveau', true)
        ligne.style.animationDelay = `${-ecoule}ms`
      }
      const pictogramme = element('span', 'fichier-icone')
      pictogramme.setAttribute('aria-hidden', 'true')
      pictogramme.innerHTML = `<span class="icone">${icone('file-doc')}</span>`
      ligne.append(pictogramme)

      const infos = element('div', 'fichier-infos')
      infos.append(element('p', 'fichier-nom', doc.nom))
      const details = element('div', 'fichier-details')
      details.append(element('span', '', tailleLisible(doc.taille)))
      const a = doc.analyse
      if (!a) details.append(element('span', 'puce puce-attente', 'Lecture…'))
      else if (a.erreur) details.append(element('span', 'puce puce-erreur', a.erreur))
      else {
        if (a.revueIssn) details.append(element('span', 'puce puce-revue', a.revueIssn))
        else if (a.issn) details.append(element('span', 'puce puce-attente', `ISSN ${a.issn} : revue inconnue`))
      }
      infos.append(details)
      if (a && !a.erreur && pret) {
        const champ = element('div', 'champ-liste champ-compact')
        champ.append(menuType(doc))
        champ.insertAdjacentHTML('beforeend', `<span class="icone" aria-hidden="true">${icone('caret-down')}</span>`)
        infos.append(champ)
      }
      ligne.append(infos)

      const retirer = element('button', 'bouton-icone')
      retirer.type = 'button'
      retirer.setAttribute('aria-label', `Retirer ${doc.nom}`)
      retirer.innerHTML = `<span class="icone" aria-hidden="true">${icone('x')}</span>`
      retirer.addEventListener('click', () => void oublier(doc.nom))
      ligne.append(retirer)
      return ligne
    }),
  )
  if (focus) listeFichiers.querySelector<HTMLElement>(`select[data-nom="${CSS.escape(focus)}"]`)?.focus()
  actualiserBoutons()
}

async function oublier(nom: string): Promise<void> {
  // Le focus passe au bouton « Retirer » du document suivant (ou précédent) ; liste vide :
  // retour au bouton d'ajout. Sans cela, il retomberait au début de la page.
  const noms = [...documents.keys()]
  const rang = noms.indexOf(nom)
  const voisin = noms[rang + 1] ?? noms[rang - 1]
  documents.delete(nom)
  afficherListe()
  annoncer(`${nom} retiré de la liste.`)
  if (voisin) listeFichiers.querySelector<HTMLElement>(`[aria-label="${CSS.escape(`Retirer ${voisin}`)}"]`)?.focus()
  else $<HTMLButtonElement>('[data-choisir-fichiers]').focus()
  if (pret) await demander({ action: 'oublier', nom })
}

const convertibles = () => [...documents.values()].filter((d) => d.analyse && !d.analyse.erreur)

function actualiserBoutons(): void {
  const n = convertibles().length
  boutonConvertir.disabled = !pret || enCours || n === 0
  libelleConvertir.textContent = enCours ? 'Conversion…' : n > 1 ? `Convertir ${n} documents` : 'Convertir'
  marquerEtape(blocResultats.hidden ? (documents.size ? 'verifier' : 'ajouter') : 'convertir')
}

function marquerEtape(courante: string): void {
  const ordre = ['ajouter', 'verifier', 'convertir']
  for (const li of document.querySelectorAll<HTMLElement>('.etapes li')) {
    li.toggleAttribute('data-fait', ordre.indexOf(li.dataset.etape!) < ordre.indexOf(courante))
    if (li.dataset.etape === courante) li.setAttribute('aria-current', 'step')
    else li.removeAttribute('aria-current')
  }
}

// ---- Conversion ----
async function convertir(): Promise<void> {
  const aConvertir = convertibles().map((d) => ({ nom: d.nom, profil: d.profil }))
  if (!aConvertir.length) return
  enCours = true
  actualiserBoutons()
  blocProgression.hidden = false
  barreProgression.value = 0
  annoncer('')
  try {
    resultats = await demander<Resultat[]>({ action: 'convertir', documents: aConvertir, revue: menuRevue.value })
    barreProgression.value = barreProgression.max
    liberer()
    const [zip, rapport] = await Promise.all([demander<ArrayBuffer>({ action: 'archive' }), demander<string>({ action: 'rapport' })])
    lienZip.href = urlObjet(zip, 'application/zip')
    lienRapport.href = urlObjet(rapport, 'text/html')

    // Un seul document : la page elle-même, images comprises, plutôt qu'un zip
    const pages = resultats.filter((r) => r.sortie)
    if (pages.length === 1) {
      const page = await demander<string>({ action: 'apercu', nom: pages[0].sortie })
      lienPrincipal.href = urlObjet(page, 'text/html')
      lienPrincipal.download = pages[0].sortie
      libellePrincipal.textContent = 'Télécharger la page (.html)'
      lienZip.hidden = false
      aideResultats.textContent = 'La page est un seul fichier .html, images comprises. Le zip contient aussi le rapport.'
    } else {
      lienPrincipal.href = lienZip.href
      lienPrincipal.download = 'miseenweb.zip'
      libellePrincipal.textContent = 'Télécharger tout (.zip)'
      lienZip.hidden = true
      aideResultats.textContent =
        'Le zip contient une page .html par document, ses images s’il y a lieu, et le rapport de conversion.'
    }
    recupere = false
    afficherResultats()
  } catch (erreur) {
    annoncer('La conversion a échoué. Rechargez la page, puis réessayez.')
    console.error(erreur)
  } finally {
    enCours = false
    blocProgression.hidden = true
    actualiserBoutons()
  }
}

const STATUTS = {
  ok: { icone: 'check-circle', texte: 'Converti', bilan: ['converti', 'convertis'] },
  avertissements: { icone: 'warning', texte: 'À vérifier', bilan: ['à vérifier', 'à vérifier'] },
  erreur: { icone: 'x-circle', texte: 'Erreur', bilan: ['en erreur', 'en erreur'] },
} as const

// « 1 titre principal, 2 sections, 3 sous-sections »
function resumeStructure(titres: Record<string, number>, images: number): string {
  const noms: Record<string, [string, string]> = {
    h1: ['titre principal', 'titres principaux'],
    h2: ['section', 'sections'],
    h3: ['sous-section', 'sous-sections'],
    h4: ['sous-sous-section', 'sous-sous-sections'],
  }
  const parties = Object.entries(titres).map(([niveau, n]) => {
    const [un, plusieurs] = noms[niveau] ?? [`titre de niveau ${niveau[1]}`, `titres de niveau ${niveau[1]}`]
    return pluriel(n, un, plusieurs)
  })
  if (images) parties.push(pluriel(images, 'image', 'images'))
  return parties.join(', ') || 'Aucun titre'
}

function listeRemarques(remarques: Remarque[]): HTMLUListElement {
  const liste = element('ul', 'remarques')
  for (const r of remarques) {
    const li = element('li', `remarque remarque-${r.gravite}`)
    li.append(element('strong', '', r.titre))
    if (r.conseil) li.append(element('span', 'conseil', r.conseil))
    liste.append(li)
  }
  return liste
}

function afficherResultats(): void {
  const nombre = (s: Resultat['statut']) => resultats.filter((r) => r.statut === s).length
  bilan.replaceChildren(
    ...(['ok', 'avertissements', 'erreur'] as const)
      .filter((s) => nombre(s))
      .map((s) => element('li', `puce statut-${s}`, `${nombre(s)} ${STATUTS[s].bilan[nombre(s) > 1 ? 1 : 0]}`)),
  )

  listeResultats.replaceChildren(
    ...resultats.map((r, rang) => {
      const ligne = element('li', 'resultat')
      ligne.style.setProperty('--rang', String(rang))
      const statut = element('span', `statut statut-${r.statut}`)
      statut.setAttribute('aria-hidden', 'true')
      statut.innerHTML = `<span class="icone">${icone(STATUTS[r.statut].icone)}</span>`
      ligne.append(statut)

      const infos = element('div', 'resultat-infos')
      const nom = element('p', 'fichier-nom', r.fichier)
      nom.append(element('span', 'visuellement-masque', ` : ${STATUTS[r.statut].texte}`))
      infos.append(nom)
      const details = element('p', 'fichier-details')
      const puce = element('span', 'puce', r.libelle)
      puce.title = `Type reconnu : ${r.raison}`
      details.append(puce)
      if (r.sortie) details.append(element('span', '', resumeStructure(r.titres, r.images)))
      infos.append(details)
      if (r.erreur) infos.append(element('p', 'erreur-texte', r.erreur))

      const avertissements = r.remarques.filter((x) => x.gravite === 'avertissement')
      const informations = r.remarques.filter((x) => x.gravite === 'info')
      if (avertissements.length) {
        infos.append(listeRemarques(avertissements.slice(0, 3)))
        if (avertissements.length > 3) {
          const plus = element('details', 'plus')
          plus.append(element('summary', '', `${pluriel(avertissements.length - 3, 'autre point', 'autres points')} à vérifier`))
          plus.append(listeRemarques(avertissements.slice(3)))
          infos.append(plus)
        }
      }
      // Les informations sont affichées directement, sans accordéon
      if (informations.length) infos.append(listeRemarques(informations))
      ligne.append(infos)

      if (r.sortie) {
        const actions = element('div', 'resultat-actions')
        const voir = avecIcone(element('button', 'bouton bouton-plein bouton-compact'), 'eye', 'Aperçu et vérification')
        voir.setAttribute('type', 'button')
        voir.setAttribute('aria-label', `Aperçu et vérification de ${r.sortie}`)
        voir.addEventListener('click', () => void ouvrirApercu(r))
        const copier = avecIcone(element('button', 'bouton bouton-contour bouton-compact'), 'copy', 'Copier le code')
        copier.setAttribute('type', 'button')
        copier.setAttribute('aria-label', `Copier le code HTML de ${r.sortie}`)
        copier.addEventListener('click', async () => copierCode(await demander<string>({ action: 'apercu', nom: r.sortie })))
        actions.append(voir, copier)
        ligne.append(actions)
      }
      return ligne
    }),
  )

  // Le panneau Résultat remplace le panneau de conversion. Défilement instantané : un défilement
  // doux montrerait d'abord la suite de la page, puis remonterait.
  carteOutil.hidden = true
  blocResultats.hidden = false
  blocResultats.scrollIntoView({ block: 'start', behavior: 'instant' })
  titreResultats.focus({ preventScroll: true })
}

async function recommencer(): Promise<void> {
  if (!recupere && !confirm('Les pages converties n’ont pas été téléchargées. Les abandonner ?')) return
  const noms = [...documents.keys()]
  documents.clear()
  resultats = []
  recupere = true
  liberer()
  blocResultats.hidden = true
  carteOutil.hidden = false
  afficherListe()
  annoncer('')
  carteOutil.scrollIntoView({ block: 'start', behavior: 'instant' })
  $<HTMLButtonElement>('[data-choisir-fichiers]').focus({ preventScroll: true })
  if (pret) await Promise.all(noms.map((nom) => demander({ action: 'oublier', nom })))
}

// ---- Copier le code : le contenu de la page, pour un CMS ou StudiUM ----
async function copierCode(page: string): Promise<void> {
  const doc = new DOMParser().parseFromString(page, 'text/html')
  const contenu = (doc.querySelector('main') ?? doc.body).innerHTML.trim()
  try {
    if ('ClipboardItem' in window) {
      // En HTML pour un éditeur visuel, en texte (le code) pour un champ de code
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([contenu], { type: 'text/html' }),
          'text/plain': new Blob([contenu], { type: 'text/plain' }),
        }),
      ])
    } else {
      await navigator.clipboard.writeText(contenu)
    }
    recupere = true
    afficherToast('Code copié. Collez-le dans l’éditeur de votre site.')
  } catch {
    afficherToast('La copie a été refusée par le navigateur. Téléchargez plutôt la page.')
  }
}

// ---- Aperçu et vérification ----
async function ouvrirApercu(resultat: Resultat): Promise<void> {
  const html = await demander<string>({ action: 'apercu', nom: resultat.sortie })
  pageOuverte = { resultat, html }
  lienPage.href = urlObjet(html, 'text/html')
  lienPage.download = resultat.sortie
  titreApercu.textContent = resultat.sortie
  listePlan.replaceChildren()
  listePoints.replaceChildren()
  cadre.addEventListener('load', () => remplirPanneau(resultat), { once: true })
  cadre.srcdoc = html
  dialogue.showModal()
}

function elementCible(doc: Document, cible: Remarque['cible']): Element | null {
  if (cible.id) return doc.getElementById(cible.id)
  if (cible.balise != null && cible.rang != null) return doc.querySelectorAll(cible.balise)[cible.rang] ?? null
  return null
}

function montrer(el: Element | null): void {
  if (!el) return
  const doc = el.ownerDocument
  if (!doc.getElementById('mew-surbrillance')) {
    const style = doc.createElement('style')
    style.id = 'mew-surbrillance'
    style.textContent =
      '.mew-surbrillance{outline:4px solid #ffca40!important;outline-offset:4px;border-radius:2px;' +
      'background-color:rgb(255 202 64 / 18%)!important;transition:outline-color .3s}'
    doc.head.append(style)
  }
  el.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  el.classList.add('mew-surbrillance')
  setTimeout(() => el.classList.remove('mew-surbrillance'), 2500)
}

function remplirPanneau(resultat: Resultat): void {
  const doc = cadre.contentDocument
  if (!doc) return

  // Points à vérifier : les avertissements, avec un lien vers l'endroit quand on le connaît
  const points = resultat.remarques.filter((r) => r.gravite === 'avertissement')
  sectionVerifier.hidden = points.length === 0
  comptePoints.textContent = `(${points.length})`
  listePoints.replaceChildren(
    ...points.map((r) => {
      const li = element('li')
      const cible = elementCible(doc, r.cible)
      const titre = cible ? element('button', 'point point-lien') : element('div', 'point')
      if (cible) {
        ;(titre as HTMLButtonElement).type = 'button'
        titre.addEventListener('click', () => montrer(cible))
      }
      titre.append(element('strong', '', r.titre))
      if (r.conseil) titre.append(element('span', 'conseil', r.conseil))
      li.append(titre)
      return li
    }),
  )

  // Plan : la liste des titres, imbriquée par niveau
  const titres = [...doc.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6')]
  if (!titres.length) {
    listePlan.replaceChildren(element('li', 'aide', 'Aucun titre : la page n’a pas de structure.'))
    return
  }
  const pile: [number, HTMLOListElement][] = [[0, listePlan]]
  for (const t of titres) {
    const niveau = Number(t.tagName[1])
    while (pile.length > 1 && pile.at(-1)![0] >= niveau) pile.pop()
    const li = element('li')
    const bouton = element('button', 'plan-titre', t.textContent?.trim() || '(titre vide)')
    bouton.type = 'button'
    bouton.dataset.niveau = String(niveau)
    bouton.addEventListener('click', () => montrer(t))
    li.append(bouton)
    pile.at(-1)![1].append(li)
    const sous = element('ol')
    li.append(sous)
    pile.push([niveau, sous])
  }
  listePlan.querySelectorAll('ol:empty').forEach((ol) => ol.remove())
}

// ---- Dossiers glissés : on lit les fichiers du premier niveau seulement ----
function lireDossier(entree: FileSystemDirectoryEntry): Promise<File[]> {
  return new Promise((resoudre) => {
    const lecteur = entree.createReader()
    const fichiers: Promise<File>[] = []
    const lot = () =>
      lecteur.readEntries(
        (entrees) => {
          if (!entrees.length) return void Promise.all(fichiers).then(resoudre)
          for (const e of entrees) {
            if (e.isFile) fichiers.push(new Promise((r, x) => (e as FileSystemFileEntry).file(r, x)))
          }
          lot()
        },
        () => resoudre([]),
      )
    lot()
  })
}

async function fichiersDeposes(transfert: DataTransfer): Promise<File[]> {
  const entrees = [...transfert.items].map((item) => item.webkitGetAsEntry?.()).filter(Boolean) as FileSystemEntry[]
  if (!entrees.some((e) => e.isDirectory)) return [...transfert.files]
  const lots = await Promise.all(
    entrees.map((e) =>
      e.isDirectory
        ? lireDossier(e as FileSystemDirectoryEntry)
        : new Promise<File[]>((r) => (e as FileSystemFileEntry).file((f) => r([f]), () => r([]))),
    ),
  )
  return lots.flat()
}

// ---- Événements ----
$<HTMLButtonElement>('[data-choisir-fichiers]').addEventListener('click', () => entreeFichiers.click())
$<HTMLButtonElement>('[data-choisir-dossier]').addEventListener('click', () => entreeDossier.click())
$<HTMLButtonElement>('[data-exemples]').addEventListener('click', () => void ajouterExemples())

entreeFichiers.addEventListener('change', () => {
  void ajouter([...(entreeFichiers.files ?? [])])
  entreeFichiers.value = ''
})

entreeDossier.addEventListener('change', () => {
  // Les sous-dossiers ne sont pas parcourus, comme dans l'interface de bureau
  const premierNiveau = [...(entreeDossier.files ?? [])].filter((f) => f.webkitRelativePath.split('/').length === 2)
  void ajouter(premierNiveau)
  entreeDossier.value = ''
})

// Le dépôt fonctionne sur toute la page ; la zone se met en évidence pendant le survol
let profondeur = 0
const porteFichiers = (e: DragEvent) => e.dataTransfer?.types.includes('Files') && !carteOutil.hidden
document.addEventListener('dragenter', (e) => {
  if (!porteFichiers(e)) return
  e.preventDefault()
  if (++profondeur === 1) depot.setAttribute('data-survol', '')
})
document.addEventListener('dragleave', () => {
  if (--profondeur <= 0) {
    profondeur = 0
    depot.removeAttribute('data-survol')
  }
})
document.addEventListener('dragover', (e) => {
  if (porteFichiers(e)) e.preventDefault()
})
document.addEventListener('drop', async (e) => {
  if (!porteFichiers(e)) return
  e.preventDefault()
  profondeur = 0
  depot.removeAttribute('data-survol')
  await ajouter(await fichiersDeposes(e.dataTransfer!))
})

menuRevue.addEventListener('change', () => void analyser())
boutonConvertir.addEventListener('click', () => void convertir())
$<HTMLButtonElement>('[data-recommencer]').addEventListener('click', () => void recommencer())
for (const lien of [lienPrincipal, lienZip, lienPage]) lien.addEventListener('click', () => (recupere = true))

$<HTMLButtonElement>('[data-vider]').addEventListener('click', async () => {
  const noms = [...documents.keys()]
  documents.clear()
  afficherListe()
  annoncer('La liste est vide.')
  // Le bouton « Vider la liste » disparaît avec la liste : le focus va au bouton d'ajout
  $<HTMLButtonElement>('[data-choisir-fichiers]').focus()
  if (pret) await Promise.all(noms.map((nom) => demander({ action: 'oublier', nom })))
})

$<HTMLButtonElement>('[data-copier-apercu]').addEventListener('click', () => {
  if (pageOuverte) void copierCode(pageOuverte.html)
})
$<HTMLButtonElement>('[data-fermer]').addEventListener('click', () => dialogue.close())
// Un clic sur le fond, hors de la fenêtre d'aperçu, la ferme aussi
dialogue.addEventListener('click', (e) => {
  if (e.target === dialogue) dialogue.close()
})
dialogue.addEventListener('close', () => {
  cadre.srcdoc = ''
  pageOuverte = null
})

// Tout se perd en fermant la page : on prévient si les résultats n'ont pas été récupérés
window.addEventListener('beforeunload', (e) => {
  if (!recupere) e.preventDefault()
})

// ---- Installer l'application (question fréquente « Puis-je installer MiseEnWeb ») ----
// Chrome et Edge proposent l'installation par l'événement beforeinstallprompt : on le garde pour
// le bouton « Installer l'application ». Ailleurs (Safari, Firefox), le bouton reste caché et la
// marche à suivre de chaque système suffit.
interface InvitationInstallation extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}
const zoneInstaller = $<HTMLElement>('[data-installer-zone]')
const dejaInstallee = $<HTMLElement>('[data-deja-installee]')
let invitation: InvitationInstallation | null = null

function montrerInstallee(): void {
  zoneInstaller.hidden = true
  dejaInstallee.hidden = false
}

if (matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone) {
  montrerInstallee()
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  invitation = e as InvitationInstallation
  zoneInstaller.hidden = false
})

$<HTMLButtonElement>('[data-installer]').addEventListener('click', async () => {
  if (!invitation) return
  await invitation.prompt()
  const { outcome } = await invitation.userChoice
  invitation = null
  zoneInstaller.hidden = true
  if (outcome === 'accepted') afficherToast('MiseEnWeb est installée. Vous la trouverez parmi vos applications.')
})

window.addEventListener('appinstalled', montrerInstallee)

// « Ouvrir avec MiseEnWeb » : l'application installée (Chrome, Edge) reçoit les .docx ouverts
// depuis le système (clic droit, « Ouvrir avec »). Ils s'ajoutent à la liste, comme s'ils
// avaient été déposés. Si le panneau Résultat est affiché, on repart d'une liste vide, comme
// avec « Convertir un autre document » (avec confirmation si les résultats n'ont pas été
// récupérés ; si la personne refuse, les fichiers ne sont pas ajoutés).
interface ParametresLancement {
  files: FileSystemFileHandle[]
}
interface FileLancement {
  setConsumer(consommateur: (parametres: ParametresLancement) => void): void
}
const fileLancement = (window as Window & { launchQueue?: FileLancement }).launchQueue
fileLancement?.setConsumer(async ({ files }) => {
  if (!files.length) return
  const fichiers = await Promise.all(files.map((poignee) => poignee.getFile()))
  if (!blocResultats.hidden) {
    await recommencer()
    if (!blocResultats.hidden) return
  }
  carteOutil.scrollIntoView({ block: 'start', behavior: 'instant' })
  await ajouter(fichiers)
})

// Service worker : visites suivantes instantanées et fonctionnement hors ligne
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  const base = import.meta.env.BASE_URL
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${base}sw.js`, { scope: base }).catch(() => {})
  })
}

// ---- Thème clair ou sombre ----
// Le thème initial est posé par le script de <head> : clair par défaut, quel que soit le système.
// Le bouton bascule et mémorise le choix.
const CLE_THEME = 'miseenweb-theme'
const basculeTheme = $<HTMLButtonElement>('[data-bascule-theme]')

function appliquerTheme(theme: 'clair' | 'sombre'): void {
  document.documentElement.dataset.theme = theme
  const sombre = theme === 'sombre'
  basculeTheme.setAttribute('aria-label', sombre ? 'Passer au thème clair' : 'Passer au thème sombre')
  basculeTheme.title = sombre ? 'Thème clair' : 'Thème sombre'
}

basculeTheme.addEventListener('click', () => {
  const nouveau = document.documentElement.dataset.theme === 'sombre' ? 'clair' : 'sombre'
  appliquerTheme(nouveau)
  try {
    localStorage.setItem(CLE_THEME, nouveau)
  } catch {}
})

appliquerTheme(document.documentElement.dataset.theme === 'sombre' ? 'sombre' : 'clair')
placerIcones()
actualiserBoutons()
