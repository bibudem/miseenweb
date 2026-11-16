"""Tableaux de la revue Science infirmière et pratiques en santé, selon l'APA (7e édition).

Le nom du fichier contient « mise_en_page » : le profil de la revue est reconnu par ce nom.
"""

import pytest
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

ARTICLE = "1234_mise_en_page.docx"
TEXTE_LONG = "Un texte assez long pour être traité comme du texte suivi, soit plus de cinquante caractères."

LIGNES = [
    ("Variable", "n", "Description"),
    ("Âge", "12", TEXTE_LONG),
    ("  Jeune", "5", TEXTE_LONG),          # retrait fait avec des espaces : ligne subordonnée
    ("Sexe", "30", TEXTE_LONG),
    ("Note. Ceci est la note du tableau.", "", ""),
]


@pytest.fixture
def page(nouveau_document, convertir):
    """Article fictif : un titre, un tableau numéroté avec sa note, puis du texte."""
    doc = nouveau_document
    titre = doc.add_paragraph().add_run("Titre de l'article fictif")
    titre.bold, titre.font.size = True, Pt(16)
    doc.add_paragraph("Table 1")
    doc.add_paragraph("Caractéristiques de l'échantillon")
    tableau = doc.add_table(rows=len(LIGNES), cols=3)
    for i, ligne in enumerate(LIGNES):
        for j, valeur in enumerate(ligne):
            tableau.cell(i, j).text = valeur
    tableau.cell(1, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT    # contraire à l'APA
    tableau.cell(4, 0).merge(tableau.cell(4, 2))
    doc.add_paragraph("Texte après le tableau.")
    page, entree = convertir(doc, nom=ARTICLE)
    assert entree.profil == "science-infirmiere/mise-en-page"
    return page


def classes(cellule):
    return set(cellule.get("class", []))


def test_titre_de_l_article_reconnu(page):
    # Paragraphe Normal, gras, 16 points : le profil en fait le titre principal
    assert page.find("h1", class_="titre-document").get_text() == "Titre de l'article fictif"


def test_en_tetes_de_colonnes_et_de_lignes(page):
    lignes = page.find("table").find_all("tr")
    assert [c.name for c in lignes[0].find_all(["td", "th"])] == ["th", "th", "th"]
    assert all(c["scope"] == "col" for c in lignes[0].find_all("th"))
    for ligne in lignes[1:]:
        premiere = ligne.find(["td", "th"])
        assert premiere.name == "th" and premiere["scope"] == "row"


def test_alignement_par_colonne(page):
    lignes = page.find("table").find_all("tr")
    for ligne in lignes:
        variable, nombre, description = ligne.find_all(["td", "th"])
        assert "centre" not in classes(variable)          # première colonne : à gauche
        assert "centre" in classes(nombre)                # colonne de données : centrée, en-tête compris
        assert "centre" not in classes(description)       # colonne de texte long : à gauche


def test_ligne_subordonnee_en_retrait(page):
    jeune = page.find("table").find_all("tr")[2].find("th")
    assert jeune.find("p")["class"] == ["retrait-1"]
    assert jeune.get_text().strip() == "Jeune"            # le navigateur n'affiche pas les espaces du début


def test_note_sous_le_tableau(page):
    tableau = page.find("table")
    assert len(tableau.find_all("tr")) == 4               # la ligne de note a quitté le tableau
    note = tableau.find_next_sibling()
    assert note.name == "p" and note["class"] == ["note-tableau"]
    assert note.get_text().startswith("Note.")


def test_tableau_nomme_par_son_numero_et_son_titre(page):
    identifiants = page.find("table")["aria-labelledby"].split()
    textes = [page.find(id=i).get_text() for i in identifiants]
    assert textes == ["Table 1", "Caractéristiques de l'échantillon"]


def test_cellule_courte_sur_une_ligne(page):
    lignes = page.find("table").find_all("tr")
    assert "insecable" in classes(lignes[0].find_all("th")[1])     # « n »
    assert "insecable" not in classes(lignes[1].find_all("td")[1])  # texte long : peut se couper
