import { useRef, useState, type DragEvent, type FormEvent } from 'react'

import { checkFile, formatSize, MAX_UPLOAD_MB, SUPPORTED_EXTENSIONS } from '../fileChecks'
import { ArrowRightIcon, AudioFileIcon, CloseIcon, ShieldIcon, UploadIcon } from './Icons'

interface Props {
  onSubmit: (file: File, glossary: string) => void
  uploading: boolean
}

const OUTPUTS = [
  { title: 'Raw transcript', text: "Whisper's timestamped output, exactly as heard." },
  { title: 'Refined transcript', text: 'Misheard technical terms fixed. Names, numbers and negations never change.' },
  { title: 'Meeting record', text: 'Summary, minutes, decisions, action items and open proposals, as Markdown and JSON.' },
]

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
    <div>
      <div className="max-w-[720px]">
        <p className="eyebrow mb-2.5 text-accent-ink">New recording</p>
        <h1 className="text-[34px] leading-[1.12] font-semibold tracking-[-0.025em] sm:text-[40px]">
          Turn a meeting into a record you can trust.
        </h1>
        <p className="mt-3.5 max-w-[640px] text-[17px] text-ink-2">
          Get the raw transcript, a refined transcript with technical terms corrected, and structured minutes. Every
          decision and action item is backed by a quote from the recording.
        </p>
      </div>

      <div className="mt-9 flex flex-wrap items-start gap-6">
        <form onSubmit={handleSubmit} className="card flex min-w-0 flex-[999_1_560px] flex-col gap-5 p-6">
          <div
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center gap-2.5 rounded-xl border-[1.5px] border-dashed px-6 py-10 text-center transition-colors ${
              dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface-2'
            }`}
          >
            <span className="flex size-[52px] items-center justify-center rounded-[14px] bg-accent-soft text-accent-ink">
              <UploadIcon size={26} strokeWidth={1.8} />
            </span>
            <p className="mt-1.5 text-[17px] font-semibold">Drop a meeting recording here</p>
            <p className="text-sm text-muted">or</p>
            <button type="button" onClick={() => inputRef.current?.click()} className="btn-secondary min-h-11 px-[18px]">
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
            <p className="mt-2 text-[12.5px] text-muted">
              English · {SUPPORTED_EXTENSIONS.join(' ')} · up to {MAX_UPLOAD_MB} MB or 120 minutes
            </p>
          </div>

          {file && (
            <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-subtle text-ink-2">
                <AudioFileIcon size={20} strokeWidth={1.8} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{file.name}</p>
                <p className="text-[13px] text-muted">{formatSize(file.size)} · ready to process</p>
              </div>
              <button
                type="button"
                aria-label="Remove file"
                onClick={() => setFile(null)}
                className="flex size-11 cursor-pointer items-center justify-center rounded-[10px] text-muted hover:bg-subtle"
              >
                <CloseIcon />
              </button>
            </div>
          )}
          {problem && (
            <p role="alert" className="rounded-xl border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger-ink">
              {problem}
            </p>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="glossary" className="text-sm font-medium">
              Terms used in this meeting <span className="font-normal text-muted">(optional)</span>
            </label>
            <input
              id="glossary"
              type="text"
              value={glossary}
              onChange={(event) => setGlossary(event.target.value)}
              placeholder="e.g. Zephyr, KubeFlow, Project Atlas"
              className="min-h-11 rounded-[10px] border border-line-strong bg-surface px-3.5 text-[15px] text-ink placeholder:text-faint focus:border-accent focus:ring-3 focus:ring-accent-soft focus:outline-none"
            />
            <p className="text-[13px] text-muted">Comma-separated. Helps the refiner spell project names and jargon correctly.</p>
          </div>

          <button type="submit" disabled={!file || uploading} className="btn-primary min-h-12 rounded-xl text-[15px]">
            {uploading ? 'Uploading…' : 'Process recording'}
            {!uploading && <ArrowRightIcon />}
          </button>
        </form>

        <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-3">
          <h2 className="eyebrow mt-1 mb-1 text-muted">What you get</h2>
          {OUTPUTS.map((output, i) => (
            <div key={output.title} className="flex gap-3 rounded-[14px] border border-line bg-surface p-4">
              <span className="h-fit rounded-md bg-subtle px-[7px] py-0.5 font-mono text-xs font-medium text-ink-2">
                0{i + 1}
              </span>
              <div>
                <p className="font-semibold">{output.title}</p>
                <p className="mt-0.5 text-sm text-muted">{output.text}</p>
              </div>
            </div>
          ))}
          <div className="flex items-start gap-3 rounded-[14px] bg-accent-soft p-4 text-accent-ink">
            <ShieldIcon size={20} className="mt-0.5 shrink-0" />
            <p className="text-sm">
              Owners and deadlines are never guessed. If they weren't said in the meeting, the record says{' '}
              <strong className="font-semibold">Unspecified</strong>.
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}
