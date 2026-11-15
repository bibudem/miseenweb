"""Normalisation d'un document Word avant conversion (avec python-docx).

Applique les règles du profil : un paragraphe qui remplit toutes les conditions
d'une règle (style, gras, taille, longueur, nombre de mots, retrait, motif de texte) reçoit le
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
          mots_min: 10                    # nombre de mots
          retrait_min: 20                 # retrait à gauche, en points
          premier_seulement: true         # la règle ne sert qu'une fois par document
          motif: "^(Chapitre|Partie)\\s+\\d+"   # regex optionnelle
          style_cible: "Heading 1"

Réglage à part, dans la même section :

    normalisation:
      numeros_sous_titres: true   # écrit en texte le numéro des sous-titres numérotés

Un sous-titre numéroté est un paragraphe de liste entièrement en gras. Mammoth en ferait une
liste d'un seul élément, qui recommence à 1 : son numéro est donc écrit dans le texte.

    normalisation:
      mise_en_forme_cellules: true   # conserve le retrait et le centrage dans les tableaux

Dans un tableau, le retrait d'un paragraphe montre qu'une ligne dépend de la précédente.
Mammoth ne transmet ni le retrait ni l'alignement : le paragraphe reçoit donc un style
(« Cellule retrait 1 », « Cellule centrée ») que la carte de styles du profil change en classe.

    normalisation:
      sortes_de_puces: true   # conserve les puces particulières : coche, losange, tiret…

Dans une liste, des puces différentes distinguent des groupes d'éléments. Mammoth donne la même
puce à tous : un élément à puce particulière reçoit donc un style (« Puce coche », « Puce tiret »)
que la carte de styles du profil change en liste d'une classe donnée.
"""

from __future__ import annotations

import copy
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .diagnostic import analyser_paragraphe


@dataclass
class Modification:
    index: int
    regle: str
    style_avant: str
    style_apres: str
    texte: str


def _extrait(texte: str, longueur: int = 80) -> str:
    """Début d'un texte, pour les rapports; des points de suspension signalent une coupure."""
    texte = texte.strip()
    return texte if len(texte) <= longueur else texte[: longueur - 1].rstrip() + "…"


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
    mots_min = regle.get("mots_min")
    if mots_min is not None and len(info.texte.split()) < int(mots_min):
        return False
    retrait_min = regle.get("retrait_min")
    if retrait_min is not None and info.retrait_pt < float(retrait_min):
        return False
    motif = regle.get("motif")
    if motif and not re.search(motif, info.texte):
        return False
    return True


def _en_lettres(n: int) -> str:
    """1 -> a, 26 -> z, 27 -> aa."""
    lettres = ""
    while n > 0:
        n, reste = divmod(n - 1, 26)
        lettres = chr(ord("a") + reste) + lettres
    return lettres


def _en_romain(n: int) -> str:
    valeurs = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
               (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    romain = ""
    for valeur, symbole in valeurs:
        while n >= valeur:
            romain += symbole
            n -= valeur
    return romain


def _formater_numero(n: int, format_word: str) -> str | None:
    """Écrit un numéro dans le format de Word; None si le format n'est pas un numéro (puce…)."""
    formats = {
        "decimal": str,
        "decimalZero": lambda v: f"{v:02d}",
        "lowerLetter": _en_lettres,
        "upperLetter": lambda v: _en_lettres(v).upper(),
        "lowerRoman": _en_romain,
        "upperRoman": lambda v: _en_romain(v).upper(),
    }
    return formats[format_word](n) if format_word in formats else None


def _listes_du_document(doc) -> dict[str, tuple[str, dict, dict]]:
    """Décrit chaque liste du document : (clé de son compteur, ses niveaux, ses départs forcés).

    Un niveau est (format, texte du numéro, valeur de départ). Deux listes fondées sur le
    même modèle partagent leur compteur, sauf si l'une impose un nouveau départ.
    """
    valeur = qn("w:val")
    numerotation = doc.part.numbering_part.element
    modeles: dict[str, dict] = {}
    for modele in numerotation.findall(qn("w:abstractNum")):
        niveaux = {}
        for niveau in modele.findall(qn("w:lvl")):
            format_word = niveau.find(qn("w:numFmt"))
            texte = niveau.find(qn("w:lvlText"))
            depart = niveau.find(qn("w:start"))
            niveaux[int(niveau.get(qn("w:ilvl")))] = (
                format_word.get(valeur) if format_word is not None else "decimal",
                texte.get(valeur) if texte is not None else "",
                int(depart.get(valeur)) if depart is not None else 1,
            )
        modeles[modele.get(qn("w:abstractNumId"))] = niveaux

    listes = {}
    for liste in numerotation.findall(qn("w:num")):
        identifiant = liste.get(qn("w:numId"))
        modele = liste.find(qn("w:abstractNumId")).get(valeur)
        departs = {
            int(o.get(qn("w:ilvl"))): int(o.find(qn("w:startOverride")).get(valeur))
            for o in liste.findall(qn("w:lvlOverride"))
            if o.find(qn("w:startOverride")) is not None
        }
        listes[identifiant] = (f"liste-{identifiant}" if departs else f"modele-{modele}", modeles.get(modele, {}), departs)
    return listes


def _texte_du_numero(niveaux: dict, valeurs: dict, niveau: int) -> str | None:
    """Compose le numéro d'un paragraphe (« 2) », « 1.3 ») à partir du texte prévu par Word."""
    texte = niveaux[niveau][1]
    for n in range(niveau + 1):
        if f"%{n + 1}" not in texte:
            continue
        format_word, _, depart = niveaux.get(n, ("decimal", "", 1))
        ecrit = _formater_numero(valeurs.get(n, depart), format_word)
        if ecrit is None:
            return None
        texte = texte.replace(f"%{n + 1}", ecrit)
    return texte.strip() if "%" not in texte and texte.strip() else None


def _ecrire_numeros_sous_titres(doc) -> list[Modification]:
    """Écrit en texte le numéro des sous-titres numérotés, et les sort de leur liste.

    Tous les paragraphes numérotés sont comptés, pour que chaque numéro soit celui que Word
    affiche; seuls ceux qui sont entièrement en gras sont modifiés.
    """
    corps = doc.element.body
    if corps.find(".//" + qn("w:numPr")) is None:
        return []
    listes = _listes_du_document(doc)
    du_corps = {p._p: (i, p) for i, p in enumerate(doc.paragraphs)}
    compteurs: dict[str, dict[int, int]] = {}
    modifications: list[Modification] = []

    for xml in corps.iter(qn("w:p")):
        numerotation = xml.pPr.numPr if xml.pPr is not None else None
        if numerotation is None or numerotation.numId is None:
            continue
        cle, niveaux, departs = listes.get(str(numerotation.numId.val), ("", {}, {}))
        niveau = numerotation.ilvl.val if numerotation.ilvl is not None else 0
        if niveau not in niveaux:
            continue
        valeurs = compteurs.setdefault(cle, {})
        valeurs[niveau] = valeurs[niveau] + 1 if niveau in valeurs else departs.get(niveau, niveaux[niveau][2])
        for plus_profond in [n for n in valeurs if n > niveau]:   # un niveau repart sous un nouveau parent
            del valeurs[plus_profond]

        if xml not in du_corps:
            continue
        index, paragraphe = du_corps[xml]
        info = analyser_paragraphe(index, paragraphe)
        if not info.texte or not info.tout_gras or not paragraphe.runs:
            continue
        numero = _texte_du_numero(niveaux, valeurs, niveau)
        if numero is None:
            continue

        # Le numéro devient un segment de texte, avec la mise en forme du premier segment
        premier = paragraphe.runs[0]._r
        segment = copy.deepcopy(premier)
        for enfant in list(segment):
            if enfant.tag != qn("w:rPr"):
                segment.remove(enfant)
        texte = OxmlElement("w:t")
        texte.text = f"{numero} "
        texte.set(qn("xml:space"), "preserve")
        segment.append(texte)
        premier.addprevious(segment)
        xml.pPr.remove(numerotation)
        modifications.append(
            Modification(index=index, regle="numero-sous-titre", style_avant=info.style_nom,
                         style_apres=info.style_nom, texte=_extrait(f"{numero} {info.texte}"))
        )
    return modifications


RETRAIT_PAR_NIVEAU = 720     # twips : un demi-pouce, le pas de retrait habituel de Word
NIVEAUX_DE_RETRAIT = 3
ESPACES_PAR_NIVEAU = 4       # un retrait fait à la main : quatre espaces


def _style_de_cellule(doc, nom: str):
    """Renvoie le style de paragraphe `nom`, créé dans la copie temporaire s'il n'existe pas."""
    if nom not in {s.name for s in doc.styles}:
        doc.styles.add_style(nom, WD_STYLE_TYPE.PARAGRAPH)
    return nom


def _marquer_cellules(doc) -> int:
    """Donne un style aux paragraphes de tableau en retrait ou centrés. Renvoie leur nombre.

    Seuls les paragraphes de style Normal sont touchés : un style choisi dans Word est conservé.
    """
    n = 0
    for cellule in doc.element.body.iter(qn("w:tc")):
        for xml in cellule.findall(qn("w:p")):
            proprietes = xml.pPr
            style = proprietes.find(qn("w:pStyle")) if proprietes is not None else None
            if proprietes is None or style is not None or not "".join(xml.itertext()).strip():
                continue
            retrait = proprietes.find(qn("w:ind"))
            gauche = retrait.get(qn("w:left")) or retrait.get(qn("w:start")) if retrait is not None else None
            niveau = round(int(gauche) / RETRAIT_PAR_NIVEAU) if gauche and gauche.lstrip("-").isdigit() else 0
            if niveau <= 0:     # retrait fait avec des espaces : une page web ne les affiche pas
                texte = "".join(xml.itertext())
                espaces = len(texte) - len(texte.lstrip(" \u00a0"))
                niveau = max(1, round(espaces / ESPACES_PAR_NIVEAU)) if espaces >= 2 else 0
            niveau = min(NIVEAUX_DE_RETRAIT, niveau)
            alignement = proprietes.find(qn("w:jc"))
            if niveau > 0:
                nom = f"Cellule retrait {niveau}"
            elif alignement is not None and alignement.get(qn("w:val")) == "center":
                nom = "Cellule centrée"
            else:
                continue
            Paragraph(xml, doc).style = _style_de_cellule(doc, nom)     # doc : pour retrouver le style
            n += 1
    return n


# Puces particulières, par police et caractère. Les polices de symboles de Word placent leurs
# caractères dans une zone privée d'Unicode (U+F000 à U+F0FF). La puce ronde ordinaire n'y est pas :
# elle reste la puce par défaut.
PUCES_PARTICULIERES = {
    ("wingdings", 0xF0FC): "coche",
    ("wingdings", 0xF076): "losange",
    ("wingdings", 0xF0A7): "carré",
    ("wingdings", 0xF0D8): "flèche",
    ("symbol", 0xF02D): "tiret",
}
TIRETS = {"-", "–", "—"}


def _sortes_de_puces(doc) -> dict[tuple[str, int], str]:
    """Associe à chaque liste à puce particulière sa sorte : {(numéro de liste, niveau): « coche »}."""
    valeur = qn("w:val")
    numerotation = doc.part.numbering_part.element
    modeles: dict[str, dict[int, str]] = {}
    for modele in numerotation.findall(qn("w:abstractNum")):
        niveaux = {}
        for niveau in modele.findall(qn("w:lvl")):
            format_word = niveau.find(qn("w:numFmt"))
            texte = niveau.find(qn("w:lvlText"))
            police = niveau.find(qn("w:rPr") + "/" + qn("w:rFonts"))
            caractere = (texte.get(valeur) or "") if texte is not None else ""
            if format_word is None or format_word.get(valeur) != "bullet" or len(caractere) != 1:
                continue
            nom_police = (police.get(qn("w:ascii")) or "").lower() if police is not None else ""
            sorte = "tiret" if caractere in TIRETS else PUCES_PARTICULIERES.get((nom_police, ord(caractere)))
            if sorte:
                niveaux[int(niveau.get(qn("w:ilvl")))] = sorte
        modeles[modele.get(qn("w:abstractNumId"))] = niveaux
    sortes = {}
    for liste in numerotation.findall(qn("w:num")):
        for niveau, sorte in modeles.get(liste.find(qn("w:abstractNumId")).get(valeur), {}).items():
            sortes[(liste.get(qn("w:numId")), niveau)] = sorte
    return sortes


def _marquer_puces(doc) -> int:
    """Donne un style aux éléments de liste à puce particulière. Renvoie leur nombre."""
    corps = doc.element.body
    if corps.find(".//" + qn("w:numPr")) is None:
        return 0
    sortes = _sortes_de_puces(doc)
    n = 0
    for xml in corps.iter(qn("w:p")):
        numerotation = xml.pPr.numPr if xml.pPr is not None else None
        if numerotation is None or numerotation.numId is None:
            continue
        niveau = numerotation.ilvl.val if numerotation.ilvl is not None else 0
        sorte = sortes.get((str(numerotation.numId.val), niveau))
        if sorte:
            Paragraph(xml, doc).style = _style_de_cellule(doc, f"Puce {sorte}")
            n += 1
    return n


def normaliser(source: Path, destination: Path, config: dict) -> list[Modification]:
    """Copie `source` vers `destination` en appliquant les règles.

    Retourne la liste des modifications faites (vide si rien à faire).
    """
    source, destination = Path(source), Path(destination)
    regles = (config or {}).get("regles") or []
    numeros = bool((config or {}).get("numeros_sous_titres"))
    cellules = bool((config or {}).get("mise_en_forme_cellules"))
    puces = bool((config or {}).get("sortes_de_puces"))
    if not (config or {}).get("active") or not (regles or numeros or cellules or puces):
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
                    texte=_extrait(info.texte),
                )
            )
            break  # première règle qui s'applique

    if numeros:     # après les règles, qui tiennent compte de la numérotation
        modifications.extend(_ecrire_numeros_sous_titres(doc))
    if cellules:
        _marquer_cellules(doc)
    if puces:       # après l'écriture des numéros, qui retire des paragraphes de leur liste
        _marquer_puces(doc)

    doc.save(str(destination))
    return modifications
