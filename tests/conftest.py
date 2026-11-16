"""Outils communs aux tests du convertisseur.

Les tests créent leurs documents Word avec python-docx : aucun document réel n'est conservé
dans le répertoire GitHub. Chaque document est écrit dans un dossier temporaire, effacé par pytest.
"""

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from docx import Document

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "python"))

from docx2html import pipeline, profils  # noqa: E402 - le chemin doit être ajouté avant


@pytest.fixture(scope="session")
def catalogue():
    """Tous les profils du répertoire, chargés une seule fois."""
    return profils.charger_profils(RACINE / "python" / "profils")


@pytest.fixture
def nouveau_document():
    """Renvoie un document Word vide, à remplir dans le test."""
    return Document()


@pytest.fixture
def convertir(tmp_path, catalogue):
    """Convertit un document et renvoie la page (BeautifulSoup) et l'entrée du rapport.

    « nom » sert à la reconnaissance du profil par le nom du fichier.
    « profil » force un profil, par exemple « science-infirmiere/mise-en-page ».
    """

    def _convertir(document, nom="essai.docx", profil=None):
        chemin = tmp_path / nom
        document.save(chemin)
        entree = pipeline.convertir_fichier(chemin, catalogue, tmp_path / "sortie", profil, journal=lambda m: None)
        assert not entree.erreur, entree.erreur
        page = BeautifulSoup(Path(entree.sortie).read_text(encoding="utf-8"), "html.parser")
        return page, entree

    return _convertir
