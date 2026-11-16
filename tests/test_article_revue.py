"""Article de la revue Science infirmière et pratiques en santé : bandeau, résumé, références, arabe."""

import pytest
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

ARTICLE = "1234_mise_en_page.docx"


def colorer(paragraphe, couleur):
    """Donne une couleur de fond au paragraphe, comme la trame de fond de Word."""
    trame = OxmlElement("w:shd")
    trame.set(qn("w:val"), "clear")
    trame.set(qn("w:fill"), couleur)
    paragraphe._p.get_or_add_pPr().append(trame)


def article(doc, couleur_bandeau):
    """Bandeau, titre, puis mots-clés et résumé dans l'ordre inverse de la lecture."""
    colorer(doc.add_paragraph("Article de recherche | Research article"), couleur_bandeau)
    titre = doc.add_paragraph().add_run("Titre de l'article fictif")
    titre.bold, titre.font.size = True, Pt(16)
    doc.add_paragraph("Mots-clés")
    doc.add_paragraph("soins, essai, fictif")
    doc.add_paragraph("Résumé")
    doc.add_paragraph("Le texte du résumé de cet article fictif.")
    doc.add_paragraph("Keywords")
    doc.add_paragraph("care, test, fictional")
    doc.add_paragraph("Abstract")
    doc.add_paragraph("The abstract of this fictional article.")
    return doc


@pytest.mark.parametrize(
    "fond, texte",
    [
        ("FFC000", "#000000"),      # jaune : le blanc n'y atteint pas 4,5:1 (WCAG 1.4.3)
        ("ED7D31", "#000000"),      # orange
        ("1F3864", "#ffffff"),      # bleu foncé
    ],
)
def test_bandeau_garde_sa_couleur_avec_un_texte_lisible(nouveau_document, convertir, fond, texte):
    page, _ = convertir(article(nouveau_document, fond), nom=ARTICLE)

    bandeau = page.find("p", class_="bandeau")
    assert bandeau.get_text() == "Article de recherche | Research article"
    assert bandeau.find_next_sibling().name == "h1"            # juste avant le titre
    assert bandeau["style"] == f"background: #{fond}; color: {texte};"


def test_resume_avant_ses_mots_cles_dans_chaque_langue(nouveau_document, convertir):
    page, entree = convertir(article(nouveau_document, "1F3864"), nom=ARTICLE)

    ordre = [p.get_text() for p in page.find("main").find_all("p", recursive=False)]
    for resume, mots_cles in (("Résumé", "Mots-clés"), ("Abstract", "Keywords")):
        assert ordre.index(resume) < ordre.index(mots_cles)
    assert ordre.index("Mots-clés") < ordre.index("Abstract")  # les deux langues ne se mêlent pas
    assert entree.passages_absents == []                       # le déplacement ne perd rien


def test_reference_reconnue_par_son_style(nouveau_document, convertir):
    doc = article(nouveau_document, "1F3864")
    doc.styles.add_style("Bibliography", WD_STYLE_TYPE.PARAGRAPH)
    doc.add_paragraph("Auteur, A. (2020). Titre fictif. Revue fictive, 1(2), 3-4.", style="Bibliography")

    page, _ = convertir(doc, nom=ARTICLE)

    reference = page.find("p", class_="reference")
    assert reference.get_text().startswith("Auteur, A.")
    assert "p.reference" in page.find("style").get_text()      # retrait négatif défini dans le gabarit


def test_passage_en_arabe_de_droite_a_gauche(nouveau_document, convertir):
    doc = article(nouveau_document, "1F3864")
    doc.add_paragraph("هذا نص تجريبي قصير")
    doc.add_paragraph("Un paragraphe en français.")

    page, _ = convertir(doc, nom=ARTICLE)

    arabe = page.find("p", attrs={"dir": "rtl"})
    assert arabe["lang"] == "ar"
    assert len(page.find_all(attrs={"dir": True})) == 1        # le reste de la page n'est pas marqué
