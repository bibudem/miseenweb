"""Analyse d'articles d'exemple : ce qui revient d'un article à l'autre dans une revue.

Le relevé sert de point de départ à la création d'un profil. Il ne décide rien : il compte.
Chaque relevé indique dans combien d'articles un élément paraît, pour distinguer une habitude
de la revue d'un cas isolé.

Le relevé contient de courts extraits des articles (un titre en gras, un bandeau), pour que la
revue reconnaisse ce dont il est question. Ces extraits restent dans le navigateur.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

from .apparence import couleurs_de_fond, empreinte, texte_normalise
from .diagnostic import analyser_paragraphe
from .pied_page import issn_du_document
from .post_traitement import MOTIF_NUMERO_SEUL, MOTIF_NUMERO_TABLEAU

EXEMPLES_MAX = 3            # extraits donnés par relevé
LONGUEUR_EXTRAIT = 80       # caractères
MOTS_MAX_TITRE = 15         # au-delà, un paragraphe en gras est du texte mis en évidence, pas un titre
TAILLE_GRAND_TITRE = 13.0   # points : à partir de cette taille, la limite de mots ne s'applique pas
LONGUEUR_MIN_NOM_COMMUN = 4


def _extrait(texte: str) -> str:
    texte = texte_normalise(texte)
    return texte if len(texte) <= LONGUEUR_EXTRAIT else texte[: LONGUEUR_EXTRAIT - 1].rstrip() + "…"


def _est_style_de_titre(nom: str) -> bool:
    return nom.lower().startswith(("heading", "title", "titre"))


# ---- Relevé d'un article -------------------------------------------------------------------

def _styles_et_titres_en_gras(doc) -> tuple[Counter, dict[float | None, list[tuple[str, str]]], dict[str, list[str]]]:
    """Compte les styles de paragraphe, relève les paragraphes courts en gras sans style de titre,
    et les paragraphes qui portent un style créé par la publication.

    Renvoie (styles, titres, propres) : « titres » associe une taille de police, en points, à la
    liste des (style, texte) de cette taille. « propres » associe le nom d'un style créé par la
    publication aux textes de ses paragraphes. Un paragraphe de style propre ne figure pas dans
    « titres » : son style dit déjà à quoi il sert.
    """
    styles: Counter = Counter()
    titres: dict[float | None, list[tuple[str, str]]] = defaultdict(list)
    propres: dict[str, list[str]] = defaultdict(list)
    for rang, paragraphe in enumerate(doc.paragraphs):
        info = analyser_paragraphe(rang, paragraphe)
        if not info.texte:
            continue
        styles[info.style_nom] += 1
        # Word distingue ses styles intégrés des styles créés dans le document
        if paragraphe.style is not None and not paragraphe.style.builtin:
            propres[info.style_nom].append(info.texte)
            continue
        if _est_style_de_titre(info.style_nom) or not info.tout_gras:
            continue
        # Le titre d'un article dépasse souvent 15 mots : sa grande taille suffit à le distinguer du texte
        grand = info.taille_pt is not None and info.taille_pt >= TAILLE_GRAND_TITRE
        if (len(info.texte.split()) > MOTS_MAX_TITRE and not grand) or info.texte[-1] in ".;,":
            continue
        if MOTIF_NUMERO_TABLEAU.match(info.texte):       # « Tableau 2 » en gras : une étiquette, pas un titre
            continue
        titres[info.taille_pt].append((info.style_nom, info.texte))
    return styles, titres, propres


def _images(doc) -> dict[str, dict]:
    """Images de l'article, par empreinte : type de fichier et endroits où elle paraît."""
    parties = {"corps": [doc.part]}
    parties["en-tete"] = [section.header.part for section in doc.sections]
    parties["pied"] = [section.footer.part for section in doc.sections]
    images: dict[str, dict] = {}
    for endroit, liste in parties.items():
        for partie in liste:
            for lien in partie.rels.values():
                if lien.reltype != RT.IMAGE or lien.is_external:
                    continue
                cle = empreinte(lien.target_part.blob)
                image = images.setdefault(cle, {"type": lien.target_part.content_type, "endroits": set()})
                image["endroits"].add(endroit)
    return images


def _titres_des_tableaux(doc) -> Counter:
    """Classe chaque tableau du corps selon la place de son numéro et de son titre.

    « deux-lignes » : le numéro, puis le titre, sur deux paragraphes (habitude de l'APA).
    « une-ligne » : le numéro et le titre dans le même paragraphe (habitude de Chicago).
    « sans-titre » : aucun numéro de tableau juste avant le tableau.
    """
    places: Counter = Counter()
    precedents: list[str] = []          # textes des deux derniers paragraphes non vides
    for element in doc.element.body.iterchildren():
        if element.tag == qn("w:p"):
            texte = texte_normalise("".join(t.text or "" for t in element.iter(qn("w:t"))))
            if texte:
                precedents = (precedents + [texte])[-2:]
        elif element.tag == qn("w:tbl"):
            dernier = precedents[-1] if precedents else ""
            avant_dernier = precedents[-2] if len(precedents) == 2 else ""
            if MOTIF_NUMERO_SEUL.match(avant_dernier) and not MOTIF_NUMERO_TABLEAU.match(dernier):
                places["deux-lignes"] += 1
            elif MOTIF_NUMERO_TABLEAU.match(dernier) and not MOTIF_NUMERO_SEUL.match(dernier):
                places["une-ligne"] += 1
            else:
                places["sans-titre"] += 1
            precedents = []
    return places


def _relever(chemin: Path) -> dict:
    doc = Document(str(chemin))
    styles, titres, propres = _styles_et_titres_en_gras(doc)
    return {
        "styles": styles,
        "titres": titres,
        "propres": propres,
        "images": _images(doc),
        "issn": issn_du_document(chemin),
        "couleurs": couleurs_de_fond(chemin),        # texte du paragraphe -> couleur
        "tableaux": _titres_des_tableaux(doc),
    }


# ---- Mise en commun ------------------------------------------------------------------------

def _nom_commun(noms: list[str]) -> str:
    """Plus longue suite de caractères présente dans tous les noms de fichier, sans l'extension."""
    radicaux = [Path(n).stem.lower() for n in noms]
    if len(radicaux) < 2:
        return ""
    commun = radicaux[0]
    for radical in radicaux[1:]:
        trouve = SequenceMatcher(None, commun, radical, autojunk=False).find_longest_match(
            0, len(commun), 0, len(radical))
        commun = commun[trouve.a: trouve.a + trouve.size]
    commun = re.sub(r"^[\W_\d]+|[\W_\d]+$", "", commun)      # ni numéro ni séparateur aux extrémités
    return commun if len(commun) >= LONGUEUR_MIN_NOM_COMMUN else ""


def analyser_exemples(chemins: list[Path]) -> dict:
    """Compare des articles d'exemple et renvoie le relevé de ce qu'ils ont en commun.

    Chaque liste est triée du plus fréquent au moins fréquent. « articles » est le nombre
    d'articles où l'élément paraît. Un fichier illisible est écarté et nommé dans « illisibles ».
    """
    releves, lus, illisibles = [], [], []
    for chemin in map(Path, chemins):
        try:
            releves.append(_relever(chemin))
            lus.append(chemin.name)
        except Exception as erreur:  # noqa: BLE001 - un fichier illisible ne doit pas arrêter l'analyse
            illisibles.append({"fichier": chemin.name, "erreur": f"{type(erreur).__name__}: {erreur}"})

    # Styles de paragraphe
    styles_articles: Counter = Counter()
    styles_total: Counter = Counter()
    for releve in releves:
        styles_articles.update(releve["styles"].keys())
        styles_total.update(releve["styles"])
    styles = [{"nom": nom, "articles": styles_articles[nom], "paragraphes": styles_total[nom],
               "titre": _est_style_de_titre(nom)}
              for nom in sorted(styles_articles, key=lambda n: (-styles_articles[n], -styles_total[n], n))]

    # Paragraphes courts en gras, par taille de police
    par_taille: dict = defaultdict(lambda: {"articles": 0, "paragraphes": 0, "styles": Counter(), "exemples": []})
    for releve in releves:
        for taille, paragraphes in releve["titres"].items():
            groupe = par_taille[taille]
            groupe["articles"] += 1
            groupe["paragraphes"] += len(paragraphes)
            for style, texte in paragraphes:
                groupe["styles"][style] += 1
                if len(groupe["exemples"]) < EXEMPLES_MAX and _extrait(texte) not in groupe["exemples"]:
                    groupe["exemples"].append(_extrait(texte))
    titres_en_gras = [{"taille": taille, "articles": g["articles"], "paragraphes": g["paragraphes"],
                       "styles": [s for s, _ in g["styles"].most_common()], "exemples": g["exemples"]}
                      for taille, g in sorted(par_taille.items(), key=lambda paire: -(paire[0] or 0))]

    # Styles créés par la publication
    par_style: dict = defaultdict(lambda: {"articles": 0, "paragraphes": 0, "exemples": []})
    for releve in releves:
        for nom, textes in releve["propres"].items():
            groupe = par_style[nom]
            groupe["articles"] += 1
            groupe["paragraphes"] += len(textes)
            for texte in textes:
                if len(groupe["exemples"]) < EXEMPLES_MAX and _extrait(texte) not in groupe["exemples"]:
                    groupe["exemples"].append(_extrait(texte))
    styles_propres = [{"nom": nom, **g}
                      for nom, g in sorted(par_style.items(), key=lambda p: (-p[1]["articles"], -p[1]["paragraphes"], p[0]))]

    # Images présentes dans plus d'un article
    images: dict[str, dict] = {}
    for releve in releves:
        for cle, image in releve["images"].items():
            commune = images.setdefault(cle, {"empreinte": cle, "type": image["type"], "articles": 0, "endroits": set()})
            commune["articles"] += 1
            commune["endroits"] |= image["endroits"]
    images_communes = [{**image, "endroits": sorted(image["endroits"])}
                       for image in sorted(images.values(), key=lambda i: (-i["articles"], i["empreinte"]))
                       if image["articles"] >= 2]

    # ISSN du pied de page
    issn = Counter(releve["issn"] for releve in releves if releve["issn"])

    # Couleurs de fond au début de l'article
    par_couleur: dict = defaultdict(lambda: {"articles": 0, "exemples": []})
    for releve in releves:
        for couleur in set(releve["couleurs"].values()):
            par_couleur[couleur]["articles"] += 1
        for texte, couleur in releve["couleurs"].items():
            exemples = par_couleur[couleur]["exemples"]
            if len(exemples) < EXEMPLES_MAX and _extrait(texte) not in exemples:
                exemples.append(_extrait(texte))
    couleurs = [{"couleur": couleur, **g} for couleur, g in sorted(par_couleur.items(), key=lambda p: (-p[1]["articles"], p[0]))]

    # Tableaux
    places: Counter = Counter()
    for releve in releves:
        places.update(releve["tableaux"])
    tableaux = {
        "articles": sum(1 for releve in releves if releve["tableaux"]),
        "total": sum(places.values()),
        "deux_lignes": places["deux-lignes"],
        "une_ligne": places["une-ligne"],
        "sans_titre": places["sans-titre"],
    }

    return {
        "nb_articles": len(releves),
        "articles": lus,
        "illisibles": illisibles,
        "styles": styles,
        "titres_en_gras": titres_en_gras,
        "styles_propres": styles_propres,
        "images_communes": images_communes,
        "issn": [{"valeur": valeur, "articles": nombre} for valeur, nombre in issn.most_common()],
        "couleurs": couleurs,
        "tableaux": tableaux,
        "nom_commun": _nom_commun(lus),
    }


def images_des_exemples(chemins: list[Path], empreintes: set[str]) -> dict[str, tuple[str, bytes]]:
    """Retrouve le fichier des images demandées : empreinte -> (type de fichier, octets).

    Sert à montrer chaque image commune à la personne qui lui donne un texte de remplacement.
    """
    trouvees: dict[str, tuple[str, bytes]] = {}
    for chemin in map(Path, chemins):
        try:
            doc = Document(str(chemin))
        except Exception:  # noqa: BLE001 - un fichier illisible est déjà nommé par analyser_exemples
            continue
        parties = [doc.part] + [s.header.part for s in doc.sections] + [s.footer.part for s in doc.sections]
        for partie in parties:
            for lien in partie.rels.values():
                if lien.reltype != RT.IMAGE or lien.is_external:
                    continue
                cle = empreinte(lien.target_part.blob)
                if cle in empreintes and cle not in trouvees:
                    trouvees[cle] = (lien.target_part.content_type, lien.target_part.blob)
        if len(trouvees) == len(empreintes):
            break
    return trouvees
