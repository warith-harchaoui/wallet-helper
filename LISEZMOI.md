# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#) [![Sans dépendance](https://img.shields.io/badge/deps-zéro%20(stdlib)-2f6f5e.svg)](#la-promesse)

![wallet-helper Logo](assets/logo.png)

`wallet-helper` fait partie d'une collection de bibliothèques nommée **AI Helpers**, développée pour construire de l'intelligence artificielle.

**Ne jamais payer deux fois le même appel facturé.** Un garde-fou minimal, local-first et agnostique du fournisseur, autour de n'importe quel appel qui coûte quelque chose — une API HTTP, un binaire payant, une fonction facturée — dans n'importe quelle devise : argent, temps, énergie, eau, CO₂. Il combine l'idempotence (un registre content-addressed renvoie le résultat conservé au lieu de relancer l'appel), la comptabilité de dépense (chaque appel réel enregistre son coût) et le contrôle de budget (un plafond optionnel refuse un appel qui dépasserait la limite, *avant* qu'il ne s'exécute) — trois choses habituellement séparées, avec **zéro dépendance runtime** pour s'intégrer à n'importe quel projet.

Par [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/wallet-helper-doc/)

[📋 Exemples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

## La promesse

> **Le même appel facturé s'exécute, et se facture, au plus une fois.** Aucun
> compte cloud, aucun framework, aucune dépendance — le garde-fou vit dans votre
> processus et le registre est un dossier de fichiers JSON sur votre disque.

Ce n'est pas un *tableau de bord* de coûts auquel vous envoyez votre trafic.
C'est une *propriété* locale : un appel identique (même namespace, même contenu,
mêmes paramètres) est servi depuis un registre content-addressed au lieu d'être
relancé, donc vous ne le payez jamais deux fois — et un budget optionnel refuse
l'appel qui dépasserait la limite avant que le moindre centime ne parte.
Agnostique du fournisseur et de la devise : `"USD"`, `"EUR"`, ou même
`"tokens"` / `"CO2"` fonctionnent.

## État — v0.1.0

Ce qui est livré aujourd'hui :

- **bibliothèque** — `Ledger` content-addressed (cache d'idempotence), types valeur `Cost` / `Budget`, et `Wallet` (la méthode `call` + le décorateur `@paid`) qui les relient. Stdlib uniquement.
- **`wallet-helper` / `cli_argparse`** — CLI sans dépendance : `stats`, `path`, `clear`.
- **`wallet-helper-click`** — CLI équivalente sur `click` (l'extra `[cli]`).
- **Surface FastAPI + `/gui`** — un registre partagé en HTTP avec un tableau de bord minimal (l'extra `[api]`).
- **`wallet-helper-mcp`** — les mêmes opérations de comptabilité en outils Model Context Protocol (l'extra `[mcp]`).

## Installation

**Prérequis** — le seul requis est **Python 3.10–3.13** ; le cœur est en
bibliothèque standard pure, donc aucun paquet système à installer. Pour
installer Python lui-même, multiplateforme :

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python`
  (installez `brew` grâce à [brew.sh](https://brew.sh/))
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12`

### Depuis les sources

Installez depuis GitHub, épinglé au tag de version :

```bash
pip install "git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"
```

Extras optionnels — chaque surface au-delà du cœur est opt-in, le cœur reste
sans dépendance (au choix) :

```bash
pip install "wallet-helper[cli] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # variante CLI click            -> click
pip install "wallet-helper[api] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # surface HTTP FastAPI + /gui    -> fastapi, uvicorn
pip install "wallet-helper[mcp] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # jeu d'outils MCP               -> mcp
```

## Prise en main

En bibliothèque :

```python
from wallet_helper import Wallet, Ledger, Budget

wallet = Wallet(Ledger("~/.cache/mon-app"), budget=Budget(10.0, "EUR"))

# Enrobe n'importe quel appel payant. Le 2e appel identique est gratuit (servi
# depuis le registre) et ne touche pas au budget.
result, from_cache = wallet.call(
    "gladia",                                    # namespace (fournisseur / endpoint)
    {"file": "appel.wav", "diarization": True},  # ce qui détermine le résultat
    lambda: call_gladia("appel.wav"),            # le travail payant (au plus une fois)
    cost=0.75, currency="EUR",
)

# Ou en décorateur — les appels identiques renvoient le résultat en cache :
@wallet.paid("openai.chat", cost=0.02, currency="USD")
def resume(texte: str) -> str:
    return openai_chat(texte)
```

Le payload est **content-addressed** : passer un chemin de fichier ou des
`bytes` — renommer le fichier hit quand même ; deux fichiers différents ne
collisionnent jamais. Les paramètres sont hashés aussi (`diarization=True` ≠
`False`).

Deux CLI interchangeables inspectent et gèrent le registre (par défaut sous
`$WALLET_HELPER_DIR` puis `~/.cache/wallet-helper`, un fichier JSON par entrée) :

```bash
python -m wallet_helper.cli_argparse stats   # dépense + économies du cache par devise
python -m wallet_helper.cli_argparse path    # où vit le registre
python -m wallet_helper.cli_argparse clear   # vide le registre

wallet-helper-click stats                     # idem, via la variante click
```

En API HTTP ou serveur MCP (aligné sur le reste de la suite `*-helper`) :

```bash
pip install -e ".[api,mcp]"

# FastAPI : registre partagé en HTTP + tableau de bord /gui — docs OpenAPI /docs
uvicorn wallet_helper.api:app                 # http://127.0.0.1:8000/gui

# MCP : expose les mêmes outils de comptabilité à un client MCP
wallet-helper-mcp                             # ou : python -m wallet_helper.mcp_server
```

Les deux surfaces n'exposent que la moitié *comptable* (dérivation de clé,
enregistrements, hits, stats, vérifications de budget). Elles n'exécutent jamais
votre appel payant — il reste dans votre processus, donc aucune surface
d'exécution de code à distance. Pour le catalogue complet de recettes, voir
[📋 EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Ce qui existe déjà sur ces sujets

wallet-helper occupe volontairement un creux. Les briques existent séparément ;
c'est la **combinaison** — idempotence + registre de coût + budget, agnostique et
local-first — qui est rare.

- **Mémoïsation / cache disque général** — `functools.lru_cache` (mémoire seule),
  `joblib.Memory`, `diskcache`. Ils dédupliquent mais **n'ont aucune notion
  d'argent** (coût, devise, budget).
- **Cache de réponses HTTP** — `requests-cache`, `CacheControl`, `VCR.py`. Cache
  par requête HTTP ; là encore **pas de comptabilité ni de budget**, et HTTP-only.
- **Coût/limites spécifiques LLM** — `litellm` (cache + suivi de dépense +
  budgets, le cousin le plus proche, mais **LLM-only et lourd**), `tokencost`
  (tables de prix, sans cache/garde), le cache LLM de LangChain, et
  l'observabilité SaaS (Helicone / OpenMeter / dashboards — **distants,
  liés à un compte, pas un garde local**).
- **Clés d'idempotence** — style Stripe, AWS Lambda Powertools. Elles évitent les
  **doubles effets de bord sur retry** (autre objectif), côté serveur/cloud.

Si votre monde n'est que des LLM et que vous utilisez déjà `litellm`, son
budget + cache peuvent suffire. wallet-helper est pour le reste : **n'importe
quel** appel payant, sans framework, sans service, sans dépendance.

## Architecture

Trois préoccupations derrière une seule porte d'entrée (`Wallet`), sur un dossier
d'entrées JSON :

| Préoccupation | Composant |
|---|---|
| **Idempotence** | `Ledger` — stockage content-addressed (`make_key` → sha256 du namespace + payload) |
| **Comptabilité** | `Cost` / `Budget` — types valeur monétaires avec refus de dépassement |
| **Garde-fou** | `Wallet` — la méthode `call` + le décorateur `@paid` qui les relient |

## Tests

```bash
make install   # installation éditable avec dev + tous les extras
make lint      # ruff (PEP 8 + ordre des imports) — le gate CI
make test      # pytest + doctests sur toutes les surfaces
make           # lint + test (à lancer avant de pousser)
```

La CI applique le même gate `lint` + `test` sur une matrice Python 3.10–3.13
(Linux, plus macOS et Windows sur la version la plus récente).

## Auteur

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## Licence

`wallet-helper` est distribué sous licence **BSD-3-Clause**. Voir [LICENSE](LICENSE).
