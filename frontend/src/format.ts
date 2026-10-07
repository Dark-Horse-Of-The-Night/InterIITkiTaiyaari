import type { Transcript } from './types'

/** Seconds -> "mm:ss" (same format as the backend's Markdown). */
export function formatTime(seconds: number): string {
  const whole = Math.floor(seconds)
  const minutes = Math.floor(whole / 60)
  const secs = whole % 60
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

/** 2.5 -> "2.5s"; 225.5 -> "3m 46s" */
export function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, '0')}s`
}

/** A transcript as plain text, one "[mm:ss] text" line per segment. */
export function transcriptToText(transcript: Transcript): string {
  return transcript.segments.map((s) => `[${formatTime(s.start)}] ${s.text}`).join('\n') + '\n'
}

/** "Team Sync.final.mp3" -> "Team Sync.final" */
export function fileStem(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot > 0 ? filename.slice(0, dot) : filename
}

/** Save text as a file in the browser (no server involved). */
export function downloadFile(filename: string, content: string, mimeType: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: `${mimeType};charset=utf-8` }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
