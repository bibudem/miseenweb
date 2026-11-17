"""Analyse d'articles d'exemple : le relevé de ce qui revient d'un article fictif à l'autre."""

import base64

import pytest
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt
from docx2html import analyse

# Deux images d'un pixel, de couleurs différentes : leur empreinte diffère
LOGO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
FIGURE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def article(dossier, nom, titre_de_tableau_sur_une_ligne=False, figure=False):
    """Crée un article fictif : bandeau coloré, titre en gras, sous-titres, logo, tableau, ISSN."""
    doc = Document()
    bandeau = doc.add_paragraph().add_run("Article de recherche")
    bandeau.font.highlight_color = WD_COLOR_INDEX.YELLOW
    titre = doc.add_paragraph().add_run(f"Titre de {nom}")
    titre.bold, titre.font.size = True, Pt(16)
    for sous_titre in ("Introduction", "Méthode"):
        segment = doc.add_paragraph().add_run(sous_titre)
        segment.bold, segment.font.size = True, Pt(12)
        doc.add_paragraph("Un paragraphe de texte ordinaire, qui se termine par un point.")
    important = doc.add_paragraph().add_run("Une phrase entière en gras, qui se termine par un point.")
    important.bold = True
    doc.add_heading("Références", level=1)
    (dossier / "logo.png").write_bytes(LOGO)
    doc.add_picture(str(dossier / "logo.png"))
    if figure:
        (dossier / "figure.png").write_bytes(FIGURE)
        doc.add_picture(str(dossier / "figure.png"))
    if titre_de_tableau_sur_une_ligne:
        doc.add_paragraph("Tableau 1. Caractéristiques de l'échantillon")
    else:
        doc.add_paragraph("Tableau 1")
        doc.add_paragraph("Caractéristiques de l'échantillon")
    doc.add_table(rows=2, cols=2)
    doc.sections[0].footer.paragraphs[0].text = "Revue fictive, ISSN 1234-5678"
    chemin = dossier / nom
    doc.save(chemin)
    return chemin


@pytest.fixture
def releve(tmp_path):
    chemins = [
        article(tmp_path, "2024_revue-fictive_01.docx"),
        article(tmp_path, "2024_revue-fictive_02.docx", figure=True),
        article(tmp_path, "2025_revue-fictive_03.docx", titre_de_tableau_sur_une_ligne=True),
    ]
    return analyse.analyser_exemples(chemins)


def test_articles_lus(releve):
    assert releve["nb_articles"] == 3 and releve["illisibles"] == []


def test_styles_comptes_par_article(releve):
    styles = {s["nom"]: s for s in releve["styles"]}
    assert styles["Normal"]["articles"] == 3
    assert styles["Heading 1"] == {"nom": "Heading 1", "articles": 3, "paragraphes": 3, "titre": True}
    assert releve["styles"][0]["nom"] == "Normal"            # le plus fréquent en premier


def test_titres_en_gras_groupes_par_taille(releve):
    tailles = {g["taille"]: g for g in releve["titres_en_gras"]}
    assert tailles[16.0]["articles"] == 3 and tailles[16.0]["paragraphes"] == 3
    assert tailles[12.0]["paragraphes"] == 6                 # deux sous-titres par article
    assert tailles[12.0]["exemples"] == ["Introduction", "Méthode"]
    assert tailles[12.0]["styles"] == ["Normal"]
    tous = [e for g in releve["titres_en_gras"] for e in g["exemples"]]
    assert not any("phrase entière" in e for e in tous)      # une phrase en gras n'est pas un titre
    assert [g["taille"] for g in releve["titres_en_gras"]] == [16.0, 12.0]     # du plus gros au plus petit


def test_image_commune_reconnue_et_figure_ecartee(releve):
    assert len(releve["images_communes"]) == 1               # le logo; la figure ne paraît que dans un article
    logo = releve["images_communes"][0]
    assert logo["articles"] == 3 and logo["type"] == "image/png" and logo["endroits"] == ["corps"]
    assert len(logo["empreinte"]) == 40


def test_issn_du_pied_de_page(releve):
    assert releve["issn"] == [{"valeur": "1234-5678", "articles": 3}]


def test_couleur_du_bandeau(releve):
    assert releve["couleurs"] == [{"couleur": "#FFFF00", "articles": 3, "exemples": ["Article de recherche"]}]


def test_place_du_titre_des_tableaux(releve):
    assert releve["tableaux"] == {"articles": 3, "total": 3, "deux_lignes": 2, "une_ligne": 1, "sans_titre": 0}


def test_partie_commune_des_noms_de_fichier(releve):
    assert releve["nom_commun"] == "revue-fictive"


def test_fichier_illisible_ecarte_et_nomme(tmp_path):
    faux = tmp_path / "pas_un_word.docx"
    faux.write_text("ceci n'est pas un document Word", encoding="utf-8")
    releve = analyse.analyser_exemples([article(tmp_path, "article.docx"), faux])
    assert releve["nb_articles"] == 1
    assert [i["fichier"] for i in releve["illisibles"]] == ["pas_un_word.docx"]
    assert releve["nom_commun"] == ""                        # un seul article lu : rien à comparer


def test_titre_long_de_grande_taille_releve(tmp_path):
    """Le titre d'un article dépasse souvent 15 mots : sa grande taille suffit à le retenir."""
    from docx import Document
    from docx.shared import Pt

    chemins = []
    for rang in (1, 2):
        document = Document()
        for taille in (16, 12):
            segment = document.add_paragraph().add_run("Titre fictif " + "très " * 20 + f"long {rang}")
            segment.bold, segment.font.size = True, Pt(taille)
        chemins.append(tmp_path / f"long_{rang}.docx")
        document.save(chemins[-1])
    tailles = [g["taille"] for g in analyse.analyser_exemples(chemins)["titres_en_gras"]]
    assert tailles == [16.0]            # à 12 points, un paragraphe en gras aussi long reste du texte


def test_styles_propres_a_la_publication(tmp_path):
    """Un style créé par la publication est relevé avec ses extraits. Ses paragraphes ne comptent pas comme texte en gras."""
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import Pt

    chemins = []
    for rang in (1, 2):
        document = Document()
        document.styles.add_style("Intertitre", WD_STYLE_TYPE.PARAGRAPH)
        segment = document.add_paragraph(style="Intertitre").add_run(f"Intertitre fictif {rang}")
        segment.bold, segment.font.size = True, Pt(12)
        document.add_paragraph("Texte courant fictif.")
        document.add_heading("Titre intégré fictif", level=1)
        chemins.append(tmp_path / f"style_{rang}.docx")
        document.save(chemins[-1])
    releve = analyse.analyser_exemples(chemins)
    assert releve["styles_propres"] == [
        {"nom": "Intertitre", "articles": 2, "paragraphes": 2, "exemples": ["Intertitre fictif 1", "Intertitre fictif 2"]}
    ]
    assert releve["titres_en_gras"] == []          # « Normal » et « Heading 1 », intégrés à Word, ne sont pas des styles propres
