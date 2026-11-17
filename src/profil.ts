// Profil de revue déposé par l'utilisateur : dépôt, validation, conservation dans le navigateur, retrait.
// Le profil ne quitte pas l'ordinateur. Le convertisseur le valide; cette page affiche le résultat.

import type { Catalogue, DemandeSansId, DepotProfil } from './protocole'

const CLE_PROFIL = 'miseenweb-profil'

interface ProfilConserve {
  fichier: string
  texte: string
}

interface Liens {
  demander: <T = unknown>(demande: DemandeSansId) => Promise<T>
  /** Appelé quand la liste des profils change : la page refait ses menus et son analyse */
  surCatalogue: (catalogue: Catalogue) => void
  annoncer: (texte: string) => void
  /** Demande une confirmation avant une action qui efface quelque chose. « suite » est l'action confirmée */
  confirmer: (textes: { titre: string; texte: string; conserver: string; effacer: string }, suite: () => void) => void
}

const $ = <T extends Element>(selecteur: string) => document.querySelector<T>(selecteur)!

function element<K extends keyof HTMLElementTagNameMap>(balise: K, classe = '', texte = ''): HTMLElementTagNameMap[K] {
  const el = document.createElement(balise)
  if (classe) el.className = classe
  if (texte) el.textContent = texte
  return el
}

function lireConserve(): ProfilConserve | null {
  try {
    const brut = localStorage.getItem(CLE_PROFIL)
    const lu = brut ? (JSON.parse(brut) as Partial<ProfilConserve>) : null
    return lu && typeof lu.fichier === 'string' && typeof lu.texte === 'string' ? { fichier: lu.fichier, texte: lu.texte } : null
  } catch {
    return null
  }
}

function conserver(profil: ProfilConserve | null): void {
  try {
    if (profil) localStorage.setItem(CLE_PROFIL, JSON.stringify(profil))
    else localStorage.removeItem(CLE_PROFIL)
  } catch {}      // navigation privée ou stockage refusé : le profil vaut pour la visite en cours
}

/** Vrai pour un fichier de profil, d'après son nom */
export const estProfil = (nom: string) => /\.ya?ml$/i.test(nom)

interface Depot {
  /** À appeler quand le convertisseur est prêt : dépose de nouveau le profil conservé, s'il y en a un */
  pret: () => Promise<void>
  /** Dépose un fichier de profil, choisi par le bouton ou glissé dans la page */
  deposerFichier: (fichier: File) => Promise<void>
  /** Dépose un profil écrit par l'assistant. Renvoie les messages d'erreur : aucun si le profil est ajouté */
  deposerTexte: (fichier: string, texte: string) => Promise<string[]>
  /** Libellés du profil ajouté, ou une liste vide */
  actif: () => string[]
}

/** Branche le dépôt d'un profil. */
export function installerProfil({ demander, surCatalogue, annoncer, confirmer }: Liens): Depot {
  const entree = $<HTMLInputElement>('[data-entree-profil]')
  const boutonDeposer = $<HTMLButtonElement>('[data-deposer-profil]')
  const libelleDeposer = $<HTMLElement>('[data-libelle-deposer]')
  const ligneActif = $<HTMLElement>('[data-profil-actif]')
  const boutonRetirer = $<HTMLButtonElement>('[data-retirer-profil]')
  const zoneErreurs = $<HTMLElement>('[data-profil-erreurs]')

  let libellesActifs: string[] = []

  function montrerActif(libelles: string[]): void {
    libellesActifs = libelles
    ligneActif.hidden = boutonRetirer.hidden = libelles.length === 0
    libelleDeposer.textContent = libelles.length ? 'Remplacer le profil' : 'Choisir un fichier'
    ligneActif.textContent = libelles.length
      ? `Profil ajouté : ${libelles.map((l) => `« ${l} »`).join(', ')}. Il est conservé dans ce navigateur.`
      : ''
  }

  function montrerErreurs(introduction: string, messages: string[], conclusion: string): void {
    zoneErreurs.replaceChildren()
    if (!messages.length) return
    const liste = element('ul')
    liste.append(...messages.map((m) => element('li', '', m)))
    zoneErreurs.append(element('p', '', introduction), liste)
    if (conclusion) zoneErreurs.append(element('p', '', conclusion))
  }

  // Les erreurs ne sont pas annoncées d'office : le focus va à leur zone, que le lecteur d'écran lit alors
  function allerAuxErreurs(): void {
    zoneErreurs.focus()
  }

  /** « origine » : d'où vient le profil. L'assistant affiche lui-même les erreurs d'un profil qu'il a écrit */
  async function deposer(profil: ProfilConserve, origine: 'fichier' | 'chargement' | 'assistant' = 'fichier'): Promise<string[]> {
    const auChargement = origine === 'chargement'
    const reponse = await demander<DepotProfil>({ action: 'deposerProfil', texte: profil.texte })
    const n = reponse.messages.length
    if (n && origine === 'assistant') return reponse.messages
    if (n === 0) {
      conserver(profil)
      montrerErreurs('', [], '')
      montrerActif(reponse.libelles)
      surCatalogue(reponse.catalogue)
      if (!auChargement) annoncer(`Profil ajouté : ${reponse.libelles.join(', ')}.`)
    } else if (auChargement) {
      conserver(null)
      montrerActif([])
      montrerErreurs(
        'Le profil conservé dans ce navigateur n’est plus valide avec cette version de MiseEnWeb. Il est retiré.',
        reponse.messages,
        '',
      )
      // Au chargement, le focus ne bouge pas : une annonce signale le message
      annoncer('Le profil conservé dans ce navigateur n’est plus valide. Il est retiré.')
    } else {
      // Un dépôt refusé ne change rien : le profil précédent, s'il y en a un, reste actif
      montrerErreurs(
        `Le profil « ${profil.fichier} » contient ${n} ${n > 1 ? 'erreurs' : 'erreur'}. Il n’est pas ajouté.`,
        reponse.messages,
        'Corriger le fichier, puis le déposer de nouveau.',
      )
      allerAuxErreurs()
    }
    return reponse.messages
  }

  boutonDeposer.addEventListener('click', () => entree.click())

  async function deposerFichier(fichier: File): Promise<void> {
    try {
      await deposer({ fichier: fichier.name, texte: await fichier.text() })
    } catch (erreur) {
      console.error(erreur)
      montrerErreurs(`Le profil « ${fichier.name} » n’a pas pu être lu.`, ['Vérifier que le fichier est un profil, au format YAML.'], '')
      allerAuxErreurs()
    }
  }

  entree.addEventListener('change', () => {
    const fichier = entree.files?.[0]
    entree.value = ''      // le même fichier, corrigé, peut être déposé de nouveau
    if (fichier) void deposerFichier(fichier)
  })

  async function retirer(): Promise<void> {
    const catalogue = await demander<Catalogue>({ action: 'retirerProfil' })
    conserver(null)
    montrerErreurs('', [], '')
    montrerActif([])
    surCatalogue(catalogue)
    annoncer('Profil retiré.')
    boutonDeposer.focus()      // le bouton de retrait vient de disparaître
  }

  boutonRetirer.addEventListener('click', () =>
    confirmer(
      {
        titre: 'Retirer le profil',
        texte: `Le profil ${libellesActifs.map((l) => `« ${l} »`).join(', ')} est retiré de ce navigateur. Sans fichier de profil téléchargé, il doit être créé de nouveau.`,
        conserver: 'Conserver le profil',
        effacer: 'Retirer le profil',
      },
      () => void retirer().catch(console.error),
    ),
  )

  return {
    deposerFichier,
    deposerTexte: (fichier, texte) => deposer({ fichier, texte }, 'assistant'),
    actif: () => libellesActifs,
    pret: async () => {
      boutonDeposer.disabled = false
      const conserve = lireConserve()
      if (conserve) await deposer(conserve, 'chargement').catch(console.error)
    },
  }
}
