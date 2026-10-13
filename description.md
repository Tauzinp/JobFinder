JobFinder est un parser d'offres de stage, thèses, emplois relatifs à la bioinformatique.

Basé sur les sites :

- SFBI
- Welcome to the jungle
- Indeed
- Academic Transfer
- ABG
- Linked in (serpapi rapidapi ?)

Les données ainsi agrégées sont stockées dans une bdd SQLite.

Un crontab est établit pour l'envoie automatique journalier d'un message récapitulant les offres en cours.

Niveau architecture il faut respecter une définition claire :

- cli.py : définit les input à passer au module typer. pour l'instant je ne vois qu'un input :
  - le profil sélectionné (pour cibler un domaine particulier)
- job_finder.py : point d'entrée principal, récupère les infos de la cli et fait tourner le pipeline de récupération des données
- domains/ : contient différents fichiers. Chaque fichier porte une fonction utilisée dans le pipeline.
  On essaie de respecter la division par responsabilité unique en divisant les fonctions en différents helper.
  Chaque bloc de fonction unique avec ses helper permettra le parsing d'un unique site.

- models/ : contient les différentes dataclass. Chaque état intermédiaire d'information devra passer par une dataclass.
  Les dataclass ne porteront que de très légères fonction (le moin de logique possible) : uniquement de petites @property ou @post_init pour valider les données

- parameters/ : contiendra les différents fichiers de config

Au niveau de la logique :
Il faut que le code soit le plus simple possible à comprendre : pas de syntaxe trop avancée, ou de librairie obscure.

Chaque site sera parsé indépendament.
Chaque fonction utilisera beautiful soup pour parser le site en question.
Chaque fonction remplira un objet JobOffer. Les différentes job se verront attribuer une id aléatoire unique pendant le processus.
Chaque fonction remplira un dictionnaire{id_unique:JobOffer}
L'orchestrateur job_finder.py fera tourner chaque pipeline et mettra à jour un dictionnaire unique à partir des jobs parsés.
Les fonctions à faire tourner (et donc les sites à parser) seront donnés par la liste définit par l'input profil

Pour que le projet soit adaptable à différents sujets et à différents niveau (stage, thèses, cdd) et donc scalable
sur le long terme. Il faut que tous les sites soient répertoriés dans la config.
On considèrera que chaque job parsé contient à minimat un titre et une description.
La config portera alors plusieurs profils,
pour différents types de recherche. Chaque profil contiendra des mots clés permettant de filtré les offres par domaine,
et aussi la liste des sites à parser (qui sera récupérer par l'orchestrateur, qui avant chaque fonction vérifiera si le site est dans la liste avec un if)

Par exemple le profil bioinformatique portera 3 infos :
titre : ai, automatisation, sequencing, ...
descripion : bioinformatics, bioingineering, ...
sites : welcome to the jungle, sfbi, ...

Il y aura donc une fonction finale de remplissage d'un bd en SQLite, et un moyen de vérification que chaque offre est réellement nouvelle.

Pour l'instant, je ne sais pas comment fonction vraiment SQLite et je souhaite l'apprendre, donc il ne faudra pas toucher à cette fonction de remplissage et de tri.
