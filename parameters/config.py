import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from models.search_profile import SearchProfile

PARAMETERS_DIR = Path(__file__).parent
PROJECT_ROOT = PARAMETERS_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

SFBI_URL = "https://www.sfbi.fr/emplois/offres-en-cours"

# --- Welcome to the Jungle ---
# WTTJ n'expose pas d'API REST publique classique : son frontend interroge un
# index Algolia public. Les identifiants ci-dessous sont donc publics (visibles
# dans https://www.welcometothejungle.com/api/env) et peuvent etre renouveles
# par WTTJ de temps en temps.
WTTJ_ALGOLIA_APP_ID = "CSEKHVMS53"
WTTJ_ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
WTTJ_ALGOLIA_INDEX = "wttj_jobs_production_fr"
WTTJ_SEARCH_QUERY = "bioinformatics"
WTTJ_PAGES = 2
WTTJ_JOBS_PER_PAGE = 30
WTTJ_WEBSITE_URL = "https://www.welcometothejungle.com/fr/companies"

# --- ABG (Association Bernard Gregory) ---
# Le site rend ses resultats cote serveur : la recherche passe par un POST AJAX
# sur /fr/candidatOffres/recherche avec le formulaire complet. On cible les
# offres avec plusieurs mots cles, puis on lit chaque page de detail.
ABG_URL = "https://www.abg.asso.fr/fr/candidatOffres"
ABG_SEARCH_QUERIES = [
    "bioinformatique",
    "bioinformatics",
    "génomique",
    "genomics",
    "séquençage",
    "sequencing",
    "métagénomique",
    "protéomique",
    "biostatistique",
    "machine learning",
]
ABG_JOBS_PER_PAGE = 50
ABG_MAX_PAGES = 1

# Registre des sites connus du projet.
# Chaque parser du pipeline doit etre repertorie ici avant d'etre activable dans un profil.
SITES = {
    "sfbi": {
        "url": SFBI_URL,
        "label": "SFBI - offres d'emploi en bioinformatique",
    },
    "wttj": {
        "url": "https://www.welcometothejungle.com/fr/jobs",
        "label": "Welcome to the Jungle - offres en France",
    },
    "abg": {
        "url": ABG_URL,
        "label": "ABG - offres pour docteurs (stages, theses, emplois)",
    },
}

PROFILES_FILE = PARAMETERS_DIR / "profiles.yaml"

# Base SQLite locale (couverte par *.db dans .gitignore).
DATABASE_PATH = PROJECT_ROOT / "jobfinder.db"

# Secrets charges depuis .env (a la racine du projet).
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def load_profile(name: str) -> SearchProfile:
    """Charge un profil de recherche depuis parameters/profiles.yaml."""
    data = yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8"))
    profiles = data["profiles"]

    if name not in profiles:
        available = ", ".join(sorted(profiles))
        raise ValueError(f"Profil inconnu : '{name}'. Profils disponibles : {available}")

    values = profiles[name]
    return SearchProfile(
        name=name,
        title_keywords=values.get("title_keywords", []),
        description_keywords=values.get("description_keywords", []),
        job_types=values.get("job_types", []),
        sites=values.get("sites", []),
    )
