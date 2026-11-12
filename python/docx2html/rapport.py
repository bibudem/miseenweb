"""Rapport de conversion (Markdown + JSON) pour un lot de fichiers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class EntreeRapport:
    fichier: str
    sortie: str = ""
    profil: str = ""
    justification_profil: str = ""
    statut: str = "ok"                     # ok | avertissements | erreur
    erreur: str = ""
    styles_presents: dict[str, int] = field(default_factory=dict)
    normalisations: list[dict] = field(default_factory=list)
    messages_mammoth: list[dict] = field(default_factory=list)
    avertissements_structure: list[str] = field(default_factory=list)
    nb_titres: dict[str, int] = field(default_factory=dict)
    images_extraites: int = 0

    def finaliser(self) -> None:
        if self.erreur:
            self.statut = "erreur"
        elif self.messages_mammoth or self.avertissements_structure:
            self.statut = "avertissements"
        else:
            self.statut = "ok"


def ecrire_rapport(entrees: list[EntreeRapport], dossier: Path, nom: str = "rapport-conversion") -> tuple[Path, Path]:
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M")

    chemin_json = dossier / f"{nom}.json"
    chemin_json.write_text(
        json.dumps({"genere_le": horodatage, "fichiers": [asdict(e) for e in entrees]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lignes = [f"# Rapport de conversion — {horodatage}", ""]
    nb = {"ok": 0, "avertissements": 0, "erreur": 0}
    for e in entrees:
        nb[e.statut] = nb.get(e.statut, 0) + 1
    lignes.append(
        f"{len(entrees)} fichier(s) : {nb['ok']} sans remarque, "
        f"{nb['avertissements']} avec avertissements, {nb['erreur']} en erreur."
    )
    lignes.append("")

    for e in entrees:
        pastille = {"ok": "✔", "avertissements": "⚠", "erreur": "✖"}[e.statut]
        lignes.append(f"## {pastille} {e.fichier}")
        lignes.append("")
        lignes.append(f"- Profil : **{e.profil}** ({e.justification_profil})")
        if e.sortie:
            lignes.append(f"- Sortie : `{e.sortie}`")
        if e.nb_titres:
            lignes.append("- Titres : " + ", ".join(f"{k} × {v}" for k, v in e.nb_titres.items()))
        if e.images_extraites:
            lignes.append(f"- Images extraites : {e.images_extraites}")
        if e.erreur:
            lignes.append(f"- **Erreur** : {e.erreur}")
        if e.normalisations:
            lignes.append(f"- Normalisation : {len(e.normalisations)} paragraphe(s) restylé(s)")
            for m in e.normalisations[:10]:
                lignes.append(f"  - [{m['regle']}] {m['style_avant']} → {m['style_apres']} : « {m['texte']} »")
            if len(e.normalisations) > 10:
                lignes.append(f"  - … et {len(e.normalisations) - 10} autres")
        if e.messages_mammoth:
            lignes.append(f"- Messages Mammoth ({len(e.messages_mammoth)}) :")
            # regrouper les messages identiques
            comptes: dict[str, int] = {}
            for m in e.messages_mammoth:
                cle = f"{m['type']} : {m['message']}"
                comptes[cle] = comptes.get(cle, 0) + 1
            for cle, n in comptes.items():
                suffixe = f" (× {n})" if n > 1 else ""
                lignes.append(f"  - {cle}{suffixe}")
        if e.avertissements_structure:
            lignes.append("- Structure :")
            for a in e.avertissements_structure:
                lignes.append(f"  - {a}")
        lignes.append("")

    chemin_md = dossier / f"{nom}.md"
    chemin_md.write_text("\n".join(lignes), encoding="utf-8")
    return chemin_md, chemin_json
