"""Chargement des profils de conversion et choix automatique du profil.

Les profils sont des fichiers YAML placés dans le dossier `profils/`. Un fichier
décrit un profil, ou une revue : dans ce cas, chaque variante devient un profil
nommé « revue/variante ». La structure est décrite dans README.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ErreurProfil(Exception):
    """Profil introuvable ou mal formé."""


@dataclass
class Profil:
    nom: str
    chemin: Path
    donnees: dict[str, Any] = field(default_factory=dict)

    # ---- accès commodes -------------------------------------------------

    @property
    def description(self) -> str:
        return str(self.donnees.get("description", ""))

    @property
    def revue(self) -> str:
        return str(self.donnees.get("revue", ""))

    @property
    def issn(self) -> str:
        return str(self.donnees.get("issn", ""))

    @property
    def est_defaut(self) -> bool:
        return bool(self.donnees.get("detection", {}).get("defaut", False))

    @property
    def priorite(self) -> int:
        return int(self.donnees.get("detection", {}).get("priorite", 0))

    @property
    def mammoth(self) -> dict[str, Any]:
        return self.donnees.get("mammoth", {}) or {}

    @property
    def normalisation(self) -> dict[str, Any]:
        return self.donnees.get("normalisation", {}) or {}

    @property
    def post_traitement(self) -> dict[str, Any]:
        return self.donnees.get("post_traitement", {}) or {}

    def carte_styles(self) -> str:
        """Retourne la carte de styles Mammoth (texte), inline ou depuis un fichier."""
        carte = self.mammoth.get("carte_styles", "") or ""
        fichier = self.mammoth.get("carte_styles_fichier")
        if fichier:
            chemin = (self.chemin.parent / fichier).resolve()
            if not chemin.exists():
                raise ErreurProfil(
                    f"Profil « {self.nom} » : carte de styles introuvable : {chemin}"
                )
            carte = chemin.read_text(encoding="utf-8") + "\n" + carte
        return carte.strip()

    # ---- détection --------------------------------------------------------

    def correspond(self, nom_fichier: str, styles_presents: set[str]) -> bool:
        """Vrai si les règles de détection du profil s'appliquent au document."""
        detection = self.donnees.get("detection", {}) or {}
        if detection.get("defaut"):
            return False  # le profil par défaut n'est jamais « détecté », il sert de repli

        motif = detection.get("motif_nom_fichier")
        if motif and not re.search(motif, nom_fichier, flags=re.IGNORECASE):
            return False

        attendus = detection.get("styles_presents") or []
        if attendus:
            attendus_min = {s.lower() for s in attendus}
            presents_min = {s.lower() for s in styles_presents}
            mode = detection.get("mode_styles", "un")  # « un » ou « tous »
            if mode == "tous" and not attendus_min.issubset(presents_min):
                return False
            if mode == "un" and not (attendus_min & presents_min):
                return False

        # Un profil sans aucune règle ne doit pas capter tous les documents.
        return bool(motif or attendus)


def _fusionner(commun: dict, variante: dict) -> dict:
    """Combine les réglages communs et ceux d'une variante; la variante l'emporte."""
    resultat = dict(commun)
    for cle, valeur in variante.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def _profils_du_fichier(chemin: Path, donnees: dict) -> list[Profil]:
    """Renvoie le profil d'un fichier, ou un profil par variante pour un fichier de revue."""
    nom = str(donnees.get("nom") or chemin.stem)
    variantes = donnees.get("variantes")
    if not variantes:
        return [Profil(nom=nom, chemin=chemin, donnees=donnees)]
    profils = []
    for nom_variante, reglages in variantes.items():
        donnees_variante = _fusionner(donnees.get("commun") or {}, reglages or {})
        donnees_variante.setdefault("description", f"{donnees.get('revue', nom)} : {nom_variante}")
        donnees_variante["revue"] = donnees.get("revue", "")
        donnees_variante["issn"] = donnees.get("issn", "")
        profils.append(Profil(nom=f"{nom}/{nom_variante}", chemin=chemin, donnees=donnees_variante))
    return profils


def charger_profils(dossier: Path) -> dict[str, Profil]:
    """Charge tous les fichiers *.yaml / *.yml du dossier."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        raise ErreurProfil(f"Dossier de profils introuvable : {dossier}")

    profils: dict[str, Profil] = {}
    for chemin in sorted(list(dossier.glob("*.yaml")) + list(dossier.glob("*.yml"))):
        with chemin.open(encoding="utf-8") as f:
            donnees = yaml.safe_load(f) or {}
        if not isinstance(donnees, dict):
            raise ErreurProfil(f"Profil mal formé (doit être un dictionnaire) : {chemin}")
        for profil in _profils_du_fichier(chemin, donnees):
            if profil.nom in profils:
                raise ErreurProfil(f"Deux profils portent le nom « {profil.nom} »")
            profils[profil.nom] = profil

    if not profils:
        raise ErreurProfil(f"Aucun profil trouvé dans {dossier}")
    return profils


def choisir_profil(
    profils: dict[str, Profil],
    nom_fichier: str,
    styles_presents: set[str],
    nom_force: str | None = None,
) -> tuple[Profil, str]:
    """Choisit le profil à appliquer et explique pourquoi.

    Ordre : profil forcé > profil détecté (priorité la plus haute) > profil par défaut.
    Retourne (profil, justification).
    """
    if nom_force:
        if nom_force not in profils:
            raise ErreurProfil(
                f"Profil « {nom_force} » introuvable. Profils disponibles : "
                + ", ".join(sorted(profils))
            )
        return profils[nom_force], "choisi explicitement"

    candidats = [p for p in profils.values() if p.correspond(nom_fichier, styles_presents)]
    if candidats:
        candidats.sort(key=lambda p: (-p.priorite, p.nom))
        choisi = candidats[0]
        autres = [p.nom for p in candidats[1:]]
        raison = "détecté par ses règles"
        if autres:
            raison += f" (autres profils compatibles : {', '.join(autres)})"
        return choisi, raison

    defauts = [p for p in profils.values() if p.est_defaut]
    if not defauts:
        raise ErreurProfil(
            "Aucun profil ne correspond au document et aucun profil n'est marqué "
            "« detection.defaut: true »."
        )
    return defauts[0], "aucune règle ne correspond, profil par défaut"
