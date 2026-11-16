"""Présentation « chicago » des tableaux (Chicago Manual of Style, 18e édition).

Aucun profil du répertoire n'utilise encore cette présentation : le test copie le profil
par défaut et y change la seule option « tableaux ».
"""

import copy
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from docx2html import pipeline
from docx2html.profils import Profil

LIGNES = [("Variable", "n"), ("Âge", "12"), ("Sexe", "30")]


@pytest.fixture
def convertir_chicago(tmp_path, catalogue):
    """Convertit un document avec le profil par défaut, réglé sur « tableaux: chicago »."""
    defaut = catalogue["defaut"]
    donnees = copy.deepcopy(defaut.donnees)
    donnees["post_traitement"]["tableaux"] = "chicago"
    profils = {"defaut": defaut, "essai-chicago": Profil("essai-chicago", defaut.chemin, donnees)}

    def _convertir(document):
        chemin = tmp_path / "essai.docx"
        document.save(chemin)
        entree = pipeline.convertir_fichier(chemin, profils, tmp_path / "sortie", "essai-chicago", journal=lambda m: None)
        assert not entree.erreur, entree.erreur
        return BeautifulSoup(Path(entree.sortie).read_text(encoding="utf-8"), "html.parser"), entree

    return _convertir


def ajouter_tableau(document):
    tableau = document.add_table(rows=len(LIGNES), cols=2)
    for i, ligne in enumerate(LIGNES):
        for j, valeur in enumerate(ligne):
            tableau.cell(i, j).text = valeur


def test_numero_et_titre_reunis_sur_une_ligne(nouveau_document, convertir_chicago):
    doc = nouveau_document
    doc.add_heading("Titre du document fictif", level=1)
    doc.add_paragraph("Texte avant le tableau.")
    doc.add_paragraph("Tableau 1")
    doc.add_paragraph("Caractéristiques de l'échantillon")
    ajouter_tableau(doc)
    page, entree = convertir_chicago(doc)
    titre = page.find(id=page.find("table")["aria-labelledby"])
    assert titre.get_text() == "Tableau 1. Caractéristiques de l'échantillon"
    assert entree.titres_tableaux_reunis == ["Tableau 1"]
    assert entree.statut == "ok"                 # une réunion est une information, pas un défaut
    assert not entree.passages_absents           # aucun texte perdu


def test_titre_deja_sur_la_ligne_du_numero_laisse_tel_quel(nouveau_document, convertir_chicago):
    doc = nouveau_document
    doc.add_paragraph("Un paragraphe ordinaire, qui ne doit pas être réuni au titre du tableau.")
    doc.add_paragraph("Table 2. Caractéristiques de l'échantillon")
    ajouter_tableau(doc)
    page, entree = convertir_chicago(doc)
    assert entree.titres_tableaux_reunis == []
    textes = [p.get_text() for p in page.find("main").find_all("p", recursive=False)]
    assert "Un paragraphe ordinaire, qui ne doit pas être réuni au titre du tableau." in textes
    assert "Table 2. Caractéristiques de l'échantillon" in textes


def test_trois_lignes_horizontales_et_en_tetes_centres(nouveau_document, convertir_chicago):
    from test_presentation_tableaux import regles_css

    ajouter_tableau(nouveau_document)
    page, _ = convertir_chicago(nouveau_document)
    regles = regles_css(page)
    assert "border-top: 1.5px solid var(--texte)" in regles["table"]
    assert "border-bottom: 1px solid var(--texte)" in regles["th"]
    assert "text-align: center" in regles["th"]
    assert "text-align: start" in regles["th.premiere-colonne"]
    assert "border: 1px" not in regles["td, th"]


def test_reunion_signalee_a_l_utilisateur(nouveau_document, pont, catalogue):
    import sys

    defaut = catalogue["defaut"]
    donnees = copy.deepcopy(defaut.donnees)
    donnees["post_traitement"]["tableaux"] = "chicago"
    sys.modules["pont"].PROFILS["essai-chicago"] = Profil("essai-chicago", defaut.chemin, donnees)

    doc = nouveau_document
    doc.add_heading("Titre du document fictif", level=1)
    doc.add_paragraph("Tableau 1")
    doc.add_paragraph("Caractéristiques de l'échantillon")
    ajouter_tableau(doc)
    resultat = pont(doc, profil="essai-chicago")
    remarque = next(r for r in resultat["remarques"] if "réunis sur une ligne" in r["titre"])
    assert remarque["gravite"] == "info"
    assert remarque["origine"] == "conversion"
    assert "« Tableau 1 »" in remarque["titre"]
    assert remarque["cible"] == {"id": "titre-tableau-1"}      # la remarque mène au titre dans la page
