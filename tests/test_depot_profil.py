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
