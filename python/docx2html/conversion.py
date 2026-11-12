"""Conversion .docx -> fragment HTML avec Mammoth, selon le profil."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path

import mammoth
import mammoth.images

from .images_emf import emf_vers_png


@dataclass
class ResultatConversion:
    html: str
    messages: list[dict] = field(default_factory=list)   # {type, message}
    images_extraites: list[Path] = field(default_factory=list)


def _contenu_image(image) -> tuple[str, bytes]:
    """Lit une image et renvoie (type, octets), en passant les EMF lisibles en PNG."""
    with image.open() as flux:
        donnees = flux.read()
    type_image = image.content_type or "image/png"
    if type_image == "image/x-emf":
        png = emf_vers_png(donnees)
        if png is not None:
            return "image/png", png
    return type_image, donnees


def _incorporateur_images():
    """Fabrique un gestionnaire Mammoth qui place les images dans le HTML (base64)."""

    def convertir(image):
        type_image, donnees = _contenu_image(image)
        encodage = base64.b64encode(donnees).decode("ascii")
        return {"src": f"data:{type_image};base64,{encodage}"}

    return mammoth.images.img_element(convertir)


def _extracteur_images(dossier_images: Path, prefixe: str, extraites: list[Path]):
    """Fabrique un gestionnaire Mammoth qui écrit les images sur disque."""
    dossier_images.mkdir(parents=True, exist_ok=True)
    compteur = {"n": 0}

    def convertir(image):
        compteur["n"] += 1
        type_image, donnees = _contenu_image(image)
        extension = type_image.split("/")[-1]
        extension = {"jpeg": "jpg", "svg+xml": "svg"}.get(extension, extension)
        nom = f"{prefixe}-image{compteur['n']:03d}.{extension}"
        chemin = dossier_images / nom
        chemin.write_bytes(donnees)
        extraites.append(chemin)
        # Chemin relatif au fichier HTML produit
        return {"src": f"{dossier_images.name}/{nom}"}

    return mammoth.images.img_element(convertir)


def convertir(chemin_docx: Path, profil, dossier_sortie: Path, nom_base: str) -> ResultatConversion:
    """Convertit un .docx en fragment HTML.

    Options lues dans `profil.mammoth` :
      carte_styles / carte_styles_fichier : carte de styles Mammoth
      inclure_carte_defaut : combiner avec la carte par défaut (défaut : true)
      images : « incorporees » (base64, défaut) ou « extraites » (fichiers)
      ignorer_images_vides : supprime les <img> sans src (défaut : false)
    """
    options = profil.mammoth
    carte = profil.carte_styles()
    extraites: list[Path] = []

    kwargs = {
        "style_map": carte,
        "include_default_style_map": bool(options.get("inclure_carte_defaut", True)),
    }
    if options.get("images", "incorporees") == "extraites":
        dossier_images = Path(dossier_sortie) / f"{nom_base}_fichiers"
        kwargs["convert_image"] = _extracteur_images(dossier_images, nom_base, extraites)
    else:
        kwargs["convert_image"] = _incorporateur_images()

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
