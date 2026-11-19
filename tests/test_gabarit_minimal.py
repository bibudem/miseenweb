"""Gabarit minimal : le rapport signale chaque élément absent d'un manuscrit, si le profil le demande."""

import base64
import io
import json

import pytest
from docx2html import generateur

# Profil écrit par l'assistant, qui active la vérification; reconnu par le nom du fichier
PROFIL = generateur.generer_profil({"revue": "Ma publication", "issn": "1234-5678", "mot_nom_fichier": "ma_publication"})

# Image d'un pixel, à la place du logo
LOGO = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
TEXTE = "Un paragraphe de texte courant, assez long pour ne pas être pris pour un sous-titre du document."

# Élément retiré du manuscrit -> titre de la remarque attendue
REMARQUES = {
    "logo": "Logo absent de l'en-tête.",
    "resume": "Résumé absent.",
    "mots_cles": "Mots-clés absents.",
    "references": "Références absentes.",
    "issn": "ISSN absent du pied de page.",
    "licence": "Licence absente du pied de page.",
    "doi": "DOI absent du pied de page.",
}


def manuscrit(doc, sauf=""):
    """Remplit un manuscrit fictif avec tous les éléments du gabarit minimal, sauf un."""
    if sauf != "logo":
        doc.sections[0].header.paragraphs[0].add_run().add_picture(io.BytesIO(LOGO))
    pied = {"issn": "ISSN 1234-5678", "licence": "CC BY 4.0", "doi": "https://doi.org/10.1234/abcd.5"}
    doc.sections[0].footer.paragraphs[0].text = "   ".join(t for cle, t in pied.items() if cle != sauf)
    doc.add_paragraph("Titre de l'article fictif", style="Title")
    if sauf != "resume":
        doc.add_paragraph("Résumé")
        doc.add_paragraph(TEXTE)
    if sauf != "mots_cles":
        doc.add_paragraph("Mots-clés : essai, gabarit")
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph(TEXTE)
    if sauf != "references":
        doc.add_heading("Références", level=1)
        doc.add_paragraph("Auteur, A. (2026). Titre d'un ouvrage fictif. Éditeur.")
    return doc


def remarques_gabarit(resultat):
    return [r["titre"] for r in resultat["remarques"] if r["titre"] in REMARQUES.values()]


def test_profil_de_l_assistant_active_la_verification():
    assert "  gabarit_minimal: true" in PROFIL


def test_manuscrit_complet(nouveau_document, pont, module_pont):
    module_pont.deposer_profil(PROFIL)
    resultat = pont(manuscrit(nouveau_document), nom="article_ma_publication.docx")
    assert resultat["profil"] == "ma-publication"
    assert remarques_gabarit(resultat) == []


@pytest.mark.parametrize("element", REMARQUES)
def test_element_absent(element, nouveau_document, pont, module_pont):
    module_pont.deposer_profil(PROFIL)
    resultat = pont(manuscrit(nouveau_document, sauf=element), nom="article_ma_publication.docx")
    assert remarques_gabarit(resultat) == [REMARQUES[element]]


def test_doi_absent_est_une_information(nouveau_document, pont, module_pont):
    module_pont.deposer_profil(PROFIL)
    resultat = pont(manuscrit(nouveau_document, sauf="doi"), nom="article_ma_publication.docx")
    assert resultat["statut"] == "ok"           # une information ne donne pas le statut « avertissements »


def test_sans_le_reglage(nouveau_document, pont, module_pont):
    reponse = json.loads(module_pont.deposer_profil(PROFIL.replace("gabarit_minimal: true", "gabarit_minimal: false")))
    assert reponse["messages"] == []
    nouveau_document.add_paragraph("Titre de l'article fictif", style="Title")
    resultat = pont(nouveau_document, nom="article_ma_publication.docx")
    assert remarques_gabarit(resultat) == []
