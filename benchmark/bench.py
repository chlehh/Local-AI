#!/usr/bin/env python3
"""Benchmark des modèles Ollama : TTFT, tokens/s, mémoire RAM/VRAM, charge CPU/GPU.

Usage :  python3 bench.py                      (3 modèles par défaut)
         python3 bench.py phi3:mini llama3.1:8b
"""
import csv
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

OLLAMA = "http://localhost:11434"
MODELES = sys.argv[1:] or ["phi3:mini", "mistral:7b-instruct", "llama3.1:8b"]
PASSES = 3
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 256, "num_ctx": 4096}
PROMPTS = {
    "court": "Explique en trois phrases ce qu'est la virtualisation.",
    "code": "Écris une fonction Python est_palindrome(texte) qui ignore la casse, "
            "les espaces et la ponctuation, avec une docstring.",
    "raisonnement": "Un train part de Mulhouse à 8 h 15 à 120 km/h vers Strasbourg (110 km). "
                    "Un autre part de Strasbourg à 8 h 45 à 100 km/h vers Mulhouse. "
                    "À quelle heure se croisent-ils ? Détaille le calcul.",
}


# ---------- 1. Dialogue avec l'API d'Ollama ----------

def appel(chemin, donnees=None):
    """Requête simple à l'API : GET sans données, POST avec données."""
    corps = json.dumps(donnees).encode() if donnees is not None else None
    req = urllib.request.Request(OLLAMA + chemin, data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read() or b"{}")


def generer(modele, prompt):
    """Génération en streaming. Renvoie (TTFT en s, texte généré, statistiques d'Ollama)."""
    corps = {"model": modele, "prompt": prompt, "options": OPTIONS, "stream": True}
    req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(corps).encode(),
                                 headers={"Content-Type": "application/json"})
    debut = time.perf_counter()
    ttft, texte = None, []
    with urllib.request.urlopen(req, timeout=900) as r:
        for ligne in r:                      # Ollama envoie un objet JSON par token
            morceau = json.loads(ligne)
            if ttft is None and morceau.get("response"):
                ttft = time.perf_counter() - debut   # premier token reçu
            texte.append(morceau.get("response", ""))
            if morceau.get("done"):          # dernier objet : statistiques
                return ttft, "".join(texte), morceau
    raise RuntimeError("réponse incomplète d'Ollama")


# ---------- 2. Mesures système pendant la génération ----------

def ram_conteneur():
    """Mémoire utilisée par le conteneur ollama, en Go (via docker stats)."""
    try:
        sortie = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}",
                                 "ollama"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return None
    valeur = sortie.split("/")[0].strip()    # ex. "5.12GiB / 48GiB" -> "5.12GiB"
    for unite, facteur in (("GiB", 1), ("MiB", 1 / 1024), ("KiB", 1 / 1024 ** 2)):
        if valeur.endswith(unite):
            return float(valeur[:-len(unite)]) * facteur
    return None


def charge_gpu():
    """Utilisation du GPU en %, ou None s'il n'y a pas de GPU NVIDIA."""
    try:
        sortie = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True)
        return float(sortie.stdout.split()[0])
    except (FileNotFoundError, IndexError, ValueError):
        return None


class Mesureur(threading.Thread):
    """Tourne en parallèle de la génération et relève CPU, RAM du conteneur et GPU."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cpu, self.ram, self.gpu = [], [], []
        self.arret = threading.Event()

    def run(self):
        psutil.cpu_percent()                 # initialise la mesure CPU
        while not self.arret.wait(0.5):
            self.cpu.append(psutil.cpu_percent())   # % moyen sur tous les cœurs de la VM
            ram = ram_conteneur()
            if ram is not None:
                self.ram.append(ram)
            gpu = charge_gpu()
            if gpu is not None:
                self.gpu.append(gpu)


# ---------- 3. Benchmark ----------

def mediane(valeurs):
    valeurs = [v for v in valeurs if isinstance(v, (int, float))]
    return round(statistics.median(valeurs), 2) if valeurs else "–"


def maximum(valeurs):
    valeurs = [v for v in valeurs if isinstance(v, (int, float))]
    return round(max(valeurs), 2) if valeurs else "–"


disponibles = {m["name"] for m in appel("/api/tags")["models"]}
dossier = Path("resultats") / datetime.now().strftime("%Y-%m-%d_%H-%M")
dossier.mkdir(parents=True, exist_ok=True)
mesures, synthese, reponses = [], [], []

for modele in MODELES:
    if modele not in disponibles:
        print(f"!! {modele} absent : docker exec ollama ollama pull {modele}")
        continue
    print(f"\n=== {modele} ===")

    # Chargement à froid : on vide la mémoire, puis on charge le modèle (prompt vide)
    for m in appel("/api/ps")["models"]:
        appel("/api/generate", {"model": m["name"], "keep_alive": 0})
    time.sleep(2)
    debut = time.perf_counter()
    appel("/api/generate", {"model": modele, "options": OPTIONS})
    chargement = time.perf_counter() - debut
    infos = next(m for m in appel("/api/ps")["models"] if m["name"] == modele)
    ram_modele = infos["size"] / 1024 ** 3        # taille du modèle chargé
    vram_modele = infos["size_vram"] / 1024 ** 3  # dont partie en mémoire GPU
    print(f"chargé en {chargement:.1f} s · {ram_modele:.2f} Go en mémoire "
          f"(dont {vram_modele:.2f} Go en VRAM)")

    lignes = []
    for passe in range(1, PASSES + 1):
        for nom, prompt in PROMPTS.items():
            mesureur = Mesureur()
            mesureur.start()
            ttft, texte, stats = generer(modele, prompt)
            mesureur.arret.set()
            mesureur.join()
            ligne = {
                "modele": modele, "prompt": nom, "passe": passe,
                "ttft_s": round(ttft, 3) if ttft else None,
                "tokens_generes": stats["eval_count"],
                "debit_tok_s": round(stats["eval_count"] / (stats["eval_duration"] / 1e9), 2),
                "debit_prompt_tok_s": round(stats["prompt_eval_count"]
                                            / (stats["prompt_eval_duration"] / 1e9), 1)
                if stats.get("prompt_eval_duration") else None,
                "cpu_moyen_pct": round(statistics.fmean(mesureur.cpu), 1) if mesureur.cpu else None,
                "cpu_max_pct": maximum(mesureur.cpu),
                "ram_conteneur_max_go": maximum(mesureur.ram),
                "gpu_max_pct": maximum(mesureur.gpu),
            }
            lignes.append(ligne)
            if passe == 1:
                reponses.append(f"## {modele} · {nom}\n\n{texte}\n")
            print(f"  passe {passe} {nom:<13} TTFT {ligne['ttft_s']} s · "
                  f"{ligne['debit_tok_s']} tok/s · CPU {ligne['cpu_moyen_pct']} %")
    mesures += lignes

    synthese.append({
        "Modèle": modele,
        "Chargement (s)": round(chargement, 1),
        "TTFT médian (s)": mediane([l["ttft_s"] for l in lignes]),
        "Débit médian (tok/s)": mediane([l["debit_tok_s"] for l in lignes]),
        "Débit prompt (tok/s)": mediane([l["debit_prompt_tok_s"] for l in lignes]),
        "RAM modèle (Go)": round(ram_modele, 2),
        "VRAM (Go)": round(vram_modele, 2),
        "RAM conteneur max (Go)": maximum([l["ram_conteneur_max_go"] for l in lignes]),
        "CPU moyen (%)": mediane([l["cpu_moyen_pct"] for l in lignes]),
        "CPU max (%)": maximum([l["cpu_max_pct"] for l in lignes]),
        "GPU max (%)": maximum([l["gpu_max_pct"] for l in lignes]),
    })

# ---------- 4. Enregistrement des résultats ----------

if mesures:
    with open(dossier / "mesures.csv", "w", newline="", encoding="utf-8") as f:
        ecrivain = csv.DictWriter(f, fieldnames=list(mesures[0]))
        ecrivain.writeheader()
        ecrivain.writerows(mesures)
    entetes = list(synthese[0])
    tableau = ["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
    tableau += ["| " + " | ".join(str(s[e]) for e in entetes) + " |" for s in synthese]
    machine = (f"{psutil.cpu_count()} vCPU, {psutil.virtual_memory().total / 1024 ** 3:.0f} Go RAM, "
               f"{len(PROMPTS)} prompts × {PASSES} passes, 256 tokens max, température 0")
    (dossier / "synthese.md").write_text(f"# Benchmark\n\n{machine}\n\n" + "\n".join(tableau) + "\n",
                                         encoding="utf-8")
    (dossier / "reponses.md").write_text("\n".join(reponses), encoding="utf-8")
    print("\n" + "\n".join(tableau))
    print(f"\nRésultats enregistrés dans {dossier}/")
