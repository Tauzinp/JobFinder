import sqlite3
from pathlib import Path
from typing import Dict

from models.job_offer import JobOffer


def open_database(db_path: Path) -> sqlite3.Connection:
    """Ouvre (ou cree) la base SQLite et prepare la table offers.

    sqlite3.connect() ne contacte aucun serveur : il ouvre simplement le
    fichier db_path et le cree s'il n'existe pas encore. Le dossier parent doit
    deja exister, sinon SQLite leve une erreur.
    """
    # 1. Ouverture du fichier de base de donnees.
    #    La "connexion" est l'objet qui represente la session avec le fichier :
    #    c'est par elle que passent toutes les requetes.
    connection = sqlite3.connect(db_path)

    # 2. Creation de la table si elle n'existe pas deja.
    #    - "CREATE TABLE IF NOT EXISTS" est idempotent : au premier run la
    #      table est creee, aux suivants la commande ne fait rien. C'est une
    #      migration minimale, suffisante tant que le schema ne change pas.
    #    - "INTEGER PRIMARY KEY" est un alias du rowid interne de SQLite : la
    #      valeur s'auto-incremente toute seule, pas besoin d'AUTOINCREMENT.
    #    - "UNIQUE" sur url est la garantie au niveau de la base qu'une meme
    #      offre ne sera jamais enregistree deux fois, meme si le code se
    #      trompe plus tard.
    #    - Les colonnes reprennent les champs de la dataclass JobOffer.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id             INTEGER PRIMARY KEY,
            id_offer       TEXT NOT NULL,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL,
            url            TEXT NOT NULL UNIQUE,
            source         TEXT NOT NULL,
            job_type       TEXT DEFAULT '',
            duration       TEXT DEFAULT '',
            lab            TEXT DEFAULT '',
            city           TEXT DEFAULT '',
            start_date     TEXT DEFAULT '',
            deadline       TEXT DEFAULT '',
            published_date TEXT DEFAULT '',
            added_date     TEXT NOT NULL
        )
        """
    )

    # 3. Index sur les colonnes qui seront utilisees dans les WHERE / GROUP BY.
    #    Un index est comme un sommaire : il accelere les lectures au prix
    #    d'un peu d'espace disque et d'ecriture. Utile ici pour les futures
    #    requetes du type "offres publiees aujourd'hui" ou "par source".
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_offers_published_date ON offers (published_date)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_offers_source ON offers (source)"
    )

    # 4. On valide la creation avant de rendre la connexion au pipeline.
    #    Sans commit, les changements peuvent etre annules (rollback) a la
    #    fermeture de la connexion.
    connection.commit()

    return connection


def find_new_offers(
    connection: sqlite3.Connection, offers: Dict[str, JobOffer]
) -> Dict[str, JobOffer]:
    """Retourne les offres dont l'url n'est pas encore presente en base.

    Cette fonction ne modifie pas la base : c'est un simple SELECT. Elle est
    appelee AVANT l'envoi du recap Discord, pour ne notifier que les offres
    jamais vues. L'insertion (save_offers) aura lieu APRES l'envoi.
    """
    # connection.execute() renvoie un "cursor", un objet iterable qui donne
    # les lignes une par une. Par defaut chaque ligne est un tuple : row[0]
    # correspond donc a la premiere (et unique) colonne du SELECT.
    # Astuce : on pourrait activer connection.row_factory = sqlite3.Row pour
    # acceder aux colonnes par leur nom (row["url"]) au lieu de l'index.
    #
    # On charge tous les urls connus dans un "set" : la recherche "in" est
    # alors quasi instantanee, meme avec des milliers d'offres.
    known_urls = {row[0] for row in connection.execute("SELECT url FROM offers")}

    # On garde les offres absentes de la base, en conservant la cle du
    # dictionnaire (l'id_offer genere pendant le parsing).
    new_offers = {}
    for offer_id, offer in offers.items():
        if offer.url not in known_urls:
            new_offers[offer_id] = offer

    return new_offers


def save_offers(connection: sqlite3.Connection, offers: Dict[str, JobOffer]) -> None:
    """Insere en base les offres qui viennent d'etre envoyees, puis commit.

    Cette fonction est appelee APRES send_recap : si l'envoi Discord echoue,
    rien n'est enregistre et les offres seront retentees au prochain run.
    """
    if not offers:
        return

    # Les valeurs sont passees par des "?" : c'est une requete parametree.
    # C'est indispensable, car les titres contiennent des apostrophes, des
    # accents et parfois des guillemets. Concatener les valeurs directement
    # dans la requete casserait le SQL et ouvrirait la porte a l'injection SQL.
    #
    # INSERT OR IGNORE insere la ligne, sauf si elle viole une contrainte
    # (ici UNIQUE(url)) : dans ce cas SQLite ignore la ligne silencieusement.
    # C'est une securite en plus du SELECT de find_new_offers, par exemple si
    # la meme offre apparait deux fois dans le dictionnaire.
    insert_sql = """
        INSERT OR IGNORE INTO offers
            (id_offer, title, description, url, source, job_type, duration,
             lab, city, start_date, deadline, published_date, added_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Une requete par offre. Le deuxieme argument de execute est un tuple :
    # les valeurs remplacent les "?" dans l'ordre.
    for offer in offers.values():
        connection.execute(
            insert_sql,
            (
                offer.id_offer,
                offer.title,
                offer.description,
                offer.url,
                offer.source,
                offer.job_type,
                offer.duration,
                offer.lab,
                offer.city,
                offer.start_date,
                offer.deadline,
                offer.published_date,
                offer.added_date,
            ),
        )

    # Un seul commit pour tout le lot : les ecritures disque sont groupees,
    # c'est plus rapide que de commiter apres chaque offre. Sans commit, rien
    # n'est definitivement enregistre dans le fichier.
    connection.commit()
