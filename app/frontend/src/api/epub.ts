import { apiFetch } from './client'

export interface BookSummary {
  id: number
  title: string
  author: string | null
  file_path: string
  cover_image_b64: string | null
  imported_at: string | null
  last_accessed: string | null
  total_chapters: number
  total_paragraphs: number
  translated_paragraphs: number
  status: 'not_started' | 'in_progress' | 'complete'
}

export interface ChapterSummary {
  id: number
  book_id: number
  chapter_index: number
  title: string
  total_paragraphs: number
  translated_paragraphs: number
  status: 'not_started' | 'in_progress' | 'complete'
  is_front_matter: boolean
}

export interface ParagraphInfo {
  id: number
  chapter_id: number
  paragraph_index: number
  source_text: string
  translated_text: string | null
  is_translated: boolean
  is_skipped: boolean
  translated_at: string | null
}

export async function importEpub(filePath: string): Promise<BookSummary> {
  const res = await apiFetch('/api/v1/epub/import', {
    method: 'POST',
    body: JSON.stringify({ file_path: filePath }),
  })
  if (!res.ok) throw new Error(`Import failed: ${res.status}`)
  return res.json() as Promise<BookSummary>
}

export async function getLibrary(): Promise<BookSummary[]> {
  const res = await apiFetch('/api/v1/epub/books')
  if (!res.ok) throw new Error(`Failed to load library: ${res.status}`)
  return res.json() as Promise<BookSummary[]>
}

export async function getChapters(bookId: number): Promise<ChapterSummary[]> {
  const res = await apiFetch(`/api/v1/epub/books/${bookId}/chapters`)
  if (!res.ok) throw new Error(`Failed to load chapters: ${res.status}`)
  return res.json() as Promise<ChapterSummary[]>
}

export async function getParagraphs(chapterId: number): Promise<ParagraphInfo[]> {
  const res = await apiFetch(`/api/v1/epub/chapters/${chapterId}/paragraphs`)
  if (!res.ok) throw new Error(`Failed to load paragraphs: ${res.status}`)
  return res.json() as Promise<ParagraphInfo[]>
}

export async function saveTranslation(paragraphId: number, text: string): Promise<void> {
  const res = await apiFetch(`/api/v1/epub/paragraphs/${paragraphId}/translation`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error(`Failed to save translation: ${res.status}`)
}

export async function exportChapter(chapterId: number, format: 'txt' = 'txt'): Promise<string> {
  const res = await apiFetch(`/api/v1/epub/export/${chapterId}?format=${format}`)
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  const data = await res.json() as { content: string }
  return data.content
}

export async function rescanBookChapters(bookId: number): Promise<BookSummary> {
  const res = await apiFetch(`/api/v1/epub/books/${bookId}/rescan`, { method: 'POST' })
  if (!res.ok) throw new Error(`Rescan failed: ${res.status}`)
  return res.json() as Promise<BookSummary>
}

export async function getEpubSettings(): Promise<{ epub_watch_folder: string; auto_scan_interval: string }> {
  const res = await apiFetch('/api/v1/epub/settings')
  if (!res.ok) throw new Error(`Failed to load settings: ${res.status}`)
  return res.json() as Promise<{ epub_watch_folder: string; auto_scan_interval: string }>
}

export async function updateEpubSetting(key: string, value: string): Promise<void> {
  const res = await apiFetch('/api/v1/epub/settings', {
    method: 'POST',
    body: JSON.stringify({ key, value }),
  })
  if (!res.ok) throw new Error(`Failed to update setting: ${res.status}`)
}
