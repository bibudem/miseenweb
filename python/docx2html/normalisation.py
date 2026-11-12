"""Normalisation d'un document Word avant conversion (avec python-docx).

Applique les règles du profil : un paragraphe qui remplit toutes les conditions
d'une règle (style, gras, taille, longueur, retrait, motif de texte) reçoit le
style cible, par exemple un style de titre ou de citation. Le fichier source
n'est jamais modifié; le travail se fait sur une copie temporaire.

Structure d'une règle dans le profil :

    normalisation:
      active: true
      regles:
        - nom: titre-niveau-1
          styles_source: ["Normal"]      # styles concernés (défaut : Normal)
          gras: true                      # tous les segments en gras
          taille_min: 16                  # points (aussi : taille_max)
          longueur_max: 100               # caractères
          retrait_min: 20                 # retrait à gauche, en points
          premier_seulement: true         # la règle ne sert qu'une fois par document
          motif: "^(Chapitre|Partie)\\s+\\d+"   # regex optionnelle
          style_cible: "Heading 1"
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE

from .diagnostic import analyser_paragraphe


@dataclass
class Modification:
    index: int
    regle: str
    style_avant: str
    style_apres: str
    texte: str


def _regle_s_applique(regle: dict, info) -> bool:
    styles_source = regle.get("styles_source") or ["Normal"]
    if info.style_nom.lower() not in {s.lower() for s in styles_source}:
        return False
    if regle.get("gras") and not info.tout_gras:
        return False
    taille_min = regle.get("taille_min")
    if taille_min is not None:
        if info.taille_pt is None or info.taille_pt < float(taille_min):
            return False
    taille_max = regle.get("taille_max")
    if taille_max is not None:
        if info.taille_pt is None or info.taille_pt > float(taille_max):
            return False
    longueur_max = regle.get("longueur_max")
    if longueur_max is not None and info.longueur > int(longueur_max):
        return False
    retrait_min = regle.get("retrait_min")
    if retrait_min is not None and info.retrait_pt < float(retrait_min):
        return False
    motif = regle.get("motif")
    if motif and not re.search(motif, info.texte):
        return False
    return True


def normaliser(source: Path, destination: Path, config: dict) -> list[Modification]:
    """Copie `source` vers `destination` en appliquant les règles.

    Retourne la liste des modifications faites (vide si rien à faire).
    """
    source, destination = Path(source), Path(destination)
    regles = (config or {}).get("regles") or []
    if not (config or {}).get("active") or not regles:
        shutil.copyfile(source, destination)
        return []

    doc = Document(str(source))
    modifications: list[Modification] = []
    noms_styles = {s.name for s in doc.styles}
    deja_appliquees: set[str] = set()   # règles « premier_seulement » déjà utilisées

    for i, p in enumerate(doc.paragraphs):
        info = analyser_paragraphe(i, p)
        if not info.texte:
            continue
        for regle in regles:
            if not _regle_s_applique(regle, info):
                continue
            nom_regle = str(regle.get("nom", "?"))
            if regle.get("premier_seulement"):
                if nom_regle in deja_appliquees:
                    continue
                deja_appliquees.add(nom_regle)
            cible = regle.get("style_cible")
            if not cible:
                continue
            if cible not in noms_styles:
                # Un document ne définit que les styles qu'il utilise : on crée le style
                # manquant, dans la copie temporaire seulement.
                doc.styles.add_style(cible, WD_STYLE_TYPE.PARAGRAPH, builtin=True)
                noms_styles.add(cible)
            avant = info.style_nom
            p.style = cible
            modifications.append(
                Modification(
                    index=i,
                    regle=str(regle.get("nom", "?")),
                    style_avant=avant,
                    style_apres=p.style.name,
                    texte=info.texte[:80],
                )
            )
            break  # première règle qui s'applique

    doc.save(str(destination))
    return modifications
