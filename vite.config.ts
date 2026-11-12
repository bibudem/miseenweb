import { defineConfig, type Plugin } from 'vite'

// Sur GitHub Pages, le site est servi dans un sous-dossier (/<nom du dépôt>/) :
// le workflow de publication le donne dans BASE. En local, il est servi à la racine.
const base = process.env.BASE ?? '/'

// Adresse publique du site, pour l'adresse canonique, l'image de partage, robots.txt et le plan
// du site. Le workflow la donne dans SITE_URL ; en local, une adresse relative suffit.
const urlSite = (process.env.SITE_URL ?? base).replace(/\/?$/, '/')
const absolue = /^https?:\/\//.test(urlSite)

function referencement(): Plugin {
  return {
    name: 'referencement',
    transformIndexHtml: (html) => html.replaceAll('%URL_SITE%', urlSite),
    generateBundle() {
      // Sans adresse publique, robots.txt et le plan du site n'auraient pas d'adresse valable
      if (!absolue) return
      this.emitFile({
        type: 'asset',
        fileName: 'robots.txt',
        source: `User-agent: *\nAllow: /\n\nSitemap: ${urlSite}sitemap.xml\n`,
      })
      this.emitFile({
        type: 'asset',
        fileName: 'sitemap.xml',
        source:
          '<?xml version="1.0" encoding="UTF-8"?>\n' +
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          `  <url><loc>${urlSite}</loc><lastmod>${new Date().toISOString().slice(0, 10)}</lastmod></url>\n` +
          '</urlset>\n',
      })
    },
  }
}

export default defineConfig({
  base,
  plugins: [referencement()],
  worker: { format: 'es' },
  build: {
    // Navigateurs « Baseline » largement disponibles : Chrome, Edge, Firefox et Safari
    // des deux dernières années et demie. La syntaxe CSS récente (imbrication) est aplatie.
    target: 'baseline-widely-available',
    cssTarget: ['chrome107', 'edge107', 'firefox104', 'safari16'],
  },
})
