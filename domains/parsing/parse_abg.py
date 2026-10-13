from typing import Dict, List, Optional
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from models.job_offer import JobOffer
from parameters.config import (
    ABG_JOBS_PER_PAGE,
    ABG_MAX_PAGES,
    ABG_SEARCH_QUERIES,
    ABG_URL,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    # La recherche ABG est un endpoint AJAX : ce header change la reponse
    # (fragment de listing au lieu de la page complete).
    "X-Requested-With": "XMLHttpRequest",
}

# Champs attendus par le formulaire de recherche ABG. Envoyer le formulaire
# complet est indispensable : un payload partiel est ignore par le serveur.
SEARCH_DEFAULTS = {
    "orderBy": "updated_at_desc",
    "autoload": "0",
    "criteria[id_type_offre]": "",
    "criteria[id_type_contrat]": "",
    "criteria[id_champs_scientifiques]": "",
    "criteria[id_niveau_etude]": "",
    "criteria[id_metier]": "",
    "criteria[id_off_liste_salaire]": "",
    "criteria[international]": "",
    "criteria[geo_liste_region_id_region]": "",
    "criteria[geo_liste_region_id_region_france]": "",
    "reset_all": "0",
    "commit": "Rechercher",
}


# --- Fonctions Principales Orchestratrices ---


def parse_abg(
    queries: List[str] = ABG_SEARCH_QUERIES, max_pages: int = ABG_MAX_PAGES
) -> Dict[str, JobOffer]:
    """Recupere les offres ABG (recherches ciblees + details) en JobOffer."""
    session = _open_session()
    listings = _fetch_abg_listings(session, queries, max_pages)

    abg_offers = {}
    for listing in listings:
        try:
            detail_html = _fetch_detail(session, listing["url"])
        except requests.RequestException:
            continue

        detail = _parse_detail(detail_html)
        if not detail["description"]:
            continue

        offer = _build_job_offer(listing, detail)
        abg_offers[offer.id_offer] = offer

    return abg_offers


def fetch_abg_offers(
    queries: List[str] = ABG_SEARCH_QUERIES, max_pages: int = ABG_MAX_PAGES
) -> List[dict]:
    """Interroge ABG pour chaque mot cle et retourne les offres de listing.

    Les offres sont dedupliquees par reference ABG : un meme resultat peut
    apparaitre dans plusieurs recherches.
    """
    session = _open_session()
    return _fetch_abg_listings(session, queries, max_pages)


# --- Helpers Internes (Prives) ---


def _open_session() -> requests.Session:
    """Cree une session HTTP reutilisee pour toute la collecte ABG."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _fetch_abg_listings(
    session: requests.Session, queries: List[str], max_pages: int
) -> List[dict]:
    """Pagine chaque recherche et retourne les listings dedupliques."""
    listings = []
    seen_refs = set()

    for query in queries:
        for page in range(1, max_pages + 1):
            html_content = _search_abg_page(session, query, page)
            if html_content is None:
                break

            items = _extract_offer_items(html_content)
            if not items:
                break

            for item in items:
                listing = _parse_list_item(item)
                if listing is None or listing["ref"] in seen_refs:
                    continue
                seen_refs.add(listing["ref"])
                listings.append(listing)

            # Derniere page atteinte si elle est incomplete.
            if len(items) < ABG_JOBS_PER_PAGE:
                break

    return listings


def _search_abg_page(session: requests.Session, query: str, page: int) -> Optional[str]:
    """Execute une recherche ABG et retourne le fragment HTML du listing.

    Retourne None si la requete echoue, ce qui arrete la pagination du mot cle.
    """
    data = dict(SEARCH_DEFAULTS)
    data["page"] = str(page)
    data["criteria[mot_cle]"] = query
    data["criteria[nb_offres_list]"] = str(ABG_JOBS_PER_PAGE)

    try:
        response = session.post(
            f"{ABG_URL}/recherche", data=data, headers=HEADERS, timeout=20
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    return response.text


def _extract_offer_items(html_content: str) -> List[Tag]:
    """Extrait les items d'offres du fragment de listing."""
    soup = BeautifulSoup(html_content, "html.parser")

    items = []
    for item in soup.find_all("div", class_="item"):
        if "it_offre" in item.get("class", []):
            items.append(item)
    return items


def _clean_text(element: Tag) -> str:
    """Recupere le texte d'un element en supprimant les espaces superflus."""
    return " ".join(element.get_text(" ", strip=True).split())


def _parse_list_item(item: Tag) -> Optional[dict]:
    """Transforme un item de listing en dictionnaire intermediaire."""
    link_tag = item.find("a", href=True)
    if not link_tag or not link_tag.has_attr("href"):
        return None

    title = _clean_text(link_tag)
    url = urljoin(ABG_URL, link_tag["href"])
    if not title or not url:
        return None

    # Employeur : texte direct de div.societe, sans le span.type qui suit.
    employer = ""
    type_label = ""
    societe = item.find("div", class_="societe")
    if societe:
        type_tag = societe.find("span", class_="type")
        if type_tag:
            type_label = _clean_text(type_tag)
        direct_text = " ".join(
            text.strip() for text in societe.find_all(string=True, recursive=False)
        )
        employer = " ".join(direct_text.split())

    city = ""
    adresse = item.find("div", class_="adresse")
    if adresse:
        # Adresse du type "Villeurbanne , Region , France" : on garde la ville.
        city = _clean_text(adresse).split(",")[0].strip()

    reference = ""
    ref_tag = item.find("div", class_="ref")
    if ref_tag:
        match = re.search(r"ABG-\d+", _clean_text(ref_tag))
        reference = match.group(0) if match else ""

    published_date = ""
    date_tag = item.find("div", class_="l_date")
    if date_tag:
        published_date = _clean_text(date_tag)

    return {
        "ref": reference or url,
        "title": title,
        "url": url,
        "lab": employer,
        "city": city,
        "job_type": _parse_job_type(type_label),
        "published_date": published_date,
    }


def _parse_job_type(abg_type: str) -> str:
    """Traduit le type d'offre ABG vers le vocabulaire commun du projet."""
    normalized = abg_type.lower()

    if "stage" in normalized:
        return "Stage"
    if "thèse" in normalized or "these" in normalized:
        return "Thèse"
    if "emploi" in normalized:
        return "Emploi"
    return abg_type


def _fetch_detail(session: requests.Session, url: str) -> str:
    """Recupere la page de detail d'une offre."""
    response = session.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def _parse_detail(html_content: str) -> dict:
    """Extrait description, duree, prise de fonction et date limite du detail."""
    soup = BeautifulSoup(html_content, "html.parser")

    # La page de detail est decoupee en blocs div.box dont les titres varient
    # selon le type d'offre (Emploi, These, Stage) : on les concatene tous.
    boxes = soup.find_all("div", class_="box")
    description = " ".join(text for text in (_clean_text(box) for box in boxes) if text)

    page_text = _clean_text(soup)
    deadline_match = re.search(
        r"Date limite de candidature\s+(\d{2}/\d{2}/\d{4})", page_text
    )
    duration_match = re.search(r"Dur[ée]e\s+([0-9]+\s*mois)", page_text)

    return {
        "description": description,
        "deadline": deadline_match.group(1) if deadline_match else "",
        "duration": duration_match.group(1) if duration_match else "",
        "start_date": _extract_start_date(soup),
    }


def _extract_start_date(soup: BeautifulSoup) -> str:
    """Recupere la valeur associee au titre 'Prise de fonction' si presente.

    Structure du site : <h3>Prise de fonction :</h3> suivi d'un <div class="text">.
    """
    for heading in soup.find_all("h3"):
        if "prise de fonction" not in heading.get_text(" ", strip=True).lower():
            continue

        value_tag = heading.find_next_sibling()
        if value_tag is not None:
            return _clean_text(value_tag)
        return ""

    return ""


def _build_job_offer(listing: dict, detail: dict) -> JobOffer:
    """Construit l'objet JobOffer a partir du listing et du detail."""
    return JobOffer(
        title=listing["title"],
        description=detail["description"],
        url=listing["url"],
        source="abg",
        job_type=listing["job_type"],
        duration=detail["duration"],
        lab=listing["lab"],
        city=listing["city"],
        start_date=detail["start_date"],
        deadline=detail["deadline"],
        published_date=listing["published_date"],
    )
