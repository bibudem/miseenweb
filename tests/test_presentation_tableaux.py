"""Présentation des tableaux : les règles CSS que la page reçoit selon le profil.

Ces tests lisent la feuille de style de la page, pas son rendu à l'écran.
"""

import re

ARTICLE = "1234_mise_en_page.docx"


def regles_css(page) -> dict[str, str]:
    """Renvoie les règles de la page : sélecteur -> déclarations. Un sélecteur répété cumule ses déclarations."""
    css = re.sub(r"/\*.*?\*/", "", page.find("style").string, flags=re.S)
    regles: dict[str, str] = {}
    for selecteur, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        cle = " ".join(selecteur.split())
        regles[cle] = (regles.get(cle, "") + " " + " ".join(declarations.split())).strip()
    return regles


def test_document_general_bordure_autour_de_chaque_cellule(nouveau_document, convertir):
    nouveau_document.add_paragraph("Texte.")
    page, entree = convertir(nouveau_document)
    assert entree.profil == "defaut"
    regles = regles_css(page)
    assert "border: 1px solid var(--bordure)" in regles["td, th"]
    assert "border-top" not in regles["table"]


def test_article_de_revue_trois_lignes_horizontales(nouveau_document, convertir):
    nouveau_document.add_paragraph("Texte.")
    page, entree = convertir(nouveau_document, nom=ARTICLE)
    assert entree.profil == "science-infirmiere/mise-en-page"
    regles = regles_css(page)
    assert "border-top: 1.5px solid var(--texte)" in regles["table"]        # ligne du haut
    assert "border-bottom: 1.5px solid var(--texte)" in regles["table"]     # ligne du bas
    assert "border-bottom: 1px solid var(--texte)" in regles["th"]          # ligne sous l'en-tête
    assert "border: 1px" not in regles["td, th"]                            # aucune bordure de cellule
    assert "font-weight: normal" in regles["th"]                            # en-têtes sans gras


def test_presentation_inconnue_refusee_avec_les_valeurs_permises():
    from pathlib import Path

    import pytest
    from docx2html import post_traitement
    from docx2html.profils import ErreurProfil

    gabarits = Path(post_traitement.__file__).resolve().parent.parent / "gabarits"
    with pytest.raises(ErreurProfil) as erreur:
        post_traitement._styles_tableaux({"tableaux": "vancouver"}, gabarits)
    message = str(erreur.value)
    assert "« vancouver »" in message
    assert "apa" in message and "bordures" in message
