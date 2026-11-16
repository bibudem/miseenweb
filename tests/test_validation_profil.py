"""Validation d'un profil déposé par une revue : chaque erreur donne un message qui nomme le réglage."""

from pathlib import Path

import pytest
import yaml
from docx2html import validation

RACINE = Path(__file__).resolve().parent.parent
GABARITS = RACINE / "python" / "gabarits"
PROFILS = RACINE / "python" / "profils"

VALIDE = """
nom: ma-revue
description: Articles de ma revue.
detection:
  motif_nom_fichier: "ma_revue"
post_traitement:
  tableaux: apa
  gabarit: ../gabarits/page.html
"""


def messages(texte, reserves=frozenset()):
    return validation.valider_texte(texte, GABARITS, reserves)[1]


def test_profil_valide_accepte():
    donnees, erreurs = validation.valider_texte(VALIDE, GABARITS)
    assert erreurs == []
    assert donnees["nom"] == "ma-revue"


@pytest.mark.parametrize("fichier", sorted(p.name for p in PROFILS.glob("*.yaml")))
def test_profils_du_repertoire_valides(fichier):
    """Un réglage ajouté au convertisseur sans être ajouté au schéma fait échouer ce test."""
    donnees = yaml.safe_load((PROFILS / fichier).read_text(encoding="utf-8"))
    assert validation.valider(donnees, GABARITS, depose=False) == []


def test_fichier_illisible_donne_la_ligne():
    erreurs = messages("nom: ma-revue\ndetection:\n  motif_nom_fichier: \"ma_revue\n")
    assert len(erreurs) == 1 and erreurs[0].startswith("Ligne ")


def test_fichier_vide_refuse():
    assert "Fichier vide" in messages("")[0]


def test_reglage_mal_ecrit_donne_le_reglage_voisin():
    erreurs = messages(VALIDE.replace("tableaux: apa", "tableau: apa"))
    assert erreurs == ["post_traitement > tableau : réglage inconnu. Réglage voisin : « tableaux »."]


def test_valeur_hors_liste_donne_les_valeurs_permises():
    erreurs = messages(VALIDE.replace("tableaux: apa", "tableaux: vancouver"))
    assert len(erreurs) == 1
    assert "« vancouver »" in erreurs[0] and "apa, bordures, chicago" in erreurs[0]


def test_oui_au_lieu_de_true_refuse():
    erreurs = messages(VALIDE + "  notes_tableaux: oui\n")
    assert erreurs == ["post_traitement > notes_tableaux : valeur « oui » refusée. Écrire true ou false."]


def test_gabarit_etranger_au_site_refuse():
    erreurs = messages(VALIDE.replace("../gabarits/page.html", "../../ailleurs.html"))
    assert len(erreurs) == 1 and "../gabarits/page.html" in erreurs[0]


def test_expression_reguliere_invalide_refusee():
    erreurs = messages(VALIDE.replace('"ma_revue"', '"(ma_revue"'))
    assert len(erreurs) == 1 and "expression régulière invalide" in erreurs[0]


def test_nom_absent_ou_mal_forme_refuse():
    assert any(m.startswith("nom : réglage obligatoire") for m in messages(VALIDE.replace("nom: ma-revue", "")))
    assert any("« Ma Revue »" in m for m in messages(VALIDE.replace("nom: ma-revue", "nom: Ma Revue")))


def test_nom_d_un_profil_du_site_refuse():
    erreurs = messages(VALIDE.replace("ma-revue", "defaut"), reserves={"defaut"})
    assert erreurs == ["nom : « defaut » est déjà le nom d'un profil du site. Choisir un autre nom."]


def test_profil_sans_regle_de_reconnaissance_refuse():
    erreurs = messages(VALIDE.replace('  motif_nom_fichier: "ma_revue"\n', "  priorite: 5\n"))
    assert len(erreurs) == 1 and "aucune règle de reconnaissance" in erreurs[0]


def test_issn_suffit_a_la_reconnaissance_mais_doit_etre_bien_forme():
    sans_regle = VALIDE.replace('  motif_nom_fichier: "ma_revue"\n', "  priorite: 5\n")
    assert messages(sans_regle + 'issn: "1234-5678"\n') == []
    assert any("issn" in m for m in messages(VALIDE + "issn: 12345678\n"))


def test_profil_depose_ne_peut_pas_etre_le_profil_par_defaut():
    erreurs = messages(VALIDE.replace('  motif_nom_fichier: "ma_revue"', "  defaut: true"))
    assert len(erreurs) == 1 and "réservé au profil par défaut" in erreurs[0]


def test_profil_de_revue_avec_variantes():
    texte = """
nom: ma-revue
revue: Ma revue
commun:
  post_traitement:
    tableaux: chicago
variantes:
  manuscrit:
    detection:
      motif_nom_fichier: "manuscrit"
    normalisation:
      regles:
        - nom: titre
          styles_source: ["Normal"]
          gras: vrai
          style_cible: "Heading 1"
"""
    erreurs = messages(texte)
    assert erreurs == ["variantes > manuscrit > normalisation > regles > élément 1 > gras : "
                       "valeur « vrai » refusée. Écrire true ou false."]
