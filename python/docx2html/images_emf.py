"""Extraction de l'image contenue dans un fichier EMF, pour produire un PNG."""

from __future__ import annotations

import struct
import zlib

EMR_EOF = 14            # type de l'enregistrement qui termine un fichier EMF
EMR_GDICOMMENT = 70     # type d'un enregistrement « commentaire »

EMFPLUS_OBJET = 0x4008      # type d'un enregistrement EMF+ qui décrit un objet
OBJET_IMAGE = 5             # sorte d'objet : une image
OBJET_SUITE = 0x8000        # indicateur : l'objet continue dans l'enregistrement suivant
IMAGE_BITMAP = 1            # sorte d'image : en pixels
BITMAP_PIXELS = 0           # pixels bruts, sans compression
FORMAT_ARGB_PREMULTIPLIE = 0x000E200B   # 4 octets par pixel, couleurs prémultipliées


def _commentaires(emf: bytes):
    """Parcourt un fichier EMF et donne le contenu de chaque commentaire."""
    position = 0
    while position + 8 <= len(emf):
        type_enregistrement, taille = struct.unpack_from("<II", emf, position)
        if taille < 8:      # fichier abîmé : on arrête plutôt que de boucler sans fin
            return
        if type_enregistrement == EMR_GDICOMMENT:
            longueur = struct.unpack_from("<I", emf, position + 8)[0]
            yield emf[position + 12 : position + 12 + longueur]
        if type_enregistrement == EMR_EOF:
            return
        position += taille


def _image_emf_plus(commentaire: bytes):
    """Cherche une image en pixels dans un commentaire EMF+.

    Renvoie (largeur, hauteur, pas, pixels), ou None si le commentaire n'en contient pas.
    Le pas est le nombre d'octets occupés par une ligne de l'image.
    """
    if commentaire[:4] != b"EMF+":
        return None
    position = 4
    while position + 12 <= len(commentaire):
        type_enr, indicateurs, taille, _ = struct.unpack_from("<HHII", commentaire, position)
        if taille < 12:
            return None
        sorte_objet = (indicateurs >> 8) & 0x7F
        est_image = type_enr == EMFPLUS_OBJET and sorte_objet == OBJET_IMAGE
        if est_image and not indicateurs & OBJET_SUITE and taille >= 12 + 28:
            debut = position + 12
            _, sorte_image, largeur, hauteur, pas, format_pixels, sorte_bitmap = struct.unpack_from(
                "<IIiiiII", commentaire, debut
            )
            pixels = commentaire[debut + 28 : debut + 28 + pas * hauteur]
            if (
                sorte_image == IMAGE_BITMAP
                and sorte_bitmap == BITMAP_PIXELS
                and format_pixels == FORMAT_ARGB_PREMULTIPLIE
                and len(pixels) == pas * hauteur
            ):
                return largeur, hauteur, pas, pixels
        position += taille
    return None


def _lignes_rgba(largeur: int, hauteur: int, pas: int, pixels: bytes) -> bytes:
    """Convertit les pixels EMF (bleu, vert, rouge, alpha) en lignes PNG (rouge, vert, bleu, alpha)."""
    lignes = bytearray()
    for y in range(hauteur):
        ligne = bytearray(pixels[y * pas : y * pas + largeur * 4])
        ligne[0::4], ligne[2::4] = ligne[2::4], ligne[0::4]     # échange le bleu et le rouge
        for i in range(3, len(ligne), 4):                       # i : position de l'alpha du pixel
            alpha = ligne[i]
            if 0 < alpha < 255:                                 # pixel semi-transparent
                for canal in range(i - 3, i):
                    ligne[canal] = min(255, ligne[canal] * 255 // alpha)
        lignes += b"\0" + ligne                                 # \0 : ligne PNG sans filtre
    return bytes(lignes)


def _bloc_png(nom: bytes, donnees: bytes) -> bytes:
    """Fabrique un bloc PNG : longueur, nom, données, somme de contrôle."""
    controle = zlib.crc32(nom + donnees)
    return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", controle)


def _encoder_png(largeur: int, hauteur: int, pas: int, pixels: bytes) -> bytes:
    """Assemble un fichier PNG complet à partir des pixels."""
    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)   # 8 bits, RVBA
    donnees = zlib.compress(_lignes_rgba(largeur, hauteur, pas, pixels), 6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _bloc_png(b"IHDR", entete)
        + _bloc_png(b"IDAT", donnees)
        + _bloc_png(b"IEND", b"")
    )


def emf_vers_png(emf: bytes) -> bytes | None:
    """Renvoie un PNG tiré d'un fichier EMF, ou None si le fichier ne contient pas d'image lisible."""
    for commentaire in _commentaires(emf):
        image = _image_emf_plus(commentaire)
        if image is not None:
            return _encoder_png(*image)
    return None
