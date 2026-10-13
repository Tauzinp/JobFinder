import sys
import traceback
from typing import Dict, List

import requests

from models.job_offer import JobOffer
from parameters.config import DISCORD_WEBHOOK_URL

# Limite imposee par Discord pour le contenu d'un message.
DISCORD_CONTENT_LIMIT = 2000

# Nombre de caracteres de traceback conserves dans l'alerte de crash.
MAX_ERROR_TRACEBACK = 1500


def send_recap(offers: Dict[str, JobOffer], profile_name: str) -> None:
    """Envoie le recapitulatif des offres filtrees sur le webhook Discord."""
    if not offers:
        return

    if not DISCORD_WEBHOOK_URL:
        raise ValueError(
            "DISCORD_WEBHOOK_URL est vide : renseigne l'URL du webhook dans le fichier .env"
        )

    for message in _build_messages(offers, profile_name):
        _post_to_discord(message)


def send_error(error: Exception, profile_name: str, site_name: str = "") -> None:
    """Previent sur Discord qu'un parsing a echoue, avec le traceback tronque."""
    if not DISCORD_WEBHOOK_URL:
        print(
            f"Erreur de parsing ({site_name or 'site inconnu'}) : {error}",
            file=sys.stderr,
        )
        return

    message = f"**Crash du parsing — profil « {profile_name} »**"
    if site_name:
        message += f"\nSite : {site_name}"
    message += f"\n`{type(error).__name__} : {error}`"

    traceback_text = "".join(traceback.format_exception(error))
    if traceback_text.strip():
        message += f"\n```\n{traceback_text[-MAX_ERROR_TRACEBACK:]}\n```"

    try:
        _post_to_discord(message[:DISCORD_CONTENT_LIMIT])
    except requests.RequestException as post_error:
        print(f"Impossible d'envoyer l'alerte Discord : {post_error}", file=sys.stderr)


def _build_messages(offers: Dict[str, JobOffer], profile_name: str) -> List[str]:
    """Decoupe la liste des offres en messages de moins de 2000 caracteres."""
    header = f"**{len(offers)} offre(s) pour le profil « {profile_name} »**"

    messages = []
    current_message = header
    for offer in offers.values():
        line = _format_offer(offer)
        if len(current_message) + len(line) + 1 > DISCORD_CONTENT_LIMIT:
            messages.append(current_message)
            current_message = line
        else:
            current_message += "\n" + line

    messages.append(current_message)
    return messages


def _format_offer(offer: JobOffer) -> str:
    """Formate une offre en une ligne Markdown avec lien sur le titre."""
    details = [offer.city, offer.job_type]
    if offer.deadline:
        details.append(f"limite : {offer.deadline}")

    details_text = " · ".join(detail for detail in details if detail)
    line = f"- [{offer.title}]({offer.url})"
    if details_text:
        line += f" — {details_text}"
    return line


def _post_to_discord(content: str) -> None:
    """Envoie un message au webhook Discord."""
    response = requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=15)
    response.raise_for_status()
