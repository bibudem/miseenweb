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

/** Branche le dépôt d'un profil. Renvoie la fonction à appeler quand le convertisseur est prêt. */
export function installerProfil({ demander, surCatalogue, annoncer }: Liens): () => Promise<void> {
  const entree = $<HTMLInputElement>('[data-entree-profil]')
  const boutonDeposer = $<HTMLButtonElement>('[data-deposer-profil]')
  const ligneActif = $<HTMLElement>('[data-profil-actif]')
  const texteActif = $<HTMLElement>('[data-texte-profil-actif]')
  const boutonRetirer = $<HTMLButtonElement>('[data-retirer-profil]')
  const zoneErreurs = $<HTMLElement>('[data-profil-erreurs]')

  function montrerActif(libelles: string[]): void {
    ligneActif.hidden = libelles.length === 0
    boutonDeposer.textContent = libelles.length ? 'Remplacer le profil' : 'Utiliser un profil de revue'
    texteActif.textContent = libelles.length
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

  async function deposer(profil: ProfilConserve, auChargement = false): Promise<void> {
    const reponse = await demander<DepotProfil>({ action: 'deposerProfil', texte: profil.texte })
    const n = reponse.messages.length
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
    } else {
      // Un dépôt refusé ne change rien : le profil précédent, s'il y en a un, reste actif
      montrerErreurs(
        `Le profil « ${profil.fichier} » contient ${n} ${n > 1 ? 'erreurs' : 'erreur'}. Il n’est pas ajouté.`,
        reponse.messages,
        'Corriger le fichier, puis le déposer de nouveau.',
      )
    }
  }

  boutonDeposer.addEventListener('click', () => entree.click())

  entree.addEventListener('change', async () => {
    const fichier = entree.files?.[0]
    entree.value = ''      // le même fichier, corrigé, peut être déposé de nouveau
    if (!fichier) return
    try {
      await deposer({ fichier: fichier.name, texte: await fichier.text() })
    } catch (erreur) {
      console.error(erreur)
      montrerErreurs(`Le profil « ${fichier.name} » n’a pas pu être lu.`, ['Vérifier que le fichier est un profil, au format YAML.'], '')
    }
  })

  boutonRetirer.addEventListener('click', async () => {
    const catalogue = await demander<Catalogue>({ action: 'retirerProfil' })
    conserver(null)
    montrerErreurs('', [], '')
    montrerActif([])
    surCatalogue(catalogue)
    annoncer('Profil retiré.')
    boutonDeposer.focus()      // le bouton de retrait vient de disparaître
  })

  return async () => {
    boutonDeposer.disabled = false
    const conserve = lireConserve()
    if (conserve) await deposer(conserve, true).catch(console.error)
  }
}
