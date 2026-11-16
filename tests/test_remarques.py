"""Remarques affichées à l'utilisateur après une conversion, et leur source."""

from docx.shared import Pt

TEXTE = "Un paragraphe de texte courant, assez long pour ne pas être pris pour un sous-titre du document."


def titres(resultat, origine=None):
    return [r["titre"] for r in resultat["remarques"] if origine in (None, r["origine"])]


def test_document_sans_defaut(nouveau_document, pont):
    doc = nouveau_document
    doc.add_paragraph("Guide du dépôt", style="Title")
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph(TEXTE)

    resultat = pont(doc)

    assert resultat["statut"] == "ok"
    assert resultat["libelle"] == "Document général"
    assert [r for r in resultat["remarques"] if r["gravite"] == "avertissement"] == []


def test_sous_titre_en_gras_sans_style(nouveau_document, pont):
    doc = nouveau_document
    doc.add_paragraph("Guide du dépôt", style="Title")
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph(TEXTE)
    doc.add_paragraph().add_run("Collecte des données").bold = True      # sous-titre fait à la main
    doc.add_paragraph(TEXTE)

    resultat = pont(doc)

    assert resultat["statut"] == "avertissements"
    assert titres(resultat, "document") == ["Sous-titre en gras sans style de titre."]


def test_tableau_sans_ligne_d_en_tete(nouveau_document, pont):
    doc = nouveau_document
    doc.add_paragraph("Guide du dépôt", style="Title")
    tableau = doc.add_table(rows=2, cols=2)
    for i, cellule in enumerate(tableau._cells):
        cellule.text = f"Cellule {i + 1}"

    resultat = pont(doc)

    assert "Tableau sans ligne d'en-tête." in titres(resultat, "document")


def test_hyperlien_au_texte_vague(nouveau_document, pont):
    doc = nouveau_document
    doc.add_paragraph("Guide du dépôt", style="Title")
    doc.add_paragraph("Pour la suite, voir https://exemple.org/guide et la documentation.")

    resultat = pont(doc)

    # Une adresse écrite au long devient un hyperlien, et son texte n'est pas vague
    assert not any(t.startswith("Hyperlien au texte vague") for t in titres(resultat))


def test_article_de_revue_reconnu_par_le_nom_du_fichier(nouveau_document, pont):
    doc = nouveau_document
    titre = doc.add_paragraph().add_run("Titre de l'article fictif")
    titre.bold, titre.font.size = True, Pt(16)
    doc.add_paragraph(TEXTE)

    resultat = pont(doc, nom="1234_mise_en_page.docx")

    assert resultat["libelle"] == "Science infirmière et pratiques en santé : article mis en page"
    assert resultat["titres"] == {"h1": 1}
