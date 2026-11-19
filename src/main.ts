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
import { estProfil, installerProfil } from './profil'
import { installerAssistant } from './assistant'

// ---- Icônes Phosphor, intégrées au script ----
const icones = import.meta.glob(
  '/node_modules/@phosphor-icons/core/assets/regular/{arrow-counter-clockwise,arrow-right,arrow-square-out,caret-down,check-circle,copy,download-simple,eye,file-doc,file-html,file-zip,folder-simple,info,arrow-left,image,layout,lightning,list-checks,lock-simple,magnifying-glass,moon,newspaper,paragraph,plus,printer,shield-check,sliders-horizontal,sparkle,sun,trash,tree-structure,upload-simple,warning,x,x-circle}.svg',
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
const boutonChoisir = $<HTMLButtonElement>('[data-choisir-fichiers]')
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
const boutonRapport = $<HTMLButtonElement>('[data-rapport]')
const dialogueRapport = $<HTMLDialogElement>('[data-dialogue-rapport]')
const cadreRapport = $<HTMLIFrameElement>('[data-cadre-rapport]')
const dialogue = $<HTMLDialogElement>('[data-apercu]')
const titreApercu = $<HTMLElement>('[data-titre-apercu]')
const cadre = $<HTMLIFrameElement>('[data-cadre]')
const lienPage = $<HTMLAnchorElement>('[data-telecharger-page]')
const sectionVerifier = $<HTMLElement>('[data-section-verifier]')
const listePoints = $<HTMLUListElement>('[data-points]')
const comptePoints = $<HTMLElement>('[data-compte-verifier]')
const sectionConversion = $<HTMLElement>('[data-section-conversion]')
const listePointsConversion = $<HTMLUListElement>('[data-points-conversion]')
const comptePointsConversion = $<HTMLElement>('[data-compte-conversion]')
const aideConvertir = $<HTMLElement>('[data-aide-convertir]')
const listePlan = $<HTMLOListElement>('[data-plan]')
const annonceGlobale = $<HTMLElement>('[data-annonce-globale]')
const confirmation = $<HTMLDialogElement>('[data-confirmation]')

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
// Vrai après un clic sur « Convertir » qui n'a rien pu lancer : la raison s'affiche alors à côté du bouton
let raisonDemandee = false
let resultats: Resultat[] = []
let rapportHtml = ''     // rapport de la dernière conversion
let recupere = true       // faux tant que les résultats n'ont pas été téléchargés
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

// Confirme une action dans son bouton : le libellé change quelques secondes, puis revient.
// Le message est aussi dit aux lecteurs d'écran. Aucune bulle temporaire : un message qui
// disparaît seul peut être manqué.
function confirmerDansBouton(bouton: HTMLElement, nomIcone: string, texte: string): void {
  annonceGlobale.textContent = texte
  if (bouton.dataset.confirme) return
  const initial = bouton.innerHTML
  bouton.dataset.confirme = 'oui'
  avecIcone(bouton, nomIcone, texte)
  window.setTimeout(() => {
    bouton.innerHTML = initial
    delete bouton.dataset.confirme
  }, 4000)
}

// Message d'erreur qui reste affiché dans `zone`, jusqu'à la prochaine tentative
function signalerErreur(zone: HTMLElement, texte: string): void {
  zone.querySelector('[data-erreur-action]')?.remove()
  if (!texte) return
  const message = element('p', 'erreur-texte erreur-action', texte)
  message.dataset.erreurAction = ''
  message.setAttribute('role', 'alert')
  zone.append(message)
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
      texteEtat.textContent = 'Le convertisseur n’a pas démarré. Recharger la page ou utiliser un navigateur récent.'
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
  texteEtat.textContent = 'Ce navigateur ne peut pas exécuter le convertisseur. Utiliser une version récente de Chrome, Edge, Firefox ou Safari.'
})

// Refait les menus quand la liste des profils change : au démarrage, puis au dépôt ou au retrait d'un profil
function appliquerCatalogue(donnees: Catalogue): void {
  catalogue = donnees
  // Au démarrage, le menu est vide : sa valeur, une chaîne vide, est aussi celle de « Document général »
  const choix = menuRevue.options.length ? menuRevue.value : AUTO
  menuRevue.replaceChildren(
    new Option('Détection automatique (recommandé)', AUTO),
    ...catalogue.revues.map((r) => new Option(`${r.depose ? 'Profil' : 'Publication'} : ${r.nom}`, r.nom)),
    new Option('Document général : thèse, rapport ou autre', AUTRE_DOCUMENT),
  )
  // Le choix est conservé s'il existe encore; une revue retirée ramène à la détection automatique
  menuRevue.value = [...menuRevue.options].some((o) => o.value === choix) ? choix : AUTO
  // Un document réglé à la main sur un profil retiré revient à la détection automatique
  const noms = new Set(catalogue.profils.map((p) => p.nom))
  for (const doc of documents.values()) if (doc.profil && !noms.has(doc.profil)) doc.profil = ''
  void analyser()
}

const depotProfil = installerProfil({
  demander,
  surCatalogue: appliquerCatalogue,
  annoncer: (texte) => (annonceGlobale.textContent = texte),
  confirmer,
})

const assistant = installerAssistant({
  demander,
  documents: () => [...documents.keys()],
  icone,
  deposerProfil: depotProfil.deposerTexte,
  profilActif: depotProfil.actif,
  publicationsDuSite: () => catalogue.revues.filter((r) => !r.depose && r.issn),
  annoncer: (texte) => (annonceGlobale.textContent = texte),
})

function demarre(donnees: Catalogue): void {
  pret = true
  etat.dataset.etat = 'pret'
  texteEtat.textContent = 'Convertisseur prêt'
  menuRevue.disabled = false
  appliquerCatalogue(donnees)
  assistant.actualiser(pret)
  void depotProfil.pret()      // dépose de nouveau le profil conservé dans ce navigateur, s'il y en a un
}

// ---- Ajout des documents ----
async function ajouter(fichiers: File[]): Promise<void> {
  const retenus: File[] = []
  const remarques: string[] = []
  const dejaPresents: string[] = []
  for (const fichier of fichiers) {
    const nom = fichier.name
    const minuscule = nom.toLowerCase()
    // Un fichier de profil glissé avec les documents suit le chemin du bouton « Choisir un fichier de profil »
    if (estProfil(nom)) {
      if (pret) void depotProfil.deposerFichier(fichier)
      continue
    }
    if (nom.startsWith('~$')) remarques.push(`« ${nom} » est un fichier temporaire de Word. Le fichier est ignoré.`)
    else if (minuscule.endsWith('.doc'))
      remarques.push(`« ${nom} » est dans le format .doc. Ouvrir le fichier dans Word, puis enregistrer le fichier dans le format .docx.`)
    else if (!minuscule.endsWith('.docx')) remarques.push(`« ${nom} » n’est pas un document Word. Le fichier est ignoré.`)
    else if (documents.has(nom) || retenus.some((f) => f.name === nom)) dejaPresents.push(nom)
    else retenus.push(fichier)
  }
  // Une seule phrase pour les documents déjà présents, quel que soit leur nombre
  if (dejaPresents.length === 1)
    remarques.push(`« ${dejaPresents[0]} » est déjà dans la liste. Deux documents de même nom produisent la même page.`)
  else if (dejaPresents.length > 1) remarques.push(`${dejaPresents.length} documents sont déjà dans la liste.`)
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
  // La pastille voisine nomme déjà la publication reconnue : le menu ne la répète pas
  const publication = doc.analyse?.revueIssn
  const reconnu = doc.analyse?.libelle ?? '…'
  const type = publication && reconnu.startsWith(`${publication} : `) ? reconnu.slice(publication.length + 3) : reconnu
  const auto = doc.profil ? 'Détection automatique' : `Automatique : ${type}`
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
  raisonDemandee = false
  // Un seul bouton principal à la fois : l'ajout quand la liste est vide, la conversion ensuite
  boutonChoisir.classList.toggle('bouton-plein', documents.size === 0)
  boutonChoisir.classList.toggle('bouton-contour', documents.size > 0)
  boutonConvertir.classList.toggle('bouton-plein', documents.size > 0)
  boutonConvertir.classList.toggle('bouton-contour', documents.size === 0)
  assistant.actualiser(pret)
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
      // Une ligne par document : le nom et ses détails, le menu du type, le bouton de retrait.
      // Sans icône : le titre « Documents » dit déjà ce que la liste contient.
      const infos = element('div', 'fichier-infos')
      infos.append(element('p', 'fichier-nom', doc.nom))
      const details = element('div', 'fichier-details')
      details.append(element('span', '', tailleLisible(doc.taille)))
      const a = doc.analyse
      if (!a) details.append(element('span', 'puce puce-attente', 'Lecture…'))
      else if (a.erreur) details.append(element('span', 'puce puce-erreur', a.erreur))
      else {
        if (a.revueIssn) details.append(element('span', 'puce puce-revue', a.revueIssn))
        else if (a.issn) details.append(element('span', 'puce puce-attente', `ISSN ${a.issn} : publication inconnue`))
      }
      infos.append(details)
      if (a && !a.erreur && pret) {
        const champ = element('div', 'champ-liste champ-compact')
        champ.append(menuType(doc))
        champ.insertAdjacentHTML('beforeend', `<span class="icone" aria-hidden="true">${icone('caret-down')}</span>`)
        ligne.append(infos, champ)
      } else ligne.append(infos)

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
  // Le bouton reste actif, sauf pendant une conversion : un bouton grisé ne dit pas pourquoi.
  // Sans document à convertir, un clic affiche la raison.
  boutonConvertir.disabled = enCours
  if (enCours || (pret && n > 0)) aideConvertir.textContent = ''
  else if (!pret) aideConvertir.textContent = 'Le convertisseur se prépare. La conversion se lance à la fin de la préparation.'
  else if (documents.size) aideConvertir.textContent = 'Aucun document de la liste ne peut être converti.'
  else aideConvertir.textContent = 'Ajouter un ou plusieurs documents afin de lancer la conversion.'
  // Liste vide : la zone de dépôt le dit déjà à l'écran. La phrase reste pour le lecteur d'écran,
  // qui la lit avec le bouton, et elle s'affiche après un clic sans effet.
  aideConvertir.classList.toggle('visuellement-masque', pret && !enCours && documents.size === 0 && !raisonDemandee)
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
  if (!pret || !aConvertir.length) {
    // Rien à lancer : la raison s'affiche à côté du bouton et le focus va à l'ajout de documents
    raisonDemandee = true
    actualiserBoutons()
    annoncer(aideConvertir.textContent ?? '')
    if (pret && !documents.size) boutonChoisir.focus()
    return
  }
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
    rapportHtml = rapport

    // Un seul document : la page elle-même, images comprises, plutôt qu'un zip
    const pages = resultats.filter((r) => r.sortie)
    if (pages.length === 1) {
      const page = await demander<string>({ action: 'apercu', nom: pages[0].sortie })
      lienPrincipal.href = urlObjet(page, 'text/html')
      lienPrincipal.download = pages[0].sortie
      libellePrincipal.textContent = 'Télécharger la page (.html)'
      lienZip.hidden = false
      aideResultats.textContent = 'La page est un seul fichier .html qui contient les images. Le fichier .zip contient aussi le rapport.'
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
    annoncer('La conversion a échoué. Recharger la page, puis relancer la conversion.')
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

// Réunit les remarques identiques : [remarque, nombre de fois], dans l'ordre de la première
function regrouper(remarques: Remarque[]): [Remarque, number][] {
  const groupes = new Map<string, [Remarque, number]>()
  for (const r of remarques) {
    const cle = `${r.titre}\n${r.conseil}`
    const groupe = groupes.get(cle)
    if (groupe) groupe[1] += 1
    else groupes.set(cle, [r, 1])
  }
  return [...groupes.values()]
}

// Titre de remarques identiques réunies : « 20 images sans… », sinon « … (20 fois) »
function titreDuGroupe(r: Remarque, nombre: number): string {
  if (nombre < 2) return r.titre
  return r.pluriel ? `${r.pluriel.replace('{n}', String(nombre))}.` : `${r.titre} (${nombre} fois)`
}

function listeRemarques(groupes: [Remarque, number][]): HTMLUListElement {
  const liste = element('ul', 'remarques')
  for (const [r, nombre] of groupes) {
    const li = element('li', `remarque remarque-${r.gravite}`)
    li.append(element('strong', '', titreDuGroupe(r, nombre)))
    if (r.conseil) li.append(element('span', 'conseil', r.conseil))
    liste.append(li)
  }
  return liste
}

// Une ligne repliée par sorte de remarque : la liste des résultats reste courte, et le détail
// est à un clic. L'endroit à corriger se trouve dans « Vérifier la page ».
// Deux sources de remarques, chacune sur sa ligne : le document d'origine, dont les défauts se
// corrigent dans Word, et la conversion. L'icône du fichier concerné précède le libellé.
type Source = 'document' | 'conversion'

function pictogramme(nom: string, classe: string): HTMLSpanElement {
  const span = element('span', `icone ${classe}`)
  span.setAttribute('aria-hidden', 'true')
  span.innerHTML = icone(nom)
  return span
}

function bilanSource(source: Source, aCorriger: Remarque[], informations: Remarque[], contexte = ''): HTMLDetailsElement {
  const groupesACorriger = regrouper(aCorriger)
  const groupesInformations = regrouper(informations)
  let resume: string
  if (groupesACorriger.length === 1) {
    resume = titreDuGroupe(...groupesACorriger[0]).replace(/\.$/, '')
  } else if (groupesACorriger.length > 1) {
    resume =
      source === 'document'
        ? pluriel(aCorriger.length, 'point à corriger', 'points à corriger')
        : pluriel(aCorriger.length, 'point à vérifier', 'points à vérifier')
  } else if (groupesInformations.length) {
    resume = pluriel(groupesInformations.length, 'information', 'informations')
  } else {
    resume = 'aucune remarque'
  }

  const volet = element('details', `bilan-source${aCorriger.length ? ' bilan-a-corriger' : ''}`)
  const sommaire = element('summary')
  sommaire.append(
    pictogramme(source === 'document' ? 'file-doc' : 'file-html', 'bilan-icone'),
    element('span', 'bilan-libelle', source === 'document' ? 'Document d’origine :' : 'Conversion :'),
    element('span', 'bilan-resume', resume),
    pictogramme('caret-down', 'bilan-chevron'),
  )

  const detail = element('div', 'bilan-detail')
  if (source === 'document') {
    detail.append(
      element('p', 'aide', 'Afin d’améliorer la qualité de la conversion, il est recommandé d’apporter des corrections dans le fichier Word et de relancer le traitement.'),
    )
  }
  if (contexte) detail.append(element('p', 'aide', contexte))
  if (groupesACorriger.length || groupesInformations.length) {
    detail.append(listeRemarques([...groupesACorriger, ...groupesInformations]))
  }
  // Ici, les remarques sont regroupées : c'est l'aperçu qui mène à chaque endroit à corriger
  if (source === 'document') {
    const aide = element('p', 'aide')
    aide.append('Cliquer sur ', element('strong', '', 'Vérifier la page'), ' afin de repérer l’emplacement des corrections suggérées.')
    detail.append(aide)
  }
  volet.append(sommaire, detail)
  return volet
}

function afficherResultats(): void {
  const nombre = (s: Resultat['statut']) => resultats.filter((r) => r.statut === s).length
  titreResultats.textContent = resultats.length > 1 ? 'Résultats' : 'Résultat'
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
      const nom = element('h3', 'fichier-nom', r.fichier)
      nom.append(element('span', 'visuellement-masque', ` : ${STATUTS[r.statut].texte}`))
      infos.append(nom)
      const details = element('p', 'fichier-details')
      const puce = element('span', 'puce', r.libelle)
      details.append(puce)
      if (r.sortie) details.append(element('span', '', resumeStructure(r.titres, r.images)))
      infos.append(details)
      if (r.erreur) infos.append(element('p', 'erreur-texte', r.erreur))

      // Chaque remarque va sous sa source : à corriger (avertissement) ou à lire (information)
      const sorte = (origine: Source, gravite: Remarque['gravite']) =>
        r.remarques.filter((x) => (x.origine === 'conversion') === (origine === 'conversion') && x.gravite === gravite)
      const duDocument = sorte('document', 'avertissement')
      const infosDuDocument = sorte('document', 'info')
      if (duDocument.length || infosDuDocument.length) infos.append(bilanSource('document', duDocument, infosDuDocument))
      if (r.sortie)
        infos.append(bilanSource('conversion', sorte('conversion', 'avertissement'), sorte('conversion', 'info'), `Type de document ${r.raison}.`))
      ligne.append(infos)

      if (r.sortie) {
        const actions = element('div', 'resultat-actions')
        const voir = avecIcone(element('button', 'bouton bouton-contour bouton-compact'), 'eye', 'Vérifier la page')
        voir.setAttribute('type', 'button')
        voir.setAttribute('aria-label', `Vérifier la page ${r.sortie}`)
        voir.addEventListener('click', () => void ouvrirApercu(r))
        const copier = avecIcone(element('button', 'bouton bouton-contour bouton-compact'), 'copy', 'Copier le code')
        copier.setAttribute('type', 'button')
        copier.setAttribute('aria-label', `Copier le code HTML de ${r.sortie}`)
        copier.addEventListener('click', async () =>
          copierCode(await demander<string>({ action: 'apercu', nom: r.sortie }), copier, infos),
        )
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
  if (!recupere) {
    confirmerAbandon(() => void recommencer())
    return
  }
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
async function copierCode(page: string, bouton: HTMLElement, zone: HTMLElement): Promise<void> {
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
    signalerErreur(zone, '')
    confirmerDansBouton(bouton, 'check-circle', 'Code copié')
  } catch {
    signalerErreur(zone, 'Le navigateur a refusé la copie. Télécharger la page.')
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

  // Points à vérifier, par source comme dans la liste des résultats : chaque point mène à son
  // endroit dans la page quand on le connaît
  const point = (r: Remarque): HTMLLIElement => {
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
  }
  const points = resultat.remarques.filter((r) => r.gravite === 'avertissement')
  const duDocument = points.filter((r) => r.origine !== 'conversion')
  const deConversion = points.filter((r) => r.origine === 'conversion')
  sectionVerifier.hidden = duDocument.length === 0
  comptePoints.textContent = `(${duDocument.length})`
  listePoints.replaceChildren(...duDocument.map(point))
  sectionConversion.hidden = deConversion.length === 0
  comptePointsConversion.textContent = `(${deConversion.length})`
  listePointsConversion.replaceChildren(...deConversion.map(point))

  // Plan : la liste des titres, imbriquée par niveau
  const titres = [...doc.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6')]
  if (!titres.length) {
    listePlan.replaceChildren(element('li', 'aide', 'La page n’a aucun titre.'))
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

// Le nom de l'outil, dans l'en-tête, ramène à l'accueil. Devant des résultats, il passe par la
// même confirmation que le bouton : la question du navigateur n'est pas garantie dans Safari.
$<HTMLAnchorElement>('.nom-outil').addEventListener('click', (e) => {
  if (blocResultats.hidden) return
  e.preventDefault()
  void recommencer()
})

// Un hyperlien qui quitte le site dans le même onglet passe aussi par cette confirmation.
// Les liens internes (#section), les téléchargements et les liens ouverts ailleurs ne quittent rien.
document.addEventListener('click', (e) => {
  if (recupere || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  const lien = (e.target as Element).closest<HTMLAnchorElement>('a[href]')
  if (!lien || lien.hasAttribute('download') || lien.target === '_blank') return
  const adresse = new URL(lien.href, location.href)
  if (adresse.origin === location.origin && adresse.pathname === location.pathname) return
  e.preventDefault()
  confirmerAbandon(() => location.assign(adresse.href))
})
for (const lien of [lienPrincipal, lienZip, lienPage]) lien.addEventListener('click', () => (recupere = true))

async function viderListe(): Promise<void> {
  const noms = [...documents.keys()]
  documents.clear()
  afficherListe()
  annoncer('La liste est vide.')
  // Le bouton « Vider la liste » disparaît avec la liste : le focus va au bouton d'ajout
  boutonChoisir.focus()
  if (pret) await Promise.all(noms.map((nom) => demander({ action: 'oublier', nom })))
}

$<HTMLButtonElement>('[data-vider]').addEventListener('click', () =>
  confirmer(
    {
      titre: 'Vider la liste',
      texte: `${documents.size > 1 ? `Les ${documents.size} documents sont retirés` : 'Le document est retiré'} de la liste. Les fichiers restent sur l’ordinateur.`,
      conserver: 'Conserver la liste',
      effacer: 'Vider la liste',
    },
    () => void viderListe(),
  ),
)

$<HTMLButtonElement>('[data-copier-apercu]').addEventListener('click', (e) => {
  const bouton = e.currentTarget as HTMLElement
  if (pageOuverte) void copierCode(pageOuverte.html, bouton, bouton.closest<HTMLElement>('.apercu-entete')!)
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

// ---- Rapport de conversion : affiché dans la page, imprimé avec elle ----
// Le rapport porte son propre bouton d'impression, utile dans le fichier du zip, inutile ici
function sansBouton(html: string): Document {
  const rapport = new DOMParser().parseFromString(html, 'text/html')
  rapport.querySelector('button')?.closest('p')?.remove()
  return rapport
}

// À l'impression, la page ne montre que cette copie du rapport (voir « zone-impression » dans page.css).
// Elle est isolée dans une racine fantôme : ses styles et ceux de la page ne se mélangent pas.
function preparerImpression(html: string): void {
  document.querySelector('.zone-impression')?.remove()
  const rapport = sansBouton(html)
  const zone = document.createElement('div')
  zone.className = 'zone-impression'
  const style = document.createElement('style')
  // Les règles du rapport visent « body » : ici, elles visent la zone
  style.textContent = (rapport.querySelector('style')?.textContent ?? '').replace(/\bbody\b/g, ':host')
  zone.attachShadow({ mode: 'open' }).append(style, ...rapport.body.childNodes)
  document.body.append(zone)
}

boutonRapport.addEventListener('click', () => {
  if (!rapportHtml) return
  cadreRapport.srcdoc = `<!DOCTYPE html>${sansBouton(rapportHtml).documentElement.outerHTML}`
  preparerImpression(rapportHtml)
  dialogueRapport.showModal()
})
$<HTMLButtonElement>('[data-imprimer-rapport]').addEventListener('click', () => window.print())
$<HTMLButtonElement>('[data-fermer-rapport]').addEventListener('click', () => dialogueRapport.close())
dialogueRapport.addEventListener('click', (e) => {
  if (e.target === dialogueRapport) dialogueRapport.close()
})
dialogueRapport.addEventListener('close', () => {
  cadreRapport.srcdoc = ''
  document.querySelector('.zone-impression')?.remove()
})

// ---- Confirmation avant une action qui efface quelque chose ----
// Une seule fenêtre pour toutes les confirmations. « suite » est l'action reprise si la personne confirme.
interface TextesConfirmation {
  titre: string
  texte: string
  /** Bouton qui annule : il a le focus à l'ouverture */
  conserver: string
  /** Bouton qui confirme l'effacement */
  effacer: string
}

let suiteConfirmee: (() => void) | null = null

function confirmer(textes: TextesConfirmation, suite: () => void): void {
  $<HTMLElement>('#titre-confirmation').textContent = textes.titre
  $<HTMLElement>('#texte-confirmation').textContent = textes.texte
  $<HTMLButtonElement>('[data-conserver]').textContent = textes.conserver
  $<HTMLButtonElement>('[data-abandonner]').textContent = textes.effacer
  suiteConfirmee = suite
  confirmation.showModal()
}

// Pages converties non téléchargées : un seul message, quelle que soit la sortie (nouvelle
// conversion, retour à l'accueil, hyperlien vers un autre site)
function confirmerAbandon(suite: () => void): void {
  confirmer(
    {
      titre: 'Pages non téléchargées',
      texte: 'Les pages converties n’ont pas été téléchargées. Quitter les résultats les efface.',
      conserver: 'Conserver les pages',
      effacer: 'Abandonner les pages',
    },
    () => {
      recupere = true
      suite()
    },
  )
}

$<HTMLButtonElement>('[data-conserver]').addEventListener('click', () => confirmation.close())
$<HTMLButtonElement>('[data-abandonner]').addEventListener('click', () => {
  const suite = suiteConfirmee
  confirmation.close()
  suite?.()
})
confirmation.addEventListener('close', () => (suiteConfirmee = null))

// Tout se perd en fermant la page : on prévient si les résultats n'ont pas été récupérés
window.addEventListener('beforeunload', (e) => {
  if (recupere) return
  e.preventDefault()
  e.returnValue = ''     // ancienne façon de demander la confirmation, encore exigée par certains navigateurs
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
  if (outcome === 'accepted') montrerInstallee()      // la mention « MiseEnWeb est installée » reste affichée
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

// ---- Version du site ----
// Le pied de page nomme la version affichée. Un onglet resté ouvert conserve son code : au retour
// sur l'onglet, la page lit version.json et signale une version plus récente.
declare const __VERSION__: string
$<HTMLElement>('[data-version]').textContent = `Version ${__VERSION__}`

const avisVersion = $<HTMLElement>('[data-avis-version]')
$<HTMLButtonElement>('[data-recharger]').addEventListener('click', () => location.reload())

async function verifierVersion(): Promise<void> {
  if (document.visibilityState !== 'visible' || !avisVersion.hidden) return
  try {
    const reponse = await fetch(`${import.meta.env.BASE_URL}version.json`, { cache: 'no-store' })
    if (!reponse.ok) return
    const publiee: { version?: string } = await reponse.json()
    if (!publiee.version || publiee.version === __VERSION__) return
    avisVersion.hidden = false
    annoncer('Une version plus récente de MiseEnWeb est publiée.')
  } catch {}   // hors ligne : la vérification reprend au prochain retour sur l'onglet
}
if (import.meta.env.PROD) document.addEventListener('visibilitychange', () => void verifierVersion())

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
