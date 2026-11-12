// Repris tel quel du site des Bibliothèques (dépôt bibweb, src/lib/animations.ts).
/*
 * Apparitions au défilement (« reveals ») des bandes de vitrine.
 *
 * Amélioration progressive : le HTML et la CSS montrent tout. Ce script
 * masque seulement ce qui est SOUS la ligne de flottaison au moment où il
 * s'exécute (classe `a-reveler`, voir src/styles/animations.css), puis le
 * révèle une seule fois quand il entre à l'écran. Sans JS, avec un script en
 * erreur, avec le mouvement réduit ou à l'impression, rien n'est masqué.
 * Rien de ce qui est déjà visible (bannière, h1, premier écran) n'est animé :
 * la lecture n'attend jamais une animation.
 *
 * Balisage (voir CONVENTIONS, « Mouvement ») :
 * - `data-revelation="zone"` : conteneur dont chaque enfant est une unité
 *   (l'intérieur d'une Section de vitrine) ;
 * - `data-revelation="groupe"` : grille, carrousel, liste ; ses enfants
 *   sont des unités distinctes, qui apparaissent en léger décalage. Un enfant
 *   de zone qui contient un groupe est parcouru jusqu'à ce groupe.
 */

const ZONE = '[data-revelation="zone"]'
const GROUPE = '[data-revelation="groupe"]'
/** Décalage maximal (en pas de --duree-courte-1) : au-delà, on n'attend plus */
const RANG_MAX = 5
/** La révélation part quand l'unité dépasse de 8 % le bas de l'écran */
const MARGE = '0px 0px -8% 0px'

function unites(): HTMLElement[] {
  const liste: HTMLElement[] = []
  const ajouter = (el: Element) => {
    if (!(el instanceof HTMLElement) || el.matches('script, style, template')) return
    // display: none (panneau d'onglet, volet fermé) ou display: contents :
    // l'opacité n'y aurait aucun effet, ou l'élément n'est pas à l'écran
    if (!el.getClientRects().length) return
    if (el.matches(GROUPE)) {
      for (const enfant of el.children) ajouter(enfant)
    } else if (el.querySelector(GROUPE)) {
      for (const enfant of el.children) ajouter(enfant)
    } else {
      liste.push(el)
    }
  }
  for (const zone of document.querySelectorAll(ZONE)) {
    // Une zone dans une zone est déjà couverte par la première
    if (zone.parentElement?.closest(ZONE)) continue
    for (const enfant of zone.children) ajouter(enfant)
  }
  return liste
}

function demarrer() {
  const reduit = window.matchMedia('(prefers-reduced-motion: reduce)')
  const impression = window.matchMedia('print')
  if (reduit.matches || impression.matches || !('IntersectionObserver' in window)) return
  // Rechargement ou retour : le navigateur restaure la position de
  // défilement après ce script ; ce qu'on y retrouve serait animé alors
  // qu'on l'a déjà lu. On n'anime que les nouvelles visites.
  const navigation = performance.getEntriesByType?.('navigation')[0] as PerformanceNavigationTiming | undefined
  if (navigation && navigation.type !== 'navigate') return

  const hauteur = window.innerHeight
  // Lien profond (#ancre) : tout ce qui précède la cible et l'écran qui la
  // suit reste visible, que le navigateur ait déjà sauté à la cible ou non.
  const cible = ancre(location.hash)
  const limite = Math.max(hauteur, cible ? cible.getBoundingClientRect().top + hauteur : 0)

  const enAttente = new Set<HTMLElement>()
  for (const unite of unites()) {
    if (unite.getBoundingClientRect().top >= limite) enAttente.add(unite)
  }
  if (!enAttente.size) return

  /** Montre sans transition (focus, ancre, impression) */
  const montrer = (unite: HTMLElement) => {
    enAttente.delete(unite)
    unite.classList.remove('a-reveler', 'revele')
    unite.style.removeProperty('--rang')
  }

  /** Révèle en fondu ; le décalage suit l'ordre du document */
  const reveler = (lot: HTMLElement[]) => {
    lot.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
    lot.forEach((unite, i) => {
      enAttente.delete(unite)
      observateur.unobserve(unite)
      unite.style.setProperty('--rang', String(Math.min(i, RANG_MAX)))
      unite.classList.add('revele')
      // Nettoyage : l'unité retrouve ses propres transitions (survol des
      // cartes). Minuterie de secours si transitionend ne vient pas
      // (onglet en arrière-plan, propriété déjà à sa valeur).
      let fini = false
      const nettoyer = () => {
        if (fini) return
        fini = true
        montrer(unite)
      }
      unite.addEventListener('transitionend', (e) => e.target === unite && e.propertyName === 'opacity' && nettoyer())
      setTimeout(nettoyer, 1200)
    })
    finirSiVide()
  }

  /** Tout ce qui est au-dessus du bas de l'écran (ou d'une limite) */
  const avant = (bas: number) => [...enAttente].filter((u) => u.getBoundingClientRect().top < bas)

  let premierAppel = true
  const observateur = new IntersectionObserver(
    (entrees) => {
      const visibles = entrees.some((e) => e.isIntersecting)
      // Premier rappel : ce qui est déjà à l'écran (restauration du
      // défilement, saut à l'ancre après la mesure) se montre sans animation.
      if (premierAppel) {
        premierAppel = false
        if (visibles) avant(window.innerHeight).forEach(montrer)
        finirSiVide()
        return
      }
      // On révèle aussi les unités voisines déjà passées ou à la même
      // hauteur : diapositives hors champ d'un carrousel, défilement rapide.
      if (visibles) reveler(avant(window.innerHeight * 0.92))
    },
    { rootMargin: MARGE },
  )

  for (const unite of enAttente) {
    unite.classList.add('a-reveler')
    observateur.observe(unite)
  }

  // Le focus clavier et les liens d'ancre montrent leur cible tout de suite
  const surFocus = (e: FocusEvent) => {
    for (const unite of enAttente) if (unite.contains(e.target as Node)) montrer(unite)
    finirSiVide()
  }
  const surAncre = (hash: string) => {
    const el = ancre(hash)
    if (!el) return
    avant(el.getBoundingClientRect().top + window.innerHeight).forEach(montrer)
    for (const unite of enAttente) if (unite.contains(el)) montrer(unite)
    finirSiVide()
  }
  const surClic = (e: MouseEvent) => {
    const lien = (e.target as Element | null)?.closest?.('a[href*="#"]') as HTMLAnchorElement | null
    if (lien && lien.pathname === location.pathname) surAncre(lien.hash)
  }
  const surHash = () => surAncre(location.hash)
  const toutMontrer = () => {
    ;[...enAttente].forEach(montrer)
    finirSiVide()
  }

  document.addEventListener('focusin', surFocus)
  document.addEventListener('click', surClic, true)
  window.addEventListener('hashchange', surHash)
  window.addEventListener('beforeprint', toutMontrer)
  reduit.addEventListener('change', toutMontrer)

  // Tout est révélé : on se déconnecte
  function finirSiVide() {
    if (enAttente.size) return
    observateur.disconnect()
    document.removeEventListener('focusin', surFocus)
    document.removeEventListener('click', surClic, true)
    window.removeEventListener('hashchange', surHash)
    window.removeEventListener('beforeprint', toutMontrer)
    reduit.removeEventListener('change', toutMontrer)
  }
}

function ancre(hash: string): HTMLElement | null {
  const id = decodeURIComponent(hash.slice(1))
  return id ? document.getElementById(id) : null
}

/*
 * Lien profond : le navigateur fait défiler jusqu'à la cible en suivant
 * scroll-behavior: smooth de html, donc en traversant toute la page (plus de
 * 5000 px sur /recherche/#orcid) avant d'afficher le contenu visé. Le temps du
 * chargement, le saut est immédiat ; le défilement doux revient ensuite pour
 * les liens internes.
 */
function sauterALAncre() {
  if (!location.hash) return
  const racine = document.documentElement
  racine.style.scrollBehavior = 'auto'
  const retablir = () => requestAnimationFrame(() => requestAnimationFrame(() => racine.style.removeProperty('scroll-behavior')))
  if (document.readyState === 'complete') retablir()
  else window.addEventListener('load', retablir, { once: true })
}

sauterALAncre()

try {
  demarrer()
} catch {
  // Un échec laisse la page telle quelle : tout est déjà visible.
  document.querySelectorAll('.a-reveler').forEach((el) => el.classList.remove('a-reveler', 'revele'))
}
