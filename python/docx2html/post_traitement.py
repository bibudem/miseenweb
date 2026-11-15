"""Post-traitement du fragment HTML produit par Mammoth (avec BeautifulSoup).

Opérations disponibles, activées par le profil (`post_traitement`) :
  identifiants_titres : ajoute un attribut id (slug) à chaque h1..h6
  table_des_matieres  : génère une <nav> imbriquée (niveau max configurable)
  niveau_max_tdm, titre_tdm, tdm_dans_fragment : réglages de cette table
  verifier_hierarchie : signale l'absence de titre, un premier titre qui n'est pas
                        un h1, les sauts de niveau (h1 -> h3) et plusieurs h1
  avertir_h1_multiples: signaler plus d'un h1 (défaut : true)
  decaler_niveaux     : « auto » (décale d'un niveau sous un h1.titre-document),
                        ou un entier; 0 = aucun décalage (défaut)
  classe_titre_document : classe du h1 qui représente le titre du document
  corriger_faux_titres: change en <p> les titres vides et ceux placés dans un tableau
  entetes_tableaux    : change en <th> les cellules des lignes d'en-tête
  notes_tableaux      : sort du tableau la note placée dans sa dernière ligne
  accessibilite_tableaux : rattache son titre à chaque tableau, marque les en-têtes de ligne
                        et relie chaque cellule à ses en-têtes (scope, id, headers)
  alignement_apa      : aligne les tableaux selon l'APA, sans égard au Word : en-têtes et
                        données centrés, première colonne à gauche
  alignement_colonnes : centre toute une colonne de données quand la plupart de ses
                        cellules sont centrées dans le Word
  tableaux_larges     : nombre de colonnes à partir duquel un tableau est placé dans une
                        zone à défilement horizontal (0 = jamais, défaut)
  bandeau_avant_titre : donne la classe « bandeau » au paragraphe qui précède le titre
  couleur_bandeau     : donne au bandeau la couleur de fond qu'il a dans le Word
                        (lue par pipeline.py), avec un texte noir ou blanc selon le contraste
  resume_avant_mots_cles : replace le résumé avant ses mots-clés quand ils sont inversés
  liens_automatiques  : rend cliquables les adresses web et les courriels
  sens_ecriture       : marque les passages en arabe (dir="rtl", lang="ar")
  supprimer_vides     : retire les <p> vides
  gabarit             : enveloppe le fragment dans une page HTML complète
  langue              : langue de la page (défaut : fr)

Le réglage `pied_page` de la même section est lu par pipeline.py.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from .apparence import texte_normalise

NIVEAUX = ["h1", "h2", "h3", "h4", "h5", "h6"]

# Étiquettes du résumé et de ses mots-clés, par langue : (résumé, mots-clés)
ETIQUETTES_RESUME = [
    (re.compile(r"résumé"), re.compile(r"mots[\s-]*clés")),
    (re.compile(r"abstract"), re.compile(r"key[\s-]*words?")),
]

# Lettres de l'écriture arabe, et éléments dont on règle le sens d'écriture
MOTIF_ARABE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
ELEMENTS_SENS = ["table", "ul", "ol", "blockquote", "p", "li", "td", "th", "figcaption", *NIVEAUX]

# Une adresse web, ou un courriel
MOTIF_ADRESSE = re.compile(r"https?://[^\s<>\"]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class ResultatPostTraitement:
    html: str                     # fragment ou page, selon le profil
    titre: str = ""
    avertissements: list[str] = field(default_factory=list)
    nb_titres: dict[str, int] = field(default_factory=dict)


def slugifier(texte: str, longueur_max: int = 60) -> str:
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()
    return texte[:longueur_max].strip("-") or "section"


def _ajouter_identifiants(soupe: BeautifulSoup) -> None:
    vus: dict[str, int] = {}
    for titre in soupe.find_all(NIVEAUX):
        if titre.get("id"):
            continue
        base = slugifier(titre.get_text(" ", strip=True))
        n = vus.get(base, 0)
        vus[base] = n + 1
        titre["id"] = base if n == 0 else f"{base}-{n + 1}"


def _verifier_hierarchie(soupe: BeautifulSoup) -> list[str]:
    avertissements: list[str] = []
    titres = soupe.find_all(NIVEAUX)
    if not titres:
        avertissements.append("Aucun titre (h1 à h6) dans le document converti.")
        return avertissements
    if titres[0].name != "h1":
        avertissements.append(f"Le document ne commence pas par un h1 (premier titre : {titres[0].name}).")
    precedent = 0
    for t in titres:
        niveau = int(t.name[1])
        if precedent and niveau > precedent + 1:
            extrait = t.get_text(" ", strip=True)[:60]
            avertissements.append(
                f"Saut de niveau : h{precedent} suivi de h{niveau} (« {extrait} »)."
            )
        precedent = niveau
    nb_h1 = sum(1 for t in titres if t.name == "h1")
    if nb_h1 > 1:
        avertissements.append(f"{nb_h1} titres de niveau h1; un seul est généralement attendu par page.")
    return avertissements


def _construire_tdm(soupe: BeautifulSoup, niveau_max: int, titre_tdm: str) -> Tag | None:
    titres = [t for t in soupe.find_all(NIVEAUX) if int(t.name[1]) <= niveau_max]
    if not titres:
        return None
    nav = soupe.new_tag("nav", attrs={"class": "table-des-matieres", "aria-label": titre_tdm})
    entete = soupe.new_tag("p", attrs={"class": "tdm-titre"})
    entete.string = titre_tdm
    nav.append(entete)

    racine = soupe.new_tag("ol")
    nav.append(racine)
    pile: list[tuple[int, Tag]] = [(0, racine)]
    for t in titres:
        niveau = int(t.name[1])
        while pile and pile[-1][0] >= niveau:
            pile.pop()
        parent_liste = pile[-1][1]
        # Si on descend de plus d'un niveau, on crée les listes intermédiaires
        while pile[-1][0] < niveau - 1:
            dernier_li = parent_liste.find_all("li", recursive=False)
            if dernier_li:
                conteneur = dernier_li[-1]
            else:
                conteneur = soupe.new_tag("li")
                parent_liste.append(conteneur)
            sous = soupe.new_tag("ol")
            conteneur.append(sous)
            pile.append((pile[-1][0] + 1, sous))
            parent_liste = sous
        li = soupe.new_tag("li")
        lien = soupe.new_tag("a", href=f"#{t.get('id')}")
        lien.string = t.get_text(" ", strip=True)
        li.append(lien)
        parent_liste.append(li)
        sous = soupe.new_tag("ol")
        li.append(sous)
        pile.append((niveau, sous))

    # retirer les <ol> vides créés par anticipation
    for ol in nav.find_all("ol"):
        if not ol.find_all("li", recursive=False):
            ol.decompose()
    return nav


def _decaler_niveaux(soupe: BeautifulSoup, mode, classe_titre_document: str) -> int:
    """Décale les titres d'un niveau (h1 -> h2, ..., h5 -> h6).

    mode « auto » : décale seulement si un h1 portant la classe du titre de
    document existe (ce h1 est conservé); un entier décale de ce nombre.
    Retourne le décalage appliqué.
    """
    if mode in (None, 0, "0", False):
        return 0
    titre_doc = None
    if mode == "auto":
        titre_doc = soupe.find("h1", class_=classe_titre_document)
        if titre_doc is None:
            return 0
        decalage = 1
    else:
        decalage = int(mode)
    for t in soupe.find_all(NIVEAUX):
        if t is titre_doc:
            continue
        niveau = min(int(t.name[1]) + decalage, 6)
        t.name = f"h{niveau}"
    return decalage


def _corriger_faux_titres(soupe: BeautifulSoup) -> int:
    """Change en <p> les titres sans texte et les titres placés dans un tableau."""
    n = 0
    for titre in soupe.find_all(NIVEAUX):
        if not titre.get_text(strip=True) or titre.find_parent(["td", "th"]):
            titre.name = "p"
            n += 1
    return n


def _marquer_entetes(soupe: BeautifulSoup) -> int:
    """Change en <th> la première ligne de chaque tableau de deux lignes ou plus.

    La deuxième ligne est aussi un en-tête si elle subdivise les cellules fusionnées de la
    première : elle a alors plus de cellules que la première, et aucune cellule fusionnée
    vers le bas. Une cellule fusionnée vers le bas commence un groupe de lignes de données.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        lignes = tableau.find_all("tr")
        if len(lignes) < 2:
            continue
        entetes = [lignes[0]]
        premieres = lignes[0].find_all(["td", "th"], recursive=False)
        secondes = lignes[1].find_all(["td", "th"], recursive=False)
        if (
            len(lignes) > 2
            and any(c.get("colspan") for c in premieres)
            and len(secondes) > len(premieres)
            and not any(c.get("rowspan") for c in secondes)
        ):
            entetes.append(lignes[1])
        for ligne in entetes:
            for cellule in ligne.find_all("td"):
                cellule.name = "th"
                n += 1
    return n


def _sortir_notes_tableaux(soupe: BeautifulSoup) -> int:
    """Sort du tableau la note écrite dans sa dernière ligne.

    Une dernière ligne faite d'une seule cellule, fusionnée sur toute la largeur, n'est pas
    une donnée : c'est une note. Son contenu devient des paragraphes « note-tableau »,
    placés après le tableau.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        lignes = tableau.find_all("tr")
        if len(lignes) < 3:
            continue
        largeur = max(sum(int(c.get("colspan", 1)) for c in ligne.find_all(["td", "th"])) for ligne in lignes)
        cellules = lignes[-1].find_all(["td", "th"])
        if largeur < 2 or len(cellules) != 1 or int(cellules[0].get("colspan", 1)) != largeur:
            continue
        cellule = cellules[0]
        if not cellule.find("p"):       # texte placé directement dans la cellule
            cellule.name = "p"
            del cellule["colspan"]
            paragraphes = [cellule.extract()]
        else:
            paragraphes = [p.extract() for p in cellule.find_all("p", recursive=False)]
        lignes[-1].decompose()
        repere = tableau
        for p in paragraphes:
            p["class"] = p.get("class", []) + ["note-tableau"]
            repere.insert_after(p)
            repere = p
        n += 1
    return n


def _grille(tableau: Tag) -> list[list[tuple[Tag, int, int]]]:
    """Position de chaque cellule d'un tableau : par ligne, une liste de (cellule, colonne, largeur).

    Une cellule fusionnée occupe plusieurs colonnes ou plusieurs lignes : la colonne de chaque
    cellule est donc calculée ligne par ligne, en tenant compte des fusions.
    """
    lignes = []
    occupees: dict[int, int] = {}       # colonne -> lignes encore couvertes par une fusion verticale
    for ligne in tableau.find_all("tr"):
        if ligne.find_parent("table") is not tableau:
            continue
        rang = []
        colonne = 0
        for cellule in ligne.find_all(["td", "th"], recursive=False):
            while occupees.get(colonne, 0) > 0:
                colonne += 1
            largeur = int(cellule.get("colspan", 1))
            rang.append((cellule, colonne, largeur))
            if int(cellule.get("rowspan", 1)) > 1:
                for c in range(colonne, colonne + largeur):
                    occupees[c] = int(cellule["rowspan"])
            colonne += largeur
        lignes.append(rang)
        occupees = {c: n - 1 for c, n in occupees.items() if n > 1}
    return lignes


def _colonnes_du_tableau(tableau: Tag) -> dict[int, list[Tag]]:
    """Range les cellules de données (<td>) d'un tableau d'après leur bord droit : {bord droit: cellules}.

    Le bord droit sert de repère parce qu'un tableau Word a parfois des limites de cellules
    différentes d'une ligne à l'autre : la même colonne de chiffres peut être une cellule
    large sur une ligne, et une cellule étroite sur la suivante. Leur bord droit est le même.
    Les cellules de la première colonne, qui nomment les lignes, ne sont pas rangées.
    """
    colonnes: dict[int, list[Tag]] = {}
    for rang in _grille(tableau):
        for cellule, colonne, largeur in rang:
            if cellule.name == "td" and colonne > 0:
                colonnes.setdefault(colonne + largeur, []).append(cellule)
    return colonnes


# Un paragraphe qui commence ainsi, juste avant un tableau, en porte le numéro
MOTIF_NUMERO_TABLEAU = re.compile(r"\s*(table|tableau)\s+\d+", re.IGNORECASE)


def _legendes_en_paragraphes(soupe: BeautifulSoup) -> int:
    """Change en <p class="legende"> les <figcaption> placés hors d'un <figure>, ce que HTML interdit."""
    n = 0
    for legende in soupe.find_all("figcaption"):
        if legende.find_parent("figure") is None:
            legende.name = "p"
            legende["class"] = legende.get("class", []) + ["legende"]
            n += 1
    return n


def _nommer_tableau(tableau: Tag, numero: int) -> bool:
    """Rattache au tableau son numéro et son titre, écrits juste avant lui (aria-labelledby).

    Sans ce lien, un lecteur d'écran annonce un tableau sans dire lequel.
    """
    ancre = tableau.parent if "tableau-large" in (tableau.parent.get("class") or []) else tableau
    precedents = []
    element = ancre.find_previous_sibling()
    while element is not None and len(precedents) < 2 and element.name == "p":
        if len(element.get_text(" ", strip=True)) > 400:
            break
        precedents.insert(0, element)
        element = element.find_previous_sibling()
    while precedents and not MOTIF_NUMERO_TABLEAU.match(precedents[0].get_text(" ", strip=True)):
        precedents.pop(0)
    if not precedents:
        return False
    identifiants = []
    for rang, paragraphe in enumerate(precedents, start=1):
        if not paragraphe.get("id"):
            paragraphe["id"] = f"titre-tableau-{numero}" + ("" if rang == 1 else f"-{rang}")
        identifiants.append(paragraphe["id"])
    tableau["aria-labelledby"] = " ".join(identifiants)
    return True


def _rendre_tableaux_accessibles(soupe: BeautifulSoup) -> int:
    """Inscrit dans chaque tableau ce que sa mise en page montre : son nom, et les en-têtes de chaque cellule.

    - Le titre placé avant le tableau lui est rattaché.
    - La première colonne, quand elle nomme les lignes, devient une colonne d'en-têtes de ligne.
    - Un en-tête simple reçoit scope="col". Un en-tête sur plusieurs lignes, ou à cellules
      fusionnées, est relié à chaque cellule par les attributs id et headers.
    Un tableau sans ligne d'en-tête ne reçoit que son nom : pont.py le signale à l'utilisateur.
    """
    n = 0
    for numero, tableau in enumerate(soupe.find_all("table"), start=1):
        grille = _grille(tableau)
        if not grille:
            continue
        _nommer_tableau(tableau, numero)
        nb_entetes = 0
        for rang in grille:
            if not rang or any(cellule.name != "th" for cellule, _, _ in rang):
                break
            nb_entetes += 1
        if nb_entetes == 0:
            continue
        n += 1
        entetes, donnees = grille[:nb_entetes], grille[nb_entetes:]
        nb_colonnes = max(colonne + largeur for rang in grille for _, colonne, largeur in rang)

        # En-têtes de ligne : la première colonne, si elle contient surtout du texte
        premieres = [(c, largeur) for rang in donnees for c, colonne, largeur in rang[:1] if colonne == 0]
        remplies = [c for c, _ in premieres if c.get_text(strip=True)]
        avec_lettres = [c for c in remplies if any(lettre.isalpha() for lettre in c.get_text())]
        if nb_colonnes >= 2 and remplies and len(avec_lettres) >= 0.8 * len(remplies):
            for cellule, largeur in premieres:
                if cellule.get_text(strip=True) and largeur < nb_colonnes:
                    cellule.name = "th"
                    cellule["scope"] = "row"

        complexe = nb_entetes > 1 or any(largeur > 1 for rang in entetes for _, _, largeur in rang)
        if not complexe:
            for cellule, _, _ in entetes[0]:
                cellule["scope"] = "col"
            continue

        # En-tête complexe : chaque cellule de données nomme ses en-têtes de colonne et de ligne
        par_colonne: dict[int, list[str]] = {}
        compteur = 0
        for rang in entetes:
            for cellule, colonne, largeur in rang:
                if not cellule.get_text(strip=True):
                    continue
                compteur += 1
                cellule["id"] = f"t{numero}-c{compteur}"
                for c in range(colonne, colonne + largeur):
                    par_colonne.setdefault(c, []).append(cellule["id"])
        groupe, lignes_du_groupe = "", 0        # en-tête de ligne fusionné vers le bas
        for rang_ligne, rang in enumerate(donnees, start=1):
            entete_de_ligne = groupe if lignes_du_groupe > 0 else ""
            for cellule, colonne, largeur in rang:
                if cellule.name == "th":
                    cellule["id"] = f"t{numero}-l{rang_ligne}"
                    entete_de_ligne = cellule["id"]
                    if int(cellule.get("rowspan", 1)) > 1:
                        groupe, lignes_du_groupe = cellule["id"], int(cellule["rowspan"])
                    continue
                if not cellule.get_text(strip=True):
                    continue
                identifiants = []
                for c in range(colonne, colonne + largeur):
                    identifiants += [i for i in par_colonne.get(c, []) if i not in identifiants]
                if entete_de_ligne:
                    identifiants.append(entete_de_ligne)
                if identifiants:
                    cellule["headers"] = " ".join(identifiants)
            lignes_du_groupe -= 1
    return n


def _regulariser_colonnes(soupe: BeautifulSoup) -> int:
    """Donne le même découpage aux lignes d'un tableau qui ont le même nombre de cellules.

    Dans Word, les limites des cellules peuvent différer d'une ligne à l'autre sans que cela
    se voie. Dans une page, les colonnes ne tombent alors plus les unes sous les autres. Quand
    au moins 60 % des lignes de même nombre de cellules partagent un découpage, les autres
    le reçoivent. Un tableau à cellules fusionnées vers le bas n'est pas touché.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        if tableau.find(["td", "th"], rowspan=True):
            continue
        lignes = [
            ligne.find_all(["td", "th"], recursive=False)
            for ligne in tableau.find_all("tr")
            if ligne.find_parent("table") is tableau
        ]
        decoupage = lambda cellules: tuple(int(c.get("colspan", 1)) for c in cellules)  # noqa: E731
        largeur = max((sum(decoupage(cellules)) for cellules in lignes), default=0)
        par_nombre: dict[int, list[list[Tag]]] = {}
        for cellules in lignes:
            if len(cellules) >= 2 and sum(decoupage(cellules)) == largeur:
                par_nombre.setdefault(len(cellules), []).append(cellules)
        for groupe in par_nombre.values():
            compte: dict[tuple, int] = {}
            for cellules in groupe:
                compte[decoupage(cellules)] = compte.get(decoupage(cellules), 0) + 1
            courant, occurrences = max(compte.items(), key=lambda paire: paire[1])
            if len(compte) < 2 or occurrences < 0.6 * len(groupe):
                continue
            for cellules in groupe:
                if decoupage(cellules) == courant:
                    continue
                for cellule, colonnes in zip(cellules, courant):
                    if colonnes > 1:
                        cellule["colspan"] = str(colonnes)
                    elif cellule.get("colspan"):
                        del cellule["colspan"]
                n += 1
    return n


LONGUEUR_CENTREE = 50       # caractères : au-delà, une cellule de données reste alignée à gauche


def _aligner_selon_apa(soupe: BeautifulSoup) -> int:
    """Aligne chaque tableau selon l'APA (7e édition), à la place de l'alignement du Word.

    - En-têtes de colonnes : centrés.
    - Première colonne, qui nomme les lignes : à gauche. Quand le Word centre une partie
      seulement des noms de lignes, le centrage y marque une ligne subordonnée : ces noms
      reçoivent un retrait d'un niveau. Quand presque tous sont centrés, ils passent à gauche
      sans retrait.
    - Autres colonnes : centrées. Une colonne dont au moins le tiers des cellules contient un
      texte long, plusieurs paragraphes ou une liste est alignée à gauche, plus lisible. Le
      choix vaut pour toute la colonne : des cellules centrées et d'autres à gauche, l'une
      sous l'autre, se liraient mal.
    """

    def est_longue(cellule: Tag) -> bool:
        remplis = [p for p in cellule.find_all("p", recursive=False) if p.get_text(strip=True)]
        return (
            len(cellule.get_text(" ", strip=True)) > LONGUEUR_CENTREE
            or len(remplis) > 1
            or cellule.find(["ul", "ol"]) is not None
        )

    n = 0
    for tableau in soupe.find_all("table"):
        grille = _grille(tableau)
        nb_entetes = 0
        for rang in grille:
            if not rang or any(cellule.name != "th" for cellule, _, _ in rang):
                break
            nb_entetes += 1
        noms_de_lignes = [c for rang in grille[nb_entetes:] for c, colonne, _ in rang if colonne == 0 and c.get_text(strip=True)]
        centres = [c for c in noms_de_lignes if c.find("p", class_="centre", recursive=False)]
        subordination = bool(centres) and len(centres) <= 0.8 * len(noms_de_lignes)
        # Colonnes de texte, repérées par leur bord droit
        par_bord: dict[int, list[Tag]] = {}
        for rang in grille[nb_entetes:]:
            for cellule, colonne, largeur in rang:
                if colonne > 0 and cellule.get_text(strip=True):
                    par_bord.setdefault(colonne + largeur, []).append(cellule)
        colonnes_de_texte = {
            bord for bord, cellules in par_bord.items()
            if 3 * sum(1 for c in cellules if est_longue(c)) >= len(cellules)
        }
        for rang_ligne, rang in enumerate(grille):
            for cellule, colonne, largeur in rang:
                paragraphes = cellule.find_all("p", recursive=False)
                en_entete = rang_ligne < nb_entetes
                premiere_colonne = colonne == 0 and not en_entete
                for paragraphe in paragraphes:
                    classes = [c for c in paragraphe.get("class", []) if c != "centre"]
                    etait_centre = len(classes) != len(paragraphe.get("class", []))
                    if premiere_colonne and subordination and etait_centre and not any(c.startswith("retrait-") for c in classes):
                        classes.append("retrait-1")
                    if classes:
                        paragraphe["class"] = classes
                    elif paragraphe.get("class") is not None:
                        del paragraphe["class"]
                texte = cellule.get_text(" ", strip=True)
                if texte and not premiere_colonne and (en_entete or colonne + largeur not in colonnes_de_texte):
                    cellule["class"] = cellule.get("class", []) + ["centre"]
                    n += 1
    return n


def _harmoniser_alignement(soupe: BeautifulSoup) -> int:
    """Centre toute une colonne de données quand plus de la moitié de ses cellules sont centrées.

    Dans Word, une colonne étroite cache une mise en forme inégale : des cellules centrées et
    d'autres alignées à gauche paraissent alignées. Dans une page, la colonne est plus large et
    l'écart devient visible. La première colonne, qui nomme les lignes, n'est pas touchée.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        for cellules in _colonnes_du_tableau(tableau).values():
            remplies = [c for c in cellules if c.get_text(strip=True)]
            centrees = [c for c in remplies if c.find("p", class_="centre")]
            if not centrees or len(centrees) * 2 <= len(remplies):
                continue
            for cellule in remplies:
                for paragraphe in cellule.find_all("p", recursive=False):
                    if not paragraphe.get("class"):
                        paragraphe["class"] = ["centre"]
                        n += 1
    return n


def _largeur_tableau(tableau: Tag) -> int:
    """Nombre de colonnes d'un tableau, cellules fusionnées comprises."""
    return max(
        (sum(int(c.get("colspan", 1)) for c in ligne.find_all(["td", "th"])) for ligne in tableau.find_all("tr")),
        default=0,
    )


LONGUEUR_INSECABLE = 24     # caractères : au-delà, le texte d'une cellule peut se couper


def _garder_cellules_courtes(soupe: BeautifulSoup) -> int:
    """Garde sur une ligne les cellules courtes de tous les tableaux, sauf dans la première colonne.

    Sans cela, un en-tête comme « I-CVI » ou un intervalle comme « 0.93 – 1.46 » se coupe au
    trait d'union quand sa colonne est étroite. La première colonne, qui nomme les lignes,
    peut se couper : c'est elle qui cède la place.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        for rang in _grille(tableau):
            for cellule, colonne, _ in rang:
                texte = cellule.get_text(" ", strip=True)
                en_entete = cellule.name == "th" and cellule.get("scope") != "row"
                if not texte or len(texte) > LONGUEUR_INSECABLE or cellule.find("br") is not None:
                    continue
                if (colonne > 0 or en_entete) and "insecable" not in cellule.get("class", []):
                    cellule["class"] = cellule.get("class", []) + ["insecable"]
                    n += 1
    return n


def _encadrer_tableaux_larges(soupe: BeautifulSoup, seuil: int) -> int:
    """Place chaque tableau d'au moins `seuil` colonnes dans une zone à défilement horizontal.

    La zone reçoit un nom et peut prendre le focus : on la fait ainsi défiler au clavier,
    et un lecteur d'écran l'annonce.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        if tableau.find_parent("table") or _largeur_tableau(tableau) < seuil:
            continue
        n += 1
        zone = soupe.new_tag(
            "div",
            attrs={
                "class": "tableau-large",
                "role": "region",
                "tabindex": "0",
                "aria-label": f"Tableau large {n}, à faire défiler horizontalement",
            },
        )
        tableau.wrap(zone)
        # Une cellule courte reste sur une ligne : un intervalle comme « 0.93 – 1.46 » ne se coupe pas.
        # Le tableau s'élargit au besoin, et la zone défile.
        for cellule in tableau.find_all(["td", "th"]):
            texte = cellule.get_text(" ", strip=True)
            if 0 < len(texte) <= LONGUEUR_INSECABLE and cellule.find("br") is None and "insecable" not in cellule.get("class", []):
                cellule["class"] = cellule.get("class", []) + ["insecable"]
    return n


def _etiquette(element: Tag) -> str:
    """Texte d'un paragraphe d'étiquette (« Résumé », « Mots-clés : »), en minuscules; sinon ''."""
    if element.name != "p":
        return ""
    texte = unicodedata.normalize("NFC", element.get_text(" ", strip=True)).lower()
    texte = texte.replace("\u00a0", " ").rstrip(" :").strip()
    connue = any(motif.fullmatch(texte) for paire in ETIQUETTES_RESUME for motif in paire)
    return texte if connue else ""


def _resume_avant_mots_cles(soupe: BeautifulSoup) -> int:
    """Replace le résumé avant ses mots-clés.

    Dans Word, ce sont deux zones de texte côte à côte : le fichier ne les enregistre pas
    toujours dans l'ordre de lecture. Un bloc commence par un paragraphe d'étiquette et
    comprend les paragraphes qui le suivent, jusqu'à l'étiquette ou au titre suivant.
    """
    blocs: list[tuple[str, list[Tag]]] = []
    for element in soupe.find_all("p", recursive=False):
        etiquette = _etiquette(element)
        if not etiquette:
            continue
        contenu = [element]
        suivant = element.find_next_sibling()
        while suivant is not None and suivant.name == "p" and not _etiquette(suivant):
            contenu.append(suivant)
            suivant = suivant.find_next_sibling()
        blocs.append((etiquette, contenu))

    n = 0
    for (etiquette_1, bloc_1), (etiquette_2, bloc_2) in zip(blocs, blocs[1:]):
        if bloc_1[-1].find_next_sibling() is not bloc_2[0]:     # les deux blocs ne se suivent pas
            continue
        for resume, mots_cles in ETIQUETTES_RESUME:
            if mots_cles.fullmatch(etiquette_1) and resume.fullmatch(etiquette_2):
                for paragraphe in bloc_2:
                    bloc_1[0].insert_before(paragraphe.extract())
                n += 1
    return n


def _sens_du_texte(texte: str) -> str:
    """« rtl » si les lettres sont en majorité arabes, « ltr » sinon; '' s'il n'y a aucune lettre."""
    lettres = [c for c in texte if c.isalpha()]
    if not lettres:
        return ""
    arabes = sum(1 for c in lettres if MOTIF_ARABE.match(c))
    return "rtl" if arabes > len(lettres) / 2 else "ltr"


def _marquer_sens_ecriture(soupe: BeautifulSoup, langue_page: str) -> int:
    """Indique le sens d'écriture et la langue des passages en arabe.

    Un élément n'est marqué que si son sens diffère de celui dont il hérite : un tableau
    tout en arabe est marqué une fois, et un passage en français qui s'y trouve est remis
    de gauche à droite. Sans ces attributs, la ponctuation et les colonnes sont mal placées,
    et un lecteur d'écran prononce le texte dans la mauvaise langue.
    """
    n = 0
    for element in soupe.find_all(ELEMENTS_SENS):       # dans l'ordre du document : parents d'abord
        sens = _sens_du_texte(element.get_text())
        if not sens:
            continue
        parent = element.find_parent(attrs={"dir": True})
        herite = parent["dir"] if parent is not None else "ltr"
        if sens != herite:
            element["dir"] = sens
            element["lang"] = "ar" if sens == "rtl" else langue_page
            n += 1
    return n


def _luminance(couleur: str) -> float:
    """Luminance relative d'une couleur « #RRGGBB », de 0 (noir) à 1 (blanc), selon les WCAG."""
    composantes = [int(couleur[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineaires = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in composantes]
    return 0.2126 * lineaires[0] + 0.7152 * lineaires[1] + 0.0722 * lineaires[2]


def _couleur_du_texte(fond: str) -> str:
    """Noir ou blanc : la couleur de texte la plus contrastée sur ce fond."""
    luminance = _luminance(fond)
    contraste_blanc = 1.05 / (luminance + 0.05)
    contraste_noir = (luminance + 0.05) / 0.05
    return "#ffffff" if contraste_blanc >= contraste_noir else "#000000"


def _marquer_bandeau(soupe: BeautifulSoup, classe_titre_document: str, couleurs_fond: dict[str, str]) -> bool:
    """Donne la classe « bandeau » au paragraphe de texte qui précède le titre du document.

    Si ce paragraphe a une couleur de fond dans le Word (retrouvée par son texte), il la garde.
    """
    titre = soupe.find("h1", class_=classe_titre_document)
    if titre is None:
        return False
    precedent = titre.find_previous_sibling()
    if precedent is None or precedent.name != "p" or not precedent.get_text(strip=True):
        return False
    precedent["class"] = precedent.get("class", []) + ["bandeau"]
    fond = couleurs_fond.get(texte_normalise(precedent.get_text()))
    if fond:
        precedent["style"] = f"background: {fond}; color: {_couleur_du_texte(fond)};"
    return True


def _nettoyer_adresse(adresse: str) -> str:
    """Retire la ponctuation de fin de phrase collée à une adresse."""
    while adresse:
        if adresse[-1] in ".,;:!?»":
            adresse = adresse[:-1]
        elif adresse[-1] == ")" and adresse.count(")") > adresse.count("("):
            adresse = adresse[:-1]
        else:
            break
    return adresse


def _lier_adresses(soupe: BeautifulSoup) -> int:
    """Transforme en liens les adresses web et les courriels écrits en texte simple."""
    n = 0
    for texte in soupe.find_all(string=MOTIF_ADRESSE):
        if texte.find_parent("a"):      # déjà dans un lien
            continue
        morceaux = []
        position = 0
        for trouve in MOTIF_ADRESSE.finditer(texte):
            # Début d'adresse collé à un vrai lien (ex. ORCID en deux morceaux) : on le laisse.
            if trouve.end() == len(texte) and getattr(texte.next_sibling, "name", None) == "a":
                continue
            adresse = _nettoyer_adresse(trouve.group())
            cible = adresse if adresse.startswith("http") else f"mailto:{adresse}"
            lien = soupe.new_tag("a", href=cible)
            lien.string = adresse
            morceaux += [texte[position : trouve.start()], lien]
            position = trouve.start() + len(adresse)
            n += 1
        morceaux.append(texte[position:])
        for morceau in morceaux:
            if morceau:
                texte.insert_before(morceau)
        texte.extract()
    return n


def _supprimer_vides(soupe: BeautifulSoup) -> int:
    n = 0
    for p in soupe.find_all("p"):
        if not p.get_text(strip=True) and not p.find(["img", "br"]):
            p.decompose()
            n += 1
    return n


def appliquer(
    fragment_html: str,
    config: dict,
    chemin_profil: Path,
    nom_fichier: str,
    pied_html: str = "",
    couleurs_fond: dict[str, str] | None = None,
) -> ResultatPostTraitement:
    config = config or {}
    soupe = BeautifulSoup(fragment_html, "html.parser")
    resultat = ResultatPostTraitement(html="")

    _legendes_en_paragraphes(soupe)      # toujours : un <figcaption> hors d'un <figure> est invalide

    if config.get("corriger_faux_titres", False):   # avant la suppression des <p> vides
        _corriger_faux_titres(soupe)

    if config.get("notes_tableaux", False):          # avant le marquage des en-têtes
        _sortir_notes_tableaux(soupe)

    if config.get("entetes_tableaux", False):
        _marquer_entetes(soupe)

    if config.get("alignement_colonnes", False):      # après le marquage des en-têtes
        _regulariser_colonnes(soupe)
        _harmoniser_alignement(soupe)

    if config.get("alignement_apa", False):           # remplace l'alignement repris du Word
        _aligner_selon_apa(soupe)

    if int(config.get("tableaux_larges", 0) or 0) > 0:   # après la sortie des notes
        _encadrer_tableaux_larges(soupe, int(config["tableaux_larges"]))

    if config.get("supprimer_vides", True):
        _supprimer_vides(soupe)

    if config.get("accessibilite_tableaux", False):   # après la suppression des <p> vides
        _rendre_tableaux_accessibles(soupe)

    _garder_cellules_courtes(soupe)      # toujours : après le marquage des en-têtes de ligne

    if config.get("resume_avant_mots_cles", False):   # après la suppression des <p> vides
        _resume_avant_mots_cles(soupe)

    if config.get("liens_automatiques", False):
        _lier_adresses(soupe)

    if config.get("sens_ecriture", False):
        _marquer_sens_ecriture(soupe, str(config.get("langue", "fr")))

    if config.get("bandeau_avant_titre", False):    # après la suppression des <p> vides
        _marquer_bandeau(
            soupe, str(config.get("classe_titre_document", "titre-document")), couleurs_fond or {}
        )

    _decaler_niveaux(
        soupe,
        config.get("decaler_niveaux", 0),
        str(config.get("classe_titre_document", "titre-document")),
    )

    if config.get("identifiants_titres", True):
        _ajouter_identifiants(soupe)

    if config.get("verifier_hierarchie", True):
        avertissements = _verifier_hierarchie(soupe)
        if not config.get("avertir_h1_multiples", True):
            avertissements = [a for a in avertissements if "niveau h1" not in a]
        resultat.avertissements.extend(avertissements)

    for niveau in NIVEAUX:
        n = len(soupe.find_all(niveau))
        if n:
            resultat.nb_titres[niveau] = n

    # Titre de la page : premier h1, sinon nom du fichier
    premier_h1 = soupe.find("h1")
    resultat.titre = premier_h1.get_text(" ", strip=True) if premier_h1 else Path(nom_fichier).stem

    tdm_html = ""
    if config.get("table_des_matieres", False):
        nav = _construire_tdm(
            soupe,
            int(config.get("niveau_max_tdm", 3)),
            str(config.get("titre_tdm", "Table des matières")),
        )
        if nav is not None:
            if config.get("tdm_dans_fragment", True):
                soupe.insert(0, nav)
            else:
                tdm_html = str(nav)

    fragment = str(soupe)

    gabarit = config.get("gabarit")
    if gabarit:
        chemin_gabarit = (chemin_profil.parent / gabarit).resolve()
        if not chemin_gabarit.exists():
            raise FileNotFoundError(f"Gabarit introuvable : {chemin_gabarit}")
        page = chemin_gabarit.read_text(encoding="utf-8")
        page = (
            page.replace("{{ titre }}", resultat.titre)
            .replace("{{ tdm }}", tdm_html)
            .replace("{{ pied }}", pied_html)
            .replace("{{ contenu }}", fragment)
            .replace("{{ langue }}", str(config.get("langue", "fr")))
        )
        resultat.html = page
    else:
        resultat.html = fragment + pied_html

    return resultat
