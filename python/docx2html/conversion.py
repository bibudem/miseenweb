"""Conversion .docx -> fragment HTML avec Mammoth, selon le profil."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path

import mammoth
import mammoth.images

from .apparence import empreinte, empreintes_images_encadrees
from .images_emf import emf_vers_png
from .normalisation import CARTE_DE_STYLES


@dataclass
class ResultatConversion:
    html: str
    messages: list[dict] = field(default_factory=list)   # {type, message}
    images_extraites: list[Path] = field(default_factory=list)


def _contenu_image(image, encadrees: set[str], connues: dict[str, str]) -> tuple[str, bytes, dict]:
    """Lit une image et renvoie (type, octets, attributs), en passant les EMF lisibles en PNG.

    Les attributs donnent la classe « encadree » aux images que Word entoure d'une bordure, et
    aux images connues du profil leur texte de remplacement. Un texte vide marque une image
    décorative. Le texte de remplacement écrit dans Word a toujours priorité.
    """
    with image.open() as flux:
        donnees = flux.read()
    signature = empreinte(donnees)
    attributs = {"class": "encadree"} if signature in encadrees else {}
    if signature in connues and not image.alt_text:
        attributs["alt"] = connues[signature]
        if not connues[signature]:
            attributs["role"] = "presentation"
    type_image = image.content_type or "image/png"
    if type_image == "image/x-emf":
        png = emf_vers_png(donnees)
        if png is not None:
            return "image/png", png, attributs
    return type_image, donnees, attributs


def _incorporateur_images(encadrees: set[str], connues: dict[str, str]):
    """Fabrique un gestionnaire Mammoth qui place les images dans le HTML (base64)."""

    def convertir(image):
        type_image, donnees, attributs = _contenu_image(image, encadrees, connues)
        encodage = base64.b64encode(donnees).decode("ascii")
        return {"src": f"data:{type_image};base64,{encodage}", **attributs}

    return mammoth.images.img_element(convertir)


def _extracteur_images(
    dossier_images: Path, prefixe: str, extraites: list[Path], encadrees: set[str], connues: dict[str, str]
):
    """Fabrique un gestionnaire Mammoth qui écrit les images sur disque."""
    dossier_images.mkdir(parents=True, exist_ok=True)
    compteur = {"n": 0}

    def convertir(image):
        compteur["n"] += 1
        type_image, donnees, attributs = _contenu_image(image, encadrees, connues)
        extension = type_image.split("/")[-1]
        extension = {"jpeg": "jpg", "svg+xml": "svg"}.get(extension, extension)
        nom = f"{prefixe}-image{compteur['n']:03d}.{extension}"
        chemin = dossier_images / nom
        chemin.write_bytes(donnees)
        extraites.append(chemin)
        # Chemin relatif au fichier HTML produit
        return {"src": f"{dossier_images.name}/{nom}", **attributs}

    return mammoth.images.img_element(convertir)


def convertir(chemin_docx: Path, profil, dossier_sortie: Path, nom_base: str) -> ResultatConversion:
    """Convertit un .docx en fragment HTML.

    Options lues dans `profil.mammoth` :
      carte_styles / carte_styles_fichier : carte de styles Mammoth
      inclure_carte_defaut : combiner avec la carte par défaut (défaut : true)
      images : « incorporees » (base64, défaut) ou « extraites » (fichiers)
      ignorer_images_vides : supprime les <img> sans src (défaut : false)
      bordures_images : donne la classe « encadree » aux images que Word encadre (défaut : false)
      images_connues : images récurrentes, reconnues par leur empreinte SHA-1, avec leur texte de
                       remplacement (« alt »); un texte vide marque une image décorative
    """
    options = profil.mammoth
    carte = (profil.carte_styles() or "") + CARTE_DE_STYLES
    extraites: list[Path] = []
    encadrees = empreintes_images_encadrees(chemin_docx) if options.get("bordures_images") else set()
    connues = {str(i["empreinte"]): str(i.get("alt") or "") for i in options.get("images_connues") or []}

    kwargs = {
        "style_map": carte,
        "include_default_style_map": bool(options.get("inclure_carte_defaut", True)),
    }
    if options.get("images", "incorporees") == "extraites":
        dossier_images = Path(dossier_sortie) / f"{nom_base}_fichiers"
        kwargs["convert_image"] = _extracteur_images(dossier_images, nom_base, extraites, encadrees, connues)
    else:
        kwargs["convert_image"] = _incorporateur_images(encadrees, connues)

    with Path(chemin_docx).open("rb") as f:
        resultat = mammoth.convert_to_html(f, **kwargs)

    html = resultat.value
    if options.get("ignorer_images_vides"):
        html = re.sub(r'<img(?![^>]*\bsrc=)[^>]*>', "", html)

    # L'avertissement EMF de Mammoth ne reste que si une image EMF n'a pas pu être convertie.
    reste_emf = "data:image/x-emf" in html or any(c.suffix == ".x-emf" for c in extraites)
    messages = [
        {"type": m.type, "message": m.message}
        for m in resultat.messages
        if reste_emf or "image/x-emf" not in m.message
    ]
    return ResultatConversion(html=html, messages=messages, images_extraites=extraites)
