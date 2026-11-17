// Assistant de création d'un profil : il compare les documents de la liste, pose ses questions
// un écran à la fois, puis fait écrire le profil par le convertisseur.
// Pendant la création, l'assistant remplace le contenu de la carte de conversion.

import type { DemandeSansId, ProfilGenere, ReleveExemples, ReponsesAssistant, RoleTitre } from './protocole'

/** Nombre de documents à partir duquel une comparaison a un sens */
export const DOCUMENTS_MIN = 2
const NB_ETAPES = 6
const MOTIF_ISSN = /^\d{4}-\d{3}[\dX]$/

/** Rôles offerts pour un groupe de paragraphes en gras. La chaîne vide : le groupe n'est pas un titre */
const ROLES: [RoleTitre | '', string][] = [
  ['titre-article', 'Titre de l’article'],
  ['section', 'Titre de section'],
  ['sous-titre', 'Sous-titre'],
  ['', 'Pas un titre'],
]

const SORTES_IMAGE: ['information' | 'decorative', string][] = [
  ['information', 'Image informative'],
  ['decorative', 'Image décorative'],
]

/** Endroits d'un document où une image paraît, tels que le relevé les nomme */
const ENDROITS: Record<string, string> = { corps: 'corps du texte', 'en-tete': 'en-tête', pied: 'pied de page' }

/** Paragraphes réunis à l'écran 2 : par un style créé par la publication, ou par leur taille quand ils sont en gras */
type Regroupement =
  | { sorte: 'style'; nom: string; articles: number; paragraphes: number; exemples: string[] }
  | { sorte: 'gras'; taille: number | null; styles: string[]; articles: number; paragraphes: number; exemples: string[] }

const nombre = (n: number, singulier: string, pluriel: string) => `${n} ${n > 1 ? pluriel : singulier}`

interface Liens {
  demander: <T = unknown>(demande: DemandeSansId) => Promise<T>
  /** Noms des documents de la liste */
  documents: () => string[]
  annoncer: (texte: string) => void
  /** Dessin d'une icône du site, en SVG */
  icone: (nom: string) => string
  /** Ajoute le profil écrit par l'assistant. Renvoie les messages d'erreur : aucun si le profil est ajouté */
  deposerProfil: (fichier: string, texte: string) => Promise<string[]>
  /** Libellés du profil déjà ajouté dans ce navigateur, ou une liste vide */
  profilActif: () => string[]
  /** Publications dont le profil fait partie du site : leur ISSN ne peut pas servir à un nouveau profil */
  publicationsDuSite: () => { nom: string; issn: string }[]
}

interface Assistant {
  /** À appeler quand la liste des documents change ou quand le convertisseur devient prêt */
  actualiser: (pret: boolean) => void
}

const $ = <T extends Element>(selecteur: string) => document.querySelector<T>(selecteur)!

function element<K extends keyof HTMLElementTagNameMap>(balise: K, classe = '', texte = ''): HTMLElementTagNameMap[K] {
  const el = document.createElement(balise)
  if (classe) el.className = classe
  if (texte) el.textContent = texte
  return el
}

/** Champ de texte avec son étiquette, son aide et l'emplacement de son message d'erreur */
function champ(id: string, etiquette: string, aide: string, valeur: string): { bloc: HTMLElement; entree: HTMLInputElement; erreur: HTMLElement } {
  const bloc = element('div', 'assistant-champ')
  const label = element('label', '', etiquette)
  label.htmlFor = id
  const entree = element('input')
  entree.type = 'text'
  entree.id = id
  entree.value = valeur
  entree.autocomplete = 'off'
  const erreur = element('p', 'erreur-texte')
  erreur.id = `${id}-erreur`
  const decrit = [erreur.id]
  bloc.append(label, entree)
  if (aide) {
    const texteAide = element('p', 'aide', aide)
    texteAide.id = `${id}-aide`
    decrit.unshift(texteAide.id)
    bloc.append(texteAide)
  }
  entree.setAttribute('aria-describedby', decrit.join(' '))
  bloc.append(erreur)
  return { bloc, entree, erreur }
}

function signaler(entree: HTMLInputElement, erreur: HTMLElement, message: string): boolean {
  erreur.textContent = message
  if (message) entree.setAttribute('aria-invalid', 'true')
  else entree.removeAttribute('aria-invalid')
  return !message
}

/** Carte d'une question : un encadré dont l'en-tête porte le sujet et, s'il y a lieu, sa place dans la série */
function carteQuestion(sujet: string, rang = ''): { bloc: HTMLFieldSetElement; corps: HTMLElement } {
  const bloc = element('fieldset', 'assistant-carte')
  const legende = element('legend')
  legende.append(element('span', 'assistant-carte-sujet', sujet))
  // Place de la carte dans la série, par exemple « 2 de 6 », au bout de l'en-tête
  if (rang) legende.append(' ', element('span', 'assistant-carte-rang', rang))
  const corps = element('div', 'assistant-carte-corps')
  bloc.append(legende, corps)
  return { bloc, corps }
}

/** Paragraphe dont chaque nombre est mis en évidence par un compteur : ces nombres viennent de l'analyse des documents */
function avecNombres<K extends 'p' | 'dd'>(balise: K, classe: string, texte: string): HTMLElementTagNameMap[K] {
  const bloc = element(balise, classe)
  // Le découpage garde les nombres : un morceau sur deux en est un
  texte.split(/(\d+)/).forEach((morceau, rang) => bloc.append(rang % 2 ? element('span', 'assistant-nombre', morceau) : morceau))
  return bloc
}

/** Début d'un écran : le constat de l'analyse, avec son nombre mis en évidence, puis l'instruction, qui s'en démarque */
function consigne(debut: string, nombreReleve: number, fin: string, instruction: string): HTMLElement {
  const bloc = element('div', 'assistant-consigne')
  const constat = element('p', 'assistant-constat')
  constat.append(debut, element('span', 'assistant-nombre', String(nombreReleve)), fin)
  bloc.append(constat, element('p', 'assistant-instruction', instruction))
  return bloc
}

/** Pastilles de faits relevés, comme celles de la liste des documents */
function pastilles(...textes: string[]): HTMLElement {
  const ligne = element('p', 'assistant-pastilles')
  ligne.append(...textes.map((texte) => element('span', 'puce', texte)))
  return ligne
}

/** Options à la verticale, une par ligne : celle qui est choisie est surlignée */
function options<T extends string>(nom: string, liste: [T, string][], actuel: T | null, surChoix: (valeur: T) => void): { bloc: HTMLElement; boutons: HTMLInputElement[] } {
  const bloc = element('div', 'assistant-options')
  const boutons = liste.map(([valeur, libelle]) => {
    const etiquette = element('label', 'assistant-option')
    const bouton = element('input')
    bouton.type = 'radio'
    bouton.name = nom
    bouton.checked = actuel === valeur
    bouton.addEventListener('change', () => surChoix(valeur))
    etiquette.append(bouton, element('span', '', libelle))
    bloc.append(etiquette)
    return bouton
  })
  return { bloc, boutons }
}

/** Branche l'assistant de création d'un profil. */
export function installerAssistant({ demander, documents, annoncer, icone, deposerProfil, profilActif, publicationsDuSite }: Liens): Assistant {
  const carte = $<HTMLElement>('.carte-outil')
  const zone = $<HTMLElement>('[data-assistant]')
  const boutonCreer = $<HTMLButtonElement>('[data-creer-profil]')
  const messageProfil = $<HTMLElement>('[data-profil-erreurs]')
  const titreCarte = $<HTMLElement>('#titre-outil')
  const titreCarteInitial = titreCarte.textContent ?? ''
  const compteEtapes = $<HTMLElement>('[data-assistant-etape]')
  // L'assistant est en construction : sur le site publié, son bouton paraît seulement à l'adresse
  // « ?assistant ». Sur le serveur local, il paraît toujours.
  const offert = import.meta.env.DEV || new URLSearchParams(location.search).has('assistant')

  let releve: ReleveExemples
  let reponses: ReponsesAssistant
  /** Regroupements de l'écran des paragraphes : les styles de la publication d'abord, puis les textes en gras */
  let regroupements: Regroupement[]
  /** Rôle choisi pour chaque regroupement, dans le même ordre */
  let roles: (RoleTitre | '')[]
  /** Réponse pour chaque image de « releve.images_communes », dans le même ordre. « sorte » vide : pas encore de réponse */
  let images: { sorte: '' | 'information' | 'decorative'; texte: string }[]

  function fermer(): void {
    zone.hidden = true
    zone.replaceChildren()
    carte.removeAttribute('data-assistant-ouvert')
    titreCarte.textContent = titreCarteInitial
    compteEtapes.hidden = true
    boutonCreer.focus()
  }

  function bouton(classe: string, texte: string, sorte: 'button' | 'submit', iconeDebut = '', iconeFin = ''): HTMLButtonElement {
    const el = element('button', `bouton ${classe}`)
    el.type = sorte
    const dessin = (nom: string, fin = false) => {
      const span = element('span', fin ? 'icone icone-fin' : 'icone')
      span.setAttribute('aria-hidden', 'true')
      span.innerHTML = icone(nom)
      return span
    }
    if (iconeDebut) el.append(dessin(iconeDebut))
    el.append(texte)
    if (iconeFin) el.append(dessin(iconeFin, true))
    return el
  }

  /** Affiche un écran : son titre reçoit le focus, pour que le lecteur d'écran l'annonce */
  function ecran(
    etape: number,
    nom: string,
    pictogramme: string,
    contenu: HTMLElement[],
    suivant: () => void,
    retour?: () => void,
    /** Dernier écran : le bouton principal change de nom, et d'autres boutons le précèdent. « null » : aucun bouton principal */
    fin?: { principal: string | null; autres: HTMLButtonElement[] },
  ): void {
    // Pendant la création, la carte porte le nom de l'assistant, une jauge et le compte des étapes
    // Une fois inscrit, le nom de la revue paraît au-dessus du titre, pour situer la personne à chaque écran
    titreCarte.replaceChildren('Création de profil')
    if (etape > 1 && reponses.revue) titreCarte.prepend(element('span', 'assistant-contexte', reponses.revue), ' ')
    const jauge = element('span', 'assistant-jauge')
    jauge.style.setProperty('--avancement', `${(etape / NB_ETAPES) * 100}%`)
    compteEtapes.replaceChildren(jauge, element('span', '', `${etape} de ${NB_ETAPES}`))
    compteEtapes.hidden = false
    // Le titre de l'écran dit ce qui est demandé. Le lecteur d'écran y lit aussi le compte des étapes
    const titre = element('h3', 'assistant-titre')
    const dessin = element('span', 'fichier-icone')
    dessin.setAttribute('aria-hidden', 'true')
    dessin.innerHTML = `<span class="icone">${icone(pictogramme)}</span>`
    titre.append(dessin, element('span', '', nom), element('span', 'visuellement-masque', `, étape ${etape} de ${NB_ETAPES}`))
    titre.id = 'titre-assistant'
    titre.tabIndex = -1
    const formulaire = element('form', 'assistant-formulaire')
    formulaire.noValidate = true      // les messages d'erreur sont ceux de la page, pas ceux du navigateur
    const actions = element('div', 'assistant-actions')
    if (retour) {
      const precedent = bouton('bouton-texte assistant-retour', 'Retour', 'button', 'arrow-left')
      precedent.addEventListener('click', retour)
      actions.append(precedent)
    }
    const annuler = bouton('bouton-contour', 'Annuler', 'button')
    annuler.addEventListener('click', () => {
      fermer()
      annoncer('Création du profil annulée.')
    })
    actions.append(annuler)
    if (!fin) actions.append(bouton('bouton-plein', 'Continuer', 'submit', '', 'arrow-right'))
    else {
      actions.append(...fin.autres)
      if (fin.principal) actions.append(bouton('bouton-plein', fin.principal, 'submit'))
    }
    formulaire.append(...contenu, actions)
    formulaire.addEventListener('submit', (evenement) => {
      evenement.preventDefault()
      suivant()
    })
    zone.replaceChildren(titre, formulaire)
    titre.focus()
  }

  function ecranRevue(): void {
    const n = releve.nb_articles
    const introduction = avecNombres(
      'p',
      '',
      `MiseEnWeb a comparé ${n} documents. Les réponses de cet assistant produisent un profil : les règles de conversion des documents de la publication.`,
    )
    const nom = champ('assistant-revue', 'Nom de la publication', '', reponses.revue)
    nom.entree.required = true
    const releveIssn = releve.issn[0]
    const issn = champ(
      'assistant-issn',
      'ISSN (facultatif)',
      'L’ISSN écrit dans le pied de page des documents, par exemple 1234-5678. MiseEnWeb reconnaît les documents de la publication par cet ISSN. Sans ISSN, la reconnaissance se fait par le nom des fichiers.',
      reponses.issn,
    )
    const connue = (valeur: string) => publicationsDuSite().find((publication) => publication.issn === valeur)
    if (releveIssn && reponses.issn === releveIssn.valeur)
      issn.bloc.insertBefore(pastilles(`Relevé dans ${nombre(releveIssn.articles, 'document', 'documents')} sur ${n}`), issn.erreur)
    else if (releveIssn && connue(releveIssn.valeur) && !reponses.issn)
      issn.bloc.insertBefore(
        element(
          'p',
          'assistant-avis',
          `Les documents portent l’ISSN ${releveIssn.valeur}, celui de « ${connue(releveIssn.valeur)!.nom} ». MiseEnWeb a déjà un profil pour cet ISSN, et deux profils ne peuvent pas porter le même. Pour ces documents, le nouveau profil se choisit dans le menu de chaque document.`,
        ),
        issn.erreur,
      )

    ecran(1, 'Identification de la publication', 'newspaper', [introduction, nom.bloc, issn.bloc], () => {
      reponses.revue = nom.entree.value.trim()
      reponses.issn = issn.entree.value.trim().toUpperCase()
      const nomValide = signaler(nom.entree, nom.erreur, reponses.revue ? '' : 'Inscrire le nom de la publication.')
      const issnValide = signaler(
        issn.entree,
        issn.erreur,
        !reponses.issn
          ? ''
          : !MOTIF_ISSN.test(reponses.issn)
            ? 'L’ISSN compte huit caractères, avec un trait d’union au milieu : 1234-5678.'
            : connue(reponses.issn)
              ? `Cet ISSN est celui de « ${connue(reponses.issn)!.nom} ». MiseEnWeb a déjà un profil pour cet ISSN. Inscrire un autre ISSN, ou laisser le champ vide.`
              : '',
      )
      if (!nomValide) nom.entree.focus()
      else if (!issnValide) issn.entree.focus()
      else ecranTitres()
    })
  }

  function ecranTitres(): void {
    const groupes = regroupements
    const n = releve.nb_articles
    const contenu: HTMLElement[] = []
    // Plusieurs titres d'article sont permis (un titre en deux langues, par exemple) : l'avis dit ce qui en résulte
    const avis = element('p', 'assistant-avis')
    avis.setAttribute('role', 'status')
    function actualiserAvis(): void {
      const titres = roles.filter((role) => role === 'titre-article').length
      avis.replaceChildren(
        ...(titres > 1
          ? avecNombres(
              'p',
              '',
              `${titres} regroupements sont indiqués comme titre de l’article. Une page web a un seul titre principal : dans chaque document, le premier de ces paragraphes devient le titre de la page, et les suivants deviennent des titres de section.`,
            ).childNodes
          : []),
      )
    }
    if (!groupes.length) {
      contenu.push(
        element('p', '', 'Aucun style propre à la publication ni paragraphe en gras sans style de titre dans ces documents. Les titres portent déjà un style de titre de Word.'),
      )
    } else {
      contenu.push(
        consigne(
          'MiseEnWeb a détecté ',
          groupes.length,
          ` ${groupes.length > 1 ? 'regroupements distincts' : 'regroupement'} de paragraphes.`,
          groupes.length > 1 ? 'Pour chacun, identifier sa fonction dans le texte.' : 'Identifier sa fonction dans le texte.',
        ),
      )
      // Une ligne par regroupement, comme la liste des documents de l'accueil : ce qui est relevé à gauche,
      // le menu de la fonction à droite. Onze regroupements tiennent ainsi sur un écran.
      const liste = element('ul', 'assistant-lignes')
      const entete = element('li', 'assistant-lignes-entete')
      entete.setAttribute('aria-hidden', 'true')      // chaque menu porte déjà son nom pour le lecteur d'écran
      entete.append(element('span', '', 'Paragraphes'), element('span', '', 'Fonction'))
      liste.append(entete)
      groupes.forEach((groupe, rang) => {
        const sujet =
          groupe.sorte === 'style'
            ? `Style « ${groupe.nom} »`
            : `Texte en gras, ${groupe.taille == null ? 'taille par défaut' : `${String(groupe.taille).replace('.', ',')} points`}`
        const ligne = element('li', 'assistant-ligne')
        const infos = element('div', 'assistant-ligne-infos')
        const details = avecNombres(
          'p',
          'aide',
          `Présent ${groupe.paragraphes} fois, dans ${nombre(groupe.articles, 'document', 'documents')} sur ${n}.`,
        )
        const exemples = element('p', 'assistant-ligne-exemples')
        groupe.exemples.forEach((texte, place) => {
          if (place) exemples.append(', ')
          // « bdi » isole chaque extrait : un extrait en arabe se lit de droite à gauche sans déplacer ses voisins
          exemples.append(element('bdi', '', `« ${texte} »`))
        })
        infos.append(element('p', 'assistant-ligne-sujet', sujet), details, exemples)

        const champMenu = element('div', 'champ-liste champ-compact')
        const menu = element('select')
        menu.setAttribute('aria-label', `Fonction : ${sujet}`)
        for (const [valeur, libelle] of ROLES) menu.append(new Option(libelle, valeur, false, roles[rang] === valeur))
        menu.addEventListener('change', () => {
          roles[rang] = menu.value as RoleTitre | ''
          actualiserAvis()
        })
        const fleche = element('span', 'icone')
        fleche.setAttribute('aria-hidden', 'true')
        fleche.innerHTML = icone('caret-down')
        champMenu.append(menu, fleche)
        ligne.append(infos, champMenu)
        liste.append(ligne)
      })
      contenu.push(liste)
      contenu.push(avis)
      actualiserAvis()
    }

    ecran(
      2,
      'Fonction des paragraphes',
      'paragraph',
      contenu,
      () => {
        reponses.titres = groupes.flatMap((groupe, rang): ReponsesAssistant['titres'] => {
          const role = roles[rang]
          if (!role) return []
          return groupe.sorte === 'style' ? [{ style: groupe.nom, role }] : [{ taille: groupe.taille, styles: groupe.styles, role }]
        })
        ecranImages()
      },
      ecranRevue,
    )
  }

  function ecranImages(): void {
    const communes = releve.images_communes
    const n = releve.nb_articles
    const contenu: HTMLElement[] = []
    /** Par image : ce qu'il faut pour vérifier la réponse et montrer son message d'erreur */
    const blocs: { erreur: HTMLElement; premierChoix: HTMLInputElement; entree: HTMLInputElement }[] = []
    if (!communes.length) {
      contenu.push(element('p', '', 'Aucune image commune à ces documents.'))
    } else {
      contenu.push(
        consigne(
          'MiseEnWeb a détecté ',
          communes.length,
          ` ${communes.length > 1 ? 'images communes' : 'image commune'} à ces documents. Un lecteur d’écran lit le texte de remplacement d’une image informative et ignore une image décorative.`,
          communes.length > 1 ? 'Pour chacune, indiquer si elle apporte une information.' : 'Indiquer si elle apporte une information.',
        ),
      )
      communes.forEach((image, rang) => {
        const reponse = images[rang]
        const { bloc, corps } = carteQuestion('Image', `${rang + 1} de ${communes.length}`)
        // Même ordre qu'à l'écran des paragraphes : la phrase qui situe, ce qui est montré, puis les choix
        corps.append(
          avecNombres(
            'p',
            'aide',
            `Présente dans ${nombre(image.articles, 'document', 'documents')} sur ${n} : ${image.endroits.map((e) => ENDROITS[e] ?? e).join(', ')}.`,
          ),
        )
        if (image.apercu) {
          const apercu = element('img', 'assistant-apercu')
          apercu.src = image.apercu
          apercu.alt = `Aperçu de l’image ${rang + 1}`
          corps.append(apercu)
        } else {
          corps.append(element('p', 'aide', 'Aperçu non disponible pour ce type d’image.'))
        }

        const texte = champ(
          `assistant-image-${rang}`,
          'Texte de remplacement',
          'Décrire ce que l’image apporte, en une phrase courte. Pour un logo : le nom qu’il porte.',
          reponse.texte,
        )
        texte.entree.addEventListener('input', () => (reponse.texte = texte.entree.value))
        texte.bloc.hidden = reponse.sorte !== 'information'

        const choix = options(`assistant-sorte-${rang}`, SORTES_IMAGE, reponse.sorte || null, (valeur) => {
          reponse.sorte = valeur
          texte.bloc.hidden = valeur !== 'information'
        })
        // Le message d'erreur est relié au groupe : le lecteur d'écran le lit quand le focus y arrive
        const erreur = element('p', 'erreur-texte')
        erreur.id = `assistant-image-${rang}-choix-erreur`
        bloc.setAttribute('aria-describedby', erreur.id)
        corps.append(choix.bloc, texte.bloc, erreur)
        contenu.push(bloc)
        blocs.push({ erreur, premierChoix: choix.boutons[0], entree: texte.entree })
      })
    }

    ecran(
      3,
      'Texte de remplacement des images',
      'image',
      contenu,
      () => {
        let aCorriger: HTMLElement | null = null
        images.forEach((reponse, rang) => {
          const { erreur, premierChoix, entree } = blocs[rang]
          reponse.texte = reponse.texte.trim()
          let message = ''
          if (!reponse.sorte) message = 'Choisir « Image informative » ou « Image décorative ».'
          else if (reponse.sorte === 'information' && !reponse.texte)
            message = 'Inscrire le texte de remplacement, ou choisir « Image décorative ».'
          erreur.textContent = message
          if (message) aCorriger ??= reponse.sorte ? entree : premierChoix
        })
        if (aCorriger) return (aCorriger as HTMLElement).focus()
        reponses.images = communes.map((image, rang) => ({
          empreinte: image.empreinte,
          texte: images[rang].sorte === 'information' ? images[rang].texte : '',
        }))
        ecranPresentation()
      },
      ecranTitres,
    )
  }

  /** Carte d'une question à choix unique. Renvoie aussi son corps, pour y ajouter une précision */
  function choixUnique<T extends string>(nom: string, question: string, liste: [T, string][], actuel: T, surChoix: (valeur: T) => void): { bloc: HTMLFieldSetElement; corps: HTMLElement } {
    const carteChoix = carteQuestion(question)
    carteChoix.corps.append(options(nom, liste, actuel, surChoix).bloc)
    return carteChoix
  }

  function caseACocher(libelle: string, cochee: boolean, surChoix: (cochee: boolean) => void): HTMLLabelElement {
    const etiquette = element('label', 'assistant-option')
    const boite = element('input')
    boite.type = 'checkbox'
    boite.checked = cochee
    boite.addEventListener('change', () => surChoix(boite.checked))
    etiquette.append(boite, element('span', '', libelle))
    return etiquette
  }

  function ecranPresentation(): void {
    const apparence = choixUnique(
      'assistant-apparence',
      'Apparence de la page',
      [
        ['article', 'Article : titres centrés, texte justifié'],
        ['document', 'Document : titres et texte alignés à gauche'],
      ],
      reponses.apparence,
      (valeur) => (reponses.apparence = valeur),
    )
    const tableaux = choixUnique(
      'assistant-tableaux',
      'Tableaux',
      [
        ['bordures', 'Bordure autour de chaque cellule'],
        ['apa', 'APA, 7e édition : trois lignes horizontales, numéro et titre sur deux lignes'],
        ['chicago', 'Chicago, 18e édition : trois lignes horizontales, numéro et titre sur une ligne'],
      ],
      reponses.tableaux,
      (valeur) => (reponses.tableaux = valeur),
    )
    const { total, deux_lignes: deux, une_ligne: une } = releve.tableaux
    if (deux || une) {
      const [compte, place] = deux >= une ? [deux, 'deux lignes'] : [une, 'une ligne']
      const debut = compte > 1 ? `${compte} tableaux sur ${total} ont leur numéro et leur titre` : `1 tableau sur ${total} a son numéro et son titre`
      tableaux.corps.append(avecNombres('p', 'aide', `Dans ces documents, ${debut} sur ${place}.`))
    }
    const contenu: HTMLElement[] = [
      element('p', '', 'Ces choix règlent l’apparence de la page web. Ils ne changent pas sa structure.'),
      apparence.bloc,
      tableaux.bloc,
    ]
    const elements = carteQuestion('Éléments de la publication')
    const cases = element('div', 'assistant-options')
    if (releve.couleurs.length)
      cases.append(
        caseACocher('Conserver le bandeau placé avant le titre, avec sa couleur de fond', reponses.bandeau, (c) => (reponses.bandeau = c)),
      )
    cases.append(
      caseACocher('Reproduire le pied de page des documents au bas de la page web', reponses.pied_page, (c) => (reponses.pied_page = c)),
    )
    elements.corps.append(cases)
    contenu.push(elements.bloc)
    ecran(4, 'Présentation de la page', 'layout', contenu, ecranReconnaissance, ecranImages)
  }

  function ecranReconnaissance(): void {
    const n = releve.nb_articles
    const avecIssn = Boolean(reponses.issn)
    // Sans ISSN, la partie commune aux noms des documents est proposée comme mot attendu
    const propose = !avecIssn && !reponses.mot_nom_fichier && releve.nom_commun ? releve.nom_commun : reponses.mot_nom_fichier
    const mot = champ(
      'assistant-mot',
      avecIssn ? 'Mot du nom de fichier (facultatif)' : 'Mot du nom de fichier',
      avecIssn
        ? 'Avec ce mot, seuls les fichiers dont le nom le contient suivent ce profil. Laisser vide pour appliquer le profil à tous les documents de la publication.'
        : 'Un mot présent dans le nom de tous les fichiers de la publication, par exemple « ma-publication ».',
      propose,
    )
    if (propose && propose === releve.nom_commun)
      mot.bloc.insertBefore(pastilles(`Partie commune aux noms des ${n} documents`), mot.erreur)
    const constat = element(
      'p',
      'assistant-constat',
      avecIssn
        ? `MiseEnWeb reconnaît les documents de la publication par l’ISSN ${reponses.issn}, écrit dans leur pied de page. Aucune autre condition n’est nécessaire.`
        : 'Sans ISSN, MiseEnWeb reconnaît les documents de la publication par le nom de leur fichier.',
    )
    ecran(
      5,
      'Reconnaissance des documents',
      'magnifying-glass',
      [constat, mot.bloc],
      () => {
        reponses.mot_nom_fichier = mot.entree.value.trim()
        const valide = signaler(
          mot.entree,
          mot.erreur,
          avecIssn || reponses.mot_nom_fichier
            ? ''
            : 'Inscrire un mot présent dans le nom des fichiers de la publication, ou revenir à l’étape 1 pour inscrire l’ISSN.',
        )
        if (valide) void ecranResume().catch(console.error)
        else mot.entree.focus()
      },
      ecranPresentation,
    )
  }

  /** Lignes du résumé : ce que le profil fera, d'après les réponses */
  function resume(): [string, string][] {
    const reconnaissance = [
      reponses.issn ? `ISSN ${reponses.issn}` : '',
      reponses.mot_nom_fichier ? `nom de fichier contenant « ${reponses.mot_nom_fichier} »` : '',
    ].filter(Boolean)
    const informatives = reponses.images.filter((image) => image.texte).length
    const decoratives = reponses.images.length - informatives
    const elements = [reponses.bandeau ? 'bandeau conservé' : '', reponses.pied_page ? 'pied de page reproduit' : ''].filter(Boolean)
    return [
      ['Reconnaissance', reconnaissance.join(', ')],
      [
        'Titres',
        reponses.titres.length
          ? `${nombre(reponses.titres.length, 'regroupement de paragraphes devient', 'regroupements de paragraphes deviennent')} des titres`
          : 'aucun paragraphe en gras ne devient un titre',
      ],
      [
        'Images',
        reponses.images.length
          ? `${informatives} avec un texte de remplacement, ${nombre(decoratives, 'décorative', 'décoratives')}`
          : 'aucune image commune',
      ],
      ['Apparence', reponses.apparence === 'article' ? 'titres centrés, texte justifié' : 'titres et texte alignés à gauche'],
      ['Tableaux', { bordures: 'bordure autour de chaque cellule', apa: 'APA, 7e édition', chicago: 'Chicago, 18e édition' }[reponses.tableaux]],
      ['Éléments de la publication', elements.join(', ') || 'aucun'],
    ]
  }

  async function ecranResume(): Promise<void> {
    const profil = await demander<ProfilGenere>({ action: 'genererProfil', reponses })
    const fichier = `${/^nom: (.+)$/m.exec(profil.texte)?.[1] ?? 'profil'}.yaml`
    const contenu: HTMLElement[] = []
    const erreurs = element('div', 'assistant-erreurs erreur-texte')
    erreurs.id = 'assistant-erreurs'
    erreurs.tabIndex = -1

    function montrerErreurs(messages: string[]): void {
      const liste = element('ul')
      liste.append(...messages.map((m) => element('li', '', m)))
      erreurs.replaceChildren(
        element('p', '', `Le profil contient ${nombre(messages.length, 'erreur', 'erreurs')}. Il n’est pas ajouté.`),
        liste,
        element('p', '', 'Revenir aux étapes précédentes pour corriger les réponses.'),
      )
    }

    const valide = profil.messages.length === 0
    if (valide) {
      contenu.push(element('p', 'assistant-instruction', `Le profil de la publication « ${reponses.revue} » est prêt.`))
    } else {
      montrerErreurs(profil.messages)
    }
    contenu.push(erreurs)      // avant le résumé : une erreur se lit en premier
    const { bloc, corps } = carteQuestion('Réglages retenus')
    const liste = element('dl', 'assistant-resume')
    for (const [terme, description] of resume())
      liste.append(element('dt', '', terme), terme === 'Titres' || terme === 'Images' ? avecNombres('dd', '', description) : element('dd', '', description))
    corps.append(liste)
    contenu.push(bloc)
    if (valide) {
      const actif = profilActif()
      contenu.push(
        element('p', 'aide', 'Ajouter le profil : il s’applique aux documents de la liste et il est conservé dans ce navigateur.'),
        element(
          'p',
          'aide',
          `Télécharger le profil : le fichier ${fichier} se dépose ensuite dans MiseEnWeb par le bouton « Choisir un fichier » de la section « Profil », sur un autre ordinateur ou par une autre personne.`,
        ),
      )
      if (actif.length)
        contenu.push(element('p', 'aide', `Ce profil remplace le profil ${actif.map((l) => `« ${l} »`).join(', ')}, déjà ajouté dans ce navigateur.`))
    }

    const telecharger = bouton('bouton-contour', 'Télécharger le profil', 'button', 'download-simple')
    telecharger.addEventListener('click', () => {
      const lien = element('a')
      lien.href = URL.createObjectURL(new Blob([profil.texte], { type: 'application/yaml' }))
      lien.download = fichier
      lien.click()
      URL.revokeObjectURL(lien.href)
      annoncer(`Profil téléchargé : ${fichier}.`)
    })

    ecran(
      6,
      'Résumé du profil',
      'list-checks',
      contenu,
      async () => {
        const messages = await deposerProfil(fichier, profil.texte)
        if (messages.length) {
          montrerErreurs(messages)
          erreurs.focus()
        } else fermer()      // l'ajout est annoncé par le dépôt du profil, comme pour un fichier déposé
      },
      ecranReconnaissance,
      valide ? { principal: 'Ajouter le profil', autres: [telecharger] } : { principal: null, autres: [] },
    )
  }

  /** Dit pourquoi l'assistant ne s'ouvre pas. Le bouton reste actif : un bouton grisé ou absent ne l'explique pas */
  function refuser(texte: string): void {
    messageProfil.replaceChildren(element('p', '', texte))
    messageProfil.focus()
  }

  async function ouvrir(): Promise<void> {
    if (documents().length < DOCUMENTS_MIN) {
      refuser(`L’assistant compare au moins ${DOCUMENTS_MIN} documents. Ajouter des documents à la liste, puis créer le profil.`)
      return
    }
    boutonCreer.disabled = true
    try {
      releve = await demander<ReleveExemples>({ action: 'releverExemples', noms: documents() })
    } finally {
      boutonCreer.disabled = false
    }
    if (releve.nb_articles < DOCUMENTS_MIN) {
      refuser(`L’assistant compare au moins ${DOCUMENTS_MIN} documents lisibles. Ajouter d’autres documents à la liste, puis créer le profil.`)
      return
    }
    reponses = {
      revue: '',
      // L'ISSN relevé est proposé, sauf s'il appartient à une publication dont le site a déjà le profil
      issn: publicationsDuSite().some((publication) => publication.issn === releve.issn[0]?.valeur) ? '' : (releve.issn[0]?.valeur ?? ''),
      mot_nom_fichier: '',
      titres: [],
      images: [],
      apparence: 'article',
      // La place du numéro et du titre suggère la norme suivie : deux lignes pour l'APA, une pour Chicago
      tableaux:
        releve.tableaux.deux_lignes > releve.tableaux.une_ligne
          ? 'apa'
          : releve.tableaux.une_ligne > releve.tableaux.deux_lignes
            ? 'chicago'
            : 'bordures',
      bandeau: releve.couleurs.length > 0,
      pied_page: true,
    }
    // Choix de départ : le groupe de plus grande taille est le titre de l'article
    images = releve.images_communes.map(() => ({ sorte: '', texte: '' }))
    regroupements = [
      ...releve.styles_propres.map((style) => ({ sorte: 'style' as const, ...style })),
      ...releve.titres_en_gras.map((groupe) => ({ sorte: 'gras' as const, ...groupe })),
    ]
    // Un style ne reçoit aucun choix d'avance : son nom ne suffit pas à dire sa fonction
    const premierGras = regroupements.findIndex((groupe) => groupe.sorte === 'gras')
    roles = regroupements.map((groupe, rang) =>
      rang === premierGras && groupe.sorte === 'gras' && groupe.taille != null ? 'titre-article' : '',
    )
    carte.setAttribute('data-assistant-ouvert', '')
    zone.hidden = false
    ecranRevue()
  }

  boutonCreer.addEventListener('click', () => void ouvrir().catch(console.error))

  return {
    actualiser: (pret) => {
      boutonCreer.hidden = !offert || !pret
      // Le refus affiché ne vaut plus dès que la liste compte assez de documents
      if (documents().length >= DOCUMENTS_MIN && messageProfil.textContent?.startsWith('L’assistant compare')) messageProfil.replaceChildren()
    },
  }
}
