# Phase 4 — Datenbank

## Datenbank-Dateien

| Pfad | Größe | Integrität | Journal Mode |
|---|---|---|---|
| `hime.db` (Projekt-Root) | 34.947.072 B (~33,3 MB) | ok | delete |
| `app/backend/hime.db` | 34.578.432 B (~33,0 MB) | ok | delete |
| `app/hime.db` | 12.288 B (~12 KB) | ok | delete |
| `.worktrees/pipeline-v2/hime.db` | 90.112 B (~88 KB) | ok | delete |

## Tabellen & Zeilenzahlen

### hime.db (Projekt-Root) — Produktionsdatenbank

| Tabelle | Zeilen | In ORM | Kommentar |
|---|---|---|---|
| books | 21 | Ja (Book) | 21 Bücher importiert |
| chapters | 430 | Ja (Chapter) | ~20 Kapitel pro Buch |
| glossaries | 6 | Ja (Glossary) | |
| glossary_terms | 5 | Ja (GlossaryTerm) | |
| hardware_stats | 0 | Nein (inline-DDL) | Wird nach 24h gepruned |
| paragraphs | 80.313 | Ja (Paragraph) | Hauptdatenvolumen |
| settings | 2 | Ja (Setting) | epub_watch_folder + auto_scan_interval |
| source_texts | 0 | Ja (SourceText) | Unbenutzt (Legacy) |
| sqlite_sequence | — | — | SQLite-intern (AUTOINCREMENT) |
| translations | 0 | Ja (Translation) | Unbenutzt (Legacy) |

### app/backend/hime.db — Backend-Kopie

| Tabelle | Zeilen | In ORM | Kommentar |
|---|---|---|---|
| books | 21 | Ja | Gleiche Bücher |
| chapters | 329 | Ja | 101 Kapitel weniger als Root-DB |
| glossaries | 0 | Ja | Leer |
| glossary_terms | 0 | Ja | Leer |
| hardware_stats | 0 | — | Gepruned |
| paragraphs | 80.077 | Ja | 236 Paragraphen weniger als Root-DB |
| settings | 2 | Ja | |
| source_texts | 0 | Ja | |
| sqlite_sequence | — | — | |
| translations | 0 | Ja | |

### app/hime.db — Veraltete Mini-DB

| Tabelle | Zeilen | In ORM | Kommentar |
|---|---|---|---|
| source_texts | 0 | Ja | Alte Schema-Version, nur 2 Tabellen |
| translations | 0 | Ja | Fehlt: confidence_log Spalte |

### .worktrees/pipeline-v2/hime.db — Worktree-Entwicklungs-DB

| Tabelle | Zeilen | In ORM | Kommentar |
|---|---|---|---|
| books | 0 | Ja | Leere Entwicklungs-DB |
| chapters | 0 | Ja | |
| glossaries | 5 | Ja | Test-Glossare |
| glossary_terms | 45 | Ja | Test-Einträge |
| hardware_stats | 0 | — | |
| paragraphs | 0 | Ja | |
| settings | 2 | Ja | |
| source_texts | 0 | Ja | |
| sqlite_sequence | — | — | |
| translations | 0 | Ja | |

## Schema

### Haupt-Schema (hime.db — Projekt-Root)

```sql
CREATE TABLE source_texts (
    id INTEGER NOT NULL,
    title VARCHAR(512) NOT NULL,
    content TEXT NOT NULL,
    language VARCHAR(10) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE books (
    id INTEGER NOT NULL,
    title VARCHAR(512) NOT NULL,
    author VARCHAR(256),
    file_path VARCHAR(1024) NOT NULL,
    cover_image_blob BLOB,
    imported_at DATETIME NOT NULL,
    last_accessed DATETIME,
    total_chapters INTEGER NOT NULL,
    total_paragraphs INTEGER NOT NULL,
    translated_paragraphs INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    series_id INTEGER,
    series_title TEXT,
    PRIMARY KEY (id),
    UNIQUE (file_path)
);

CREATE TABLE settings (
    "key" VARCHAR(128) NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY ("key")
);

CREATE TABLE translations (
    id INTEGER NOT NULL,
    source_text_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(128) NOT NULL,
    notes TEXT,
    created_at DATETIME NOT NULL,
    stage1_gemma_output TEXT,
    stage1_deepseek_output TEXT,
    stage1_qwen32b_output TEXT,
    consensus_output TEXT,
    stage2_output TEXT,
    final_output TEXT,
    pipeline_duration_ms INTEGER,
    current_stage VARCHAR(32),
    confidence_log TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY(source_text_id) REFERENCES source_texts (id)
);

CREATE TABLE chapters (
    id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title VARCHAR(512) NOT NULL,
    total_paragraphs INTEGER NOT NULL,
    translated_paragraphs INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    is_front_matter BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(book_id) REFERENCES books (id)
);

CREATE TABLE paragraphs (
    id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    paragraph_index INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT,
    is_translated BOOLEAN NOT NULL,
    is_skipped BOOLEAN NOT NULL,
    translated_at DATETIME,
    verification_result TEXT,
    is_reviewed BOOLEAN DEFAULT 0,
    reviewed_at TIMESTAMP,
    reviewer_notes TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY(chapter_id) REFERENCES chapters (id)
);

CREATE TABLE hardware_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    gpu_name TEXT,
    gpu_vram_used_mb INTEGER,
    gpu_vram_total_mb INTEGER,
    gpu_vram_pct REAL,
    gpu_utilization_pct INTEGER,
    gpu_memory_pct INTEGER,
    gpu_temp_celsius INTEGER,
    gpu_power_draw_w REAL,
    gpu_power_limit_w REAL,
    gpu_clock_mhz INTEGER,
    gpu_max_clock_mhz INTEGER,
    cpu_utilization_pct REAL,
    cpu_freq_mhz REAL,
    cpu_core_count INTEGER,
    ram_used_gb REAL,
    ram_total_gb REAL,
    ram_pct REAL,
    disk_read_mb_s REAL,
    disk_write_mb_s REAL
);

CREATE TABLE glossaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id),
    series_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE glossary_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    glossary_id INTEGER NOT NULL REFERENCES glossaries(id),
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    category TEXT,
    notes TEXT,
    occurrences INTEGER DEFAULT 0,
    is_locked BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Indexe

### Benutzerdefinierte Indexe (alle 3 Haupt-DBs identisch)

| Index | Tabelle | Spalte(n) |
|---|---|---|
| `idx_hw_timestamp` | hardware_stats | timestamp |
| `idx_translations_created` | translations | created_at |
| `idx_translations_source_text_id` | translations | source_text_id |
| `idx_chapters_book_id` | chapters | book_id |
| `idx_paragraphs_chapter_id` | paragraphs | chapter_id |
| `idx_glossary_terms_glossary` | glossary_terms | glossary_id |
| `idx_glossary_terms_source` | glossary_terms | source_term |

### Automatische Indexe

| Index | Tabelle | Grund |
|---|---|---|
| `sqlite_autoindex_books_1` | books | UNIQUE(file_path) |
| `sqlite_autoindex_settings_1` | settings | PRIMARY KEY(key) |

### Fehlende Indexe in app/hime.db

Die veraltete `app/hime.db` hat keine benutzerdefinierten Indexe.

## Foreign Keys

| Datenbank | PRAGMA foreign_keys |
|---|---|
| Alle 4 Datenbanken | **0 (deaktiviert)** |

Foreign Key Constraints sind in SQLite standardmaeßig deaktiviert. Sie werden nicht zur Laufzeit erzwungen. Die FK-Definitionen existieren im Schema, werden aber von SQLite ignoriert, solange `PRAGMA foreign_keys = ON` nicht gesetzt wird.

## Migrations-System

### Typ: Inline-Migrationen in `database.py`

Es gibt **kein Alembic** und kein separates Migrations-Framework. Alle Schema-Migrationen werden in der `init_db()`-Funktion in `app/backend/app/database.py` ausgefuehrt:

1. **Basis-Schema**: `Base.metadata.create_all` erstellt Tabellen aus den ORM-Modellen (nur bei neuen Tabellen)
2. **Spalten-Migrationen**: `PRAGMA table_info()` prueft existierende Spalten, fehlende werden per `ALTER TABLE ADD COLUMN` hinzugefuegt
3. **Tabellen-Migrationen**: `CREATE TABLE IF NOT EXISTS` fuer Tabellen, die nicht im ORM definiert sind (hardware_stats, glossaries, glossary_terms)
4. **Index-Erstellung**: `CREATE INDEX IF NOT EXISTS` fuer Performance-Indexe
5. **Seed-Daten**: `INSERT OR IGNORE` fuer Default-Settings

### Migrierte Spalten (chronologisch)

| Version | Tabelle | Spalten |
|---|---|---|
| Pipeline v1 | translations | stage1_gemma_output, stage1_deepseek_output, stage1_qwen32b_output, consensus_output, stage2_output, final_output, pipeline_duration_ms, current_stage |
| v1.2.0 | chapters | is_front_matter |
| v1.2.1 | paragraphs | verification_result, is_reviewed, reviewed_at, reviewer_notes |
| v1.2.1 | books | series_id, series_title |
| v1.2.1 | translations | confidence_log |

### Bedenken

- Kein Versionsfeld oder Migrations-Log: Es ist nicht nachvollziehbar, welche Migrationen bereits gelaufen sind (wird durch idempotente Checks kompensiert)
- `DELETE FROM hardware_stats` in `init_db()` ist eine **Schreib-Operation beim Start** — kein reines Schema-Setup
- Keine Rollback-Moeglichkeit fuer fehlgeschlagene Migrationen

## ORM-Abgleich

| ORM-Model | `__tablename__` | In Root-DB | In Backend-DB | Diskrepanz |
|---|---|---|---|---|
| SourceText | source_texts | Ja | Ja | Keine |
| Translation | translations | Ja | Ja | Keine |
| Book | books | Ja | Ja | Root-DB: series_title ist TEXT, ORM: VARCHAR(512) — Typ-Differenz durch Inline-Migration |
| Chapter | chapters | Ja | Ja | Backend-DB: is_front_matter hat DEFAULT 0, Root-DB: NOT NULL ohne DEFAULT — unterschiedl. Constraint |
| Paragraph | paragraphs | Ja | Ja | is_reviewed/reviewed_at: Root+Backend haben DEFAULT 0/TIMESTAMP statt ORM's BOOLEAN NOT NULL/DATETIME — Inline-Migration vs. ORM-DDL |
| Setting | settings | Ja | Ja | Keine |
| Glossary | glossaries | Ja | Ja | Root-DB: Inline-DDL-Schema (TIMESTAMP DEFAULT), Backend-DB: ORM-Schema (DATETIME NOT NULL) — strukturell unterschiedlich |
| GlossaryTerm | glossary_terms | Ja | Ja | Root-DB: TEXT/DEFAULT 0, Backend-DB: VARCHAR(64)/NOT NULL — gleiche Divergenz |
| — | hardware_stats | Ja | Ja | **Kein ORM-Model** — nur als Inline-DDL in database.py definiert |

## Probleme

1. **Vier separate DB-Dateien**: Es existieren 4 `hime.db`-Dateien an verschiedenen Pfaden. Die Root-DB und Backend-DB enthalten fast identische Daten (gleiche 21 Buecher), aber mit unterschiedlichen Kapitel- und Paragraphen-Zahlen (430 vs. 329 Kapitel, 80.313 vs. 80.077 Paragraphen). Es ist unklar, welche die autoritative Quelle ist.

2. **Veraltete app/hime.db**: Die Datei unter `app/hime.db` (12 KB) hat ein altes Schema mit nur 2 Tabellen und fehlendem `confidence_log`. Sie sollte entfernt oder in `.gitignore` aufgenommen werden.

3. **Foreign Keys deaktiviert**: `PRAGMA foreign_keys` ist in allen Datenbanken auf 0 (deaktiviert). Referenzielle Integritaet wird nicht erzwungen — verwaiste Datensaetze (z.B. Paragraphen ohne Kapitel) sind moeglich.

4. **Schema-Divergenz zwischen DBs**: Die Root-DB wurde teilweise durch Inline-Migrationen (`ALTER TABLE ADD COLUMN`) erweitert, die Backend-DB teilweise durch ORM-`create_all`. Dadurch unterscheiden sich Spaltentypen und Constraints (z.B. `TEXT` vs. `VARCHAR(512)`, `DEFAULT 0` vs. `NOT NULL`).

5. **hardware_stats ohne ORM-Model**: Die Tabelle `hardware_stats` wird nur per Inline-DDL erstellt, hat aber kein SQLAlchemy-Model. Zugriff muss ueber Raw-SQL erfolgen.

6. **Schreib-Operation in init_db()**: `DELETE FROM hardware_stats WHERE timestamp < datetime('now', '-24 hours')` wird bei jedem Server-Start ausgefuehrt. Dies ist eine destruktive Operation im Migrations-Kontext.

7. **Kein Migrations-Tracking**: Es gibt keinen Versionszaehler oder ein Migrations-Log. Bei komplexeren Schema-Aenderungen wird dieses System fragil.

8. **source_texts und translations unbenutzt**: Beide Legacy-Tabellen sind in allen DBs leer (0 Zeilen). Die eigentliche Uebersetzungsarbeit laeuft ueber books/chapters/paragraphs. Diese Tabellen koennten bereinigt oder als deprecated markiert werden.
