# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#) [![Local-first](https://img.shields.io/badge/privacy-local--first-2f6f5e.svg)](#la-promesse)

![wallet-helper Logo](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/logo.png)

`wallet-helper` fait partie d'une collection de bibliothèques nommée **AI Helpers**, développée pour construire de l'intelligence artificielle.

Ne jamais relancer deux fois le même appel coûteux. wallet-helper est une mémoïsation persistante pour les appels coûteux (une requête d'API payante, un modèle lent, n'importe quelle fonction lourde) : un appel identique est servi depuis un stockage local au lieu d'être relancé, y compris après un redémarrage. Quand deux appels identiques démarrent en même temps, ils fusionnent : le second attend le résultat du premier et le réutilise au lieu de tourner en parallèle (single-flight).

Par [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/wallet-helper-doc/)

[🗺️ Paysage](https://github.com/warith-harchaoui/wallet-helper/blob/main/PAYSAGE.md)

[📋 Exemples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXEMPLES.md)

## Ce que ça fait

Un appel lourd, on ne veut pas le payer deux fois. Deux causes de double exécution :

1. Vous le rappelez la semaine suivante. wallet-helper stocke chaque résultat sur disque, adressé par contenu à partir d'un namespace et des entrées (arguments, contenu d'un fichier ou octets), donc la répétition est servie depuis le stockage plutôt que recalculée.
2. Vous le lancez deux fois en même temps. Deux threads ou deux processus démarrent le même appel lent avant que l'un ne finisse. wallet-helper laisse l'un l'exécuter et fait attendre les autres pour ce résultat, donc le travail n'a lieu qu'une fois.

C'est adressé par contenu : un fichier d'entrée renommé fait quand même mouche et deux entrées différentes n'entrent jamais en collision. Le stockage par défaut est un dossier de fichiers JSON, simple à lire et à supprimer. Un backend SQLite ajoute un stockage partagé et sûr en concurrence, plus le single-flight entre processus. Un petit serveur HTTP centralise cette déduplication pour plusieurs clients.

## État

Éprouvé en production : 112 tests, une matrice de CI (intégration continue) au vert sur Python 3.10 à 3.13 sous Linux et macOS, plus un test d'installation sous Windows, et des versions publiées sur PyPI selon le versionnage sémantique (voir les badges ci-dessus). Ce qui est livré aujourd'hui :

- **bibliothèque** avec `Wallet` et le décorateur `@memoize` (synchrone et `async def`), sur un `Ledger` (fichiers JSON), un `SqliteLedger` (un fichier partagé) ou un `RemoteLedger` (un serveur HTTP). Le single-flight en processus est intégré.
- **single-flight entre processus** via le backend SQLite ou le serveur, avec un jeton de fencing (une valeur aléatoire et unique attribuée à chaque bail ; un nouveau leader qui reprend un bail périmé en reçoit une nouvelle, si bien qu'une écriture tardive portant l'ancienne valeur ne correspond plus et se voit rejetée) pour que le travail s'exécute une seule fois même si un leader plante, un délai de bail et un heartbeat pour les jobs longs.
- **durée de vie et éviction** : `ttl` par entrée, stale-while-revalidate optionnel, une politique `evict` par âge ou taille et un plafond automatique (`max_entries`).
- **`wallet-helper` / `cli_argparse`** et **`wallet-helper-click`** : inspecter, vider et éviter le stockage.
- **serveur HTTP de déduplication** (l'extra `[api]`) plus `RemoteLedger`, pour que plusieurs clients sur n'importe quelle machine partagent un point de déduplication.
- **outils MCP** (l'extra `[mcp]`) : le même serveur HTTP de déduplication exposé comme outils MCP pour tout hôte agentique compatible.

## Installation

Le seul prérequis est **Python 3.10 à 3.13**. Pour installer Python :

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python`
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12`

Installez depuis PyPI :

```bash
pip install wallet-helper
```

Ou depuis les sources :

```bash
git clone https://github.com/warith-harchaoui/wallet-helper.git
cd wallet-helper
pip install -e .
```

Les surfaces ligne de commande et HTTP sont des extras optionnels :

```bash
pip install "wallet-helper[cli]"   # variante CLI click    -> click
pip install "wallet-helper[api]"   # serveur HTTP de dédup -> fastapi, uvicorn
pip install "wallet-helper[mcp]"   # outils MCP + ce qui précède -> fastapi-mcp
```

Lancez le serveur MCP avec `wallet-helper-mcp` (API HTTP + un endpoint `/mcp`, même app).

## Prise en main

Mémoïsez n'importe quelle fonction en une ligne. Le résultat est stocké sur disque et réutilisé au prochain appel identique, cette exécution ou la semaine prochaine :

```python
from wallet_helper import memoize

@memoize
def transcribe(path):
    return call_some_paid_api(path)   # lent et facturé ; s'exécute au plus une fois par fichier

transcribe("reunion.wav")   # s'exécute, stocke le résultat
transcribe("reunion.wav")   # servi depuis le stockage, pas de second appel
```

Un argument fichier est identifié par son contenu, pas par son chemin. Le même fichier atteint sous un autre nom ou une copie octet pour octet dans un autre dossier, fait donc mouche et deux fichiers différents ne se télescopent jamais même si leurs noms se ressemblent :

```python
transcribe("reunion.wav")           # s'exécute
transcribe("archive/reunion.wav")   # une copie de mêmes octets, servie depuis le stockage
```

Ignorez un argument qui ne devrait pas changer le résultat, par exemple un handle client :

```python
@memoize(ignore=("client",))
def fetch(doc_id, client):
    return client.get(doc_id)
```

Inspectez ou videz le cache d'une fonction, comme `functools.lru_cache` :

```python
transcribe.cache_info()    # {'entries': 1, 'hits': 1}
transcribe.cache_clear()   # oublier les résultats stockés de cette fonction
```

Fixez une fenêtre de fraîcheur avec `ttl` (secondes) et partagez un stockage sur tout un parc en pointant vers un serveur :

```python
from wallet_helper import Wallet, RemoteLedger, memoize

@memoize(ttl=3600)                       # les résultats expirent après une heure
def price(symbol):
    return call_pricing_api(symbol)

wallet = Wallet(RemoteLedger("http://cache.internal:8000"))
@memoize(wallet=wallet)                  # chaque machine déduplique via un serveur
def transcribe(path):
    return call_some_paid_api(path)
```

Les fonctions asynchrones marchent pareil. C'est le résultat qui est mis en cache, jamais la coroutine et les `await` concurrents fusionnent :

```python
@memoize
async def fetch(url):
    return await http_get(url)
```

Deux outils en ligne de commande inspectent et gèrent le stockage (par défaut `$WALLET_HELPER_DIR`, puis `~/.cache/wallet-helper`) :

```bash
python -m wallet_helper.cli_argparse stats   # combien de résultats en cache et combien d'appels évités
python -m wallet_helper.cli_argparse path    # où vit le stockage
python -m wallet_helper.cli_argparse clear    # vider le stockage

wallet-helper-click stats                     # idem, via la variante click
```

Pour un stockage partagé et le single-flight entre processus, utilisez le backend SQLite ou le serveur HTTP. Voir [EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Construit sur os-helper

wallet-helper fait partie de la suite AI Helpers et s'appuie sur [os-helper](https://github.com/warith-harchaoui/os-helper) pour le hachage adressé par contenu, les utilitaires de chemins, les dossiers temporaires et la journalisation. C'est une seule dépendance directe, qui entraîne quelques bibliothèques transitives courantes (requests, pyyaml, tqdm, etc.). wallet-helper est local-first et ne nécessite aucun service séparé, mais n'est pas sans dépendance.

## Architecture

| Pièce | Rôle |
|---|---|
| `make_key` | Hachage de contenu d'un namespace et d'un payload (arguments, contenu de fichier ou octets). |
| `Ledger` | Stockage par défaut : un fichier JSON par entrée. |
| `SqliteLedger` | Un fichier SQLite partagé, compteurs atomiques, TTL et le bail claim/submit/release/extend. |
| `RemoteLedger` | Un `LedgerLike` qui parle au serveur, donc `Wallet(RemoteLedger(url))` déduplique sur tout un parc. |
| `Wallet` / `memoize` | Porte d'entrée : recherche, single-flight (en processus ou via le bail), puis stockage. |
| `wallet_helper.api` | Serveur HTTP qui centralise la déduplication pour plusieurs clients. |

## Tests

```bash
make install   # installation éditable avec les extras dev, cli et api
make lint      # ruff (PEP 8 et ordre des imports)
make test      # pytest et doctests
make           # lint puis test
```

La CI exécute toute la suite de tests sur une matrice Python 3.10 à 3.13 sous Linux (🐧), plus la version la plus récente sous macOS (🍎). En complément, un **test de fumée d'installation** léger tourne sur les trois plateformes où vous pourriez installer (🐧 Linux, 🍎 macOS, 🪟 Windows) : il installe le paquet et ses extras, puis vérifie qu'il s'importe, que les deux outils en ligne de commande répondent et qu'un aller-retour de mémoïsation n'exécute le travail qu'une seule fois. L'installation est donc vérifiée partout, tandis que la suite exhaustive tourne là où elle est rapide et fiable (le test entre processus s'appuie sur le multiprocessing par `spawn`, très lent sur les runners Windows).

## La promesse

wallet-helper fait partie d'une suite « local-first », soucieuse de
souveraineté et comme os-helper c'est une petite boîte à outils, pas un
service. Plutôt que d'en faire un argument marketing, voici la réalité honnête,
cas par cas :

1. **Garanti local.** Le `Ledger` par défaut (un dossier de fichiers JSON) et le
   `SqliteLedger` (un seul fichier) vivent sous `$WALLET_HELPER_DIR`, ou
   `~/.cache/wallet-helper`, sur votre machine. Rien n'est envoyé, aucune
   télémétrie, aucun compte. Vos résultats mis en cache, et les entrées qui les
   indexent, ne quittent jamais le disque.

2. **Là où le local n'est pas possible : la réserve.** wallet-helper existe pour
   *éviter* de relancer votre appel coûteux ; il ne fait aucune requête réseau
   de lui-même. La seule exception est voulue : le serveur de dédup optionnel
   (`[api]`) et `RemoteLedger` parlent HTTP pour qu'une flotte partage un même
   point de dédup ; ils ne s'adressent qu'à l'endpoint que vous leur
   indiquez.

3. **Votre décision.** wallet-helper stocke ce que votre fonction renvoie ; si
   cette fonction appelle une API cloud payante, c'est le choix de votre code,
   jamais celui de wallet-helper. Pointez `RemoteLedger` vers votre propre hôte
   et le stockage partagé reste souverain ; pointez-le vers un tiers, c'est
   aussi votre choix, jamais un défaut.

## Auteur

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## Licence

`wallet-helper` est distribué sous licence **BSD-3-Clause**. Voir [LICENSE](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE).
