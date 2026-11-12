"""Pont entre la page web et le convertisseur docx2html.

- Choix du profil : détection automatique par défaut (règles des profils, et ISSN du pied
  de page qui limite le choix à la revue reconnue), revue imposée dans le menu « Revue »,
  ou type de document choisi à la main pour un fichier.
- Remarques : les avertissements du convertisseur sont traduits en langage courant, avec la
  correction à faire dans Word, et complétés par des vérifications d'accessibilité de la page
  produite (images sans texte de remplacement, liens vagues, tableaux sans entête).
- Rapport : en Markdown (celui du convertisseur) et en HTML lisible, à imprimer.

Les fichiers vivent dans le système de fichiers en mémoire du navigateur : /entree reçoit
les documents Word, /sortie les pages produites. Rien n'est envoyé sur un serveur.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup

from docx2html.diagnostic import inventorier
from docx2html.pied_page import issn_du_document
from docx2html.pipeline import convertir_fichier
from docx2html.profils import Profil, charger_profils, choisir_profil
from docx2html.rapport import ecrire_rapport

ENTREE = Path("/entree")
SORTIE = Path("/sortie")
PROFILS = charger_profils(Path("/app/profils"))
AUTO = "__auto__"

# Noms des profils pour les personnes : ceux des fichiers YAML sont des identifiants
LIBELLES = {
    "defaut": "Document général",
    "these": "Thèse ou mémoire",
    "rapport-recherche": "Rapport de recherche",
}
VARIANTES = {
    "mise-en-page": "article mis en page",
    "manuscrit": "manuscrit",
}

# Ce que l'on sait de chaque document déposé, pour ne pas le relire à chaque changement
_documents: dict[str, dict] = {}
_resultats: list[dict] = []


def libelle(profil: Profil) -> str:
    if profil.nom in LIBELLES:
        return LIBELLES[profil.nom]
    if "/" in profil.nom and profil.revue:
        variante = profil.nom.split("/", 1)[1]
        return f"{profil.revue} : {VARIANTES.get(variante, variante.replace('-', ' '))}"
    return profil.description.split(".")[0] or profil.nom


# ---- Catalogue et choix du profil ------------------------------------------------------

def catalogue() -> str:
    """Revues et profils, pour les menus de la page."""
    revues = {p.revue: p.issn for p in PROFILS.values() if p.revue}
    profils = sorted(PROFILS.values(), key=lambda p: (bool(p.revue), p.revue, libelle(p)))
    return json.dumps({
        "revues": [{"nom": nom, "issn": issn} for nom, issn in sorted(revues.items())],
        "profils": [{"nom": p.nom, "libelle": libelle(p), "revue": p.revue} for p in profils],
    })


def _profils_pour(issn: str | None, revue: str) -> dict:
    """Profils permis pour un document.

    - Détection automatique : un ISSN connu limite le choix à sa revue, un ISSN inconnu aux
      profils génériques ; sans ISSN, tous les profils sont candidats, choisis par leurs règles.
    - Revue imposée : profils génériques et profils de cette revue (l'ISSN l'emporte, comme dans
      l'interface de bureau). Chaîne vide : profils génériques seulement.
    """
    generiques = {n: p for n, p in PROFILS.items() if not p.revue}
    if revue == AUTO:
        if not issn:
            return dict(PROFILS)
        return {n: p for n, p in PROFILS.items() if not p.revue or p.issn == issn}
    if not revue:
        return generiques
    if issn:
        return {n: p for n, p in PROFILS.items() if not p.revue or p.issn == issn}
    return {n: p for n, p in PROFILS.items() if not p.revue or p.revue == revue}


def lire(nom: str) -> None:
    """Relève l'ISSN et les styles d'un document qui vient d'être déposé dans /entree."""
    chemin = ENTREE / nom
    infos: dict = {"issn": None, "styles": set(), "erreur": ""}
    try:
        infos["styles"] = inventorier(chemin).styles_presents
        infos["issn"] = issn_du_document(chemin)
    except Exception as exc:  # noqa: BLE001 - un fichier illisible est signalé dans la liste
        infos["erreur"] = _message_illisible(chemin, exc)
    _documents[nom] = infos


def _message_illisible(chemin: Path, exc: Exception) -> str:
    debut = chemin.read_bytes()[:8] if chemin.exists() else b""
    if debut.startswith(b"\xd0\xcf\x11\xe0"):
        return ("Document protégé par un mot de passe, ou enregistré dans l'ancien format .doc. "
                "Retirez le mot de passe, ou enregistrez-le en .docx dans Word.")
    if not zipfile.is_zipfile(chemin) or isinstance(exc, (zipfile.BadZipFile, KeyError, ValueError)):
        return "Ce fichier n'est pas un document Word (.docx) valide. Ouvrez-le dans Word et enregistrez-le de nouveau."
    return f"Fichier illisible ({type(exc).__name__})."


def _choisir(nom: str, revue: str, profil_force: str = "") -> tuple[Profil | None, str, dict]:
    infos = _documents.get(nom)
    if infos is None:
        lire(nom)
        infos = _documents[nom]
    if infos["erreur"]:
        return None, "", infos
    if profil_force:
        return PROFILS[profil_force], "type de document choisi à la main", infos
    profil, raison = choisir_profil(_profils_pour(infos["issn"], revue), nom, infos["styles"])
    raison = {
        "détecté par ses règles": "reconnu d'après le nom du fichier et les styles du document",
        "aucune règle ne correspond, profil par défaut": "aucun type particulier reconnu",
    }.get(raison.split(" (")[0], raison)
    if infos["issn"] and profil.issn == infos["issn"]:
        raison += f", revue reconnue par l'ISSN {infos['issn']}"
    return profil, raison, infos


def analyser(nom: str, revue: str, profil_force: str = "") -> str:
    """Profil qui serait appliqué au document, et revue reconnue par son ISSN."""
    profil, raison, infos = _choisir(nom, revue, profil_force)
    if profil is None:
        return json.dumps({"erreur": infos["erreur"]})
    issn = infos["issn"] or ""
    revue_issn = next((p.revue for p in PROFILS.values() if issn and p.issn == issn), "")
    return json.dumps({
        "profil": profil.nom,
        "libelle": libelle(profil),
        "raison": raison,
        "issn": issn,
        "revueIssn": revue_issn,
    })


def oublier(nom: str) -> None:
    """Retire un document de la liste et de la mémoire."""
    _documents.pop(nom, None)
    (ENTREE / nom).unlink(missing_ok=True)


# ---- Remarques en langage courant ------------------------------------------------------

@dataclass
class Remarque:
    gravite: str                  # « avertissement » ou « info »
    titre: str
    conseil: str = ""
    cible: dict = field(default_factory=dict)   # {"id": …} ou {"balise": …, "rang": …}


def _cible_titre(soupe: BeautifulSoup, extrait: str) -> dict:
    for titre in soupe.find_all(re.compile(r"^h[1-6]$")):
        if titre.get_text(" ", strip=True).startswith(extrait.rstrip("…")) and titre.get("id"):
            return {"id": titre["id"]}
    return {}


def _decalage(soupe: BeautifulSoup, profil: Profil | None) -> int:
    """Écart entre les niveaux HTML et les styles Word : avec un titre de document (style Titre),
    Titre 1 devient h2, Titre 2 devient h3, etc."""
    mode = (profil.post_traitement.get("decaler_niveaux", 0) if profil else 0) or 0
    if mode == "auto":
        classe = str(profil.post_traitement.get("classe_titre_document", "titre-document"))
        return 1 if soupe.find("h1", class_=classe) else 0
    return int(mode)


def _traduire_structure(message: str, soupe: BeautifulSoup, decalage: int = 0) -> Remarque:
    if message.startswith("Aucun titre"):
        return Remarque("avertissement", "Aucun titre n'a été trouvé.",
                        "Dans Word, appliquez les styles Titre 1, Titre 2… à vos titres, au lieu de les mettre "
                        "en gras ou en gros caractères.")
    if trouve := re.match(r"Le document ne commence pas par un h1", message):
        return Remarque("avertissement", "Le document ne commence pas par son titre principal.",
                        "Dans Word, appliquez le style Titre au titre du document.")
    if trouve := re.match(r"Saut de niveau : h(\d) suivi de h(\d) \(« (.*) »\)", message):
        # Niveaux exprimés en styles Word, et non en balises HTML
        avant, apres, extrait = int(trouve[1]) - decalage, int(trouve[2]) - decalage, trouve[3]
        nom_style = lambda n: "Titre" if n <= 0 else f"Titre {n}"  # noqa: E731
        return Remarque("avertissement", f"Un niveau de titre manque avant « {extrait} ».",
                        f"Ce titre porte le style {nom_style(apres)}, mais le titre précédent est en "
                        f"{nom_style(avant)}. Dans Word, appliquez-lui plutôt le style {nom_style(avant + 1)}, "
                        "ou ajoutez le titre intermédiaire qui manque.",
                        _cible_titre(soupe, extrait))
    if trouve := re.match(r"(\d+) titres de niveau h1", message):
        return Remarque("avertissement", f"Le document a {trouve[1]} titres principaux.",
                        "Une page ne devrait avoir qu'un titre principal. Dans Word, gardez le style Titre pour "
                        "le titre du document, et Titre 1 pour les grandes parties.")
    return Remarque("avertissement", message)


def _traduire_mammoth(message: dict) -> Remarque:
    texte = message["message"]
    if trouve := re.match(r"Unrecognised (paragraph|run) style: '(.*?)'", texte):
        sorte = "paragraphes" if trouve[1] == "paragraph" else "mots mis en forme"
        return Remarque("info", f"Le style Word « {trouve[2]} » n'est pas reconnu.",
                        f"Ses {sorte} deviennent du texte ordinaire. C'est sans conséquence s'il ne sert pas à "
                        "des titres.")
    if "image/x-emf" in texte:
        return Remarque("avertissement", "Une image au format EMF n'a pas pu être convertie.",
                        "Les navigateurs n'affichent pas ce format. Dans Word, enregistrez l'image en PNG et "
                        "remplacez-la.")
    return Remarque("info", "Remarque technique du convertisseur.", texte)


def _traduire_normalisation(m: dict) -> Remarque:
    style = m["style_apres"]
    if style == "Title":
        quoi = "Titre du document reconnu"
    elif trouve := re.match(r"Heading (\d)", style):
        quoi = f"Titre de niveau {trouve[1]} reconnu"
    elif style == "Quote":
        quoi = "Citation longue reconnue"
    else:
        quoi = f"Style « {style} » appliqué"
    return Remarque("info", f"{quoi} : « {m['texte']} »",
                    "Ce paragraphe était mis en forme à la main. Vérifiez qu'il s'agit bien de cela.")


LIENS_VAGUES = {"ici", "cliquez ici", "cliquer ici", "lien", "ce lien", "en savoir plus", "plus", "voir",
                "click here", "here", "link", "read more", "more"}


def _verifier_accessibilite(soupe: BeautifulSoup) -> list[Remarque]:
    remarques = []
    sans_alt = [i for i, img in enumerate(soupe.find_all("img"))
                if not img.find_parent("footer") and not (img.get("alt") or "").strip()]
    for rang in sans_alt:
        remarques.append(Remarque(
            "avertissement", "Image sans texte de remplacement.",
            "Les personnes ayant une déficience visuelle ne pourront pas savoir ce qu'elle montre. "
            "Dans Word, faites un clic droit sur l'image, puis "
            "« Afficher le texte de remplacement », et décrivez-la. Si elle est purement décorative, cochez "
            "« Marquer comme décoratif ».",
            {"balise": "img", "rang": rang}))
    for rang, lien in enumerate(soupe.find_all("a")):
        texte = re.sub(r"[\s.:!»«]+", " ", lien.get_text(" ", strip=True)).strip().casefold()
        if texte in LIENS_VAGUES:
            remarques.append(Remarque(
                "avertissement", f"Lien au texte vague : « {lien.get_text(strip=True)} ».",
                "Hors de sa phrase, ce lien ne dit pas où il mène. Dans Word, mettez le lien sur des mots qui "
                "décrivent la destination.",
                {"balise": "a", "rang": rang}))
    for rang, tableau in enumerate(soupe.find_all("table")):
        if len(tableau.find_all("tr")) > 1 and not tableau.find("th"):
            remarques.append(Remarque(
                "avertissement", "Tableau sans ligne d'entête.",
                "Dans Word, sélectionnez la première ligne du tableau, puis ouvrez « Propriétés du tableau », "
                "onglet « Ligne », et cochez « Répéter en haut de chaque page en tant que ligne d'en-tête ».",
                {"balise": "table", "rang": rang}))
    return remarques


def _remarques(entree, page: str, profil: Profil | None) -> list[Remarque]:
    soupe = BeautifulSoup(page, "html.parser")
    decalage = _decalage(soupe, profil)
    remarques = [_traduire_structure(a, soupe, decalage) for a in entree.avertissements_structure]
    remarques += _verifier_accessibilite(soupe)
    remarques += [_traduire_mammoth(m) for m in entree.messages_mammoth]
    remarques += [_traduire_normalisation(m) for m in entree.normalisations]
    # Mammoth répète le même message pour chaque paragraphe : on n'en garde qu'un
    vues, uniques = set(), []
    for r in remarques:
        cle = (r.titre, json.dumps(r.cible))
        if cle not in vues:
            vues.add(cle)
            uniques.append(r)
    return uniques


# ---- Conversion ------------------------------------------------------------------------

def convertir(demandes: list, revue: str, journal) -> str:
    """Convertit les documents et écrit les rapports. Renvoie le résumé de chaque document.

    `demandes` : liste de {"nom": …, "profil": nom du profil choisi à la main, ou ""}.
    `journal` reçoit les messages de progression.
    """
    shutil.rmtree(SORTIE, ignore_errors=True)
    SORTIE.mkdir(parents=True)
    entrees, _resultats[:] = [], []
    for i, demande in enumerate(demandes, start=1):
        nom = demande["nom"]
        journal(json.dumps({"fichier": nom, "rang": i, "total": len(demandes)}))
        profil, raison, _ = _choisir(nom, revue, demande.get("profil") or "")
        entree = convertir_fichier(ENTREE / nom, PROFILS, SORTIE, profil.nom if profil else None,
                                   lambda _texte: None)
        # Le profil est imposé au convertisseur : on remet la vraie raison du choix
        entree.justification_profil = raison or entree.justification_profil
        page = ""
        if entree.sortie:
            entree.sortie = Path(entree.sortie).name     # chemin relatif dans le zip
            page = (SORTIE / entree.sortie).read_text(encoding="utf-8")
        remarques = _remarques(entree, page, profil) if page else []
        statut = ("erreur" if entree.erreur
                  else "avertissements" if any(r.gravite == "avertissement" for r in remarques)
                  else "ok")
        entrees.append(entree)
        _resultats.append({
            "fichier": nom,
            "sortie": entree.sortie,
            "statut": statut,
            "profil": entree.profil,
            "libelle": libelle(PROFILS[entree.profil]) if entree.profil in PROFILS else entree.profil,
            "raison": entree.justification_profil,
            "erreur": entree.erreur,
            "remarques": [asdict(r) for r in remarques],
            "titres": entree.nb_titres,
            "images": len(BeautifulSoup(page, "html.parser").find_all("img")) if page else 0,
        })
    ecrire_rapport(entrees, SORTIE)
    (SORTIE / "rapport-conversion.html").write_text(rapport_html(), encoding="utf-8")
    return json.dumps(_resultats)


def archive() -> bytes:
    """Le contenu de /sortie en zip : pages, images extraites et rapports."""
    tampon = BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(SORTIE.rglob("*")):
            if chemin.is_file():
                zf.write(chemin, chemin.relative_to(SORTIE).as_posix())
    return tampon.getvalue()


def apercu(nom_html: str) -> str:
    """La page produite, en un seul fichier : ses images extraites y sont incorporées."""
    page = (SORTIE / nom_html).read_text(encoding="utf-8")
    dossier = f"{Path(nom_html).stem}_fichiers/"

    def incorporer(trouve: re.Match) -> str:
        chemin = SORTIE / trouve.group(2)
        if not chemin.is_file():
            return trouve.group(0)
        type_image = mimetypes.guess_type(chemin.name)[0] or "application/octet-stream"
        donnees = base64.b64encode(chemin.read_bytes()).decode("ascii")
        return f'{trouve.group(1)}"data:{type_image};base64,{donnees}"'

    return re.sub(r'(src=)"(' + re.escape(dossier) + r'[^"]+)"', incorporer, page)


# ---- Rapport lisible -------------------------------------------------------------------

def _resume_titres(titres: dict) -> str:
    noms = {"h1": ("titre principal", "titres principaux"), "h2": ("section", "sections"),
            "h3": ("sous-section", "sous-sections"), "h4": ("sous-sous-section", "sous-sous-sections")}
    parties = []
    for niveau, n in titres.items():
        un, plusieurs = noms.get(niveau, (f"titre de niveau {niveau[1]}", f"titres de niveau {niveau[1]}"))
        parties.append(f"{n} {un if n == 1 else plusieurs}")
    return ", ".join(parties) or "aucun titre"


def rapport_html() -> str:
    """Le rapport de conversion en HTML : lisible par tous, et prêt à imprimer."""
    e = html.escape
    statuts = {"ok": ("Converti", "ok"), "avertissements": ("À vérifier", "attention"), "erreur": ("Erreur", "erreur")}
    blocs = []
    for r in _resultats:
        texte_statut, classe = statuts[r["statut"]]
        avertissements = [x for x in r["remarques"] if x["gravite"] == "avertissement"]
        infos = [x for x in r["remarques"] if x["gravite"] == "info"]
        lignes = [f'<section><h2>{e(r["fichier"])} <span class="statut {classe}">{texte_statut}</span></h2>',
                  f'<p class="meta">Type de document : <strong>{e(r["libelle"])}</strong> ({e(r["raison"])})</p>']
        if r["sortie"]:
            lignes.append(f'<p class="meta">Page produite : {e(r["sortie"])}. Structure : {e(_resume_titres(r["titres"]))}.</p>')
        if r["erreur"]:
            lignes.append(f'<p class="erreur-texte">{e(r["erreur"])}</p>')
        for titre, liste in (("À corriger ou à vérifier", avertissements), ("Pour information", infos)):
            if liste:
                lignes.append(f"<h3>{titre}</h3><ul>")
                lignes += [f'<li><strong>{e(x["titre"])}</strong>{"<br>" + e(x["conseil"]) if x["conseil"] else ""}</li>'
                           for x in liste]
                lignes.append("</ul>")
        if not r["remarques"] and not r["erreur"]:
            lignes.append("<p>Aucune remarque. Relisez tout de même la page avant de la publier.</p>")
        lignes.append("</section>")
        blocs.append("\n".join(lignes))

    nb = {s: sum(1 for r in _resultats if r["statut"] == s) for s in statuts}
    bilan = (f"{len(_resultats)} document(s) : {nb['ok']} converti(s) sans remarque, "
             f"{nb['avertissements']} à vérifier, {nb['erreur']} en erreur.")
    return f"""<!DOCTYPE html>
<html lang="fr-CA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport de conversion · MiseEnWeb</title>
<style>
  body {{ max-width: 48rem; margin: 0 auto; padding: 2rem 1.25rem; color: #0b113a; background: #fff;
         font: 500 1rem/1.55 Figtree, "Segoe UI", Roboto, Arial, sans-serif; }}
  h1 {{ font-size: 2rem; margin: 0 0 .25rem; }}
  h2 {{ font-size: 1.3rem; margin: 2rem 0 .5rem; padding-top: 1.5rem; border-top: 1px solid #c3ccd5;
        display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; overflow-wrap: anywhere; }}
  h3 {{ font-size: 1rem; margin: 1.25rem 0 .25rem; }}
  ul {{ padding-left: 1.25rem; }} li {{ margin: .4rem 0; }}
  .meta, .bilan {{ color: #4a5160; margin: .25rem 0; }}
  .statut {{ font-size: .8rem; padding: .1rem .6rem; border-radius: 999px; }}
  .ok {{ background: #d6f0e2; }} .attention {{ background: #ffe0c2; }} .erreur {{ background: #fee1de; }}
  .erreur-texte {{ color: #b10000; }}
  button {{ font: inherit; padding: .6rem 1.4rem; border: 0; border-radius: 999px; background: #0b113a;
            color: #fff; cursor: pointer; }}
  button:hover {{ background: #0057ac; }}
  @media print {{ button {{ display: none; }} body {{ padding: 0; }} }}
</style>
</head>
<body>
<h1>Rapport de conversion</h1>
<p class="bilan">MiseEnWeb, {datetime.now().strftime("%Y-%m-%d %H:%M")}. {bilan}</p>
<p><button type="button" onclick="print()">Imprimer ou enregistrer en PDF</button></p>
{"".join(blocs)}
</body>
</html>
"""


def rapport() -> str:
    return (SORTIE / "rapport-conversion.html").read_text(encoding="utf-8")
