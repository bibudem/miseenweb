"""Page produite par le profil par défaut : structure générale et contrôle d'intégrité."""


def test_titres_et_gabarit(nouveau_document, convertir):
    doc = nouveau_document
    doc.add_paragraph("Guide du dépôt", style="Title")
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("Un paragraphe de texte courant.")

    page, entree = convertir(doc)

    assert entree.profil == "defaut"
    assert page.find("h1", class_="titre-document").get_text() == "Guide du dépôt"
    assert page.find("h2").get_text() == "Introduction"      # Title = h1, donc Heading 1 = h2
    assert "{{" not in str(page)                             # aucun marqueur du gabarit oublié
    assert "div.tableau-large" in page.find("style").get_text()   # règles de commun.css insérées


def test_aucun_texte_perdu(nouveau_document, convertir):
    doc = nouveau_document
    doc.add_heading("Méthode", level=1)
    doc.add_paragraph("Premier paragraphe du document.")
    tableau = doc.add_table(rows=2, cols=2)
    tableau.cell(1, 1).text = "Cellule de tableau"

    page, entree = convertir(doc)

    assert entree.passages_absents == []
    assert "Cellule de tableau" in page.get_text()


def test_tableau_large_defile_dans_sa_zone(nouveau_document, convertir):
    doc = nouveau_document
    etroit = doc.add_table(rows=2, cols=3)
    doc.add_paragraph("Entre les deux tableaux.")
    large = doc.add_table(rows=2, cols=9)
    for tableau in (etroit, large):
        for i, cellule in enumerate(tableau.rows[0].cells):
            cellule.text = f"Colonne {i + 1}"

    page, _ = convertir(doc)

    zones = page.find_all("div", class_="tableau-large")
    assert len(zones) == 1                                   # seul le tableau de 9 colonnes
    zone = zones[0]
    assert len(zone.find("tr").find_all(["td", "th"])) == 9
    assert zone["role"] == "region" and zone["tabindex"] == "0" and zone.get("aria-label")
