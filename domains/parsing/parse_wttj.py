from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from models.job_offer import JobOffer
from parameters.config import (
    WTTJ_ALGOLIA_API_KEY,
    WTTJ_ALGOLIA_APP_ID,
    WTTJ_ALGOLIA_INDEX,
    WTTJ_JOBS_PER_PAGE,
    WTTJ_PAGES,
    WTTJ_SEARCH_QUERY,
    WTTJ_WEBSITE_URL,
)

# WTTJ expose un index Algolia public. L'URL ci-dessous est celle utilisee par
# le frontend du site pour la recherche d'offres.
ALGOLIA_URL = (
    f"https://{WTTJ_ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
    f"/1/indexes/{WTTJ_ALGOLIA_INDEX}/query"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    # Identifiants Algolia publics + en-tetes exiges par la cle de recherche.
    "x-algolia-application-id": WTTJ_ALGOLIA_APP_ID,
    "x-algolia-api-key": WTTJ_ALGOLIA_API_KEY,
    "Origin": "https://www.welcometothejungle.com",
    "Referer": "https://www.welcometothejungle.com/",
}

# Filtre Algolia conserve cote serveur : on ne veut que les stages.
INTERNSHIP_FILTER = [["contract_type:internship"]]


# --- Fonction Principale Orchestratrice ---


def parse_wttj(
    query: str = WTTJ_SEARCH_QUERY, pages: int = WTTJ_PAGES
) -> Dict[str, JobOffer]:
    """Recupere les stages WTTJ et les transforme en JobOffer."""
    internships = fetch_wttj_internships(query=query, pages=pages)

    wttj_offers = {}
    for internship in internships:
        if not internship["description"]:
            continue

        offer = _build_job_offer(internship)
        wttj_offers[offer.id_offer] = offer

    return wttj_offers


def fetch_wttj_internships(
    query: str = WTTJ_SEARCH_QUERY, pages: int = WTTJ_PAGES
) -> List[dict]:
    """Interroge WTTJ et retourne les stages normalises.

    La pagination s'arrete proprement des qu'une page echoue (statut HTTP
    different de 200) ou ne renvoie plus d'offres (liste `hits` vide).
    """
    internships = []
    for page in range(pages):
        response_data = _search_wttj_page(query, page)
        if response_data is None:
            break

        hits = response_data.get("hits")
        if not hits:
            break

        for hit in hits:
            internships.append(_normalize_job(hit))

    return internships


# --- Helpers Internes (Prives) ---


def _search_wttj_page(query: str, page: int) -> Optional[dict]:
    """Execute une requete de recherche sur l'index Algolia de WTTJ.

    Attention : la pagination Algolia demarre a 0 (la premiere page est 0).
    Retourne None si la requete echoue, ce qui arrete la pagination.
    """
    payload = {
        "query": query,
        "page": page,
        "hitsPerPage": WTTJ_JOBS_PER_PAGE,
        "facetFilters": INTERNSHIP_FILTER,
    }

    try:
        response = requests.post(ALGOLIA_URL, headers=HEADERS, json=payload, timeout=15)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    return response.json()


def _normalize_job(hit: dict) -> dict:
    """Normalise un resultat WTTJ au format intermediaire du projet."""
    organization = hit.get("organization") or {}
    organization_slug = organization.get("slug", "")

    # Selon les offres, l'API remplit `office` (objet) ou `offices` (liste).
    offices = hit.get("offices") or []
    first_office = offices[0] if offices else hit.get("office") or {}
    location = first_office.get("city") or ""

    slug = hit.get("slug", "")
    job_id = hit.get("reference") or hit.get("objectID") or ""

    return {
        "id": f"wttj_{job_id}",
        "title": hit.get("name", ""),
        "company": organization.get("name", ""),
        "location": location,
        "url": f"{WTTJ_WEBSITE_URL}/{organization_slug}/jobs/{slug}",
        "created_at": hit.get("published_at") or hit.get("published_at_date") or "",
        # Champs supplementaires necessaires a la construction du JobOffer.
        "description": _build_description(hit),
        "job_type": _parse_job_type(hit.get("contract_type", "")),
        "duration": _format_duration(hit),
    }


def _build_description(hit: dict) -> str:
    """Assemble la description a partir du resume, des missions et du profil."""
    parts = []
    for field in ("summary", "profile"):
        value = hit.get(field)
        if value:
            parts.append(value)
    parts.extend(hit.get("key_missions") or [])
    return _clean_text(" ".join(parts))


def _clean_text(text: str) -> str:
    """Supprime le HTML et les espaces superflus d'un texte."""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def _parse_job_type(contract_type: str) -> str:
    """Traduit le type de contrat WTTJ vers le vocabulaire commun du projet."""
    normalized = contract_type.lower()

    if "internship" in normalized:
        return "Stage"
    if "apprenticeship" in normalized:
        return "Alternance"
    if "fixed_term" in normalized or "temporary" in normalized:
        return "Emploi CDD"
    if "full_time" in normalized or "part_time" in normalized:
        return "Emploi CDI"
    if "freelance" in normalized:
        return "Freelance"
    return contract_type


def _format_duration(hit: dict) -> str:
    """Formate la duree du contrat (ex. '5-6 mois') quand elle est renseignee."""
    minimum = hit.get("contract_duration_minimum")
    maximum = hit.get("contract_duration_maximum")

    if minimum and maximum and minimum != maximum:
        return f"{minimum}-{maximum} mois"
    if minimum:
        return f"{minimum} mois"
    if maximum:
        return f"{maximum} mois"
    return ""


def _build_job_offer(internship: dict) -> JobOffer:
    """Construit l'objet JobOffer a partir d'un stage normalise."""
    return JobOffer(
        title=internship["title"],
        description=internship["description"],
        url=internship["url"],
        source="wttj",
        job_type=internship["job_type"],
        duration=internship["duration"],
        lab=internship["company"],
        city=internship["location"],
        published_date=internship["created_at"],
    )
