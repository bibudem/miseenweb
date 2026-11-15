"""Contrôle d'intégrité : le texte du document Word se retrouve-t-il dans la page produite?

Le contrôle ne dépend d'aucun profil. Il sert de filet pour les documents que personne n'a
testés : si la conversion laisse tomber un paragraphe, l'utilisateur en est averti.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REPLI = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
ESPACES = re.compile(r"\s+")

# Un paragraphe plus court ne dit rien d'utile : puce, numéro, symbole isolé
LONGUEUR_MINIMALE = 4


def _sans_espaces(texte: str) -> str:
    """Retire tous les espaces : une tabulation ou un saut de ligne ne doit pas fausser la comparaison."""
    return ESPACES.sub("", texte)


# Éléments placés dans le fil du texte et que la page rend par un autre caractère, ou ne rend
# pas : trait d'union insécable, symbole, appel de note, saut de ligne. Le texte est comparé
# morceau par morceau, de part et d'autre de ces éléments.
COUPURES = {
    W + nom
    for nom in ("noBreakHyphen", "softHyphen", "sym", "footnoteReference", "endnoteReference",
                "br", "cr", "tab", "ptab", "drawing", "pict", "object", "fldChar")
}


def _paragraphes_du_document(chemin_docx: Path) -> list[list[str]]:
    """Texte de chaque paragraphe du corps du document, en morceaux, tableaux et zones de texte compris.

    Word enregistre certaines zones de texte en double, pour les anciennes versions du logiciel.
    La copie de repli est ignorée. Un paragraphe sans morceau d'au moins quatre caractères
    n'est pas renvoyé.
    """
    with zipfile.ZipFile(chemin_docx) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    corps = document.find(W + "body")
    paragraphes = []
    for paragraphe in corps.iter(W + "p"):
        if any(ancetre.tag == REPLI for ancetre in paragraphe.iterancestors()):
            continue
        morceaux = [""]
        for element in paragraphe.iter():
            if element.tag != W + "t" and element.tag not in COUPURES:
                continue
            # Le contenu d'une zone de texte appartient aux paragraphes de cette zone, lus à leur tour
            if next(a for a in element.iterancestors() if a.tag == W + "p") is not paragraphe:
                continue
            if element.tag == W + "t":
                morceaux[-1] += element.text or ""
            else:
                morceaux.append("")
        morceaux = [m.strip() for m in morceaux if len(_sans_espaces(m)) >= LONGUEUR_MINIMALE]
        if morceaux:
            paragraphes.append(morceaux)
    return paragraphes


def passages_absents(chemin_docx: Path, page_html: str) -> list[str]:
    """Renvoie le début des paragraphes du document Word dont un morceau manque dans la page.

    La comparaison ignore les espaces et la mise en forme. Elle ne dit rien de l'ordre du
    texte ni de son apparence : elle détecte seulement un texte qui manque.
    """
    page = _sans_espaces(BeautifulSoup(page_html, "html.parser").get_text(""))
    absents = []
    for morceaux in _paragraphes_du_document(Path(chemin_docx)):
        manquants = [m for m in morceaux if _sans_espaces(m) not in page]
        if manquants:
            absents.append(manquants[0][:80])
    return absents
