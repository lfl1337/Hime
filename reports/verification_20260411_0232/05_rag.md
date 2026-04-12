# Phase 5 — RAG-System

## Status: implementiert

Das RAG-System ist vollstaendig implementiert mit Backend-Modulen, REST-API-Endpoints, Frontend-UI-Integration und Obsidian-Vault-Export. Die Kernabhaengigkeiten (sqlite_vec, sentence_transformers, MeCab, jamdict) sind installiert. Das bge-m3 Embedding-Modell ist noch nicht lokal heruntergeladen — wird bei erstem Aufruf automatisch geladen, sofern `HIME_ALLOW_DOWNLOADS=true`.

## Modul-Uebersicht

| Datei | Zeilen | Klassen / Funktionen |
|---|---|---|
| `__init__.py` | 1 | (Docstring-only) |
| `chunker.py` | 43 | `ChunkPair` (BaseModel), `chunk_paragraph_pairs()` |
| `embeddings.py` | 66 | `_resolve_embeddings_dir()`, `get_model()`, `embed_texts()`, `embedding_dim()` |
| `indexer.py` | 76 | `build_for_book()` (async) |
| `retriever.py` | 37 | `retrieve_top_k()` (async), `format_rag_context()` |
| `store.py` | 145 | `_open_with_vec()`, `SeriesStore` (Klasse mit initialize, insert_chunks, query, count, stats, all_chunks, wipe, close) |
| `vault_exporter.py` | 236 | `sync_series()`, diverse Hilfsfunktionen fuer Obsidian-Vault-Export |
| **Gesamt** | **604** | |

## Architektur

Das RAG-System arbeitet auf **Series-Ebene** — jede Series bekommt eine eigene SQLite-Datenbank (`series_{id}.db`) im RAG-Verzeichnis (`${HIME_RAG_DIR}`, Standard: `data/rag/`).

### Datenfluss

1. **Indexierung** (`indexer.py`): Laedt alle *reviewed* Paragraphen eines Buches aus der Haupt-DB (SQLAlchemy async). Nur Paragraphen mit `is_reviewed=True` und vorhandenem source_text + translated_text werden beruecksichtigt.
2. **Chunking** (`chunker.py`): Paragraph-Level-Granularitaet (1:1 Paragraph = 1 Chunk). Sub-Satz-Chunking ist als Future-Work markiert.
3. **Embedding** (`embeddings.py`): Nutzt `bge-m3` (BAAI/bge-m3) via `sentence-transformers`. Embedding-Dimension: 1024. Embeddings werden ueber Konkatenation von `source_text + translated_text` erzeugt.
4. **Speicherung** (`store.py`): sqlite-vec Extension fuer Vektorsuche. Zwei Tabellen: `chunks` (Metadaten) und `chunk_vectors` (vec0 Virtual Table mit FLOAT[1024]).
5. **Retrieval** (`retriever.py`): Query-Text wird embedded, dann kNN-Suche via `MATCH` in der vec0-Tabelle. Ergebnis wird als Prompt-Kontext formatiert.
6. **Vault-Export** (`vault_exporter.py`): Nach jeder Indexierung werden Chunks als Markdown-Dateien in den Obsidian-Vault geschrieben (inkrementell). Erzeugt Series-Index, Top-Level-Index und `.obsidian/graph.json` fuer farbige Graph-Darstellung.

### Idempotenz

- Insert ist idempotent: `paragraph_id` hat UNIQUE-Constraint, bestehende werden uebersprungen.
- Vault-Export prueft existierende `paragraph_id` in Chunk-Dateien und schreibt nur neue.

## Abhaengigkeiten

| Dependency | Import | Verfuegbar |
|---|---|---|
| `sqlite_vec` | `import sqlite_vec` in store.py | OK (v.a. `sqlite_vec.load(conn)`) |
| `sentence_transformers` | `from sentence_transformers import SentenceTransformer` in embeddings.py | OK (Version 5.4.0) |
| `bge-m3` Modell | Erwartet unter `${HIME_EMBEDDINGS_DIR}/bge-m3` (Standard: `modelle/embeddings/bge-m3`) | FEHLT lokal — Verzeichnis `modelle/embeddings/` existiert nicht. Wird bei erstem Aufruf automatisch heruntergeladen (~1.3 GB) wenn `HIME_ALLOW_DOWNLOADS=true`. |
| `sqlalchemy` (async) | in indexer.py | OK (Teil der Backend-Deps) |
| `pydantic` | in chunker.py | OK |

## JMdict / MeCab

Der Lexikon-Service (`app/backend/app/services/lexicon_service.py`, 110 Zeilen) ist **separat vom RAG-System** und dient als "Literal Translation Anchor" fuer die Consensus-Pipeline:

| Komponente | Status | Details |
|---|---|---|
| MeCab | OK | `import MeCab` erfolgreich, Tagger funktioniert |
| jamdict (JMdict) | OK | `from jamdict import Jamdict` erfolgreich, Lookup funktioniert |
| unidic | FEHLT | `import unidic` schlaegt fehl (`ModuleNotFoundError`). MeCab nutzt stattdessen ein anderes Dictionary (vermutlich `unidic-lite` oder System-Dictionary). |

Der Lexikon-Service ist **nicht Teil des RAG-Systems**, sondern ein eigenstaendiger Service, der MeCab fuer Tokenisierung und jamdict fuer Wort-Glossare nutzt. Er erzeugt eine wortwoertliche Uebersetzung als Qualitaetsanker.

## RAG-Router

Datei: `app/backend/app/routers/rag.py` (112 Zeilen)

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/rag/index/{book_id}` | POST | Indexiert ein Buch in seinen Series-Store. Gibt `book_id` und `new_chunks` zurueck. |
| `/rag/query` | POST | Semantische Suche: nimmt `series_id`, `text`, `top_k` entgegen, gibt aehnliche Chunks zurueck. |
| `/rag/series/{series_id}/stats` | GET | Statistiken eines Series-Index: Chunk-Anzahl und letztes Update. |
| `/rag/series/{series_id}` | DELETE | Loescht den gesamten Series-Index (DB-Datei wird geloescht). |
| `/rag/vault/sync` | POST | Synchronisiert RAG-Index in den Obsidian-Vault. Optional `series_id`-Parameter; ohne wird alles synchronisiert. |

## Frontend-Integration

Die Frontend-Integration ist vollstaendig vorhanden:

| Datei | Funktion |
|---|---|
| `app/frontend/src/api/rag.ts` | API-Client mit `buildIndex()`, `getStats()`, `deleteIndex()` |
| `app/frontend/src/components/RagIndexPanel.tsx` | UI-Panel mit Index-Status-Anzeige, "Add to series index"-Button und "Rebuild index"-Button |
| `app/frontend/src/components/BookDetails.tsx` | Bindet `RagIndexPanel` in die Book-Detail-Ansicht ein (unter "RAG Index"-Ueberschrift) |

Die UI zeigt Chunk-Anzahl und letztes Update an und erlaubt das Indexieren einzelner Buecher sowie das Neuaufbauen des gesamten Series-Index.

## Obsidian-Vault-Export

Der Vault unter `obsidian-vault/` ist aktiv und enthaelt:
- `_index.md` (Top-Level-Index)
- `series_1/` und `series_2/` (mit Chunk-Dateien)
- `.obsidian/`-Konfiguration (inkl. graph.json fuer farbige Darstellung)

## Was zur vollstaendigen Nutzung fehlt

1. **bge-m3 Modell nicht lokal vorhanden**: Das Verzeichnis `modelle/embeddings/bge-m3` existiert nicht. Beim ersten RAG-Aufruf muss entweder `HIME_ALLOW_DOWNLOADS=true` gesetzt sein (automatischer Download ~1.3 GB) oder das Modell manuell bereitgestellt werden.
2. **RAG-Datenverzeichnis nicht erstellt**: `data/rag/` existiert noch nicht. Wird automatisch beim ersten Indexierungsaufruf erstellt (`mkdir parents=True` in store.py).
3. **unidic-Modul fehlt**: `import unidic` schlaegt fehl. Dies betrifft aber nur den Lexikon-Service, nicht das RAG-System direkt. MeCab funktioniert trotzdem mit einem anderen Dictionary.
4. **Kein Rate-Limiting auf RAG-Endpoints**: Die Router-Endpoints haben keine Rate-Limit-Dekoratoren, obwohl die Projekt-Konventionen dies fuer teure Endpoints vorsehen.
5. **Query-Endpoint nicht im Frontend**: Der `/rag/query`-Endpoint wird aktuell nicht vom Frontend aufgerufen — die Nutzung erfolgt vermutlich Backend-intern (z.B. `format_rag_context()` im Retriever fuer die Pipeline).
