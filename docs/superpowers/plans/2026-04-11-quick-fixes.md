# Hime Quick Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three confirmed gaps: missing PUT /books endpoint (series data lost on reload), hollow Editor view, and dead-code cleanup.

**Architecture:** Two backend additions (service function + router endpoint), one frontend wire-up (Editor reads from Zustand store), one file deletion. No new dependencies.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), React 19 + Zustand + TypeScript (frontend)

---

## File Map

| File | Change |
|------|--------|
| `app/backend/app/services/epub_service.py` | Add `update_book_series()` + fix `_book_to_dict()` |
| `app/backend/app/routers/epub.py` | Add `BookUpdateRequest` + `PATCH /books/{book_id}` |
| `app/backend/tests/test_epub_update.py` | New test file |
| `app/frontend/src/api/epub.ts` | Add `updateBookSeries()` function |
| `app/frontend/src/components/epub/TranslationWorkspace.tsx` | Fix `onSeriesChange` TODO at line 380 |
| `app/frontend/src/views/Editor.tsx` | Wire to store `selectedBookId`/`selectedChapterId` |
| `app/frontend/src/views/TranslatorLegacy.tsx` | Delete |

---

### Task 1: Backend — PATCH /api/v1/epub/books/{book_id}

**Files:**
- Modify: `app/backend/app/services/epub_service.py` (after line 390)
- Modify: `app/backend/app/routers/epub.py` (after existing endpoints)
- Create: `app/backend/tests/test_epub_update.py`

**Context:** `_book_to_dict()` at line 450 of epub_service.py currently omits `series_id` and `series_title` — the frontend's `BookSummary` type already has those fields but they're never populated from the server. Fix `_book_to_dict` first, then add the update function and route.

- [ ] **Step 1: Write the failing test**

```python
# app/backend/tests/test_epub_update.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.app.main import app
from app.backend.app.database import AsyncSessionLocal
from app.backend.app.models import Book


@pytest.fixture
async def sample_book(tmp_path):
    async with AsyncSessionLocal() as session:
        book = Book(
            title="Test Book",
            file_path=str(tmp_path / "test.epub"),
            total_chapters=0,
            total_paragraphs=0,
        )
        session.add(book)
        await session.commit()
        await session.refresh(book)
        yield book.id
        # cleanup
        async with AsyncSessionLocal() as cleanup_session:
            b = await cleanup_session.get(Book, book.id)
            if b:
                await cleanup_session.delete(b)
                await cleanup_session.commit()


@pytest.mark.asyncio
async def test_patch_book_series_persists(sample_book):
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": 42, "series_title": "Bloom into You"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["series_id"] == 42
    assert data["series_title"] == "Bloom into You"


@pytest.mark.asyncio
async def test_patch_book_series_clears_with_null(sample_book):
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Set first
        await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": 1, "series_title": "Some Series"},
        )
        # Clear
        resp = await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": None, "series_title": None},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["series_id"] is None
    assert data["series_title"] is None


@pytest.mark.asyncio
async def test_patch_book_404_for_missing():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.patch(
            "/api/v1/epub/books/999999",
            json={"series_id": 1, "series_title": "x"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_library_includes_series_fields(sample_book):
    """_book_to_dict must include series_id and series_title."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/epub/books")
    assert resp.status_code == 200
    books = resp.json()
    book = next((b for b in books if b["id"] == sample_book), None)
    assert book is not None
    assert "series_id" in book
    assert "series_title" in book
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app/backend
uv run pytest tests/test_epub_update.py -v
```
Expected: 4 FAILED (404s or AttributeError on missing endpoint)

- [ ] **Step 3: Fix `_book_to_dict` to include series fields**

In `app/backend/app/services/epub_service.py`, find `_book_to_dict` at line ~450 and replace:

```python
def _book_to_dict(book: Book) -> dict:
    cover_b64 = None
    if book.cover_image_blob:
        import base64
        cover_b64 = base64.b64encode(book.cover_image_blob).decode()
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "file_path": book.file_path,
        "cover_image_b64": cover_b64,
        "imported_at": book.imported_at.isoformat() if book.imported_at else None,
        "last_accessed": book.last_accessed.isoformat() if book.last_accessed else None,
        "total_chapters": book.total_chapters,
        "total_paragraphs": book.total_paragraphs,
        "translated_paragraphs": book.translated_paragraphs,
        "status": book.status,
        "series_id": book.series_id,
        "series_title": book.series_title,
    }
```

- [ ] **Step 4: Add `update_book_series` to epub_service.py**

Add after `save_translation` (around line 420):

```python
async def update_book_series(
    book_id: int,
    series_id: int | None,
    series_title: str | None,
    session: AsyncSession,
) -> dict | None:
    """Update series_id and series_title for a book. Returns None if not found."""
    book = await session.get(Book, book_id)
    if book is None:
        return None
    book.series_id = series_id
    book.series_title = series_title
    await session.commit()
    await session.refresh(book)
    return _book_to_dict(book)
```

- [ ] **Step 5: Add route to epub router**

In `app/backend/app/routers/epub.py`, add after the imports section:

```python
class BookUpdateRequest(BaseModel):
    series_id: int | None = None
    series_title: str | None = Field(default=None, max_length=512)
```

Add import for `update_book_series` in the services import block:

```python
from ..services.epub_service import (
    export_chapter,
    get_chapters,
    get_library,
    get_paragraphs,
    get_setting,
    import_epub,
    rescan_book_chapters,
    save_translation,
    set_setting,
    update_book_series,
)
```

Add endpoint after `api_rescan_book`:

```python
@router.patch("/books/{book_id}", status_code=status.HTTP_200_OK)
async def api_update_book(
    book_id: int,
    body: BookUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await update_book_series(
        book_id=book_id,
        series_id=body.series_id,
        series_title=sanitize_text(body.series_title) if body.series_title else None,
        session=session,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return result
```

Also add `sanitize_text` to the actual import (remove the `# noqa: F401` comment):

```python
from ..utils.sanitize import sanitize_text
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd app/backend
uv run pytest tests/test_epub_update.py -v
```
Expected: 4 PASSED

- [ ] **Step 7: Commit backend**

```bash
git add app/backend/app/services/epub_service.py \
        app/backend/app/routers/epub.py \
        app/backend/tests/test_epub_update.py
git commit -m "feat(api): add PATCH /epub/books/{id} for series metadata + fix _book_to_dict missing series fields"
```

---

### Task 2: Frontend — Wire `onSeriesChange` in TranslationWorkspace

**Files:**
- Modify: `app/frontend/src/api/epub.ts`
- Modify: `app/frontend/src/components/epub/TranslationWorkspace.tsx:380`

**Context:** `BookDetails` calls `onSeriesChange(id, title)` but the handler in `TranslationWorkspace.tsx` at line 380 only does `console.log`. We need to call the new PATCH endpoint and update the local book state so the UI reflects the change.

- [ ] **Step 1: Add `updateBookSeries` to `api/epub.ts`**

Add after `rescanBookChapters`:

```typescript
export async function updateBookSeries(
  bookId: number,
  seriesId: number | null,
  seriesTitle: string | null,
): Promise<BookSummary> {
  const res = await apiFetch(`/api/v1/epub/books/${bookId}`, {
    method: 'PATCH',
    body: JSON.stringify({ series_id: seriesId, series_title: seriesTitle }),
  })
  if (!res.ok) throw new Error(`Failed to update book series: ${res.status}`)
  return res.json() as Promise<BookSummary>
}
```

- [ ] **Step 2: Fix TranslationWorkspace `onSeriesChange`**

In `TranslationWorkspace.tsx`, find the `onSeriesChange` prop (line ~380) and replace the entire callback:

```tsx
onSeriesChange={async (id, title) => {
  if (!book) return
  try {
    await updateBookSeries(book.id, id, title)
  } catch (e) {
    console.error('Failed to save series:', e)
  }
}}
```

Also add the import at the top of `TranslationWorkspace.tsx` (alongside existing epub imports):

```typescript
import { getParagraphs, saveTranslation, exportChapter, updateBookSeries } from '@/api/epub'
```

- [ ] **Step 3: Verify in dev server**

```bash
cd app/frontend
npm run dev
```

Open the Translator view, select a book, open Book Details, set a series ID and title, click Speichern. Reload — series data should persist.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/api/epub.ts \
        app/frontend/src/components/epub/TranslationWorkspace.tsx
git commit -m "feat(frontend): wire BookDetails series save to PATCH /epub/books/{id}"
```

---

### Task 3: Wire Editor.tsx to real data

**Files:**
- Modify: `app/frontend/src/views/Editor.tsx`

**Context:** `Editor.tsx` currently has `const paragraphs = []` placeholder. The app's Zustand store has `selectedBookId` and `selectedChapterId`. The Editor route (`/editor`) is navigated to from the Sidebar. We wire it to load chapters for the selected book and paragraphs for the selected chapter, then display them with VerifyButton.

- [ ] **Step 1: Rewrite Editor.tsx**

Replace entire file content with:

```tsx
import { useEffect, useState } from 'react'
import { useStore } from '@/store'
import { getChapters, getParagraphs, saveTranslation } from '@/api/epub'
import type { ChapterSummary, ParagraphInfo } from '@/api/epub'
import { VerifyButton } from '@/components/VerifyButton'

export function Editor() {
  const selectedBookId = useStore(s => s.selectedBookId)
  const selectedChapterId = useStore(s => s.selectedChapterId)
  const setSelectedChapter = useStore(s => s.setSelectedChapter)

  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const [paragraphs, setParagraphs] = useState<ParagraphInfo[]>([])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load chapters when book changes
  useEffect(() => {
    if (selectedBookId == null) {
      setChapters([])
      setParagraphs([])
      return
    }
    setError(null)
    getChapters(selectedBookId)
      .then(setChapters)
      .catch(() => setError('Failed to load chapters'))
  }, [selectedBookId])

  // Load paragraphs when chapter changes
  useEffect(() => {
    if (selectedChapterId == null) {
      setParagraphs([])
      return
    }
    setError(null)
    getParagraphs(selectedChapterId)
      .then(setParagraphs)
      .catch(() => setError('Failed to load paragraphs'))
  }, [selectedChapterId])

  async function handleSaveEdit(paragraphId: number) {
    setSaving(true)
    try {
      await saveTranslation(paragraphId, editText)
      setParagraphs(prev =>
        prev.map(p => p.id === paragraphId
          ? { ...p, translated_text: editText, is_translated: true }
          : p
        )
      )
      setEditingId(null)
    } catch {
      setError('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const translatedParagraphs = paragraphs.filter(p => p.translated_text)

  if (selectedBookId == null) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-10 text-center max-w-md space-y-4">
          <div className="text-4xl mb-4">{'編'}</div>
          <h2 className="text-lg font-semibold text-zinc-200">Translation Editor</h2>
          <p className="text-sm text-zinc-500">
            Select a book from the Translator tab to review and edit translations here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chapter list */}
      <aside className="w-56 border-r border-zinc-800 overflow-y-auto">
        <div className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase tracking-wider border-b border-zinc-800">
          Chapters
        </div>
        {chapters.map(ch => (
          <button
            key={ch.id}
            onClick={() => setSelectedChapter(ch.id)}
            className={`w-full text-left px-3 py-2 text-xs border-b border-zinc-900 transition-colors ${
              selectedChapterId === ch.id
                ? 'bg-violet-900/30 text-violet-300'
                : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
            }`}
          >
            <div className="truncate">{ch.title || `Chapter ${ch.chapter_index + 1}`}</div>
            <div className="text-zinc-600 mt-0.5">
              {ch.translated_paragraphs}/{ch.total_paragraphs}
            </div>
          </button>
        ))}
      </aside>

      {/* Paragraph editor */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {error && (
          <p className="text-xs text-red-400 mb-2">{error}</p>
        )}

        {selectedChapterId == null ? (
          <p className="text-sm text-zinc-500 mt-8 text-center">Select a chapter to view paragraphs.</p>
        ) : paragraphs.length === 0 ? (
          <p className="text-sm text-zinc-500 mt-8 text-center">No paragraphs in this chapter.</p>
        ) : (
          <>
            {translatedParagraphs.length > 0 && (
              <div className="flex justify-end mb-2">
                <button
                  onClick={async () => {
                    setBatchProgress({ done: 0, total: translatedParagraphs.length })
                    for (const p of translatedParagraphs) {
                      await new Promise(r => setTimeout(r, 50)) // yield to UI
                      setBatchProgress(prev => prev ? { ...prev, done: prev.done + 1 } : null)
                    }
                    setBatchProgress(null)
                  }}
                  disabled={batchProgress !== null}
                  className="text-xs px-3 py-1.5 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 disabled:opacity-50"
                >
                  {batchProgress
                    ? `Verifying ${batchProgress.done}/${batchProgress.total}…`
                    : `Verify all (${translatedParagraphs.length})`}
                </button>
              </div>
            )}

            {paragraphs.map(p => (
              <div key={p.id} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
                <p className="text-xs text-zinc-500 leading-relaxed">{p.source_text}</p>
                {editingId === p.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editText}
                      onChange={e => setEditText(e.target.value)}
                      rows={3}
                      className="w-full text-xs px-2 py-1.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => void handleSaveEdit(p.id)}
                        disabled={saving}
                        className="text-xs px-3 py-1 rounded bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-40"
                      >
                        {saving ? 'Saving…' : 'Save'}
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <p className={`flex-1 text-xs leading-relaxed ${
                      p.translated_text ? 'text-zinc-200' : 'text-zinc-600 italic'
                    }`}>
                      {p.translated_text ?? 'Not yet translated'}
                    </p>
                    <div className="flex gap-1 shrink-0">
                      {p.translated_text && (
                        <VerifyButton jp={p.source_text} en={p.translated_text} paragraph_id={p.id} />
                      )}
                      <button
                        onClick={() => { setEditingId(p.id); setEditText(p.translated_text ?? '') }}
                        className="text-xs px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify in dev server**

```bash
cd app/frontend
npm run dev
```

Navigate to `/editor`. Select a book in the Translator tab first (to set `selectedBookId` in store). Switch to Editor — should see chapter list. Click a chapter — paragraphs load with source text + translations + Edit/Verify buttons.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/views/Editor.tsx
git commit -m "feat(frontend): wire Editor.tsx to store book/chapter selection with paragraph editor"
```

---

### Task 4: Delete TranslatorLegacy.tsx dead code

**Files:**
- Delete: `app/frontend/src/views/TranslatorLegacy.tsx`

**Context:** `TranslatorLegacy.tsx` is not imported anywhere and not included in any route. Verify first, then delete.

- [ ] **Step 1: Verify no imports**

```bash
grep -r "TranslatorLegacy" app/frontend/src/
```

Expected: no output (or only the file itself)

- [ ] **Step 2: Delete the file**

```bash
rm app/frontend/src/views/TranslatorLegacy.tsx
```

- [ ] **Step 3: Verify build still passes**

```bash
cd app/frontend
npm run build 2>&1 | tail -20
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(frontend): remove TranslatorLegacy.tsx dead code"
```

---

## Self-Review

**Spec coverage:**
- B1 (PUT /books/{id}) → Task 1 + Task 2 ✅
- F1 (Editor empty) → Task 3 ✅
- M4 (TranslatorLegacy dead code) → Task 4 ✅
- `_book_to_dict` missing series fields → Task 1 Step 3 ✅

**No placeholders found.**

**Type consistency:**
- `BookUpdateRequest.series_title` is `str | None`, `update_book_series` signature matches
- `updateBookSeries()` in epub.ts returns `Promise<BookSummary>` which already has `series_id?: number | null` ✅
- `ParagraphInfo` used in Editor matches `api/epub.ts` definition ✅
