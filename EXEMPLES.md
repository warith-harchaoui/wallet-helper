# Exemples wallet-helper

🇫🇷 Français · [🇬🇧 EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

Un livre de recettes des usages courants. La plupart des blocs Python sont
autonomes et écrivent dans un magasin temporaire : on peut en coller un dans un
REPL et regarder le résultat. La sortie notée à côté de chaque `print` est celle
que le bloc a réellement affichée lors de la dernière vérification de ce
fichier ; `tests/test_examples_md.py` rejoue chaque bloc autonome, donc un
changement d'API casse la CI plutôt que la lecture.

Trois blocs ne sont volontairement **pas** exécutables tels quels et le disent
là où ils apparaissent : les deux qui appellent un `call_some_paid_api` fictif
puis le client du serveur HTTP de l'exemple 7, qui suppose ce serveur démarré.

## Table des matières

- [Mise en place](#mise-en-place)
- [1. Mémoïser un appel coûteux](#1-mémoïser-un-appel-coûteux)
- [2. Le décorateur, avec cache_info et cache_clear](#2-le-décorateur-avec-cache_info-et-cache_clear)
- [3. Ignorer un argument volatil](#3-ignorer-un-argument-volatil)
- [4. Adresser un fichier par son contenu](#4-adresser-un-fichier-par-son-contenu)
- [5. Single-flight entre threads](#5-single-flight-entre-threads)
- [6. Un magasin partagé avec SQLite](#6-un-magasin-partagé-avec-sqlite)
- [7. Single-flight inter-processus par HTTP](#7-single-flight-inter-processus-par-http)
- [8. Un magasin partagé par HTTP avec RemoteLedger](#8-un-magasin-partagé-par-http-avec-remoteledger)
- [9. Durée de vie et éviction](#9-durée-de-vie-et-éviction)
- [10. Stale-while-revalidate](#10-stale-while-revalidate)
- [11. Fonctions asynchrones](#11-fonctions-asynchrones)
- [Ligne de commande](#ligne-de-commande)
- [Dépannage](#dépannage)

## Mise en place

La bibliothèque puis la commande `wallet-helper` arrivent avec l'installation de
base. Seuls les exemples 7 et 8 demandent davantage, parce qu'ils mettent en jeu
le serveur HTTP de déduplication :

```bash
pip install wallet-helper            # bibliothèque + la commande wallet-helper
pip install "wallet-helper[api]"     # ajoute le serveur HTTP de dédup (exemples 7, 8)
```

Tous les extraits ci-dessous sont écrits avec ces noms et chaque bloc répète
ceux dont il a besoin, pour qu'on puisse commencer la lecture à n'importe quelle
section. `osh`, c'est
[os-helper](https://github.com/warith-harchaoui/os-helper), la couche utilitaire
partagée de la suite, d'où vient `temporary_folder` :

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, SqliteLedger, RemoteLedger, make_key, memoize
```

Le magasin que les exemples ne redéfinissent *pas* se trouve sous
`$WALLET_HELPER_DIR`, à défaut `~/.cache/wallet-helper`. `wallet-helper path`
l'affiche.

## 1. Mémoïser un appel coûteux

On enveloppe n'importe quelle fonction dont l'exécution coûte cher. Le premier
appel l'exécute ; un second appel identique est servi depuis le magasin.
`from_cache` indique lequel des deux s'est produit.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    def transcribe(path):
        return {"text": "hello"}  # tient lieu d'appel lent à une API payante

    r1, from_cache1 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))
    r2, from_cache2 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))

    print(r1, from_cache1)  # {'text': 'hello'} False   -> exécuté
    print(r2, from_cache2)  # {'text': 'hello'} True    -> servi depuis le magasin
```

## 2. Le décorateur, avec cache_info et cache_clear

`@memoize` ne demande aucune configuration : il utilise par défaut un magasin
partagé situé à `~/.cache/wallet-helper`. On peut lui passer un `wallet=` pour
le pointer ailleurs (ici, un magasin temporaire). La fonction décorée porte
`cache_info()` et `cache_clear()`, comme `functools.lru_cache`.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    @memoize(wallet=wallet)
    def square(n):
        return n * n

    print(square(9), square(9), square(10))  # 81 81 100
    print(square.cache_info())
    # {'entries': 2, 'hits': 1, 'lifetime_hits': 1, 'lifetime_misses': 2}
    square.cache_clear()
    print(square.cache_info())
    # {'entries': 0, 'hits': 0, 'lifetime_hits': 1, 'lifetime_misses': 2}
```

`entries` puis `hits` décrivent ce que contient le magasin **maintenant** : un
`cache_clear()` les remet donc à zéro. `lifetime_hits` et `lifetime_misses` sont
des totaux cumulés à l'échelle du magasin, qui survivent à un vidage, à une
éviction puis à une expiration — c'est ce qui permet de calculer un taux de
touche qui veut dire quelque chose.

## 3. Ignorer un argument volatil

Quand un argument ne change pas le résultat (un handle de client, un objet de
session), `ignore=` l'exclut de la clé sans qu'on ait à écrire de fonction de
clé personnalisée.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    @memoize(wallet=wallet, ignore=("client",))
    def fetch(doc_id, client):
        return client.get(doc_id)

    class Client:
        def get(self, doc_id):
            return f"doc:{doc_id}"

    print(fetch(7, client=Client()))  # exécuté
    print(fetch(7, client=Client()))  # client différent, même clé, servi depuis le magasin
```

## 4. Adresser un fichier par son contenu

Un argument fichier est indexé par son contenu, pas par son chemin, où qu'il
se trouve dans l'appel. Le même fichier atteint par un chemin différent (un
renommage, une copie octet pour octet ailleurs) touche donc toujours la même
entrée ; deux fichiers distincts ne se percutent jamais, même quand le
chemin n'est qu'un argument parmi d'autres :

```python
import os_helper as osh
from pathlib import Path
from wallet_helper import make_key

with osh.temporary_folder() as tmp:
    d = Path(tmp)
    (d / "clip.wav").write_bytes(b"AUDIO-BYTES")
    (d / "renamed.wav").write_bytes(b"AUDIO-BYTES")  # même contenu, nom différent

    # Chemin porté par tout le payload : le renommage touche quand même.
    print(make_key("asr", d / "clip.wav") == make_key("asr", d / "renamed.wav"))  # True

    # Un chemin niché parmi d'autres arguments est lui aussi adressé par contenu.
    a = {"args": (str(d / "clip.wav"),), "kwargs": {"lang": "en"}}
    b = {"args": (str(d / "renamed.wav"),), "kwargs": {"lang": "en"}}
    print(make_key("asr", a) == make_key("asr", b))  # True
```

En pratique on ne construit jamais ce payload soi-même : `@memoize` s'en
charge, si bien que deux copies d'un même fichier à des chemins différents ne
déclenchent l'appel coûteux qu'une seule fois. Illustratif —
`call_some_paid_api` tient la place de votre propre appel lent et facturé :

```python
from wallet_helper import memoize


@memoize
def transcribe(path, lang="en"):
    return call_some_paid_api(path, lang)  # exécuté une fois pour un fichier et une langue donnés


transcribe("clip.wav")  # exécuté
transcribe("archive/clip.wav")  # mêmes octets, chemin différent : servi depuis le magasin
```

## 5. Single-flight entre threads

Deux threads déclenchent le même appel lent au même instant. Un seul l'exécute,
l'autre attend et reçoit le même résultat : pas de double travail, pas de
double facturation.

```python
import os_helper as osh
import threading, time
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    runs = []

    def slow():
        runs.append(1)
        time.sleep(0.3)  # assez long pour que le second thread arrive en cours de route
        return "value"

    out = []

    def worker():
        out.append(wallet.call("job", {"x": 1}, slow))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(len(runs))  # 1   -> exécuté une seule fois
    print(sorted(c for _, c in out))  # [False, True]  -> un meneur, un suiveur
```

## 6. Un magasin partagé avec SQLite

Le backend SQLite conserve un seul fichier que plusieurs processus peuvent
partager, avec des compteurs de réutilisation atomiques. On le branche dans un
`Wallet` exactement comme le magasin JSON.

```python
import os_helper as osh
from wallet_helper import Wallet, SqliteLedger

with osh.temporary_folder() as tmp:
    wallet = Wallet(SqliteLedger(tmp + "/ledger.db"))
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)  # 42 False
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)  # 42 True
```

## 7. Single-flight inter-processus par HTTP

`pip install "wallet-helper[api]"` fait tourner un serveur qui centralise la
déduplication pour de nombreux clients, via le protocole claim, submit,
release. Démarrage :

```bash
uvicorn wallet_helper.api:app     # documentation sur http://127.0.0.1:8000/docs
```

Un client revendique une clé. S'il est meneur, il exécute le travail et
soumet le résultat ; sinon, il attend et lit le résultat. Cette approche
n'utilise que la bibliothèque standard, si bien qu'un client n'a besoin
d'aucune dépendance installée :

```python
import json, time, urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req))


def get_or_run(namespace, payload, work):
    call = {"namespace": namespace, "payload": payload}
    while True:
        outcome = post("/claim", call)
        if outcome["status"] == "hit":
            return outcome["result"]  # déjà calculé
        if outcome["status"] == "leased":
            result = work()  # nous sommes le meneur
            post("/submit", {**call, "result": result})
            return result
        time.sleep(0.2)  # en attente : quelqu'un d'autre l'exécute


print(get_or_run("transcribe", {"file": "a.wav"}, lambda: {"text": "hello"}))
```

Un suiveur peut aussi bloquer sur un seul appel avec `GET
/result/{key}?wait=SECONDES`, qui attend en long-polling que le résultat du
meneur arrive. Pour un travail long, le meneur maintient son bail actif avec
`POST /extend` (ou, en local, le context manager `SqliteLedger.heartbeat`).

## 8. Un magasin partagé par HTTP avec RemoteLedger

`RemoteLedger` est un magasin adossé à ce serveur : on obtient un single-flight
inter-processus sans écrire une ligne de protocole, il suffit de le passer à
un `Wallet` et d'utiliser `@memoize` comme d'habitude. Chaque hôte qui pointe
vers le même serveur se déduplique contre le même bail. Il n'utilise que la
bibliothèque standard. Illustratif à deux titres : l'URL doit être un serveur
que vous faites réellement tourner puis `call_some_paid_api` est le vôtre :

```python
from wallet_helper import Wallet, RemoteLedger, memoize

wallet = Wallet(RemoteLedger("http://cache.internal:8000"))


@memoize(wallet=wallet)
def transcribe(path):
    return call_some_paid_api(path)  # exécuté une fois pour toute la flotte


transcribe("meeting.wav")
```

## 9. Durée de vie et éviction

Un `ttl` (en secondes) donne à une entrée une fenêtre de fraîcheur. Passé ce
délai, l'appel suivant recalcule. `evict` purge le magasin : il retire
toujours les entrées expirées et peut aussi plafonner par âge ou par nombre.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    ledger = Ledger(tmp)
    wallet = Wallet(ledger)

    wallet.call("price", {"sym": "ACME"}, lambda: 100, ttl=3600)  # fraîche pendant une heure

    ledger.put("old", 1, ttl=0.0)  # déjà expirée
    print(ledger.evict())  # 1   -> entrée expirée retirée
    print(ledger.evict(max_entries=10))  # 0   -> une seule entrée, rien à plafonner
    print(ledger.evict(older_than=86400))  # 0   -> cette entrée a quelques secondes
```

`evict` renvoie le nombre d'entrées retirées : c'est bien le `0` des deux
derniers appels qui fait la démonstration, le magasin tenait déjà dans les deux
limites.

## 10. Stale-while-revalidate

Pour le magasin en mémoire, on sert un résultat périmé immédiatement et on le
rafraîchit en arrière-plan, si bien qu'un appelant n'attend jamais le
recalcul.

```python
import os_helper as osh
import time
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    version = [0]

    def build():
        version[0] += 1
        return version[0]

    print(wallet.call("cfg", {}, build, ttl=0.05))  # (1, False)  -> calculé
    time.sleep(0.06)  # on laisse expirer
    print(
        wallet.call("cfg", {}, build, ttl=60, stale_while_revalidate=True)
    )  # (1, True) -> périmé, servi tout de suite
    time.sleep(0.2)  # le rafraîchissement en arrière-plan aboutit
    print(wallet.call("cfg", {}, build, ttl=60))  # (2, True)   -> valeur rafraîchie
```

Le `ttl` passé à l'appel stale-while-revalidate est celui sous lequel le
**rafraîchissement** enregistre, pas seulement la fenêtre à l'aune de laquelle
l'entrée courante est jugée. Redemander `ttl=0.05` rafraîchirait vers une entrée
qui expire 50 ms plus tard : l'appelant suivant recalculerait donc sans jamais
voir la valeur rafraîchie — d'où le `ttl=60` du troisième appel.

## 11. Fonctions asynchrones

`@memoize` gère aussi les `async def`. Il met en cache le résultat attendu,
jamais l'objet coroutine ; deux attentes concurrentes du même appel
fusionnent en une seule exécution.

```python
import asyncio
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    runs = []

    @memoize(wallet=wallet)
    async def fetch(n):
        runs.append(n)
        await asyncio.sleep(0.1)
        return n * n

    async def main():
        # Deux `await` concurrents du même appel n'exécutent le travail qu'une fois.
        a, b = await asyncio.gather(fetch(6), fetch(6))
        c = await fetch(6)  # servi depuis le magasin
        return a, b, c, len(runs)

    print(asyncio.run(main()))  # (36, 36, 36, 1)
```

## Ligne de commande

Une seule commande est livrée avec le paquet : `wallet-helper`, avec quatre
sous-commandes. On la pointe vers un répertoire JSON avec `--dir` ou vers un
fichier SQLite avec `--sqlite`.

```bash
wallet-helper stats                            # entrées et appels économisés
wallet-helper path                             # emplacement du magasin
wallet-helper clear                            # vide le magasin (demande confirmation)
wallet-helper evict --older-than 604800        # supprime les entrées vieilles de plus d'une semaine

wallet-helper --sqlite ./ledger.db stats       # inspecte un magasin SQLite
wallet-helper evict --max-entries 1000         # ne garde que les 1000 plus récentes
wallet-helper clear --yes                      # saute la confirmation
```

`stats` affiche trois lignes — l'emplacement du magasin, son nombre d'entrées
puis les appels que ces entrées ont économisés :

```text
ledger: /Users/vous/.cache/wallet-helper
entries: 0
calls saved (cache hits): 0
```

Installer l'extra `[mcp]` ajoute une seconde commande, `wallet-helper-mcp`, qui
sert l'API HTTP de l'exemple 7 en même temps qu'un endpoint MCP sur `/mcp`.

## Dépannage

**Le résultat en cache est périmé après que j'ai modifié la fonction.** La clé,
c'est le namespace plus les arguments — jamais le source de la fonction. Changez
le corps et tous les résultats stockés restent valides du point de vue de
wallet-helper. Videz ce namespace — ou changez-en :

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 1.08))  # (1.08, False)
    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 9.99))  # (1.08, True) -> ancienne valeur
    wallet.ledger.clear("rate")  # n'oublie que ce namespace
    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 9.99))  # (9.99, False)
```

`cache_clear()` sur une fonction mémoïsée fait la même chose pour son propre
namespace.

**`stale_while_revalidate=True` n'a rien fait.** C'est implémenté pour le
`Ledger` en processus uniquement. `SqliteLedger` puis `RemoteLedger` passent par
le bail claim/submit, où le drapeau est ignoré et une entrée expirée est
recalculée de façon synchrone — l'appel renvoie donc `(2, False)`, pas le
`(1, True)` périmé de l'exemple 10.

**`cache_info()` affiche des totaux à vie inattendus.** `entries` puis `hits`
sont limités au namespace de la fonction décorée ; `lifetime_hits` et
`lifetime_misses` sont par construction à l'échelle du magasin, parce qu'ils ne
sont pas attachés aux entrées et n'ont donc rien sur quoi être filtrés. Deux
fonctions mémoïsées qui partagent un magasin partagent ces deux totaux.

**Un appel qui échoue n'est jamais mis en cache.** Si le travail lève, rien
n'est stocké et l'exception se propage : l'appel suivant réessaie. Le raté est
tout de même compté, d'où un `lifetime_misses` qui grimpe pendant que `entries`
reste à `0`.

**`wallet-helper stats` annonce un magasin vide.** Presque toujours parce qu'il
regarde ailleurs. Lancez `wallet-helper path`, comparez avec le `Ledger` que
votre code construit et rappelez-vous que `$WALLET_HELPER_DIR` prime sur
`~/.cache/wallet-helper`.
