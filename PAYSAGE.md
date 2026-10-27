# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/LANDSCAPE.md)

Où se situe wallet-helper parmi les outils de mise en cache, de mémoïsation, de
single-flight et d'idempotence. Les pièces existent séparément. Ce qui est rare,
c'est la combinaison : une mémoïsation persistante et adressée par contenu qui
fusionne aussi les appels identiques concurrents, dans un processus et entre
processus, tout en restant locale (aucun service séparé requis).

Une note sur les dépendances : wallet-helper a une seule dépendance directe,
os-helper (la couche utilitaire partagée de la suite AI Helpers), qui à son tour
tire quelques bibliothèques courantes (requests, pyyaml, tqdm, validators,
python-dotenv, psutil). Il est donc local-first et autonome au niveau du service, mais
pas exempt de dépendances.

Deux problèmes font qu'un appel lourd tourne deux fois :

- **La répétition dans le temps.** Vous le rappelez au prochain lancement ou la
  semaine suivante. Un cache persistant résout cela.
- **La concurrence.** Deux appelants démarrent le même appel avant que l'un ne
  finisse. Le single-flight (aussi appelé coalescence de requêtes, dogpile,
  protection contre les avalanches) résout cela.

La plupart des outils ne traitent qu'un seul problème. wallet-helper traite les
deux, avec la même clé.

## En un coup d'œil

Noté de ⭐ (absent ou faible) à ⭐⭐⭐⭐⭐ (meilleur de sa catégorie) par colonne.
Ces notes sont la lecture que fait un mainteneur de la documentation de chaque
projet, pas un banc d'essai ; la section
[Sources et date de relevé](#sources-et-date-de-relevé) dit d'où elles viennent
puis quand.

- **Persistant** : les résultats survivent à un redémarrage de processus.
- **Adresse par contenu d'entrée** : la clé porte sur le contenu d'un fichier ou des octets bruts, pas seulement sur les arguments.
- **Single-flight intra-processus** : les appels identiques concurrents dans un processus fusionnent en un seul.
- **Single-flight inter-processus** : idem, entre processus ou hôtes.
- **TTL / expiration** : fraîcheur par entrée avec expiration et éviction.
- **Serveur pour plusieurs clients** : un point d'accès partagé qui centralise la déduplication.
- **Décorateur** : ergonomie transparente `@decorator`.
- **Support asynchrone** : fonctionne avec les coroutines `async def`, pas seulement les fonctions synchrones.
- **Local (sans service)** : fonctionne sans base de données ni serveur de cache séparé. Il s'agit de l'empreinte de déploiement, pas du nombre de dépendances.
- **Taux de touche visible** : le magasin sait dire s'il est rentable — pas
  seulement combien d'entrées il détient, mais combien d'appels il a servis puis
  manqués depuis le début.

<!-- TABLE:START -->
| Mise en cache | Persistant | Adresse par contenu d'entrée | Single-flight intra-processus | Single-flight inter-processus | TTL / expiration | Serveur pour plusieurs clients | Décorateur | Support asynchrone | Local (sans service) | Taux de touche visible |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **wallet-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| functools.lru_cache | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| joblib.Memory | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| diskcache | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| cachier | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| requests-cache | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| dogpile.cache | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ |
| Redis | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| Go singleflight | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ |
| AWS Powertools Idempotency | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| Stripe idempotency keys | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| litellm cache | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| cashews | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| cacheme | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| GPTCache (sémantique) | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/paysage.png)

La carte est un résumé en 2D des 10 critères : à lire comme une forme, pas comme un classement. « wallet-helper » se situe dans le coin en haut à droite. Les axes se lisent **Horizontal : Autonomie ↔ Efficacité** et **Vertical : Adaptabilité ↔ Créativité**.
<!-- FIGURE:END -->

## Positionnement

Les colonnes qui situent wallet-helper sont **Adresse par contenu d'entrée** puis
les deux colonnes de single-flight, à lire avec **Local (sans service)**.

Prises une par une, elles découpent le terrain proprement. La persistance est
partout : `joblib.Memory`, `diskcache`, `cachier` et `requests-cache` survivent
tous à un redémarrage. La coalescence n'est pas rare non plus : le
`singleflight` de Go en est la primitive de référence, `dogpile.cache` a
`get_or_create` depuis des années, `cashews` et `cacheme` livrent une protection
anti-avalanche. L'adressage par contenu existe aussi — c'est la signature de
`joblib.Memory`.

Ce qui est rare, c'est de tenir les trois *avec une seule clé et sans service*.
Les outils qui fusionnent entre processus le font le plus souvent en déléguant à
quelque chose qu'il faut faire tourner : redis pour `dogpile.cache`, `cashews`
puis `cacheme`, DynamoDB ou redis pour AWS Powertools Idempotency. Chez eux,
« local » et « inter-processus » ne sont pas vrais en même temps. La voie
inter-processus de wallet-helper est un bail protégé dans un fichier SQLite, ou
dans son propre petit serveur HTTP : un portable et une flotte exécutent le même
code, seul le backend change.

Cette forme — le coin en haut à droite de la carte — s'achète au prix de la
forme opposée. Redis occupe volontairement l'autre bout de l'axe Autonomie ↔
Efficacité : c'est le magasin partagé et exploité sur lequel beaucoup de ces
outils s'appuient et rien ici ne lui dispute l'échelle d'une flotte.
wallet-helper revendique délibérément moins — un fichier ou un dossier, aucun
démon, rien à exploiter — et devient le mauvais outil dès qu'on veut un cache
que plusieurs équipes administrent comme une infrastructure.

## Avantages et inconvénients

| Mise en cache | Avantages | Inconvénients |
|---|---|---|
| **wallet-helper** | Persistant et adressé par contenu (hache le contenu des fichiers et les octets, pas seulement les arguments) ; single-flight intra-processus (threads) et inter-processus (un bail SQLite ou HTTP protégé, de sorte qu'un leader planté ou bloqué ne peut pas gêner un nouveau leader) ; synchrone et asynchrone (`async def`) ; durée de vie, stale-while-revalidate et éviction automatique ; serveur HTTP optionnel et `RemoteLedger` centralisent la déduplication pour une flotte ; simple `@memoize` ; fonctionne sans service séparé. | Plus jeune et plus petit que les vétérans ; une dépendance directe (os-helper) qui tire quelques bibliothèques transitives ; le bail inter-processus a besoin du backend SQLite ou du serveur ; pas de fenêtres de budget glissantes ni de correspondance sémantique (par embeddings). |
| `functools.lru_cache` | De la bibliothèque standard, zéro configuration, excellent `cache_info()`. | En mémoire seulement (perdu au redémarrage) ; la clé porte sur les arguments seuls ; ne fusionne pas les appels concurrents ; borné par `maxsize`. |
| `joblib.Memory` | Mature ; persiste sur disque ; hache le contenu des arguments (compatible numpy) ; invalide quand le source de la fonction change. | Pas de coalescence des appels concurrents ; plus lourd ; orienté pipelines scientifiques. |
| `diskcache` | Stockage SQLite rapide ; tags et éviction en masse ; `memoize_stampede` ; verrous. | La clé porte sur les arguments, pas sur le contenu du fichier d'entrée ; mono-hôte ; les outils anti-avalanche sont optionnels et séparés. |
| `cachier` | Décorateur simple ; durée de vie (`stale_after`) ; plusieurs backends. | Pas de vrai single-flight ; l'usage distribué nécessite mongo ou redis. |
| `requests-cache` | Transparent pour `requests` ; riches métadonnées de cache par réponse. | HTTP seulement ; pas de coalescence ; pas pour des fonctions arbitraires. |
| `dogpile.cache` | Vrai verrou dogpile (`get_or_create`) ; stale-while-revalidate ; extensible. | A besoin d'un backend de cache (memcached, redis) pour le cas partagé ; plus de pièces mobiles. |
| Redis | Le pôle scalable opposé à wallet-helper : le magasin en mémoire sur lequel beaucoup de ces outils s'appuient ; TTL et éviction ; un serveur partagé qui centralise l'état entre clients et hôtes ; clients asynchrones. | Un service séparé à faire tourner et exploiter, donc ni local ni autonome ; vous gérez les clés explicitement, sans adressage par contenu d'entrée ; pas de coalescence d'appels ni de `@decorator` intégrés ; single-flight seulement si vous ajoutez un verrou par-dessus. |
| Go `singleflight` | La primitive de référence de coalescence en vol ; minuscule. | En vol seulement (pas de cache) ; mono-processus ; en Go, pas en Python. |
| AWS Powertools Idempotency | Bail INPROGRESS robuste ; suppression en cas d'échec ; expiration ; éprouvé. | A besoin de DynamoDB ou redis ; les suiveurs rejettent-et-réessaient au lieu d'attendre ; centré sur AWS. |
| Stripe idempotency keys | Standard de l'industrie ; rejoue les résultats terminés ; rejette les doublons concurrents. | Distant et lié au compte ; HTTP seulement ; l'appelant doit gérer les clés. |
| `litellm` cache | Mise en cache plus fonctionnalités fournisseur pour les LLM. | LLM seulement ; grosse dépendance ; pas d'adressage par contenu d'entrées arbitraires. |
| `cashews` | Cache moderne à décorateur, async-first ; TTL / modèles de clé ; protection anti-avalanche intégrée (`lock=True`, recalcul anticipé) ; backends mémoire / disque / redis. | Asynchrone seulement ; la clé porte sur les arguments / modèles, pas sur le contenu du fichier d'entrée ; le verrou distribué (inter-processus) a besoin de redis, donc « local » et « inter-processus » ne sont pas vrais en même temps. |
| `cacheme` | Framework de cache asyncio avec forte protection contre l'avalanche (single-flight) ; nœuds typés ; stockage extensible (TLRU en mémoire, redis, mongo). | Asynchrone seulement ; la clé porte sur les arguments de nœud, pas sur le contenu d'entrée ; l'inter-processus nécessite redis / mongo ; pas de voie inter-processus locale et autonome. |
| GPTCache (sémantique) | Un autre axe : fait correspondre des invites *similaires* via embeddings + recherche vectorielle, donc les paraphrases font mouche : la mise en cache sémantique que wallet-helper ne fait délibérément pas. | Orienté LLM ; a besoin d'un encodeur (embedder) et d'un magasin vectoriel ; correspondances probabilistes (un seuil de similarité) plutôt qu'une réutilisation exacte et adressée par contenu. |

## Deux choses que wallet-helper n'est pas

- **Pas un cache sémantique.** GPTCache et les outils similaires font correspondre
  des invites *similaires* via des embeddings et un seuil de similarité, troquant
  l'exactitude contre un taux de succès plus élevé sur les paraphrases.
  wallet-helper est l'inverse par conception : une correspondance exacte, adressée
  par contenu ou un échec, sans modèle dans la boucle. Les deux sont
  complémentaires, pas concurrents.
- **Pas un cache de protocole HTTP.** `requests-cache` et le plus récent
  [hishel](https://github.com/karpetrosyan/hishel) (mise en cache RFC 9111 pour
  HTTPX) mettent en cache les réponses HTTP selon leur sémantique de cache-control.
  wallet-helper met en cache le résultat de *n'importe quelle* fonction par le
  contenu de ses entrées, donc il couvre aussi un modèle local lent ou un appel
  non-HTTP, mais il ne lit pas les en-têtes de cache HTTP.

## Idées empruntées

wallet-helper emprunte délibérément des idées éprouvées :

- Le modèle leader/suiveur d'attente-et-partage, de Go `singleflight` et du
  `get_or_create` de `dogpile.cache`, pour que le second appelant reçoive le
  résultat du premier au lieu d'échouer.
- Un bail avec délai d'expiration sur le marqueur en cours et sa suppression en
  cas d'échec, d'AWS Powertools Idempotency, pour qu'un leader planté ne bloque
  pas les attendeurs et qu'un appel échoué ne soit pas mis en cache.
- La réclamation atomique avec `BEGIN IMMEDIATE` et la journalisation en écriture
  anticipée sur SQLite, pour que l'étape vérifier-puis-réserver soit exempte de
  course entre processus.
- `cache_info()` et `cache_clear()` sur la fonction décorée, de
  `functools.lru_cache` et l'éviction par namespace, des tags de `diskcache`.
- La durée de vie par entrée et le stale-while-revalidate, de `requests-cache`
  (`expire_after`), `diskcache` (`expire`) et `dogpile.cache`.

## Quand choisir quoi

La plupart du temps, la réponse honnête n'est pas ce paquet.

- **Un seul processus, fonction peu coûteuse, aucun redémarrage à encaisser.**
  `functools.lru_cache` ou `functools.cache`. Bibliothèque standard, aucun
  fichier, rien à nettoyer. On ne passe à un magasin persistant qu'une fois
  qu'un résultat mérite d'être conservé entre deux exécutions.
- **Un pipeline scientifique dont les entrées sont des tableaux et des
  dataframes.** `joblib.Memory`. Il hache le contenu des arguments en
  connaissant numpy puis invalide quand le source de la fonction change, ce que
  wallet-helper ne fait pas — modifiez ici le corps d'une fonction mémoïsée et
  l'ancien résultat continue d'être servi jusqu'à ce que vous vidiez son
  namespace.
- **Un gros cache clé/valeur local sur un seul hôte.** `diskcache`. Rapide,
  mature, avec tags et éviction en masse, plus `memoize_stampede` s'il faut
  fusionner les appels.
- **Mettre en cache des réponses HTTP selon leur sémantique de cache-control.**
  `requests-cache` pour `requests`, [hishel](https://github.com/karpetrosyan/hishel)
  pour HTTPX. Ils lisent les en-têtes ; wallet-helper ne les regarde jamais.
- **Une base de code async-first où redis tourne déjà.** `cashews` ou `cacheme`.
  Tous deux sont conçus pour `async def` et font bien la protection
  anti-avalanche ; le verrou distribué est l'affaire de redis.
- **Un cache que plusieurs équipes exploitent comme une infrastructure.** Redis,
  avec votre propre verrou par-dessus. C'est le pôle opposé à wallet-helper puis
  la bonne réponse à cette échelle.
- **De l'idempotence pour un gestionnaire de requêtes, sur AWS.** AWS Powertools
  Idempotency, avec DynamoDB. Conçu exactement pour ce cycle de vie.
- **Les paraphrases d'une invite doivent tomber sur la même réponse en cache.**
  GPTCache. C'est de la correspondance sémantique, ce que wallet-helper refuse
  délibérément : ici, c'est une touche exacte adressée par contenu ou un échec.

Choisissez wallet-helper quand plusieurs de ces points sont vrais à la fois :

- L'appel coûte assez cher pour que le relancer soit une dépense réelle : une
  API facturée, un modèle lent, un job long.
- Un résultat mérite d'être conservé d'une exécution à l'autre, pas seulement
  au sein d'une seule.
- L'entrée est — ou contient — un **fichier ou un blob** et vous voulez qu'une
  copie sous un autre nom tombe sur la même entrée.
- Deux appelants peuvent plausiblement démarrer le même appel en même temps et
  vous voulez que le second attende plutôt que de payer.
- Vous voulez que cela tienne **entre processus** sans monter d'abord redis ou
  DynamoDB : un fichier SQLite, voire un petit serveur HTTP qui est le vôtre.

## Sources et date de relevé

**Relevé le 27/10/2026.** Les étoiles puis les avantages/inconvénients sont une
lecture qualitative de la documentation et du README de chaque projet, faite par
le mainteneur de ce paquet. Aucun banc d'essai n'a été lancé, aucun chiffre de
latence ou de débit n'est avancé dans ce document et aucun numéro de version
n'est cité : une étoile ici dit « la documentation décrit cette capacité », pas
« nous l'avons mesurée ».

Traitez les notes portant sur le logiciel des autres comme un point de départ et
vérifiez la colonne qui vous importe dans leur propre documentation, car ces
projets bougent et ce fichier ne bouge pas avec eux.

- `functools.lru_cache` — <https://docs.python.org/3/library/functools.html>
- joblib — <https://joblib.readthedocs.io/>
- diskcache — <https://grantjenks.com/docs/diskcache/>
- cachier — <https://github.com/python-cachier/cachier>
- requests-cache — <https://requests-cache.readthedocs.io/en/stable/>
- dogpile.cache — <https://dogpilecache.sqlalchemy.org/>
- Redis — <https://redis.io/docs/latest/>
- `singleflight` de Go — <https://pkg.go.dev/golang.org/x/sync/singleflight>
- AWS Powertools Idempotency —
  <https://docs.powertools.aws.dev/lambda/python/latest/utilities/idempotency/>
- Requêtes idempotentes Stripe — <https://docs.stripe.com/api/idempotent_requests>
- Mise en cache litellm — <https://docs.litellm.ai/docs/proxy/caching>
- cashews — <https://github.com/Krukov/cashews>
- cacheme — <https://github.com/Yiling-J/cacheme>
- GPTCache — <https://github.com/zilliztech/GPTCache>
- hishel — <https://github.com/karpetrosyan/hishel>

La ligne wallet-helper est l'exception : elle est relevée sur le code puis la
suite de tests de ce dépôt, à la version inscrite dans `pyproject.toml`. C'est
donc la seule ligne vérifiée mécaniquement plutôt qu'à la lecture.
