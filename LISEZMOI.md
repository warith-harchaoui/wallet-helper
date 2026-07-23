# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

![wallet-helper Logo](assets/logo.png)

`wallet-helper` fait partie d'une collection de bibliothèques nommée **AI Helpers**, développée pour construire de l'intelligence artificielle.

Ne jamais relancer deux fois le même appel coûteux. wallet-helper est une mémoïsation persistante pour les appels coûteux (une requête d'API payante, un modèle lent, n'importe quelle fonction lourde) : un appel identique est servi depuis un stockage local au lieu d'être relancé, y compris après un redémarrage. Quand deux appels identiques démarrent en même temps, ils fusionnent : le second attend le résultat du premier et le réutilise au lieu de tourner en parallèle (single-flight).

Par [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Documentation

[📋 Exemples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

[🔭 Paysage](https://github.com/warith-harchaoui/wallet-helper/blob/main/LANDSCAPE.md)

## Ce que ça fait

Un appel lourd, on ne veut pas le payer deux fois. Deux causes de double exécution :

1. Vous le rappelez la semaine suivante. wallet-helper stocke chaque résultat sur disque, adressé par contenu à partir d'un namespace et des entrées (arguments, contenu d'un fichier, ou octets), donc la répétition est servie depuis le stockage plutôt que recalculée.
2. Vous le lancez deux fois en même temps. Deux threads, ou deux processus, démarrent le même appel lent avant que l'un ne finisse. wallet-helper laisse l'un l'exécuter et fait attendre les autres pour ce résultat, donc le travail n'a lieu qu'une fois.

C'est adressé par contenu : un fichier d'entrée renommé fait quand même mouche et deux entrées différentes n'entrent jamais en collision. Le stockage par défaut est un dossier de fichiers JSON, simple à lire et à supprimer. Un backend SQLite ajoute un stockage partagé et sûr en concurrence, plus le single-flight entre processus. Un petit serveur HTTP centralise cette déduplication pour plusieurs clients.

## État

Ce qui est livré aujourd'hui :

- **bibliothèque** avec `Wallet` et le décorateur `@memoize`, sur un `Ledger` (fichiers JSON) ou un `SqliteLedger` (un fichier partagé). Le single-flight en processus est intégré.
- **single-flight entre processus** via le bail (claim, submit, release) du backend SQLite.
- **`wallet-helper` / `cli_argparse`** et **`wallet-helper-click`** : inspecter et vider le stockage.
- **serveur HTTP de déduplication** (l'extra `[api]`) : claim, submit, et attente longue d'un résultat pour plusieurs clients.

## Installation

Le seul prérequis est **Python 3.10 à 3.13**. Pour installer Python :

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python`
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12`

Installez depuis GitHub, épinglé au tag de version :

```bash
pip install "git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"
```

Les surfaces ligne de commande et HTTP sont des extras optionnels :

```bash
pip install "wallet-helper[cli] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"   # variante CLI click    -> click
pip install "wallet-helper[api] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"   # serveur HTTP de dédup -> fastapi, uvicorn
```

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

Deux outils en ligne de commande inspectent et gèrent le stockage (par défaut `$WALLET_HELPER_DIR`, puis `~/.cache/wallet-helper`) :

```bash
python -m wallet_helper.cli_argparse stats   # combien de résultats en cache et combien d'appels évités
python -m wallet_helper.cli_argparse path    # où vit le stockage
python -m wallet_helper.cli_argparse clear    # vider le stockage

wallet-helper-click stats                     # idem, via la variante click
```

Pour un stockage partagé et le single-flight entre processus, utilisez le backend SQLite ou le serveur HTTP. Voir [EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Construit sur os-helper

wallet-helper fait partie de la suite AI Helpers et s'appuie sur [os-helper](https://github.com/warith-harchaoui/os-helper) pour le hachage adressé par contenu, les dossiers temporaires, les utilitaires de chemins et la journalisation.

## Architecture

| Pièce | Rôle |
|---|---|
| `make_key` | Hachage de contenu d'un namespace et d'un payload (arguments, contenu de fichier, ou octets). |
| `Ledger` | Stockage par défaut : un fichier JSON par entrée. |
| `SqliteLedger` | Un fichier SQLite partagé, compteurs de réutilisation atomiques, et le bail claim/submit/release. |
| `Wallet` / `memoize` | Porte d'entrée : recherche, single-flight en processus, puis stockage. |
| `wallet_helper.api` | Serveur HTTP qui centralise la déduplication pour plusieurs clients. |

## Tests

```bash
make install   # installation éditable avec dev et tous les extras
make lint      # ruff (PEP 8 et ordre des imports)
make test      # pytest et doctests
make           # lint puis test
```

La CI applique le même gate sur une matrice Python 3.10 à 3.13 (Linux, plus macOS et Windows sur la version la plus récente).

## Auteur

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## Licence

`wallet-helper` est distribué sous licence **BSD-3-Clause**. Voir [LICENSE](LICENSE).
