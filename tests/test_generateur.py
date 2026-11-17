"""Générateur de profil : le fichier produit est valide et donne la conversion attendue."""

import hashlib
import io
import json
import struct
import zlib
from pathlib import Path

import pytest
from docx.shared import Pt
from docx2html import generateur, validation

from test_presentation_tableaux import regles_css

GABARITS = Path(__file__).resolve().parent.parent / "python" / "gabarits"


def _image_png() -> bytes:
    """Une image fictive d'un seul point, écrite à la main : aucun fichier d'image dans le répertoire."""
    def bloc(sorte: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + sorte + donnees + struct.pack(">I", zlib.crc32(sorte + donnees))
    entete = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + bloc(b"IEND", b"")


IMAGE = _image_png()
REPONSES = {
    "revue": "Revue d'études fictives",
    "issn": "1234-5678",
    "mot_nom_fichier": "",
    "titres": [
        {"taille": 12, "styles": ["Normal"], "role": "section"},
        {"taille": 16, "styles": ["Normal"], "role": "titre-article"},
    ],
    "images": [{"empreinte": hashlib.sha1(IMAGE).hexdigest(), "texte": "Logo de la revue fictive"}],
    "apparence": "article",
    "tableaux": "chicago",
    "bandeau": False,
    "pied_page": True,
}


def _en_gras(document, texte, taille):
    segment = document.add_paragraph().add_run(texte)
    segment.bold = True
    segment.font.size = Pt(taille)


def test_nom_de_profil_tire_du_nom_de_la_revue():
    assert generateur.nom_de_profil("Revue d'études fictives") == "revue-d-etudes-fictives"
    assert generateur.nom_de_profil("  ") == "revue"


def test_profil_produit_valide():
    texte = generateur.generer_profil(REPONSES)
    donnees, messages = validation.valider_texte(texte, GABARITS)
    assert messages == []
    assert donnees["nom"] == "revue-d-etudes-fictives"
    assert donnees["issn"] == "1234-5678"
    assert "detection" not in donnees                       # reconnu par l'ISSN seul


def test_mot_du_nom_de_fichier_devient_la_regle_de_reconnaissance():
    texte = generateur.generer_profil({**REPONSES, "issn": "", "mot_nom_fichier": "revue.fictive"})
    donnees, messages = validation.valider_texte(texte, GABARITS)
    assert messages == []
    assert "issn" not in donnees
    assert donnees["detection"]["motif_nom_fichier"] == r"revue\.fictive"     # le point est pris tel quel


def test_guillemets_dans_le_nom_de_la_revue():
    texte = generateur.generer_profil({**REPONSES, "revue": 'Revue "entre guillemets" : essais'})
    donnees, messages = validation.valider_texte(texte, GABARITS)
    assert messages == []
    assert donnees["revue"] == 'Revue "entre guillemets" : essais'


def test_role_inconnu_refuse():
    with pytest.raises(ValueError, match="« chapitre »"):
        generateur.generer_profil({**REPONSES, "titres": [{"taille": 12, "role": "chapitre"}]})


def test_article_converti_avec_le_profil_produit(nouveau_document, pont, module_pont):
    reponse = json.loads(module_pont.deposer_profil(generateur.generer_profil(REPONSES)))
    assert reponse["messages"] == []

    _en_gras(nouveau_document, "Titre de l'article fictif", 16)
    _en_gras(nouveau_document, "Méthode fictive", 12)
    nouveau_document.add_paragraph("Texte courant du document fictif.")
    _en_gras(nouveau_document, "Mise en évidence fictive", 10)       # taille sans rôle : reste un paragraphe
    nouveau_document.add_picture(io.BytesIO(IMAGE))
    nouveau_document.sections[0].footer.paragraphs[0].text = "ISSN 1234-5678"

    resultat = pont(nouveau_document, nom="nom_quelconque.docx")
    assert resultat["profil"] == "revue-d-etudes-fictives"

    from bs4 import BeautifulSoup
    page = BeautifulSoup((module_pont.SORTIE / resultat["sortie"]).read_text(encoding="utf-8"), "html.parser")
    assert page.h1.get_text() == "Titre de l'article fictif"
    assert [h.get_text() for h in page.find_all("h2")] == ["Méthode fictive"]
    assert page.find("img")["alt"] == "Logo de la revue fictive"
    assert page.find("footer", class_="pied-page") is not None
    regles = regles_css(page)
    assert "text-align: center" in regles["h1, h2"]                  # apparence « article »
    assert "border: 1px" not in regles["td, th"]                     # tableaux sans bordure de cellule


# ---- Par le pont, comme le fait la page ----

def test_releve_et_profil_par_le_pont(nouveau_document, module_pont):
    from docx import Document

    noms = []
    for rang in (1, 2):
        document = Document()
        _en_gras(document, f"Titre fictif {rang}", 16)
        document.add_picture(io.BytesIO(IMAGE))
        document.sections[0].footer.paragraphs[0].text = "ISSN 1234-5678"
        noms.append(f"exemple_{rang}.docx")
        document.save(module_pont.ENTREE / noms[-1])

    releve = json.loads(module_pont.relever_exemples(json.dumps(noms)))
    assert releve["nb_articles"] == 2
    assert releve["issn"] == [{"valeur": "1234-5678", "articles": 2}]
    [image] = releve["images_communes"]
    assert image["empreinte"] == hashlib.sha1(IMAGE).hexdigest()
    assert image["apercu"].startswith("data:image/png;base64,")

    reponse = json.loads(module_pont.generer_profil(json.dumps(REPONSES)))
    assert reponse["messages"] == []
    assert json.loads(module_pont.deposer_profil(reponse["texte"]))["messages"] == []


def test_profil_genere_avec_l_issn_d_une_revue_du_site_refuse(module_pont):
    reponse = json.loads(module_pont.generer_profil(json.dumps({**REPONSES, "issn": "2561-7516"})))
    assert "déjà l'ISSN de la revue" in reponse["messages"][0]


def test_reponses_incompletes_signalees(module_pont):
    reponse = json.loads(module_pont.generer_profil(json.dumps({**REPONSES, "titres": [{"taille": 12}]})))
    assert reponse["texte"] == "" and reponse["messages"][0].startswith("Réponses incomplètes")
