from models.job_offer import JobOffer
from models.search_profile import SearchProfile


def filter_offers(
    offers: dict[str, JobOffer], profile: SearchProfile
) -> dict[str, JobOffer]:
    """Garde les offres qui matchent les types et mots cles du profil."""
    filtered_offers = {}
    for offer_id, offer in offers.items():
        if profile.job_types and not _matches(offer.job_type, profile.job_types):
            continue

        if profile.title_keywords or profile.description_keywords:
            title_match = _matches(offer.title, profile.title_keywords)
            description_match = _matches(offer.description, profile.description_keywords)
            if not title_match and not description_match:
                continue

        filtered_offers[offer_id] = offer

    return filtered_offers


def _normalize(text: str) -> str:
    """Minuscule et suppression des separateurs pour comparer les textes."""
    return text.lower().replace("-", "").replace("'", "").replace(" ", "")


def _matches(text: str, keywords: list[str]) -> bool:
    """Retourne True si au moins un mot cle est present dans le texte."""
    normalized_text = _normalize(text)
    for keyword in keywords:
        if _normalize(keyword) in normalized_text:
            return True
    return False
