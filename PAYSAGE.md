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
python-dotenv). Il est donc local-first et autonome au niveau du service, mais
pas exempt de dépendances.

Deux problèmes font qu'un appel lourd tourne deux fois :

- **La répétition dans le temps.** Vous le rappelez au prochain lancement ou la
  semaine suivante. Un cache persistant résout cela.
- **La concurrence.** Deux appelants démarrent le même appel avant que l'un ne
  finisse. Le single-flight (aussi appelé coalescence de requêtes, dogpile,
  protection contre les avalanches) résout cela.

La plupart des outils ne traitent qu'un seul problème. wallet-helper traite les
deux, avec la même clé.

## Comparaison des fonctionnalités

Noté de ⭐ (absent ou faible) à ⭐⭐⭐⭐⭐ (meilleur de sa catégorie) par colonne.

- **Persistant** : les résultats survivent à un redémarrage de processus.
- **Adresse par contenu d'entrée** : la clé porte sur le contenu d'un fichier ou des octets bruts, pas seulement sur les arguments.
- **Single-flight intra-processus** : les appels identiques concurrents dans un processus fusionnent en un seul.
- **Single-flight inter-processus** : idem, entre processus ou hôtes.
- **TTL / expiration** : fraîcheur par entrée avec expiration et éviction.
- **Serveur pour plusieurs clients** : un point d'accès partagé qui centralise la déduplication.
- **Décorateur** : ergonomie transparente `@decorator`.
- **Support asynchrone** : fonctionne avec les coroutines `async def`, pas seulement les fonctions synchrones.
- **Local (sans service)** : fonctionne sans base de données ni serveur de cache séparé. Il s'agit de l'empreinte de déploiement, pas du nombre de dépendances.

<!-- TABLE:START -->
| Mise en cache | Persistant | Adresse par contenu d'entrée | Single-flight intra-processus | Single-flight inter-processus | TTL / expiration | Serveur pour plusieurs clients | Décorateur | Support asynchrone | Local (sans service) |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **wallet-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| functools.lru_cache | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| joblib.Memory | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| diskcache | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| cachier | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| requests-cache | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| dogpile.cache | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| Redis | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ |
| Go singleflight | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| AWS Powertools Idempotency | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ |
| Stripe idempotency keys | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ |
| litellm cache | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ |
| cashews | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| cacheme | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| GPTCache (sémantique) | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/paysage.png)

La carte est un résumé en 2D des 9 critères : à lire comme une forme, pas comme un classement. « wallet-helper » se situe dans le coin en haut à droite. Les axes se lisent **Horizontal — Autonomie ↔ Efficacité** et **Vertical — Adaptabilité ↔ Créativité**.
<!-- FIGURE:END -->

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
| GPTCache (sémantique) | Un autre axe : fait correspondre des invites *similaires* via embeddings + recherche vectorielle, donc les paraphrases font mouche — la mise en cache sémantique que wallet-helper ne fait délibérément pas. | Orienté LLM ; a besoin d'un encodeur (embedder) et d'un magasin vectoriel ; correspondances probabilistes (un seuil de similarité) plutôt qu'une réutilisation exacte et adressée par contenu. |

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
  non-HTTP — mais il ne lit pas les en-têtes de cache HTTP.

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
