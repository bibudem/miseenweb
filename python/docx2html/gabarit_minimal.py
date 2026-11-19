"""Gabarit minimal : éléments que chaque manuscrit déposé par une publication doit porter.

Le module dit quels éléments manquent. Il ne vérifie que ce qui se repère sans erreur :
le logo dans l'en-tête, le résumé, les mots-clés, les références, puis l'ISSN, la licence
et le DOI dans le pied de page. Le titre de l'article fait déjà l'objet d'une remarque.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

ESPACES_XML = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
}
# Requêtes compilées par lxml : la méthode xpath() de python-docx ne connaît pas l'espace « v »
IMAGES = etree.XPath(".//a:blip | .//v:imagedata", namespaces=ESPACES_XML)
TEXTES = etree.XPath(".//w:t/text()", namespaces=ESPACES_XML)

# Repérés dans le texte du pied de page
MOTIF_ISSN = re.compile(r"ISSN\s*:?\s*\d{4}-\d{3}[\dX]", re.IGNORECASE)
MOTIF_LICENCE = re.compile(r"\bCC[\s-]?(BY|0)\b|creative\s+commons", re.IGNORECASE)
MOTIF_DOI = re.compile(r"\b10\.\d{4,9}/\S+")

# Repérés au début d'un paragraphe ou d'un titre de la page
MOTIF_RESUME = re.compile(r"(résumé|abstract)\b")
MOTIF_MOTS_CLES = re.compile(r"(mots[\s-]*clés|key[\s-]*words?)\b")
MOTIF_REFERENCES = re.compile(r"(références|references|bibliographie|bibliography)")

TITRES = ["h1", "h2", "h3", "h4", "h5", "h6"]


def _parties(document, sorte: str) -> list:
    """Toutes les parties d'une sorte (RT.HEADER ou RT.FOOTER), pour toutes les sections."""
    return [r.target_part for r in document.part.rels.values() if r.reltype == sorte]


def _texte(element: object) -> str:
    """Texte d'un élément de la page, en minuscules, sans le deux-points final."""
    texte = unicodedata.normalize("NFC", element.get_text(" ", strip=True)).lower()
    return texte.replace(" ", " ").rstrip(" :").strip()


def elements_absents(chemin_docx: Path, soupe: BeautifulSoup) -> list[str]:
    """Renvoie les éléments du gabarit minimal absents du manuscrit, dans l'ordre de lecture.

    Clés possibles : logo, resume, mots_cles, references, issn, licence, doi.
    """
    document = Document(str(chemin_docx))
    logo = any(IMAGES(partie.element) for partie in _parties(document, RT.HEADER))
    pied = " ".join(t for partie in _parties(document, RT.FOOTER) for t in TEXTES(partie.element))

    debuts = [_texte(e) for e in soupe.find_all(["p", *TITRES])]
    titres = [_texte(e) for e in soupe.find_all(TITRES)]
    presents = {
        "logo": logo,
        "resume": any(MOTIF_RESUME.match(t) for t in debuts),
        "mots_cles": any(MOTIF_MOTS_CLES.match(t) for t in debuts),
        "references": any(MOTIF_REFERENCES.fullmatch(t) for t in titres)
                      or soupe.find("p", class_="reference") is not None,
        "issn": bool(MOTIF_ISSN.search(pied)),
        "licence": bool(MOTIF_LICENCE.search(pied)),
        "doi": bool(MOTIF_DOI.search(pied)),
    }
    return [cle for cle, present in presents.items() if not present]
