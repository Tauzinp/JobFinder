# SQLite et JobFinder

Ce document présente les bases de SQLite, pourquoi ce choix est adapté à
JobFinder, et comment l'intégrer proprement au projet quand tu seras prêt.

---

## 1. SQLite en deux minutes

SQLite est une bibliothèque (écrite en C) qui implémente un moteur de base de
données relationnelle **dans un simple fichier**.

- Pas de serveur à lancer, pas de port réseau, pas d'utilisateur ni de mot de passe.
- Toute la base tient dans un fichier, par exemple `jobfinder.db`.
- Les transactions respectent les propriétés ACID (Atomicité, Cohérence,
  Isolation, Durabilité).
- Python embarque le module `sqlite3` dans sa bibliothèque standard : rien à
  installer, juste `import sqlite3`.

Différence avec PostgreSQL ou MySQL : ces derniers tournent dans un processus
serveur séparé et sont conçus pour des accès concurrents massifs. SQLite est
conçu pour être intégré dans une application, avec un écrivain à la fois.

---

## 2. Pourquoi SQLite est adapté à JobFinder

- **Un seul processus écrit** : le cron lance le pipeline une fois par jour.
  C'est exactement le cas d'usage de SQLite.
- **Aucune administration** : pas de service à maintenir, pas de configuration
  réseau. Le fichier suffit.
- **Portable** : sauvegarder la base = copier un fichier.
- **Requêtes SQL puissantes** : filtrer les offres du jour, les offres non
  expirées, compter par source, etc. Bien plus pratique qu'un gros JSON.
- **Suffisamment scalable** : SQLite gère sans problème des millions de lignes.
  La limite arrive surtout au niveau des écritures concurrentes, pas ici.

Le site officiel résume bien les cas d'usage :
<https://sqlite.org/whentouse.html>

---

## 3. Premier contact avec le module `sqlite3`

```python
import sqlite3

# Ouvre (ou crée) le fichier de base de données.
connection = sqlite3.connect("jobfinder.db")
cursor = connection.cursor()

cursor.execute(
    "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, nom TEXT NOT NULL)"
)

# INSERT : toujours passer les valeurs par des parametres "?".
# Ne jamais construire la requete avec des f-strings (injection SQL + bugs
# d'echappement avec les apostrophes des titres d'offres).
cursor.execute("INSERT INTO demo (nom) VALUES (?)", ("bioinformatique",))

# Les changements ne sont definitifs qu'apres commit.
connection.commit()
connection.close()
```

Le gestionnaire de contexte `with` gère le commit/rollback automatiquement,
mais **ne ferme pas** la connexion :

```python
with sqlite3.connect("jobfinder.db") as connection:
    connection.execute("INSERT INTO demo (nom) VALUES (?)", ("genomique",))
    # commit automatique si aucune exception, rollback sinon
```

Pour lire les colonnes par leur nom plutôt que par index :

```python
connection.row_factory = sqlite3.Row
cursor = connection.execute("SELECT id, nom FROM demo")
for row in cursor:
    print(row["id"], row["nom"])
```

---

## 4. Schéma de table recommandé

Le plus simple est de calquer les colonnes sur la dataclass `JobOffer` :

```sql
CREATE TABLE IF NOT EXISTS offers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
);

CREATE INDEX IF NOT EXISTS idx_offers_published_date ON offers (published_date);
CREATE INDEX IF NOT EXISTS idx_offers_source ON offers (source);
```

Points importants :

- `INTEGER PRIMARY KEY` est un alias du `rowid` interne de SQLite : il
  s'auto-incrémente, inutile d'écrire `AUTOINCREMENT` sauf besoin précis.
- `UNIQUE` sur `url` est la garantie au niveau base qu'une même offre ne sera
  jamais insérée deux fois.
- `CREATE TABLE IF NOT EXISTS` sert de « migration » minimale : au premier run
  la table est créée, aux suivants la commande ne fait rien.
- `job_type` contient la **catégorie normalisée** de l'offre (`Stage`, `Thèse`,
  `Postdoc`, `Emploi CDD`, `Emploi CDI`, `Concours`) : chaque parser traduit la
  nomenclature de son site vers ce vocabulaire commun.

Si un jour les URLs des sites changent (ou pour dédupliquer entre sites), on
pourra ajouter une colonne `fingerprint` contenant un hash de `title + lab`,
elle aussi `UNIQUE`.

---

## 5. Détecter qu'une offre est réellement nouvelle

Il y a deux approches classiques.

**Option A : `INSERT OR IGNORE` + `rowcount`** (recommandée, atomique)

```python
cursor.execute(
    """
    INSERT OR IGNORE INTO offers
        (id_offer, title, description, url, source, job_type, duration,
         lab, city, start_date, deadline, published_date, added_date)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        offer.id_offer, offer.title, offer.description, offer.url, offer.source,
        offer.job_type, offer.duration, offer.lab, offer.city,
        offer.start_date, offer.deadline, offer.published_date, offer.added_date,
    ),
)

if cursor.rowcount == 1:
    nouvelles_offres.append(offer)
# rowcount == 0 : l'offre existait deja (contrainte UNIQUE sur url)
```

**Option B : vérifier avant d'insérer**

```python
row = connection.execute(
    "SELECT 1 FROM offers WHERE url = ?", (offer.url,)
).fetchone()

if row is None:
    connection.execute("INSERT INTO offers (...) VALUES (...)", (...))
    nouvelles_offres.append(offer)
```

L'option A est plus courte et évite la fenêtre entre le `SELECT` et l'`INSERT`.
Attention : `executemany` insère en lot mais `rowcount` donne le total inséré,
pas la liste des nouvelles lignes. Pour un récapitulatif qui ne liste que les
nouvelles offres, reste sur une boucle avec l'option A.

Astuce SQLite récent (>= 3.35) : `INSERT ... RETURNING id` permet aussi de
récupérer les lignes réellement insérées.

Dans JobFinder, c'est l'**option B** qui est utilisée pour `find_new_offers`
(un `SELECT url FROM offers` avant l'envoi), car l'insertion (`save_offers`) a
lieu seulement **après** l'envoi du récapitulatif. Un `INSERT OR IGNORE` au
moment de l'insertion reste une bonne sécurité.

---

## 6. Requêtes utiles pour le récapitulatif

```sql
-- Offres ajoutees aujourd'hui
SELECT * FROM offers WHERE date(added_date) = date('now');

-- Offres encore ouvertes
SELECT * FROM offers WHERE deadline = '' OR date(deadline) > date('now');

-- Nombre d'offres par source
SELECT source, COUNT(*) AS total FROM offers GROUP BY source;

-- Derniere offre ajoutee par source
SELECT source, MAX(added_date) FROM offers GROUP BY source;
```

⚠️ Les dates affichées par SFBI sont en français (« 27 septembre 2026 »).
SQLite compare des dates au format ISO (`YYYY-MM-DD`). Pour que les requêtes
ci-dessus fonctionnent, il faudra soit convertir les dates au moment du
parsing, soit stocker une colonne supplémentaire `deadline_iso` /
`published_date_iso` en format ISO.

---

## 7. Bonnes pratiques

- **Une connexion par run**, ouverte au début du pipeline et fermée à la fin.
- **Toujours des requêtes paramétrées** (`?`), jamais de concaténation.
- **Un commit par lot cohérent**, pas après chaque ligne (moins d'écritures
  disque). Un seul commit final convient pour ce projet.
- **Ne pas stocker le HTML brut** : uniquement les champs du modèle. La base
  doit rester légère et lisible.
- **Index** sur les colonnes utilisées dans les `WHERE` / `GROUP BY`
  (`url`, `source`, `published_date`, `deadline`).
- **Faire évoluer le schéma** avec `ALTER TABLE offers ADD COLUMN ... DEFAULT ''`
  plutôt que de recréer la table. Pour aller plus loin : `PRAGMA user_version`
  permet de versionner le schéma et d'écrire des migrations.
- **Sauvegarde** : copier le fichier `.db` suffit (à faire hors écriture, ou
  via `.backup`). Le mode `PRAGMA journal_mode = WAL;` améliore la concurrence
  lecture/écriture mais crée des fichiers `-wal` et `-shm` à côté de la base.

---

## 8. Intégration dans l'architecture JobFinder

Le module est déjà en place : `storage/sqlite_storage.py` contient les
signatures, les docstrings et les TODO. Trois fonctions sont attendues :

```python
import sqlite3
from pathlib import Path
from models.job_offer import JobOffer


def open_database(db_path: Path) -> sqlite3.Connection:
    """Ouvre la base et cree la table offers si besoin."""


def find_new_offers(
    connection: sqlite3.Connection, offers: dict[str, JobOffer]
) -> dict[str, JobOffer]:
    """Retourne les offres dont l'url n'est pas encore en base."""


def save_offers(connection: sqlite3.Connection, offers: dict[str, JobOffer]) -> None:
    """Insere en base les offres envoyees (INSERT OR IGNORE) puis commit."""
```

L'enchaînement dans `job_finder.run_pipeline` est le suivant :

1. parsing des sites du profil (avec alerte Discord en cas de crash) ;
2. `_remove_duplicates` (doublons internes à un run) ;
3. `filter_offers` par type d'offre et mots-clés ;
4. `find_new_offers` → `SELECT` des URLs déjà connues, on ne garde que les nouvelles ;
5. `send_recap(nouvelles_offres, profile.name)` ;
6. `save_offers(connection, nouvelles_offres)` → insertion **après** l'envoi.

L'ordre 5 puis 6 est volontaire : si l'envoi Discord échoue, rien n'est
enregistré et les offres seront retentées au prochain run au lieu d'être
perdues. Contrepartie : si l'insertion échoue après un envoi réussi, les offres
seront renvoyées au prochain run.

Ainsi `_remove_duplicates` gère les doublons internes à un run, et la base
gère la nouveauté entre deux runs (le vrai critère pour le récapitulatif).

---

## 9. Exemple complet minimal

```python
import sqlite3

connection = sqlite3.connect(":memory:")  # ":memory:" = base jetable en RAM
connection.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY, url TEXT UNIQUE)")
connection.commit()

urls = [
    "https://exemple.fr/offre/1",
    "https://exemple.fr/offre/2",
    "https://exemple.fr/offre/1",  # doublon
]

nouvelles = []
for url in urls:
    connection.execute("INSERT OR IGNORE INTO offers (url) VALUES (?)", (url,))
    if connection.rowcount == 1:
        nouvelles.append(url)

connection.commit()
print(nouvelles)  # ['https://exemple.fr/offre/1', 'https://exemple.fr/offre/2']

total = connection.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
print(total)  # 2 : le doublon a bien ete ignore
connection.close()
```

---

## 10. Pour aller plus loin

- Module `sqlite3` (Python) : <https://docs.python.org/3/library/sqlite3.html>
- Documentation SQLite : <https://sqlite.org/docs.html>
- Quand utiliser SQLite (et quand ne pas l'utiliser) : <https://sqlite.org/whentouse.html>
- Syntaxe SQL (tutoriel) : <https://sqlite.org/lang.html>
