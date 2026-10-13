# JobFinder

Agrégateur d'offres de **stages, thèses et emplois en bioinformatique** : les
offres sont collectées sur plusieurs sites, filtrées par profil de recherche,
envoyées sur Discord et conservées dans une base SQLite locale.

> **Projet test d'ingénierie agentique.** JobFinder a été conçu et développé
> comme un banc d'essai de l'**ingénierie agentique** (*agentic engineering*)
> avec [opencode](https://opencode.ai) : l'agent a exploré les sites, écrit le
> code, lancé les tests et les runs réels, tandis que l'humain a validé chaque
> bloc fonctionnel (choix d'architecture, revues de code, réponse aux questions
> de cadrage). Le dépôt est donc autant une démonstration de ce mode de
> développement qu'un outil réellement fonctionnel.

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Sites pris en charge](#sites-pris-en-charge)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Stockage et déduplication](#stockage-et-déduplication)
- [Automatisation (cron)](#automatisation-cron)
- [Ajouter un nouveau site](#ajouter-un-nouveau-site)
- [Limites connues](#limites-connues)

---

## Fonctionnalités

- Parsing indépendant de chaque site (un module par site).
- Filtrage par **profil de recherche** : type d'offre, mots-clés du titre,
  mots-clés de la description.
- Envoi d'un **récapitulatif Discord** découpé en messages de moins de
  2000 caractères.
- **Alerte Discord** en cas de crash d'un parser (avec traceback tronqué).
- Stockage SQLite avec **déduplication inter-runs** par URL : une offre déjà
  notifiée ne l'est jamais deux fois.
- Orchestration CLI simple et compatible cron.

## Sites pris en charge

| Site | Accès | Statut |
|---|---|---|
| [SFBI](https://www.sfbi.fr/emplois/offres-en-cours) | HTML (BeautifulSoup) + pages de détail | Intégré |
| [Welcome to the Jungle](https://www.welcometothejungle.com/fr/jobs) | Index Algolia public | Intégré |
| [ABG](https://www.abg.asso.fr/fr/) | HTML (recherche AJAX + pages de détail) | Intégré |
| Indeed, Academic Transfer, LinkedIn | — | Envisagé |

## Architecture

```
JobFinder/
├── cli.py                      # Point d'entrée Typer (option --profil)
├── job_finder.py               # Orchestrateur du pipeline
├── models/
│   ├── job_offer.py            # Dataclass JobOffer (données d'une offre)
│   └── search_profile.py       # Dataclass SearchProfile (critères de recherche)
├── parameters/
│   ├── config.py               # Constantes, registre SITES, chargement .env
│   └── profiles.yaml           # Profils de recherche (mots-clés, types, sites)
├── domains/
│   ├── parsing/                # Un parser par site
│   │   ├── parse_sfbi.py
│   │   ├── parse_wttj.py
│   │   └── parse_abg.py
│   ├── filtering.py            # Filtrage par profil
│   └── notifications/recap.py  # Envoi Discord (récap + alertes)
├── storage/
│   └── sqlite_storage.py       # Base SQLite (catalogue + déduplication)
├── SQLITE.md                   # Documentation pédagogique sur SQLite
└── .env                        # Secrets locaux (webhook Discord), non versionné
```

### Pipeline (`job_finder.run_pipeline`)

1. **Chargement du profil** (`parameters/profiles.yaml`).
2. **Parsing** des sites listés dans le profil : chaque parser retourne un
   dictionnaire `{id_offre: JobOffer}`. Un site en échec déclenche une alerte
   Discord sans bloquer les autres.
3. **Déduplication intra-run** par URL.
4. **Filtrage** : type d'offre obligatoire (si défini) ET (mot-clé de titre OU
   mot-clé de description).
5. **Détection des nouveautés** : `SELECT` des URLs déjà connues en base.
6. **Envoi Discord** des seules offres nouvelles.
7. **Insertion en base** après l'envoi (si l'envoi échoue, rien n'est
   enregistré et les offres seront retentées au prochain run).

## Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) et Python ≥ 3.14.

```bash
git clone <url-du-depot>
cd JobFinder
uv sync
```

## Configuration

### Profils de recherche — `parameters/profiles.yaml`

Chaque profil définit :

- `job_types` : types acceptés (`Stage`, `Thèse`, `Postdoc`, `Emploi CDD`,
  `Emploi CDI`, `Concours`, `Emploi`, `Alternance`…). Liste vide = tous.
- `title_keywords` : mots-clés cherchés dans le titre.
- `description_keywords` : mots-clés cherchés dans la description.
- `sites` : sites à parser (doivent exister dans `SITES`, `parameters/config.py`).

Exemple :

```yaml
profiles:
  bioinformatique:
    job_types:
      - Stage
    title_keywords:
      - bioinformatique
      - bioinformatics
    description_keywords:
      - génomique
      - séquençage
    sites:
      - sfbi
      - wttj
      - abg
```

Chaque parser traduit la nomenclature de son site vers ce vocabulaire commun
(ex. `Sujet de Thèse` → `Thèse`, `internship` → `Stage`).

### Secrets — `.env`

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Le fichier `.env` est ignoré par git. Sans webhook valide, `send_recap` et
`send_error` ne peuvent rien envoyer.

## Utilisation

```bash
# Profil par défaut (bioinformatique, stages)
uv run python cli.py

# Profil explicite
uv run python cli.py --profil bioinformatique
uv run python cli.py --profil bioinformatique-these

# Aide
uv run python cli.py --help
```

La commande affiche le nombre de nouvelles offres envoyées.

## Stockage et déduplication

Les offres sont stockées dans `jobfinder.db` (gitignoré). La table `offers` a
une contrainte `UNIQUE(url)` : une même offre ne peut être enregistrée deux
fois. La déduplication est donc **globale par URL**, inter-runs (SQLite) et
intra-run (dictionnaire).

La documentation détaillée (schéma, requêtes, bonnes pratiques) se trouve dans
[`SQLITE.md`](SQLITE.md).

## Automatisation (cron)

Exemple de crontab quotidien (8 h) :

```cron
0 8 * * * cd /chemin/vers/JobFinder && /chemin/vers/uv run python cli.py --profil bioinformatique
0 8 30 * * cd /chemin/vers/JobFinder && /chemin/vers/uv run python cli.py --profil bioinformatique-these
```

## Ajouter un nouveau site

1. Créer `domains/parsing/parse_<site>.py` sur le modèle de `parse_sfbi.py` :
   une fonction publique `parse_<site>() -> Dict[str, JobOffer]` et des helpers
   privés.
2. Mapper le type d'offre du site vers le vocabulaire commun (`_parse_job_type`).
3. Déclarer le site dans `SITES` (`parameters/config.py`).
4. L'enregistrer dans `PARSERS` (`job_finder.py`).
5. L'ajouter aux `sites` des profils concernés dans `parameters/profiles.yaml`.

## Limites connues

- **Dates** : SFBI/ABG fournissent des dates texte (`27 septembre 2026`,
  `01/11/2026`), pas encore converties en ISO — voir la note dans `SQLITE.md`.
- **Clés WTTJ** : l'index Algolia utilise une clé publique extraite de
  `https://www.welcometothejungle.com/api/env`. Si WTTJ la renouvelle, mettre à
  jour `WTTJ_ALGOLIA_APP_ID` / `WTTJ_ALGOLIA_API_KEY` dans
  `parameters/config.py`.
- **Déduplication** : globale par URL, pas par profil. Deux profils ne
  renverront jamais la même offre.
- **Description ABG** : concaténation des blocs de la page de détail (inclut
  quelques métadonnées comme la durée et la date limite).
- **LinkedIn** : non implémenté (nécessiterait un service tiers type SerpAPI).
