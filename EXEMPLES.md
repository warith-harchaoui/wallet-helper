# Exemples wallet-helper

Un livre de recettes des usages courants. Chaque bloc Python est autonome et
s'appuie sur un magasin temporaire : on peut le coller tel quel dans un REPL
et regarder le résultat.

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
- [12. Ligne de commande](#12-ligne-de-commande)

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
        return {"text": "hello"}   # tient lieu d'appel lent à une API payante

    r1, from_cache1 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))
    r2, from_cache2 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))

    print(r1, from_cache1)   # {'text': 'hello'} False   -> exécuté
    print(r2, from_cache2)   # {'text': 'hello'} True    -> servi depuis le magasin
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

    print(square(9), square(9), square(10))   # 81 81 100
    print(square.cache_info())                 # {'entries': 2, 'hits': 1}
    square.cache_clear()
    print(square.cache_info())                 # {'entries': 0, 'hits': 0}
```

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

    print(fetch(7, client=Client()))   # exécuté
    print(fetch(7, client=Client()))   # client différent, même clé, servi depuis le magasin
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
    (d / "renamed.wav").write_bytes(b"AUDIO-BYTES")   # même contenu, nom différent

    # Chemin porté par tout le payload : le renommage touche quand même.
    print(make_key("asr", d / "clip.wav") == make_key("asr", d / "renamed.wav"))   # True

    # Un chemin niché parmi d'autres arguments est lui aussi adressé par contenu.
    a = {"args": (str(d / "clip.wav"),), "kwargs": {"lang": "en"}}
    b = {"args": (str(d / "renamed.wav"),), "kwargs": {"lang": "en"}}
    print(make_key("asr", a) == make_key("asr", b))                                # True
```

En pratique on ne construit jamais ce payload soi-même : `@memoize` s'en
charge, si bien que deux copies d'un même fichier à des chemins différents ne
déclenchent l'appel coûteux qu'une seule fois.

```python
from wallet_helper import memoize

@memoize
def transcribe(path, lang="en"):
    return call_some_paid_api(path, lang)   # exécuté une fois pour un fichier et une langue donnés

transcribe("clip.wav")            # exécuté
transcribe("archive/clip.wav")    # mêmes octets, chemin différent : servi depuis le magasin
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
        time.sleep(0.3)   # assez long pour que le second thread arrive en cours de route
        return "value"

    out = []
    def worker():
        out.append(wallet.call("job", {"x": 1}, slow))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    print(len(runs))                       # 1   -> exécuté une seule fois
    print(sorted(c for _, c in out))       # [False, True]  -> un meneur, un suiveur
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
    print(r, from_cache)   # 42 False
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)   # 42 True
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
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get_or_run(namespace, payload, work):
    call = {"namespace": namespace, "payload": payload}
    while True:
        outcome = post("/claim", call)
        if outcome["status"] == "hit":
            return outcome["result"]                       # déjà calculé
        if outcome["status"] == "leased":
            result = work()                                # nous sommes le meneur
            post("/submit", {**call, "result": result})
            return result
        time.sleep(0.2)                                    # en attente : quelqu'un d'autre l'exécute

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
bibliothèque standard.

```python
from wallet_helper import Wallet, RemoteLedger, memoize

wallet = Wallet(RemoteLedger("http://cache.internal:8000"))

@memoize(wallet=wallet)
def transcribe(path):
    return call_some_paid_api(path)   # exécuté une fois pour toute la flotte

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

    wallet.call("price", {"sym": "ACME"}, lambda: 100, ttl=3600)   # fraîche pendant une heure

    ledger.put("old", 1, ttl=0.0)                 # déjà expirée
    print(ledger.evict())                          # 1   -> entrée expirée retirée
    print(ledger.evict(max_entries=10))            # ne garde que les 10 plus récentes
    print(ledger.evict(older_than=86400))          # supprime les entrées vieilles de plus d'un jour
```

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

    print(wallet.call("cfg", {}, build, ttl=0.05))   # (1, False)  -> calculé
    time.sleep(0.06)                                   # on laisse expirer
    print(wallet.call("cfg", {}, build, ttl=0.05, stale_while_revalidate=True))  # (1, True) périmé désormais
    time.sleep(0.2)                                    # le rafraîchissement en arrière-plan s'exécute
    print(wallet.call("cfg", {}, build, ttl=100))     # (2, True)   -> valeur rafraîchie
```

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
        c = await fetch(6)          # servi depuis le magasin
        return a, b, c, len(runs)

    print(asyncio.run(main()))       # (36, 36, 36, 1)
```

## 12. Ligne de commande

Inspecter et gérer le magasin. Deux outils interchangeables sont fournis :
l'un en argparse (toujours disponible), l'autre en click (extra `[cli]`).
On pointe l'un ou l'autre vers un répertoire JSON avec `--dir` ou vers un
fichier SQLite avec `--sqlite`.

```bash
python -m wallet_helper.cli_argparse stats            # entrées et appels sauvegardés
python -m wallet_helper.cli_argparse path              # emplacement du magasin
python -m wallet_helper.cli_argparse clear             # vide le magasin
python -m wallet_helper.cli_argparse evict --older-than 604800   # supprime les entrées vieilles de plus d'une semaine

wallet-helper-click --sqlite ./ledger.db stats         # inspecte un magasin SQLite
wallet-helper-click evict --max-entries 1000           # ne garde que les 1000 plus récentes
wallet-helper-click clear --yes                        # saute la confirmation
```
