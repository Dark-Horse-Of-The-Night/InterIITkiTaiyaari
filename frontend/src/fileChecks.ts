// Quick checks in the browser so obvious mistakes are caught before uploading.
// The backend still checks everything (only it can tell whether a file is really audio).

// Must match SUPPORTED_EXTENSIONS and MAX_UPLOAD_MB in the backend.
export const SUPPORTED_EXTENSIONS = ['.flac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.ogg', '.wav', '.webm']
export const MAX_UPLOAD_MB = 200

/** Returns a message explaining what's wrong with the file, or null if it looks fine. */
export function checkFile(file: File): string | null {
  const dot = file.name.lastIndexOf('.')
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : ''
  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    return `"${extension || 'no extension'}" files are not supported. Choose an audio file in one of these formats: ${SUPPORTED_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) {
    return 'This file is empty (0 bytes). Choose a recording that contains audio.'
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `This file is ${formatSize(file.size)}, above the ${MAX_UPLOAD_MB} MB limit. Choose a shorter or more compressed recording.`
  }
  return null
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
