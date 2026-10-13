import secrets
from dataclasses import dataclass, field
from datetime import datetime


def _new_offer_id() -> str:
    """Génère un identifiant aléatoire unique pour une offre."""
    return secrets.token_hex(3)


def _current_datetime() -> str:
    """Retourne la date et l'heure courantes au format SQLite."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class JobOffer:
    title: str
    description: str
    url: str
    source: str
    job_type: str = ""
    duration: str = ""
    lab: str = ""
    city: str = ""
    start_date: str = ""
    deadline: str = ""
    published_date: str = ""
    id_offer: str = field(default_factory=_new_offer_id)
    added_date: str = field(default_factory=_current_datetime)

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("JobOffer.title ne peut pas être vide")
        if not self.description or not self.description.strip():
            raise ValueError("JobOffer.description ne peut pas être vide")
