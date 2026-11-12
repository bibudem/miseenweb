"""Inventaire des styles d'un document Word (avec python-docx).

Sert à deux choses :
  1. alimenter la détection automatique du profil;
  2. aider la personne qui rédige un profil à connaître les noms de styles
     exacts tels qu'ils sont enregistrés dans le fichier.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.shared import Pt


@dataclass
class ParagrapheInfo:
    index: int
    style_nom: str
    style_id: str
    texte: str
    tout_gras: bool
    taille_pt: float | None
    longueur: int
    retrait_pt: float = 0.0


@dataclass
class Inventaire:
    fichier: Path
    nb_paragraphes: int = 0
    styles_paragraphes: Counter = field(default_factory=Counter)
    identifiants_styles: dict[str, str] = field(default_factory=dict)  # nom -> style_id
    nb_tableaux: int = 0
    nb_images: int = 0
    titres_manuels_suspects: list[ParagrapheInfo] = field(default_factory=list)

    @property
    def styles_presents(self) -> set[str]:
        return set(self.styles_paragraphes)

    @property
    def styles_titres(self) -> list[str]:
        """Styles dont le nom évoque un titre (Heading n, Title, Titre n...)."""
        return sorted(
            s for s in self.styles_paragraphes
            if s.lower().startswith(("heading", "title", "titre"))
        )


def _taille_effective_pt(paragraphe, run) -> float | None:
    """Taille de police du segment, ou de son style, ou du style du paragraphe."""
    for candidat in (run.font.size, getattr(run.style, "font", None) and run.style.font.size):
        if candidat is not None:
            return candidat.pt
    style = paragraphe.style
    while style is not None:
        if style.font is not None and style.font.size is not None:
            return style.font.size.pt
        style = style.base_style
    return None


def _est_gras(paragraphe, run) -> bool:
    if run.bold is not None:
        return bool(run.bold)
    style = paragraphe.style
    while style is not None:
        if style.font is not None and style.font.bold is not None:
            return bool(style.font.bold)
        style = style.base_style
    return False


def _retrait_gauche_pt(paragraphe) -> float:
    """Retrait à gauche d'un bloc de texte, en points; 0 pour un élément de liste."""
    proprietes = paragraphe._p.pPr
    premiere_ligne = paragraphe.paragraph_format.first_line_indent
    if (proprietes is not None and proprietes.numPr is not None) or (
        premiere_ligne is not None and premiere_ligne < 0
    ):
        return 0.0      # une puce ou un numéro crée aussi un retrait
    retrait = paragraphe.paragraph_format.left_indent
    if retrait is not None:
        return retrait.pt
    style = paragraphe.style
    while style is not None:
        if style.paragraph_format.left_indent is not None:
            return style.paragraph_format.left_indent.pt
        style = style.base_style
    return 0.0


def analyser_paragraphe(index: int, paragraphe) -> ParagrapheInfo:
    runs = [r for r in paragraphe.runs if r.text.strip()]
    texte = paragraphe.text.strip()
    tout_gras = bool(runs) and all(_est_gras(paragraphe, r) for r in runs)
    tailles = [t for t in (_taille_effective_pt(paragraphe, r) for r in runs) if t is not None]
    taille = max(tailles) if tailles else None
    style = paragraphe.style
    return ParagrapheInfo(
        index=index,
        style_nom=style.name if style is not None else "",
        style_id=style.style_id if style is not None else "",
        texte=texte,
        tout_gras=tout_gras,
        taille_pt=taille,
        longueur=len(texte),
        retrait_pt=_retrait_gauche_pt(paragraphe),
    )


def inventorier(chemin: Path, seuil_taille_pt: float = 13.0, longueur_max: int = 120) -> Inventaire:
    """Parcourt le document et retourne son inventaire.

    Les « titres manuels suspects » sont des paragraphes de style non-titre,
    entièrement en gras, d'une taille >= seuil et d'une longueur <= longueur_max.
    Ils signalent des documents dont la structure n'est pas portée par les styles.
    """
    chemin = Path(chemin)
    doc = Document(str(chemin))
    inv = Inventaire(fichier=chemin)

    for i, p in enumerate(doc.paragraphs):
        info = analyser_paragraphe(i, p)
        if not info.texte:
            continue
        inv.nb_paragraphes += 1
        inv.styles_paragraphes[info.style_nom] += 1
        inv.identifiants_styles.setdefault(info.style_nom, info.style_id)
        est_style_titre = info.style_nom.lower().startswith(("heading", "title", "titre"))
        if (
            not est_style_titre
            and info.tout_gras
            and info.taille_pt is not None
            and info.taille_pt >= seuil_taille_pt
            and info.longueur <= longueur_max
        ):
            inv.titres_manuels_suspects.append(info)

    inv.nb_tableaux = len(doc.tables)
    inv.nb_images = len(doc.inline_shapes)
    return inv


def formater_inventaire(inv: Inventaire) -> str:
    """Rendu texte pour la commande `diagnostic`."""
    lignes = [
        f"Fichier : {inv.fichier}",
        f"Paragraphes non vides : {inv.nb_paragraphes}   Tableaux : {inv.nb_tableaux}   Images : {inv.nb_images}",
        "",
        "Styles de paragraphe utilisés (nom enregistré | identifiant | occurrences) :",
    ]
    for nom, n in inv.styles_paragraphes.most_common():
        lignes.append(f"  {nom:<32} {inv.identifiants_styles.get(nom, ''):<24} {n}")
    lignes.append("")
    if inv.styles_titres:
        lignes.append("Styles de titre détectés : " + ", ".join(inv.styles_titres))
    else:
        lignes.append("Aucun style de titre détecté.")
    if inv.titres_manuels_suspects:
        lignes.append("")
        lignes.append(
            f"Titres faits à la main (gras, >= 13 pt, style non-titre) : {len(inv.titres_manuels_suspects)}"
        )
        for p in inv.titres_manuels_suspects[:15]:
            taille = f"{p.taille_pt:.0f} pt" if p.taille_pt else "?"
            lignes.append(f"  [{p.style_nom}, {taille}] {p.texte[:70]}")
        if len(inv.titres_manuels_suspects) > 15:
            lignes.append(f"  ... et {len(inv.titres_manuels_suspects) - 15} autres")
    return "\n".join(lignes)
