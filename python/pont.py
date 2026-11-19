"""Pont entre la page web et le convertisseur docx2html.

- Choix du profil : détection automatique par défaut (règles des profils, et ISSN du pied
  de page qui limite le choix à la publication reconnue), publication imposée dans le menu
  « Règles », ou type de document choisi à la main pour un fichier.
- Profils : ajout et retrait du profil de l'utilisateur, relevé des documents et écriture d'un
  profil pour l'assistant de création de profil.
- Remarques : les avertissements du convertisseur sont traduits en langage courant, avec la
  correction à faire dans Word, et complétés par des vérifications d'accessibilité de la page
  produite (images sans texte de remplacement, liens vagues, tableaux sans en-tête).
- Rapport : en Markdown (celui du convertisseur) et en HTML lisible, à imprimer.

Les fichiers vivent dans le système de fichiers en mémoire du navigateur : /entree reçoit
les documents Word, /sortie les pages produites. Rien n'est envoyé sur un serveur.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup

from docx2html.analyse import analyser_exemples, images_des_exemples
from docx2html.diagnostic import inventorier
from docx2html.gabarit_minimal import elements_absents
from docx2html.generateur import generer_profil as _generer_profil
from docx2html.pied_page import issn_du_document
from docx2html.pipeline import convertir_fichier
from docx2html.profils import Profil, charger_profils, choisir_profil, profils_du_fichier
from docx2html.rapport import ecrire_rapport
from docx2html.validation import valider_texte

# Dans le navigateur, les dossiers sont à la racine du système de fichiers en mémoire.
# Les tests automatiques les placent ailleurs, par deux variables d'environnement.
_RACINE = Path(os.environ.get("MISEENWEB_RACINE", "/"))
ENTREE = _RACINE / "entree"
SORTIE = _RACINE / "sortie"
_APP = Path(os.environ.get("MISEENWEB_APP", "/app"))
PROFILS = charger_profils(_APP / "profils")
_PROFILS_DU_SITE = frozenset(PROFILS)      # le catalogue commun, tel que publié
_profils_deposes: set[str] = set()         # noms des profils ajoutés par l'utilisateur
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
    if profil.nom in _profils_deposes and profil.revue:      # profil ajouté : le nom de sa publication suffit
        return profil.revue
    return profil.description.split(".")[0] or profil.nom


# ---- Catalogue et choix du profil ------------------------------------------------------

def _groupe(profil: Profil) -> str:
    """Nom sous lequel un profil figure dans le menu « Règles ». Vide : profil général.

    Une revue regroupe ses variantes sous son nom. Un profil déposé sans nom de revue forme
    son propre groupe, pour être choisi dans ce menu comme une revue.
    """
    if profil.revue:
        return profil.revue
    return libelle(profil) if profil.nom in _profils_deposes else ""


def catalogue() -> str:
    """Revues et profils, pour les menus de la page."""
    revues = {_groupe(p): p for p in PROFILS.values() if _groupe(p)}
    profils = sorted(PROFILS.values(), key=lambda p: (bool(p.revue), p.revue, libelle(p)))
    return json.dumps({
        "revues": [{"nom": nom, "issn": p.issn, "depose": p.nom in _profils_deposes}
                   for nom, p in sorted(revues.items())],
        "profils": [{"nom": p.nom, "libelle": libelle(p), "revue": p.revue,
                     "depose": p.nom in _profils_deposes} for p in profils],
    })


def retirer_profil() -> str:
    """Retire le profil déposé par l'utilisateur. Renvoie le catalogue, pour les menus de la page."""
    for nom in _profils_deposes:
        PROFILS.pop(nom, None)
    _profils_deposes.clear()
    return catalogue()


def _valider_depot(texte: str) -> tuple[dict | None, list[str]]:
    """Valide un profil qui ne vient pas du site. Renvoie (réglages, messages) : sans erreur, aucun message."""
    reserves = {nom.split("/")[0] for nom in _PROFILS_DU_SITE}
    donnees, messages = valider_texte(texte, _APP / "gabarits", reserves)
    if donnees is not None:
        revues = {p.issn: p.revue for nom, p in PROFILS.items() if nom in _PROFILS_DU_SITE and p.issn}
        issn = str(donnees.get("issn") or "")
        if issn in revues:
            donnees, messages = None, [f"issn : « {issn} » est déjà l'ISSN de la publication « {revues[issn]} », "
                                       "dont le profil fait partie du site."]
    return donnees, messages


# Types d'image qu'un navigateur affiche. Les autres (EMF, WMF, TIFF) sont relevés sans aperçu.
_IMAGES_AFFICHABLES = {"image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp", "image/bmp"}


def relever_exemples(noms_json: str) -> str:
    """Relevé de ce que les documents déposés ont en commun, pour l'assistant de création d'un profil.

    « noms_json » est la liste des noms de fichier, en JSON. Chaque image commune reçoit un
    « apercu » : l'image elle-même, à afficher dans la page, ou une chaîne vide si le navigateur
    ne sait pas afficher ce type de fichier.
    """
    chemins = [ENTREE / nom for nom in json.loads(noms_json)]
    releve = analyser_exemples(chemins)
    fichiers = images_des_exemples(chemins, {image["empreinte"] for image in releve["images_communes"]})
    for image in releve["images_communes"]:
        sorte, octets = fichiers.get(image["empreinte"], ("", b""))
        image["apercu"] = (f"data:{sorte};base64,{base64.b64encode(octets).decode()}"
                           if sorte in _IMAGES_AFFICHABLES else "")
    return json.dumps(releve)


def generer_profil(reponses_json: str) -> str:
    """Écrit le profil qui correspond aux réponses de l'assistant, puis le valide comme un profil déposé.

    Renvoie {"texte": …, "messages": […]}. Le profil n'est pas ajouté : la page le dépose
    ensuite par deposer_profil, ou le donne à télécharger.
    """
    try:
        texte = _generer_profil(json.loads(reponses_json))
    except (ValueError, KeyError, TypeError) as erreur:
        return json.dumps({"texte": "", "messages": [f"Réponses incomplètes : {erreur}"]})
    return json.dumps({"texte": texte, "messages": _valider_depot(texte)[1]})


def deposer_profil(texte: str) -> str:
    """Valide le profil déposé par l'utilisateur et, s'il est valide, l'ajoute aux profils du site.

    Un seul profil déposé à la fois : un nouveau dépôt valide remplace le précédent. Un dépôt
    refusé ne change rien. Renvoie {"messages": […], "libelles": […], "catalogue": {…}} :
    « messages » est vide quand le profil est accepté.
    """
    donnees, messages = _valider_depot(texte)
    libelles = []
    if donnees is not None:
        retirer_profil()
        # Le profil n'est pas écrit sur le disque : son chemin sert seulement à situer les gabarits
        for profil in profils_du_fichier(_APP / "profils" / "profil-depose.yaml", donnees):
            PROFILS[profil.nom] = profil
            _profils_deposes.add(profil.nom)
            libelles.append(libelle(profil))
    return json.dumps({"messages": messages, "libelles": libelles, "catalogue": json.loads(catalogue())})


def _profils_pour(issn: str | None, revue: str) -> dict:
    """Profils permis pour un document.

    - Détection automatique : un ISSN connu limite le choix à sa revue, un ISSN inconnu aux
      profils génériques ; sans ISSN, tous les profils sont candidats, choisis par leurs règles.
    - Revue imposée : profils génériques et profils de cette revue. L'ISSN du document l'emporte
      s'il est celui d'une revue connue. Un ISSN inconnu ne change rien au choix : un profil
      déposé sans ISSN reste applicable aux articles de sa revue. Chaîne vide : profils
      génériques seulement.
    """
    generiques = {n: p for n, p in PROFILS.items() if not _groupe(p)}
    if revue == AUTO:
        if not issn:
            return dict(PROFILS)
        return {n: p for n, p in PROFILS.items() if not p.revue or p.issn == issn}
    if not revue:
        return generiques
    if issn and any(p.issn == issn for p in PROFILS.values()):
        return {n: p for n, p in PROFILS.items() if not _groupe(p) or p.issn == issn}
    return {n: p for n, p in PROFILS.items() if not _groupe(p) or _groupe(p) == revue}


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
        return ("Le document est protégé par un mot de passe ou enregistré dans le format .doc. "
                "Dans Word, retirer le mot de passe ou enregistrer le document dans le format .docx.")
    if not zipfile.is_zipfile(chemin) or isinstance(exc, (zipfile.BadZipFile, KeyError, ValueError)):
        return ("Le fichier n'est pas un document Word (.docx) valide. Ouvrir le fichier dans Word, puis "
                "enregistrer le fichier de nouveau.")
    return f"Le fichier est illisible ({type(exc).__name__})."


def _choisir(nom: str, revue: str, profil_force: str = "") -> tuple[Profil | None, str, dict]:
    infos = _documents.get(nom)
    if infos is None:
        lire(nom)
        infos = _documents[nom]
    if infos["erreur"]:
        return None, "", infos
    if profil_force:
        return PROFILS[profil_force], "type de document choisi à la main", infos
    profil, raison = choisir_profil(_profils_pour(infos["issn"], revue), nom, infos["styles"], issn=infos["issn"])
    raison = {
        "détecté par son ISSN": "seul type de document de la publication",
        "détecté par ses règles": "reconnu d'après le nom du fichier et les styles du document",
        "aucune règle ne correspond, profil par défaut": "aucun type particulier reconnu",
    }.get(raison.split(" (")[0], raison)
    if infos["issn"] and profil.issn == infos["issn"]:
        raison += f", publication reconnue par l'ISSN {infos['issn']}"
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
    pluriel: str = ""             # titre d'un groupe de remarques identiques : « {n} images sans… »
    origine: str = "document"     # « document » : défaut du document Word; « conversion » : défaut de la page


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
        return Remarque("avertissement", "Aucun titre.",
                        "Les lecteurs d'écran parcourent une page par ses titres. Dans Word, appliquer les styles "
                        "Titre 1 et Titre 2 aux titres.")
    if trouve := re.match(r"Le document ne commence pas par un h1", message):
        return Remarque("avertissement", "Titre principal absent au début du document.",
                        "Dans Word, appliquer le style Titre au titre du document.")
    if trouve := re.match(r"Saut de niveau : h(\d) suivi de h(\d) \(« (.*) »\)", message):
        # Niveaux exprimés en styles Word, et non en balises HTML
        avant, apres, extrait = int(trouve[1]) - decalage, int(trouve[2]) - decalage, trouve[3]
        nom_style = lambda n: "Titre" if n <= 0 else f"Titre {n}"  # noqa: E731
        return Remarque("avertissement", f"Niveau de titre manquant avant « {extrait} ».",
                        f"Ce titre a le style {nom_style(apres)}. Le titre précédent a le style "
                        f"{nom_style(avant)}. Dans Word, appliquer le style {nom_style(avant + 1)} à ce titre "
                        "ou ajouter le titre intermédiaire.",
                        _cible_titre(soupe, extrait))
    if trouve := re.match(r"(\d+) titres de niveau h1", message):
        return Remarque("avertissement", f"{trouve[1]} titres principaux.",
                        "Une page a un seul titre principal. Dans Word, réserver le style Titre au titre du "
                        "document. Appliquer le style Titre 1 aux sections.")
    return Remarque("avertissement", message)


# Éléments de Word que Mammoth ignore sans effet sur la page : verrous et tracés des formes
# et des zones de texte, exceptions de mise en forme d'un tableau.
ELEMENTS_SANS_CONSEQUENCE = ("}lock", ":anchorlock", "v:path", "w:tblPrEx")


MOTIF_STYLE_INCONNU = re.compile(r"Unrecognised (paragraph|run) style: '?(.*?)'? \(Style ID")


def _styles_inconnus(messages: list[dict]) -> Remarque | None:
    """Une seule remarque pour tous les styles non reconnus, s'il y en a plusieurs."""
    noms = list(dict.fromkeys(t[2] for m in messages if (t := MOTIF_STYLE_INCONNU.match(m["message"]))))
    if len(noms) < 2:
        return None
    return Remarque("info", f"{len(noms)} styles Word non reconnus : "
                            + ", ".join(f"« {nom} »" for nom in noms) + ".",
                    "Le texte de ces styles devient du texte courant. La structure de la page reste complète "
                    "si ces styles ne servent pas à des titres.")


def _traduire_mammoth(message: dict) -> Remarque | None:
    """Traduit un message de Mammoth; None s'il n'apprend rien d'utile à la personne."""
    texte = message["message"]
    if trouve := re.match(r"An unrecognised element was ignored: (.+)", texte):
        if trouve[1].endswith(ELEMENTS_SANS_CONSEQUENCE):
            return None
        return Remarque("info", f"Élément Word ignoré : {trouve[1]}.",
                        "Le convertisseur ne connaît pas cet élément. Vérifier que la page produite est "
                        "complète.")
    if trouve := MOTIF_STYLE_INCONNU.match(texte):
        return Remarque("info", f"Style Word non reconnu : « {trouve[2]} ».",
                        "Le texte de ce style devient du texte courant. La structure de la page reste complète "
                        "si ce style ne sert pas à des titres.")
    if "image/x-emf" in texte:
        return Remarque("avertissement", "Image EMF non convertie.",
                        "Les navigateurs n'affichent pas le format EMF. Dans Word, remplacer l'image par une "
                        "version PNG.")
    return Remarque("info", "Remarque technique du convertisseur.", texte)


def _traduire_normalisation(m: dict, titre_de_section: bool = False) -> Remarque:
    if m["regle"] == "numero-sous-titre":       # le style n'a pas changé : seul le numéro est écrit
        return Remarque("info", f"Numéro de sous-titre écrit dans le texte : « {m['texte']} »",
                        "Le convertisseur remplace la numérotation automatique de Word par un numéro écrit "
                        "dans le texte.")
    style = m["style_apres"]
    if style == "Title":
        quoi = "Titre de section reconnu" if titre_de_section else "Titre du document reconnu"
    elif trouve := re.match(r"Heading (\d)", style):
        quoi = f"Titre de niveau {trouve[1]} reconnu"
    elif style == "Quote":
        quoi = "Citation longue reconnue"
    else:
        quoi = f"Style « {style} » appliqué"
    return Remarque("info", f"{quoi} : « {m['texte']} »",
                    "Le convertisseur reconnaît ce paragraphe d'après sa mise en forme. Vérifier cette "
                    "interprétation.")


LIENS_VAGUES = {"ici", "cliquez ici", "cliquer ici", "lien", "ce lien", "en savoir plus", "plus", "voir",
                "click here", "here", "link", "read more", "more"}


# Un paragraphe en gras qui commence ainsi étiquette un tableau ou une figure : ce n'est pas un titre
MOTIF_ETIQUETTE = re.compile(r"(tableau|table|figure|fig\.|annexe|appendix|encadré|box)\b", re.IGNORECASE)
MOTIF_ECRITURE_ARABE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
MOTS_MAX_SOUS_TITRE = 15


def _tout_en_gras(paragraphe) -> bool:
    texte = paragraphe.get_text("", strip=True)
    gras = "".join(g.get_text("", strip=True) for g in paragraphe.find_all(["strong", "b"])
                   if not g.find_parent(["strong", "b"]))
    return bool(texte) and len(gras) >= 0.98 * len(texte)


def _sous_titres_a_la_main(soupe: BeautifulSoup) -> list[int]:
    """Rang (parmi les <p> de la page) des paragraphes en gras qui servent de sous-titres.

    Ce sont, après le premier titre, des paragraphes courts, entièrement en gras, qui ne sont ni
    une étiquette de tableau ou de figure, ni une phrase terminée par une ponctuation. Le texte
    en écriture arabe est laissé de côté : on ne peut pas juger de son rôle.
    """
    rang_de = {id(p): rang for rang, p in enumerate(soupe.find_all("p"))}
    premier_titre = soupe.find(["h2", "h3", "h4", "h5", "h6"]) or soupe.find("h1")
    if premier_titre is None:
        return []
    rangs = []
    for paragraphe in premier_titre.find_next_siblings("p"):
        texte = paragraphe.get_text(" ", strip=True)
        if not 1 <= len(texte.split()) <= MOTS_MAX_SOUS_TITRE or texte[-1] in ".:;,":
            continue
        if MOTIF_ETIQUETTE.match(texte) or MOTIF_ECRITURE_ARABE.search(texte):
            continue
        if paragraphe.get("class") or not _tout_en_gras(paragraphe):
            continue
        rangs.append(rang_de[id(paragraphe)])
    return rangs


def _verifier_accessibilite(soupe: BeautifulSoup) -> list[Remarque]:
    remarques = []
    for rang in _sous_titres_a_la_main(soupe):
        remarques.append(Remarque(
            "avertissement", "Sous-titre en gras sans style de titre.",
            "Les lecteurs d'écran ne reconnaissent pas un paragraphe en gras comme un titre. Dans Word, "
            "appliquer un style de titre au sous-titre, par exemple Titre 2.",
            {"balise": "p", "rang": rang},
            "{n} sous-titres en gras sans style de titre"))
    sans_alt = [i for i, img in enumerate(soupe.find_all("img"))
                if not img.find_parent("footer") and not (img.get("alt") or "").strip()
                and img.get("role") != "presentation"]      # image décorative, selon le profil
    for rang in sans_alt:
        remarques.append(Remarque(
            "avertissement", "Image sans texte de remplacement.",
            "Les lecteurs d'écran ne peuvent pas décrire une image sans texte de remplacement. Dans Word, "
            "faire un clic droit sur l'image, puis choisir « Afficher le texte de remplacement ». Pour une "
            "image décorative, cocher « Marquer comme décoratif ».",
            {"balise": "img", "rang": rang},
            "{n} images sans texte de remplacement"))
    for rang, lien in enumerate(soupe.find_all("a")):
        texte = re.sub(r"[\s.:!»«]+", " ", lien.get_text(" ", strip=True)).strip().casefold()
        if texte in LIENS_VAGUES:
            remarques.append(Remarque(
                "avertissement", f"Hyperlien au texte vague : « {lien.get_text(strip=True)} ».",
                "Les lecteurs d'écran peuvent lire les hyperliens hors de leur phrase. Ce texte n'indique pas la "
                "destination de l'hyperlien. Dans Word, placer l'hyperlien sur des mots qui décrivent la "
                "destination.",
                {"balise": "a", "rang": rang}))
    for rang, tableau in enumerate(soupe.find_all("table")):
        if len(tableau.find_all("tr")) > 1 and not tableau.find("th"):
            remarques.append(Remarque(
                "avertissement", "Tableau sans ligne d'en-tête.",
                "Les lecteurs d'écran associent chaque cellule à l'en-tête de sa colonne. Dans Word, sélectionner "
                "la première ligne du tableau. Ouvrir « Propriétés du tableau », onglet « Ligne ». Cocher "
                "« Répéter en haut de chaque page en tant que ligne d'en-tête ».",
                {"balise": "table", "rang": rang},
                "{n} tableaux sans ligne d'en-tête"))
    return remarques


# Élément du gabarit minimal absent -> (gravité, titre, correction à faire dans le document)
REMARQUES_GABARIT = {
    "logo": ("avertissement", "Logo absent de l'en-tête.",
             "Ajouter le logo de la publication dans l'en-tête du document."),
    "resume": ("avertissement", "Résumé absent.",
               "Ajouter le résumé, précédé de l'étiquette « Résumé » ou « Abstract »."),
    "mots_cles": ("avertissement", "Mots-clés absents.",
                  "Ajouter les mots-clés après le résumé, précédés de « Mots-clés » ou « Keywords »."),
    "references": ("avertissement", "Références absentes.",
                   "Ajouter la liste des références, sous le titre « Références »."),
    "issn": ("avertissement", "ISSN absent du pied de page.",
             "Ajouter l'ISSN de la publication dans le pied de page."),
    "licence": ("avertissement", "Licence absente du pied de page.",
                "Ajouter la licence de l'article dans le pied de page."),
    "doi": ("info", "DOI absent du pied de page.", "Si un DOI est attribué, l'ajouter dans le pied de page."),
}


def _verifier_gabarit(chemin_docx: Path, soupe: BeautifulSoup, profil: Profil | None) -> list[Remarque]:
    """Une remarque par élément du gabarit minimal absent. Seulement si le profil le demande."""
    if not (profil and profil.post_traitement.get("gabarit_minimal", False)):
        return []
    return [Remarque(*REMARQUES_GABARIT[cle]) for cle in elements_absents(chemin_docx, soupe)]


def _remarques(entree, page: str, profil: Profil | None) -> list[Remarque]:
    soupe = BeautifulSoup(page, "html.parser")
    decalage = _decalage(soupe, profil)
    # Le texte absent vient en premier : c'est le seul défaut qui retire de l'information
    remarques = [
        Remarque("avertissement", f"Texte du document absent de la page : « {passage} »",
                 "La conversion n'a pas repris ce paragraphe du document Word. Comparer la page au "
                 "document avant la publication.", {}, "{n} paragraphes du document absents de la page",
                 "conversion")
        for passage in entree.passages_absents
    ]
    remarques += _verifier_gabarit(ENTREE / entree.fichier, soupe, profil)
    remarques += [_traduire_structure(a, soupe, decalage) for a in entree.avertissements_structure]
    remarques += _verifier_accessibilite(soupe)
    messages = entree.messages_mammoth
    if groupe := _styles_inconnus(messages):
        remarques.append(groupe)
        messages = [m for m in messages if not MOTIF_STYLE_INCONNU.match(m["message"])]
    remarques += [r for r in map(_traduire_mammoth, messages) if r is not None]
    for numero in entree.titres_tableaux_reunis:
        paragraphe = next((p for p in soupe.find_all("p", id=re.compile("^titre-tableau"))
                           if p.get_text(" ", strip=True).startswith(numero)), None)
        remarques.append(Remarque(
            "info", f"Numéro et titre de tableau réunis sur une ligne : « {numero} »",
            "Le document Word place le numéro et le titre sur deux paragraphes. La présentation Chicago "
            "les place sur la même ligne. Vérifier que le texte réuni au numéro est le titre du tableau.",
            {"id": paragraphe["id"]} if paragraphe is not None else {},
            "{n} numéros de tableau réunis à leur titre sur une ligne", "conversion"))
    # Quand les titres sont décalés d'un niveau, seul le premier paragraphe reconnu comme titre
    # est le titre du document : les suivants deviennent des titres de section.
    titres_reconnus = 0
    for m in entree.normalisations:
        est_titre = m["style_apres"] == "Title" and m["regle"] != "numero-sous-titre"
        remarques.append(_traduire_normalisation(m, est_titre and decalage > 0 and titres_reconnus > 0))
        titres_reconnus += est_titre
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


def _regrouper(remarques: list[dict]) -> list[tuple[dict, int]]:
    """Réunit les remarques identiques : (remarque, nombre de fois), dans l'ordre de la première."""
    comptes: dict[tuple[str, str], list] = {}
    for remarque in remarques:
        comptes.setdefault((remarque["titre"], remarque["conseil"]), [remarque, 0])[1] += 1
    return [(remarque, nombre) for remarque, nombre in comptes.values()]


def _titre_du_groupe(remarque: dict, nombre: int) -> str:
    """Titre de remarques identiques réunies : « 20 images sans… », sinon « … (20 fois) »."""
    if nombre < 2:
        return remarque["titre"]
    if remarque.get("pluriel"):
        return remarque["pluriel"].format(n=nombre) + "."
    return f"{remarque['titre']} ({nombre} fois)"


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
        de_conversion = [x for x in avertissements if x.get("origine") == "conversion"]
        du_document = [x for x in avertissements if x.get("origine") != "conversion"]
        for titre, liste in (("Document d'origine", du_document), ("Conversion", de_conversion + infos)):
            if liste:
                lignes.append(f"<h3>{titre}</h3><ul>")
                # Dans la page, chaque remarque mène à son endroit; sur papier, la répéter n'apprend rien
                lignes += [f'<li><strong>{e(_titre_du_groupe(x, nombre))}</strong>'
                           f'{"<br>" + e(x["conseil"]) if x["conseil"] else ""}</li>'
                           for x, nombre in _regrouper(liste)]
                lignes.append("</ul>")
        if not r["remarques"] and not r["erreur"]:
            lignes.append("<p>Le convertisseur n'a aucune remarque. Relire la page avant la publication.</p>")
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
