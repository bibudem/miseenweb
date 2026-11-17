"""Dépôt d'un profil par l'utilisateur : le pont le valide, l'ajoute aux profils, puis le retire."""

import json

PROFIL = """
nom: ma-revue
description: Articles de ma revue.
detection:
  motif_nom_fichier: "ma_revue"
post_traitement:
  tableaux: apa
  gabarit: ../gabarits/page.html
"""


def test_profil_valide_ajoute_puis_applique(nouveau_document, pont, module_pont):
    reponse = json.loads(module_pont.deposer_profil(PROFIL))
    assert reponse["messages"] == []
    assert reponse["libelles"] == ["Articles de ma revue"]
    deposes = [p["nom"] for p in reponse["catalogue"]["profils"] if p["depose"]]
    assert deposes == ["ma-revue"]

    nouveau_document.add_heading("Titre du document fictif", level=1)
    resultat = pont(nouveau_document, nom="article_ma_revue.docx")
    assert resultat["profil"] == "ma-revue"          # reconnu par le nom du fichier


def test_profil_refuse_ne_change_rien(module_pont):
    avant = json.loads(module_pont.catalogue())
    reponse = json.loads(module_pont.deposer_profil(PROFIL.replace("tableaux: apa", "tableaux: vancouver")))
    assert len(reponse["messages"]) == 1
    assert reponse["libelles"] == []
    assert reponse["catalogue"] == avant


def test_nouveau_depot_remplace_le_precedent(module_pont):
    module_pont.deposer_profil(PROFIL)
    reponse = json.loads(module_pont.deposer_profil(PROFIL.replace("ma-revue", "autre-revue")))
    assert [p["nom"] for p in reponse["catalogue"]["profils"] if p["depose"]] == ["autre-revue"]


def test_retrait_du_profil(module_pont):
    avant = json.loads(module_pont.catalogue())
    module_pont.deposer_profil(PROFIL)
    assert json.loads(module_pont.retirer_profil()) == avant


def test_nom_et_issn_d_un_profil_du_site_refuses(module_pont):
    reponse = json.loads(module_pont.deposer_profil(PROFIL.replace("ma-revue", "science-infirmiere")))
    assert "déjà le nom d'un profil du site" in reponse["messages"][0]
    reponse = json.loads(module_pont.deposer_profil(PROFIL + 'issn: "2561-7516"\n'))
    assert "déjà l'ISSN de la revue « Science infirmière et pratiques en santé »" in reponse["messages"][0]


def test_profil_depose_offert_dans_le_menu_des_regles(nouveau_document, pont, module_pont):
    reponse = json.loads(module_pont.deposer_profil(PROFIL))
    deposes = [r for r in reponse["catalogue"]["revues"] if r["depose"]]
    assert deposes == [{"nom": "Articles de ma revue", "issn": "", "depose": True}]

    # Choisi dans le menu, le profil s'applique d'après ses règles de reconnaissance
    nouveau_document.add_heading("Titre du document fictif", level=1)
    nom = "article_ma_revue.docx"
    nouveau_document.save(module_pont.ENTREE / nom)
    module_pont.lire(nom)
    assert json.loads(module_pont.analyser(nom, "Articles de ma revue"))["profil"] == "ma-revue"
    # « Document général » écarte le profil déposé, comme il écarte une revue
    assert json.loads(module_pont.analyser(nom, ""))["profil"] == "defaut"


def test_revues_du_site_non_marquees_comme_deposees(module_pont):
    revues = json.loads(module_pont.catalogue())["revues"]
    assert revues == [{"nom": "Science infirmière et pratiques en santé", "issn": "2561-7516", "depose": False}]


def test_revue_imposee_et_issn_inconnu_le_choix_du_menu_s_applique(nouveau_document, module_pont):
    """Un ISSN que le site ne connaît pas ne retire pas la revue choisie dans le menu."""
    nouveau_document.add_heading("Titre du document fictif", level=1)
    nouveau_document.sections[0].footer.paragraphs[0].text = "ISSN 1234-5678"
    nom = "1234_mise_en_page.docx"
    nouveau_document.save(module_pont.ENTREE / nom)
    module_pont.lire(nom)
    analyse = json.loads(module_pont.analyser(nom, "Science infirmière et pratiques en santé"))
    assert analyse["issn"] == "1234-5678"
    assert analyse["profil"] == "science-infirmiere/mise-en-page"
    # En détection automatique, un ISSN inconnu limite toujours le choix aux règles générales
    assert json.loads(module_pont.analyser(nom, module_pont.AUTO))["profil"] == "defaut"


# ---- Reconnaissance par l'ISSN seul ----

PROFIL_ISSN_SEUL = """
nom: ma-revue
revue: Ma revue
issn: "1234-5678"
description: Articles de ma revue.
post_traitement:
  gabarit: ../gabarits/page.html
"""


def _avec_issn(document, issn):
    document.add_heading("Titre du document fictif", level=1)
    document.sections[0].footer.paragraphs[0].text = f"ISSN {issn}"
    return document


def test_issn_seul_suffit_pour_un_profil_sans_regle(nouveau_document, pont, module_pont):
    assert json.loads(module_pont.deposer_profil(PROFIL_ISSN_SEUL))["messages"] == []
    resultat = pont(_avec_issn(nouveau_document, "1234-5678"), nom="nom_quelconque.docx")
    assert resultat["profil"] == "ma-revue"


def test_profil_sans_regle_ne_capte_pas_un_document_sans_son_issn(nouveau_document, pont, module_pont):
    module_pont.deposer_profil(PROFIL_ISSN_SEUL)
    assert pont(_avec_issn(nouveau_document, "8765-4321"), nom="a.docx")["profil"] == "defaut"


def test_revue_a_variantes_demande_toujours_le_nom_du_fichier(nouveau_document, pont):
    resultat = pont(_avec_issn(nouveau_document, "2561-7516"), nom="nom_quelconque.docx")
    assert resultat["profil"] == "defaut"
