from typing import Dict

from domains.filtering import filter_offers
from domains.parsing.parse_abg import parse_abg
from domains.parsing.parse_sfbi import parse_sfbi
from domains.parsing.parse_wttj import parse_wttj
from models.job_offer import JobOffer
from domains.notifications.recap import send_error, send_recap
from parameters.config import DATABASE_PATH, load_profile
from storage.sqlite_storage import find_new_offers, open_database, save_offers

# Association entre le nom d'un site (utilise dans les profils) et sa fonction de parsing.
PARSERS = {
    "sfbi": parse_sfbi,
    "wttj": parse_wttj,
    "abg": parse_abg,
}


def run_pipeline(profile_name: str) -> Dict[str, JobOffer]:
    """Fait tourner les parsers, filtre, envoie puis enregistre les nouvelles offres."""
    profile = load_profile(profile_name)

    all_offers = {}
    for site_name, parse_function in PARSERS.items():
        if site_name in profile.sites:
            try:
                all_offers.update(parse_function())
            except Exception as error:
                # Un site qui plante ne doit pas empecher les autres de tourner.
                send_error(error, profile.name, site_name)

    unique_offers = _remove_duplicates(all_offers)
    filtered_offers = filter_offers(unique_offers, profile)

    connection = open_database(DATABASE_PATH)
    try:
        new_offers = find_new_offers(connection, filtered_offers)
        send_recap(new_offers, profile.name)
        save_offers(connection, new_offers)
    finally:
        connection.close()

    return new_offers


def _remove_duplicates(offers: Dict[str, JobOffer]) -> Dict[str, JobOffer]:
    """Supprime les offres en double (meme URL) au sein d'un meme run."""
    unique_offers = {}
    seen_urls = set()
    for offer in offers.values():
        if offer.url in seen_urls:
            continue
        seen_urls.add(offer.url)
        unique_offers[offer.id_offer] = offer
    return unique_offers
