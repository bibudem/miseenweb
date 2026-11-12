"""Lecture du pied de page d'un document Word : son ISSN, et son contenu à reproduire en HTML."""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

from docx import Document
from docx.text.hyperlink import Hyperlink


def _premier_pied(document):
    """Renvoie le premier pied de page qui contient du texte, ou None."""
    for section in document.sections:
        pied = section.footer
        if not pied.is_linked_to_previous and any(p.text.strip() for p in pied.paragraphs):
            return pied
    return None


def _images_html(run, partie) -> str:
    """Renvoie les balises <img> des images contenues dans un segment de texte."""
    balises = ""
    for identifiant in run._r.xpath(".//a:blip/@r:embed"):
        image = partie.related_parts[identifiant]
        encodage = base64.b64encode(image.blob).decode("ascii")
        balises += f'<img src="data:{image.content_type};base64,{encodage}" alt="">'
    return balises


def _paragraphe_html(paragraphe, partie) -> str:
    """Convertit un paragraphe du pied de page; les grands espaces séparent des blocs."""
    contenu = ""
    for element in paragraphe.iter_inner_content():
        if isinstance(element, Hyperlink):
            adresse = html.escape(element.address or "", quote=True)
            contenu += f'<a href="{adresse}">{html.escape(element.text)}</a>'
        else:
            contenu += _images_html(element, partie) + html.escape(element.text)
    blocs = [b.strip() for b in re.split(r"\t|\s{3,}", contenu) if b.strip()]
    return "<p>" + "".join(f"<span>{b}</span>" for b in blocs) + "</p>" if blocs else ""


def issn_du_document(chemin_docx: Path) -> str | None:
    """Renvoie l'ISSN écrit dans le pied de page du document, ou None."""
    pied = _premier_pied(Document(str(chemin_docx)))
    if pied is None:
        return None
    texte = " ".join(p.text for p in pied.paragraphs)
    trouve = re.search(r"ISSN\s*:?\s*(\d{4}-\d{3}[\dXx])", texte)
    return trouve.group(1).upper() if trouve else None


def pied_page_html(chemin_docx: Path) -> str:
    """Renvoie le pied de page du document en HTML, ou une chaîne vide s'il n'y en a pas."""
    pied = _premier_pied(Document(str(chemin_docx)))
    if pied is None:
        return ""
    paragraphes = "".join(_paragraphe_html(p, pied.part) for p in pied.paragraphs)
    return f'<footer class="pied-page">{paragraphes}</footer>'
