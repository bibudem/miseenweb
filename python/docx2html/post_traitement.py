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
  entetes_tableaux    : change en <th> les cellules des lignes d'entête
  notes_tableaux      : sort du tableau la note placée dans sa dernière ligne
  tableaux_larges     : nombre de colonnes à partir duquel un tableau est placé dans une
                        zone à défilement horizontal (0 = jamais, défaut)
  bandeau_avant_titre : donne la classe « bandeau » au paragraphe qui précède le titre
  liens_automatiques  : rend cliquables les adresses web et les courriels
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

NIVEAUX = ["h1", "h2", "h3", "h4", "h5", "h6"]

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

    Si la première ligne a des cellules fusionnées, la deuxième est aussi un entête.
    """
    n = 0
    for tableau in soupe.find_all("table"):
        lignes = tableau.find_all("tr")
        if len(lignes) < 2:
            continue
        entetes = [lignes[0]]
        if len(lignes) > 2 and any(c.get("colspan") for c in lignes[0].find_all("td")):
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


def _largeur_tableau(tableau: Tag) -> int:
    """Nombre de colonnes d'un tableau, cellules fusionnées comprises."""
    return max(
        (sum(int(c.get("colspan", 1)) for c in ligne.find_all(["td", "th"])) for ligne in tableau.find_all("tr")),
        default=0,
    )


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
    return n


def _marquer_bandeau(soupe: BeautifulSoup, classe_titre_document: str) -> bool:
    """Donne la classe « bandeau » au paragraphe de texte qui précède le titre du document."""
    titre = soupe.find("h1", class_=classe_titre_document)
    if titre is None:
        return False
    precedent = titre.find_previous_sibling()
    if precedent is None or precedent.name != "p" or not precedent.get_text(strip=True):
        return False
    precedent["class"] = precedent.get("class", []) + ["bandeau"]
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
    fragment_html: str, config: dict, chemin_profil: Path, nom_fichier: str, pied_html: str = ""
) -> ResultatPostTraitement:
    config = config or {}
    soupe = BeautifulSoup(fragment_html, "html.parser")
    resultat = ResultatPostTraitement(html="")

    if config.get("corriger_faux_titres", False):   # avant la suppression des <p> vides
        _corriger_faux_titres(soupe)

    if config.get("notes_tableaux", False):          # avant le marquage des entêtes
        _sortir_notes_tableaux(soupe)

    if config.get("entetes_tableaux", False):
        _marquer_entetes(soupe)

    if int(config.get("tableaux_larges", 0) or 0) > 0:   # après la sortie des notes
        _encadrer_tableaux_larges(soupe, int(config["tableaux_larges"]))

    if config.get("supprimer_vides", True):
        _supprimer_vides(soupe)

    if config.get("liens_automatiques", False):
        _lier_adresses(soupe)

    if config.get("bandeau_avant_titre", False):    # après la suppression des <p> vides
        _marquer_bandeau(soupe, str(config.get("classe_titre_document", "titre-document")))

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
