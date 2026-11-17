"""Générateur de profil : écrit le fichier de profil d'une publication d'après les réponses de l'assistant.

Le générateur ne décide rien : il transcrit. Le texte produit est un profil comme les autres.
Il passe par la même validation qu'un profil déposé (validation.py) avant d'être utilisé.

Réponses attendues :

    {
        "revue": "Ma revue",
        "issn": "1234-5678",            # ou ""
        "mot_nom_fichier": "",          # mot attendu dans le nom des fichiers, ou ""
        "titres": [                     # un élément par regroupement de paragraphes retenu
            {"style": "Intertitre", "role": "section"},                         # style créé par la publication
            {"taille": 16, "styles": ["Normal"], "role": "titre-article"},      # texte en gras de cette taille
            {"taille": 12, "styles": ["Normal"], "role": "section"},
        ],
        "images": [                     # images communes aux articles
            {"empreinte": "ab12…", "texte": "Ma revue"},
            {"empreinte": "cd34…", "texte": ""},      # texte vide : image décorative
        ],
        "apparence": "article",         # ou "document"
        "tableaux": "apa",              # ou "bordures", "chicago"
        "bandeau": True,
        "pied_page": True,
    }

« style », « taille », « styles » et « empreinte » viennent tels quels du relevé de analyse.py.
"""

from __future__ import annotations

import json
import re
import unicodedata

# Rôle choisi dans l'assistant -> style Word donné au paragraphe avant la conversion.
# Avec « decaler_niveaux: auto », Title devient h1, Heading 1 devient h2, Heading 2 devient h3.
STYLES_DES_ROLES = {"titre-article": "Title", "section": "Heading 1", "sous-titre": "Heading 2"}
LONGUEUR_MAX_TITRE = 120      # caractères : au-delà, un paragraphe en gras n'est pas un titre de section

CARTE_STYLES = """\
    p[style-name='Title'] => h1.titre-document:fresh
    p[style-name='Subtitle'] => p.sous-titre:fresh
    p[style-name='Quote'] => blockquote:fresh
    p[style-name='Intense Quote'] => blockquote.mise-en-relief:fresh
    p[style-name='Caption'] => figcaption:fresh
    p[style-name='EndNote Bibliography'] => p.reference:fresh
    p[style-name='Bibliography'] => p.reference:fresh
    p[style-name='References'] => p.reference:fresh
    r[style-name='Strong'] => strong
    u => em
"""


def nom_de_profil(revue: str) -> str:
    """Nom de fichier tiré du nom de la revue : minuscules sans accent, mots joints par un trait d'union."""
    sans_accent = unicodedata.normalize("NFKD", revue).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sans_accent.lower()).strip("-") or "publication"


def _texte(valeur: str) -> str:
    """Écrit un texte entre guillemets. Une chaîne JSON est aussi une chaîne YAML valide."""
    return json.dumps(str(valeur), ensure_ascii=False)


def _booleen(valeur: object) -> str:
    return "true" if valeur else "false"


def _nombre(valeur: float) -> str:
    return str(int(valeur)) if float(valeur).is_integer() else str(valeur)


def _regles_des_titres(titres: list[dict]) -> list[str]:
    """Une règle par regroupement de paragraphes : un style créé par la publication, ou du texte en gras
    d'une taille donnée. Les styles passent en premier : un style dit à lui seul à quoi sert le paragraphe.
    Les groupes en gras sans taille connue passent en dernier : leur règle n'a pas de borne de taille et
    s'appliquerait sinon avant les autres."""
    lignes: list[str] = []
    ordonnes = sorted(titres, key=lambda t: ("style" not in t, t.get("taille") is None, -(t.get("taille") or 0)))
    for rang, titre in enumerate(ordonnes, start=1):
        role = titre["role"]
        if role not in STYLES_DES_ROLES:
            raise ValueError(f"Rôle de titre inconnu : « {role} ». Rôles permis : {', '.join(STYLES_DES_ROLES)}.")
        if "style" in titre:                 # tout paragraphe de ce style, quelle que soit sa mise en forme
            lignes += [f"    - nom: {role}-{rang}", f"      styles_source: [{_texte(titre['style'])}]",
                       f"      style_cible: {_texte(STYLES_DES_ROLES[role])}"]
            continue
        styles = ", ".join(_texte(s) for s in titre.get("styles") or ["Normal"])
        lignes += [f"    - nom: {role}-{rang}", f"      styles_source: [{styles}]", "      gras: true"]
        if titre.get("taille") is not None:
            taille = _nombre(titre["taille"])
            lignes += [f"      taille_min: {taille}", f"      taille_max: {taille}"]
        if role != "titre-article":      # le titre d'un article n'a pas de longueur maximale
            lignes.append(f"      longueur_max: {LONGUEUR_MAX_TITRE}")
        lignes.append(f"      style_cible: {_texte(STYLES_DES_ROLES[role])}")
    return lignes


def generer_profil(reponses: dict) -> str:
    """Renvoie le texte du fichier de profil (YAML) qui correspond aux réponses de l'assistant."""
    revue = str(reponses.get("revue", "")).strip()
    issn = str(reponses.get("issn", "")).strip().upper()
    mot = str(reponses.get("mot_nom_fichier", "")).strip()
    titres = reponses.get("titres") or []
    images = reponses.get("images") or []

    lignes = [
        f"# Profil de la publication {revue}, créé par l'assistant de MiseEnWeb.",
        "# Réglages décrits dans le README : https://github.com/bibudem/miseenweb",
        "",
        f"nom: {nom_de_profil(revue)}",
        f"revue: {_texte(revue)}",
    ]
    if issn:
        lignes.append(f"issn: {_texte(issn)}")
    lignes += [f"description: {_texte(f'Documents de la publication {revue}')}", ""]

    if mot:
        lignes += [
            "# Reconnaissance : le nom du fichier contient ce mot.",
            "detection:",
            f"  motif_nom_fichier: {_texte(re.escape(mot))}",
            "",
        ]
    elif issn:
        lignes += ["# Reconnaissance : par l'ISSN écrit dans le pied de page des documents.", ""]

    lignes += ["# Correspondance entre les styles de Word et les balises de la page.", "mammoth:", "  carte_styles: |"]
    lignes += CARTE_STYLES.rstrip("\n").split("\n")
    lignes += ["  inclure_carte_defaut: true", "  images: incorporees", "  bordures_images: true"]
    if images:
        lignes.append("  images_connues:            # images de la publication, reconnues par leur empreinte")
        for image in images:
            texte = str(image.get("texte", "")).strip()
            lignes.append(f"    - empreinte: {_texte(image['empreinte'])}")
            lignes.append(f"      alt: {_texte(texte)}" + ("" if texte else "            # image décorative"))
    lignes.append("")

    lignes += [
        "# Corrections faites sur une copie du document avant la conversion.",
        "normalisation:",
        "  active: true",
        "  numeros_sous_titres: true",
        "  mise_en_forme_cellules: true",
        "  sortes_de_puces: true",
    ]
    if titres:
        lignes.append("  regles:                    # titres sans style de titre de Word : style de la publication, ou texte en gras")
        lignes += _regles_des_titres(titres)
    lignes.append("")

    lignes += [
        "# Structure et présentation de la page produite.",
        "post_traitement:",
        "  supprimer_vides: true",
        "  corriger_faux_titres: true",
        "  entetes_tableaux: true",
        "  notes_tableaux: true",
        "  accessibilite_tableaux: true",
        "  alignement_colonnes: true",
        f"  apparence: {reponses.get('apparence', 'document')}",
        f"  tableaux: {reponses.get('tableaux', 'bordures')}",
        "  tableaux_larges: 9",
        "  liens_automatiques: true",
        "  sens_ecriture: true",
        "  identifiants_titres: true",
        "  decaler_niveaux: auto",
        "  verifier_hierarchie: true",
        "  avertir_h1_multiples: true",
        "  table_des_matieres: false",
        f"  bandeau_avant_titre: {_booleen(reponses.get('bandeau'))}",
        f"  couleur_bandeau: {_booleen(reponses.get('bandeau'))}",
        f"  pied_page: {_booleen(reponses.get('pied_page'))}",
        "  gabarit: ../gabarits/page.html",
        "  langue: fr",
    ]
    return "\n".join(lignes) + "\n"
