"""Enchaînement complet pour un fichier ou un lot de fichiers."""

from __future__ import annotations

import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from . import conversion, diagnostic, normalisation, pied_page, post_traitement
from .profils import ErreurProfil, Profil, choisir_profil
from .rapport import EntreeRapport

Journal = Callable[[str], None]


def message_acces_refuse(exc: PermissionError) -> str:
    """Explique un accès refusé par le système, en termes compréhensibles pour l'usager."""
    return (
        f"Accès refusé par le système : {exc.filename}. "
        "Choisissez un autre dossier de sortie, ou autorisez l'accès à ce dossier."
    )


def convertir_fichier(
    chemin_docx: Path,
    profils: dict[str, Profil],
    dossier_sortie: Path,
    nom_profil_force: str | None = None,
    journal: Journal = print,
) -> EntreeRapport:
    """Convertit un seul fichier et retourne l'entrée de rapport correspondante."""
    chemin_docx = Path(chemin_docx)
    dossier_sortie = Path(dossier_sortie)
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    entree = EntreeRapport(fichier=chemin_docx.name)

    try:
        # 1. Diagnostic
        inv = diagnostic.inventorier(chemin_docx)
        entree.styles_presents = dict(inv.styles_paragraphes)

        # 2. Choix du profil
        profil, raison = choisir_profil(profils, chemin_docx.name, inv.styles_presents, nom_profil_force)
        entree.profil, entree.justification_profil = profil.nom, raison
        journal(f"  profil « {profil.nom} » ({raison})")

        # 3. Normalisation sur une copie temporaire
        with tempfile.TemporaryDirectory(prefix="docx2html-") as tmp:
            copie = Path(tmp) / chemin_docx.name
            modifs = normalisation.normaliser(chemin_docx, copie, profil.normalisation)
            entree.normalisations = [asdict(m) for m in modifs]
            if modifs:
                journal(f"  normalisation : {len(modifs)} paragraphe(s) restylé(s)")

            # 4. Conversion Mammoth
            nom_base = chemin_docx.stem
            res_conv = conversion.convertir(copie, profil, dossier_sortie, nom_base)
        entree.messages_mammoth = res_conv.messages
        entree.images_extraites = len(res_conv.images_extraites)

        # 5. Post-traitement
        pied_html = ""
        if profil.post_traitement.get("pied_page"):
            pied_html = pied_page.pied_page_html(chemin_docx)
        res_post = post_traitement.appliquer(
            res_conv.html, profil.post_traitement, profil.chemin, chemin_docx.name, pied_html
        )
        entree.avertissements_structure = res_post.avertissements
        entree.nb_titres = res_post.nb_titres

        # 6. Écriture
        sortie = dossier_sortie / f"{nom_base}.html"
        sortie.write_text(res_post.html, encoding="utf-8")
        entree.sortie = str(sortie)
        journal(f"  -> {sortie}")

    except ErreurProfil as exc:
        entree.erreur = f"Profil : {exc}"
        journal(f"  ERREUR : {entree.erreur}")
    except PermissionError as exc:      # dossier protégé : pas besoin du détail technique
        entree.erreur = message_acces_refuse(exc)
        journal(f"  ERREUR : {entree.erreur}")
    except Exception as exc:  # noqa: BLE001 - on veut tout attraper pour le rapport
        entree.erreur = f"{type(exc).__name__}: {exc}"
        journal(f"  ERREUR : {entree.erreur}")
        journal(traceback.format_exc(limit=3))

    entree.finaliser()
    return entree


def lister_docx(chemin: Path, recursif: bool = False) -> list[Path]:
    chemin = Path(chemin)
    if chemin.is_file():
        return [chemin]
    motif = "**/*.docx" if recursif else "*.docx"
    return sorted(
        p for p in chemin.glob(motif)
        if not p.name.startswith("~$")  # fichiers de verrouillage Word
    )
