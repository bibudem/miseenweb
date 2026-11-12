// Service worker de MiseEnWeb : rend les visites suivantes presque instantanées et permet
// d'utiliser la page sans connexion.
//
// - Pyodide et les paquets Python (pyodide/<version>/…) : gardés après le premier
//   téléchargement. Leur adresse change avec la version : jamais périmés.
// - Fichiers de la construction (assets/…, au nom haché) : gardés de la même façon.
// - La page et les autres fichiers : réseau d'abord, copie gardée en cas de panne.
//
// Aucun document de l'utilisateur ne passe par ici : ils restent dans la mémoire de la page.

const CACHE_DURABLE = 'miseenweb-durable-v1'
const CACHE_PAGE = 'miseenweb-page-v1'
const PORTEE = new URL(self.registration.scope)

const estDurable = (url) => {
  const chemin = url.pathname.slice(PORTEE.pathname.length)
  return chemin.startsWith('assets/') || /^pyodide\/[^/]+\//.test(chemin)
}

self.addEventListener('install', (evenement) => {
  evenement.waitUntil(
    caches.open(CACHE_PAGE).then((cache) => cache.add(PORTEE.href)).then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (evenement) => {
  evenement.waitUntil(
    caches
      .keys()
      .then((noms) => Promise.all(noms.filter((n) => ![CACHE_DURABLE, CACHE_PAGE].includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (evenement) => {
  const requete = evenement.request
  const url = new URL(requete.url)
  if (requete.method !== 'GET' || url.origin !== PORTEE.origin || !url.pathname.startsWith(PORTEE.pathname)) return

  if (estDurable(url)) {
    evenement.respondWith(
      caches.open(CACHE_DURABLE).then(async (cache) => {
        const garde = await cache.match(requete)
        if (garde) return garde
        const reponse = await fetch(requete)
        if (reponse.ok) await cache.put(requete, reponse.clone())
        return reponse
      }),
    )
    return
  }

  evenement.respondWith(
    caches.open(CACHE_PAGE).then(async (cache) => {
      try {
        const reponse = await fetch(requete)
        if (reponse.ok) await cache.put(requete, reponse.clone())
        return reponse
      } catch {
        return (await cache.match(requete, { ignoreSearch: true })) ?? Response.error()
      }
    }),
  )
})
