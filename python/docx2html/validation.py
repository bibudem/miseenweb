"""Validation d'un profil : le fichier est-il lisible, et chaque réglage est-il connu et bien écrit?

La validation sert aux profils déposés dans le site par une revue. Elle ne modifie rien : elle
renvoie une liste de messages. Chaque message nomme le réglage, dit ce qui ne va pas et donne
la correction. Une liste vide signifie que le profil est valide.

Le schéma ci-dessous est la liste de tous les réglages permis. Un réglage ajouté au
convertisseur doit y être ajouté aussi : un test valide les profils du répertoire et le rappelle.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import yaml

TAILLE_MAXIMALE = 200_000          # caractères : un profil est un petit fichier de texte
MOTIF_NOM = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*$")
MOTIF_ISSN = re.compile(r"\d{4}-\d{3}[\dX]$")

# ---- Sortes de valeurs -------------------------------------------------------------------
BOOLEEN, ENTIER, NOMBRE, TEXTE, LISTE_TEXTES, MOTIF = "booleen", "entier", "nombre", "texte", "liste", "motif"


def _choix(*valeurs: Any) -> tuple:
    return ("choix", valeurs)


REGLE = {
    "nom": TEXTE, "styles_source": LISTE_TEXTES, "gras": BOOLEEN, "taille_min": NOMBRE, "taille_max": NOMBRE,
    "longueur_max": ENTIER, "mots_min": ENTIER, "retrait_min": NOMBRE, "motif": MOTIF,
    "premier_seulement": BOOLEEN, "style_cible": TEXTE,
}
IMAGE_CONNUE = {"empreinte": TEXTE, "alt": TEXTE}
SECTIONS = {
    "detection": {
        "styles_presents": LISTE_TEXTES, "mode_styles": _choix("un", "tous"), "motif_nom_fichier": MOTIF,
        "priorite": ENTIER, "defaut": BOOLEEN,
    },
    "mammoth": {
        "carte_styles": TEXTE, "inclure_carte_defaut": BOOLEEN, "images": _choix("incorporees", "extraites"),
        "ignorer_images_vides": BOOLEEN, "bordures_images": BOOLEEN, "images_connues": ("liste_de", IMAGE_CONNUE),
    },
    "normalisation": {
        "active": BOOLEEN, "numeros_sous_titres": BOOLEEN, "mise_en_forme_cellules": BOOLEEN,
        "sortes_de_puces": BOOLEEN, "regles": ("liste_de", REGLE),
    },
    "post_traitement": {
        "supprimer_vides": BOOLEEN, "corriger_faux_titres": BOOLEEN, "entetes_tableaux": BOOLEEN,
        "notes_tableaux": BOOLEEN, "accessibilite_tableaux": BOOLEEN, "alignement_colonnes": BOOLEEN,
        "apparence": "apparence", "tableaux": "presentation", "tableaux_larges": ENTIER, "liens_automatiques": BOOLEEN,
        "sens_ecriture": BOOLEEN, "identifiants_titres": BOOLEEN, "decaler_niveaux": "decalage",
        "verifier_hierarchie": BOOLEEN, "avertir_h1_multiples": BOOLEEN, "gabarit_minimal": BOOLEEN,
        "table_des_matieres": BOOLEEN,
        "niveau_max_tdm": ENTIER, "titre_tdm": TEXTE, "tdm_dans_fragment": BOOLEEN,
        "classe_titre_document": TEXTE, "bandeau_avant_titre": BOOLEEN, "couleur_bandeau": BOOLEEN,
        "resume_avant_mots_cles": BOOLEEN, "pied_page": BOOLEEN, "gabarit": "gabarit", "langue": TEXTE,
    },
}
ENTETE = {"nom": TEXTE, "description": TEXTE, "revue": TEXTE, "issn": TEXTE}
RACINE_SIMPLE = {**ENTETE, **SECTIONS}
RACINE_REVUE = {**ENTETE, "commun": SECTIONS, "variantes": "variantes"}
VARIANTE = {"description": TEXTE, **SECTIONS}


# ---- Vérification d'une valeur -------------------------------------------------------------

def _valeur(valeur: Any, sorte: Any, ou: str, gabarits: Path, messages: list[str]) -> None:
    """Ajoute un message si la valeur n'est pas de la sorte attendue. « ou » nomme le réglage."""
    if valeur is None:               # réglage laissé vide : il garde sa valeur par défaut
        return
    if isinstance(sorte, dict):
        _section(valeur, sorte, ou, gabarits, messages)
    elif sorte == BOOLEEN:
        if not isinstance(valeur, bool):
            messages.append(f"{ou} : valeur « {valeur} » refusée. Écrire true ou false.")
    elif sorte == ENTIER:
        if isinstance(valeur, bool) or not isinstance(valeur, int):
            messages.append(f"{ou} : valeur « {valeur} » refusée. Écrire un nombre entier, par exemple 9.")
    elif sorte == NOMBRE:
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            messages.append(f"{ou} : valeur « {valeur} » refusée. Écrire un nombre, par exemple 14 ou 13.9.")
    elif sorte == TEXTE:
        if not isinstance(valeur, str):
            messages.append(f"{ou} : valeur « {valeur} » refusée. Écrire un texte entre guillemets droits.")
    elif sorte == LISTE_TEXTES:
        if not isinstance(valeur, list) or not all(isinstance(v, str) for v in valeur):
            messages.append(f'{ou} : écrire une liste de textes, par exemple ["Normal", "Titre 1"].')
    elif sorte == MOTIF:
        if not isinstance(valeur, str):
            messages.append(f"{ou} : écrire l'expression régulière entre guillemets droits.")
        else:
            try:
                re.compile(valeur)
            except re.error as erreur:
                messages.append(f"{ou} : expression régulière invalide ({erreur}).")
    elif sorte == "decalage":
        if valeur != "auto" and (isinstance(valeur, bool) or not isinstance(valeur, int)):
            messages.append(f"{ou} : valeur « {valeur} » refusée. Écrire auto ou un nombre entier.")
    elif sorte == "apparence":
        _parmi(valeur, sorted(f.stem for f in (gabarits / "apparence").glob("*.css")), ou, messages)
    elif sorte == "presentation":
        _parmi(valeur, sorted(f.stem for f in (gabarits / "tableaux").glob("*.css")), ou, messages)
    elif sorte == "gabarit":
        _parmi(valeur, sorted(f"../gabarits/{f.name}" for f in gabarits.glob("*.html")), ou, messages)
    elif sorte == "variantes":
        if not isinstance(valeur, dict) or not valeur:
            messages.append(f"{ou} : écrire au moins une variante, chacune avec ses réglages en retrait.")
            return
        for nom, reglages in valeur.items():
            if not MOTIF_NOM.match(str(nom)):
                messages.append(f"{ou} > {nom} : nom de variante refusé. {_REGLE_DE_NOM}")
            _section(reglages or {}, VARIANTE, f"{ou} > {nom}", gabarits, messages)
    elif sorte[0] == "choix":
        _parmi(valeur, list(sorte[1]), ou, messages)
    elif sorte[0] == "liste_de":
        if not isinstance(valeur, list):
            messages.append(f"{ou} : écrire une liste, un élément par ligne commençant par un tiret.")
            return
        for rang, element in enumerate(valeur, start=1):
            _section(element, sorte[1], f"{ou} > élément {rang}", gabarits, messages)


_REGLE_DE_NOM = "Écrire des minuscules sans accent, des chiffres et des traits d'union, par exemple « ma-publication »."


def _parmi(valeur: Any, permises: list, ou: str, messages: list[str]) -> None:
    if valeur not in permises:
        messages.append(f"{ou} : valeur « {valeur} » refusée. Valeurs permises : {', '.join(map(str, permises))}.")


def _section(valeur: Any, schema: dict, ou: str, gabarits: Path, messages: list[str]) -> None:
    """Vérifie un groupe de réglages : chaque nom doit être connu, chaque valeur de la bonne sorte."""
    if not isinstance(valeur, dict):
        messages.append(f"{ou or 'Profil'} : écrire les réglages en retrait, sous la forme « nom: valeur ».")
        return
    for cle, contenu in valeur.items():
        chemin = f"{ou} > {cle}" if ou else str(cle)
        if cle not in schema:
            voisins = difflib.get_close_matches(str(cle), list(schema), n=1)
            suite = f" Réglage voisin : « {voisins[0]} »." if voisins else ""
            messages.append(f"{chemin} : réglage inconnu.{suite}")
        else:
            _valeur(contenu, schema[cle], chemin, gabarits, messages)


# ---- Vérification d'un profil ----------------------------------------------------------------

def _a_une_regle(detection: Any) -> bool:
    return isinstance(detection, dict) and bool(detection.get("motif_nom_fichier") or detection.get("styles_presents"))


def valider(donnees: Any, gabarits: Path, noms_reserves: frozenset[str] | set[str] = frozenset(),
            depose: bool = True) -> list[str]:
    """Renvoie les messages d'erreur d'un profil déjà lu. Liste vide : profil valide.

    « noms_reserves » : noms des profils du catalogue, qu'un profil déposé ne peut pas reprendre.
    « depose » : faux pour un profil du répertoire, qui peut être le profil par défaut.
    """
    messages: list[str] = []
    if not isinstance(donnees, dict):
        return ["Profil : le fichier doit contenir des réglages sous la forme « nom: valeur »."]
    revue = "variantes" in donnees or "commun" in donnees
    _section(donnees, RACINE_REVUE if revue else RACINE_SIMPLE, "", gabarits, messages)

    nom = donnees.get("nom")
    if not nom:
        messages.append("nom : réglage obligatoire. Il identifie le profil, par exemple « ma-publication ».")
    elif isinstance(nom, str):
        if not MOTIF_NOM.match(nom):
            messages.append(f"nom : valeur « {nom} » refusée. {_REGLE_DE_NOM}")
        elif nom in noms_reserves:
            messages.append(f"nom : « {nom} » est déjà le nom d'un profil du site. Choisir un autre nom.")
    issn = donnees.get("issn")
    if isinstance(issn, str) and issn and not MOTIF_ISSN.match(issn):
        messages.append(f"issn : valeur « {issn} » refusée. Écrire huit caractères en deux groupes, "
                        'par exemple "1234-5678".')

    # Reconnaissance : sans ISSN, chaque profil doit avoir une règle, sinon il ne s'applique jamais seul
    if revue:
        variantes = donnees.get("variantes") if isinstance(donnees.get("variantes"), dict) else {}
        if "variantes" not in donnees:
            messages.append("variantes : réglage obligatoire quand « commun » est présent.")
        commun = donnees.get("commun") if isinstance(donnees.get("commun"), dict) else {}
        groupes = [(f"variantes > {n} > detection", _fusion_detection(commun, v)) for n, v in variantes.items()]
    else:
        groupes = [("detection", donnees.get("detection"))]
    for ou, detection in groupes:
        if depose and isinstance(detection, dict) and detection.get("defaut"):
            messages.append(f"{ou} > defaut : réglage réservé au profil par défaut du site. Le retirer.")
        elif not issn and not _a_une_regle(detection) and not (not depose and isinstance(detection, dict)
                                                               and detection.get("defaut")):
            messages.append(f"{ou} : aucune règle de reconnaissance. Ajouter « motif_nom_fichier » ou "
                            "« styles_presents », ou inscrire l'ISSN de la publication dans « issn ».")
    return messages


def _fusion_detection(commun: dict, variante: Any) -> dict:
    """Règles de reconnaissance d'une variante : celles de « commun », remplacées par les siennes."""
    propre = variante.get("detection") if isinstance(variante, dict) else None
    return {**(commun.get("detection") or {}), **(propre if isinstance(propre, dict) else {})}


def valider_texte(texte: str, gabarits: Path, noms_reserves: frozenset[str] | set[str] = frozenset(),
                  depose: bool = True) -> tuple[dict | None, list[str]]:
    """Lit le texte d'un fichier de profil et le valide. Renvoie (réglages ou None, messages)."""
    if len(texte) > TAILLE_MAXIMALE:
        return None, ["Fichier trop volumineux pour un profil. Vérifier que le fichier déposé est bien un profil."]
    try:
        donnees = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        marque = getattr(erreur, "problem_mark", None)
        ou = f"Ligne {marque.line + 1}" if marque is not None else "Fichier"
        return None, [f"{ou} : le fichier ne peut pas être lu. Vérifier les retraits, les deux-points "
                      "et les guillemets autour de cette ligne."]
    if donnees is None:
        return None, ["Fichier vide. Vérifier que le fichier déposé est bien un profil."]
    messages = valider(donnees, gabarits, noms_reserves, depose)
    return (donnees if not messages else None), messages
