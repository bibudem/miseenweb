"""Lecture, dans un document Word, de la mise en forme que Mammoth ne transmet pas."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

# Couleurs de surlignage de Word, désignées par un nom dans le fichier
SURLIGNAGES = {
    "yellow": "FFFF00", "green": "00FF00", "cyan": "00FFFF", "magenta": "FF00FF",
    "blue": "0000FF", "red": "FF0000", "darkBlue": "000080", "darkCyan": "008080",
    "darkGreen": "008000", "darkMagenta": "800080", "darkRed": "800000",
    "darkYellow": "808000", "darkGray": "808080", "lightGray": "C0C0C0", "black": "000000",
}


def texte_normalise(texte: str) -> str:
    """Ramène les suites d'espaces à un seul espace, pour comparer un texte du Word à celui de la page."""
    return " ".join(texte.split())


def _remplissage(element) -> str | None:
    """Couleur de fond déclarée par un élément <w:shd>, ou None."""
    if element is None:
        return None
    couleur = element.get(qn("w:fill"))
    if not couleur or couleur.lower() in ("auto", "ffffff"):
        return None
    return couleur.upper()


def _fond_du_paragraphe(paragraphe) -> str | None:
    """Couleur de fond d'un paragraphe : la sienne, sinon celle que partagent tous ses segments."""
    proprietes = paragraphe._p.pPr
    fond = _remplissage(proprietes.find(qn("w:shd"))) if proprietes is not None else None
    if fond:
        return fond
    couleurs = set()
    for segment in paragraphe.runs:
        if not any(c.isalnum() for c in segment.text):     # espace ou séparateur : sans effet
            continue
        mise_en_forme = segment._r.rPr
        couleur = None
        if mise_en_forme is not None:
            couleur = _remplissage(mise_en_forme.find(qn("w:shd")))
            surlignage = mise_en_forme.find(qn("w:highlight"))
            if couleur is None and surlignage is not None:
                couleur = SURLIGNAGES.get(surlignage.get(qn("w:val")))
        couleurs.add(couleur)
    return couleurs.pop() if len(couleurs) == 1 else None


def couleurs_de_fond(chemin_docx: Path, limite: int = 12) -> dict[str, str]:
    """Associe à leur texte les paragraphes colorés du début du document.

    Seuls les `limite` premiers paragraphes non vides sont lus : la bannière d'un article
    s'y trouve. Renvoie par exemple {"Article court | Short article": "#FFC000"}.
    """
    couleurs: dict[str, str] = {}
    lus = 0
    for paragraphe in Document(str(chemin_docx)).paragraphs:
        texte = texte_normalise(paragraphe.text)
        if not texte:
            continue
        lus += 1
        if lus > limite:
            break
        fond = _fond_du_paragraphe(paragraphe)
        if fond:
            couleurs[texte] = f"#{fond}"
    return couleurs
