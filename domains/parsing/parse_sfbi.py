from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from models.job_offer import JobOffer
from parameters.config import SFBI_URL

HEADERS = {"User-Agent": "Mozilla/5.0"}


# --- Fonction Principale Orchestratrice ---


def parse_sfbi() -> Dict[str, JobOffer]:
    """Recupere les offres du SFBI (liste + pages de detail) et les transforme en JobOffer."""
    html_content = _fetch_page(SFBI_URL)
    rows = _extract_job_rows(html_content)

    sfbi_offers = {}
    for row in rows:
        summary = _parse_list_row(row, base_url=SFBI_URL)
        if summary is None:
            continue

        try:
            detail_html = _fetch_page(summary["url"])
        except requests.RequestException:
            continue

        description = _extract_description(detail_html)
        if not description:
            continue

        offer = _build_job_offer(summary, description)
        sfbi_offers[offer.id_offer] = offer

    return sfbi_offers


# --- Helpers Internes (Prives) ---


def _fetch_page(url: str) -> str:
    """Recupere le contenu HTML d'une page."""
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.text


def _extract_job_rows(html_content: str) -> List[Tag]:
    """Parse le HTML et extrait les lignes (tr) du tableau d'offres."""
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", id="offreEmploi")
    if not table or not table.find("tbody"):
        return []
    return table.find("tbody").find_all("tr")


def _clean_text(element: Tag) -> str:
    """Recupere le texte d'un element en supprimant les espaces superflus."""
    return " ".join(element.get_text(" ", strip=True).split())


def _parse_job_type(post_type: str, contract_type: str) -> str:
    """Traduit le type d'offre SFBI vers le vocabulaire commun du projet."""
    normalized_post = post_type.lower()
    normalized_contract = contract_type.lower()

    if "stage" in normalized_post or "stage" in normalized_contract:
        return "Stage"
    if "thèse" in normalized_post:
        return "Thèse"
    if "postdoc" in normalized_post:
        return "Postdoc"
    if "cdi" in normalized_contract:
        return "Emploi CDI"
    if "cdd" in normalized_contract:
        return "Emploi CDD"
    if "concours" in normalized_contract:
        return "Concours"
    return post_type or contract_type


def _parse_list_row(row: Tag, base_url: str) -> Optional[dict]:
    """Transforme une ligne du tableau en dictionnaire intermediaire."""
    cells = row.find_all("td")
    if len(cells) != 10:
        return None

    link_tag = cells[0].find("a")
    title = _clean_text(link_tag) if link_tag else _clean_text(cells[0])
    relative_url = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
    if not title or not relative_url:
        return None

    post_type = _clean_text(cells[2])
    contract_type = _clean_text(cells[3])

    return {
        "title": title,
        "url": urljoin(base_url, relative_url),
        "job_type": _parse_job_type(post_type, contract_type),
        "duration": _clean_text(cells[4]),
        "lab": _clean_text(cells[5]),
        "city": _clean_text(cells[6]),
        "start_date": _clean_text(cells[7]),
        "deadline": _clean_text(cells[8]),
        "published_date": _clean_text(cells[9]),
    }


def _extract_description(html_content: str) -> str:
    """Recupere la description complete d'une offre depuis sa page de detail."""
    soup = BeautifulSoup(html_content, "html.parser")
    description_tag = soup.find("p", class_="descrOffre")
    if not description_tag:
        return ""
    return _clean_text(description_tag)


def _build_job_offer(summary: dict, description: str) -> JobOffer:
    """Construit l'objet JobOffer a partir du resume et de la description."""
    return JobOffer(
        title=summary["title"],
        description=description,
        url=summary["url"],
        source="sfbi",
        job_type=summary["job_type"],
        duration=summary["duration"],
        lab=summary["lab"],
        city=summary["city"],
        start_date=summary["start_date"],
        deadline=summary["deadline"],
        published_date=summary["published_date"],
    )
