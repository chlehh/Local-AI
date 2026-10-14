# Benchmark

16 vCPU, 63 Go RAM, 3 prompts × 3 passes, 256 tokens max, température 0

| Modèle | Chargement (s) | TTFT médian (s) | Débit médian (tok/s) | Débit prompt (tok/s) | RAM modèle (Go) | VRAM (Go) | RAM conteneur max (Go) | CPU moyen (%) | CPU max (%) | GPU max (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| phi3:mini | 2.5 | 0.36 | 27.43 | 138.8 | 3.59 | 0.0 | 4.02 | 99.6 | 100.0 | – |
| mistral:7b-instruct | 4.3 | 0.53 | 15.13 | 71.1 | 4.69 | 0.0 | 4.9 | 99.8 | 100.0 | – |
| llama3.1:8b | 4.9 | 0.82 | 14.54 | 51.8 | 5.19 | 0.0 | 5.51 | 99.8 | 100.0 | – |
