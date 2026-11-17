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

/** Relevé de ce que des articles d'exemple ont en commun. « articles » : nombre d'articles où l'élément paraît */
export interface ReleveExemples {
  nb_articles: number
  articles: string[]
  illisibles: { fichier: string; erreur: string }[]
  styles: { nom: string; articles: number; paragraphes: number; titre: boolean }[]
  /** Paragraphes courts en gras sans style de titre, groupés par taille de police (null : taille par défaut) */
  titres_en_gras: { taille: number | null; articles: number; paragraphes: number; styles: string[]; exemples: string[] }[]
  /** Styles créés par la publication, avec des extraits de leurs paragraphes */
  styles_propres: { nom: string; articles: number; paragraphes: number; exemples: string[] }[]
  /** « apercu » : l'image en adresse « data: », ou une chaîne vide si le navigateur ne l'affiche pas */
  images_communes: { empreinte: string; type: string; articles: number; endroits: string[]; apercu: string }[]
  issn: { valeur: string; articles: number }[]
  couleurs: { couleur: string; articles: number; exemples: string[] }[]
  tableaux: { articles: number; total: number; deux_lignes: number; une_ligne: number; sans_titre: number }
  nom_commun: string
}

export type RoleTitre = 'titre-article' | 'section' | 'sous-titre'

/** Réponses de l'assistant de création d'un profil, telles que les reçoit le générateur */
export interface ReponsesAssistant {
  revue: string
  issn: string
  mot_nom_fichier: string
  /** Un regroupement retenu comme titre : un style créé par la publication, ou du texte en gras d'une taille donnée */
  titres: ({ style: string; role: RoleTitre } | { taille: number | null; styles: string[]; role: RoleTitre })[]
  /** « texte » vide : image décorative */
  images: { empreinte: string; texte: string }[]
  apparence: 'document' | 'article'
  tableaux: 'bordures' | 'apa' | 'chicago'
  bandeau: boolean
  pied_page: boolean
}

/** Profil écrit par le générateur : « messages » est vide quand le profil est valide */
export interface ProfilGenere {
  texte: string
  messages: string[]
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
  | { action: 'releverExemples'; noms: string[] }
  | { action: 'genererProfil'; reponses: ReponsesAssistant }

export type Demande = SansId & { id: number }
export type DemandeSansId = SansId

export type Evenement =
  | { type: 'etat'; etape: 'python' | 'bibliotheques'; texte: string }
  | { type: 'telechargement'; fait: number; total: number }
  | { type: 'pret'; catalogue: Catalogue }
  | { type: 'echec'; texte: string }
  | { type: 'progression'; fichier: string; rang: number; total: number }
  | { type: 'reponse'; id: number; resultat?: unknown; erreur?: string }
