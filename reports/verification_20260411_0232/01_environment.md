# Phase 1 — Environment & Dependencies

## Conda-Env `hime`

| Eigenschaft | Wert |
|---|---|
| Status | **Vorhanden** |
| Pfad | `N:\Projekte\NiN\conda\envs\hime` |
| Python | 3.11.15 |
| Conda | 26.1.1 |

## CUDA & GPU

| Eigenschaft | Wert |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 |
| VRAM | 34.2 GB (32607 MiB) |
| CUDA (torch) | 12.8 |
| CUDA (Treiber) | 13.2 |
| Treiber | 595.97 |
| torch | 2.11.0+cu128 |
| torch.cuda.is_available | True |
| GPU-Auslastung | 45% (bei Messung) |
| VRAM belegt | 4453 MiB / 32607 MiB |

## Python-Packages (Conda-Env `hime`)

| Package | Version | Status |
|---|---|---|
| unsloth | 2026.4.4 | OK |
| transformers | 5.5.0 | OK |
| trl | 0.24.0 | OK |
| accelerate | 1.13.0 | OK |
| bitsandbytes | 0.49.2 | OK |
| peft | 0.18.1 | OK |
| datasets | 4.3.0 | OK |
| flash_attn | — | FEHLT (optional) |
| pynvml | — | FEHLT |
| fugashi | — | FEHLT |
| MeCab (mecab-python3) | 0.996 | OK (Ersatz fuer fugashi) |
| ebooklib | vorhanden | OK |
| fastapi | 0.135.3 | OK |
| uvicorn | 0.44.0 | OK |
| pydantic | 2.12.5 | OK |
| sentence_transformers | 5.4.0 | OK |
| sqlite_vec | 0.1.9 | OK |

### Hinweise zu fehlenden Packages

- **flash_attn**: Optional, nicht installiert. Wird fuer schnellere Attention-Berechnungen benoetigt, ist aber kein Blocker.
- **pynvml**: Nicht in Conda-Env installiert, aber `nvidia-ml-py` (v13.595.45) ist im Backend uv-Environment vorhanden. Das Backend nutzt nvidia-ml-py direkt.
- **fugashi**: Nicht installiert. Das Projekt nutzt stattdessen `mecab-python3` (MeCab 0.996) + `unidic-lite` fuer japanische Tokenisierung.

## Backend uv-Environment

### pyproject.toml Deklarationen vs. Installiert

| Deklarierte Abhaengigkeit | Min-Version | Installiert | Status |
|---|---|---|---|
| fastapi | >=0.111.0 | 0.135.1 | OK |
| uvicorn[standard] | >=0.29.0 | 0.42.0 | OK |
| sqlalchemy[asyncio] | >=2.0.0 | 2.0.48 | OK |
| aiosqlite | >=0.20.0 | 0.22.1 | OK |
| python-dotenv | >=1.0.0 | 1.2.2 | OK |
| slowapi | >=0.1.9 | 0.1.9 | OK |
| pydantic | >=2.7.0 | 2.12.5 | OK |
| pydantic-settings | >=2.2.0 | 2.13.1 | OK |
| openai | >=1.30.0 | 2.29.0 | OK |
| ebooklib | >=0.20 | 0.20 | OK |
| beautifulsoup4 | >=4.14.3 | 4.14.3 | OK |
| lxml | >=6.0.2 | 6.0.2 | OK |
| psutil | >=7.2.2 | 7.2.2 | OK |
| nvidia-ml-py | >=11.5.0 | 13.595.45 | OK |
| mecab-python3 | >=1.0.9 | 1.0.12 | OK |
| unidic-lite | >=1.0.8 | 1.0.8 | OK |
| jamdict | >=0.1a11 | 0.1a11.post2 | OK |
| jamdict-data | >=1.5 | 1.5 | OK |
| sqlite-vec | >=0.1.6 | 0.1.9 | OK |
| sentence-transformers | >=3.0.0 | 5.4.0 | OK |
| transformers | >=5.0.0 | 5.5.3 | OK |
| huggingface_hub | >=0.24.0 | 1.10.1 | OK |
| mcp | >=1.0.0 | 1.27.0 | OK |

### Lockfiles

- `uv.lock` — vorhanden
- `hime-backend.lock` — vorhanden (untracked in git)

### Abweichungen

- Keine fehlenden Abhaengigkeiten erkannt.
- Conda-Env `hime` hat leicht andere Versionen als das uv-Backend-Environment (z.B. transformers 5.5.0 vs 5.5.3, fastapi 0.135.3 vs 0.135.1). Die Conda-Env wird hauptsaechlich fuer Training (unsloth, trl, peft) genutzt, das uv-Env fuer den Backend-Server.

## Frontend Node-Environment

| Eigenschaft | Wert |
|---|---|
| Node.js | v22.20.0 |
| npm | 10.9.3 |
| Tauri CLI | 2.10.1 |
| Lockfile | `package-lock.json` (npm) |

### Dependencies (package.json v1.1.2)

**Runtime:**
- @tauri-apps/api ^2.10.1
- @tauri-apps/plugin-dialog ^2.6.0
- @tauri-apps/plugin-fs ^2.4.5
- @tauri-apps/plugin-opener ^2.5.3
- @tauri-apps/plugin-shell ^2.3.5
- react ^19.2.4
- react-dom ^19.2.4
- react-router-dom ^6.30.3
- recharts ^3.8.1
- zustand ^4.5.7

**Dev:**
- @tauri-apps/cli ^2.10.1
- typescript ~5.9.3
- vite ^8.0.3
- tailwindcss ^3.4.19
- eslint ^9.39.4
- @vitejs/plugin-react ^6.0.1
- concurrently ^8.2.2

## nvidia-smi Output

```
Sat Apr 11 02:39:00 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.97                 Driver Version: 595.97         CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 5090      WDDM  |   00000000:08:00.0  On |                  N/A |
| 30%   50C    P0            121W /  600W |    4453MiB /  32607MiB |     45%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

Ollama laeuft im Hintergrund (PID 30708, Compute-Prozess).

## Probleme

1. **pynvml fehlt im Conda-Env** — Nicht kritisch, da das Backend (uv-Env) `nvidia-ml-py` installiert hat und Training-Skripte GPU-Status typischerweise ueber `torch.cuda` abfragen.

2. **fugashi fehlt** — Nicht kritisch. Das Projekt nutzt `mecab-python3` + `unidic-lite` statt fugashi. Beide Environments haben MeCab installiert.

3. **flash_attn fehlt** — Optional. Kann Inference/Training beschleunigen, ist aber kein Funktionsblocker. Installation auf Windows ist oft problematisch.

4. **Zwei getrennte Python-Environments** — Conda `hime` (fuer Training/ML) und uv Backend (fuer den Server) haben teilweise unterschiedliche Package-Versionen. Dies ist beabsichtigt, sollte aber bei Updates synchron gehalten werden.

5. **hime-backend.lock nicht in Git** — Die Lockdatei ist untracked. Sollte committed werden fuer reproduzierbare Builds.

6. **Doppelter huggingface_hub Eintrag** — In `pyproject.toml` Zeile 31 und 33 ist `huggingface_hub>=0.24.0` doppelt deklariert. Funktional harmlos, aber unsauber.
