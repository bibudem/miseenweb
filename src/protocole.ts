// Messages échangés entre la page et le worker du convertisseur.

export interface Revue {
  nom: string
  issn: string
  /** Vrai pour le profil déposé par l'utilisateur, faux pour une revue du site */
  depose: boolean
}

export interface ProfilCatalogue {
  nom: string
  libelle: string
  revue: string
  /** Vrai pour un profil déposé par l'utilisateur, faux pour un profil du site */
  depose: boolean
}

/** Réponse au dépôt d'un profil : « messages » est vide quand le profil est accepté */
export interface DepotProfil {
  messages: string[]
  libelles: string[]
  catalogue: Catalogue
}

export interface Catalogue {
  revues: Revue[]
  profils: ProfilCatalogue[]
}

export interface Analyse {
  nom: string
  profil?: string
  libelle?: string
  raison?: string
  issn?: string
  revueIssn?: string
  erreur?: string
}

export interface Remarque {
  gravite: 'avertissement' | 'info'
  titre: string
  conseil: string
  cible: { id?: string; balise?: string; rang?: number }
  /** Titre d'un groupe de remarques identiques, par exemple « {n} images sans texte de remplacement » */
  pluriel: string
  /** « document » : défaut du document Word, à corriger dans Word; « conversion » : défaut de la page produite */
  origine: 'document' | 'conversion'
}

export interface Resultat {
  fichier: string
  sortie: string
  statut: 'ok' | 'avertissements' | 'erreur'
  profil: string
  libelle: string
  raison: string
  erreur: string
  remarques: Remarque[]
  titres: Record<string, number>
  images: number
}

type SansId =
  | { action: 'deposer'; nom: string; octets: ArrayBuffer }
  | { action: 'analyser'; documents: { nom: string; profil: string }[]; revue: string }
  | { action: 'oublier'; nom: string }
  | { action: 'convertir'; documents: { nom: string; profil: string }[]; revue: string }
  | { action: 'archive' }
  | { action: 'apercu'; nom: string }
  | { action: 'rapport' }
  | { action: 'deposerProfil'; texte: string }
  | { action: 'retirerProfil' }

export type Demande = SansId & { id: number }
export type DemandeSansId = SansId

export type Evenement =
  | { type: 'etat'; etape: 'python' | 'bibliotheques'; texte: string }
  | { type: 'telechargement'; fait: number; total: number }
  | { type: 'pret'; catalogue: Catalogue }
  | { type: 'echec'; texte: string }
  | { type: 'progression'; fichier: string; rang: number; total: number }
  | { type: 'reponse'; id: number; resultat?: unknown; erreur?: string }
