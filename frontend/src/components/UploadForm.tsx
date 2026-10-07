import { useRef, useState, type DragEvent, type FormEvent } from 'react'

import { checkFile, formatSize, MAX_UPLOAD_MB, SUPPORTED_EXTENSIONS } from '../fileChecks'

interface Props {
  onSubmit: (file: File, glossary: string) => void
  uploading: boolean
}

export default function UploadForm({ onSubmit, uploading }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [glossary, setGlossary] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function choose(chosen: File | undefined) {
    if (!chosen) return
    const issue = checkFile(chosen)
    setProblem(issue)
    setFile(issue ? null : chosen)
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    choose(event.dataTransfer.files[0])
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (file) onSubmit(file, glossary)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          dragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40'
            : 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-900'
        }`}
      >
        <p className="text-base font-medium text-slate-800 dark:text-slate-100">Drop a meeting recording here</p>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">or</p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-3 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
        >
          Choose file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={SUPPORTED_EXTENSIONS.join(',')}
          aria-label="Meeting recording"
          className="hidden"
          onChange={(event) => {
            choose(event.target.files?.[0])
            event.target.value = '' // allow choosing the same file again
          }}
        />
        <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
          English recordings · {SUPPORTED_EXTENSIONS.join(' ')} · up to {MAX_UPLOAD_MB} MB
        </p>
      </div>

      {file && (
        <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
          Selected: <span className="font-medium">{file.name}</span> ({formatSize(file.size)})
        </p>
      )}
      {problem && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/50 dark:text-red-200">
          {problem}
        </p>
      )}

      <div>
        <label htmlFor="glossary" className="block text-sm font-medium text-slate-700 dark:text-slate-200">
          Terms used in this meeting <span className="font-normal text-slate-500 dark:text-slate-400">(optional)</span>
        </label>
        <input
          id="glossary"
          type="text"
          value={glossary}
          onChange={(event) => setGlossary(event.target.value)}
          placeholder="e.g. Zephyr, KubeFlow, Project Atlas"
          className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-indigo-900"
        />
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Comma-separated. Helps the refiner spell project names and jargon correctly.
        </p>
      </div>

      <button
        type="submit"
        disabled={!file || uploading}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? 'Uploading…' : 'Process recording'}
      </button>
    </form>
  )
}
