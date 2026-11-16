"""Outils communs aux tests du convertisseur.

Les tests créent leurs documents Word avec python-docx : aucun document réel n'est conservé
dans le répertoire GitHub. Chaque document est écrit dans un dossier temporaire, effacé par pytest.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True      # aucun dossier __pycache__ dans python/ ni dans tests/

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


@pytest.fixture
def pont(tmp_path, monkeypatch):
    """Le pont entre la page et le convertisseur, avec ses dossiers dans un dossier temporaire.

    Renvoie une fonction : elle dépose un document, le convertit comme le fait le site et
    renvoie le résultat affiché à l'utilisateur (statut, profil, remarques).
    « profil » force un profil, comme le fait l'utilisateur quand il choisit le type de document.
    """
    import importlib
    import json

    monkeypatch.setenv("MISEENWEB_RACINE", str(tmp_path))
    monkeypatch.setenv("MISEENWEB_APP", str(RACINE / "python"))
    sys.modules.pop("pont", None)                 # le pont lit ses dossiers à l'importation
    module = importlib.import_module("pont")
    module.ENTREE.mkdir()

    def _convertir(document, nom="essai.docx", profil=""):
        document.save(module.ENTREE / nom)
        module.lire(nom)
        resultats = json.loads(module.convertir([{"nom": nom, "profil": profil}], module.AUTO, lambda m: None))
        assert not resultats[0]["erreur"], resultats[0]["erreur"]
        return resultats[0]

    yield _convertir
    sys.modules.pop("pont", None)


@pytest.fixture
def module_pont(pont):
    """Le module du pont lui-même, pour appeler ses autres fonctions (catalogue, dépôt d'un profil)."""
    return sys.modules["pont"]
