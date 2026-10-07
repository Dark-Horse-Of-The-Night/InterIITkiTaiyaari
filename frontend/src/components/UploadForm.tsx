import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'

import { ApiError, fetchSample, listSamples } from '../api'
import { checkFile, formatSize } from '../fileChecks'
import { formatTime } from '../format'
import type { Sample } from '../types'
import { SoundBars } from './Brand'
import { ArrowRightIcon, AudioFileIcon, CloseIcon } from './Icons'

interface Props {
  onSubmit: (file: File, glossary: string) => void
  uploading: boolean
}

const SAMPLE_TINTS = ['bg-orange-soft text-orange-ink', 'bg-mint-soft text-mint-ink', 'bg-sky-soft text-sky-ink']

export default function UploadForm({ onSubmit, uploading }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [glossary, setGlossary] = useState('')
  const [dragging, setDragging] = useState(false)
  const [samples, setSamples] = useState<Sample[]>([])
  const [loadingSample, setLoadingSample] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listSamples().then(setSamples).catch(() => setSamples([])) // samples are a bonus; hide them if unavailable
  }, [])

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

  async function trySample(sample: Sample) {
    setLoadingSample(sample.id)
    setProblem(null)
    try {
      onSubmit(await fetchSample(sample), glossary)
    } catch (error) {
      setProblem(error instanceof ApiError ? `${error.error.message} ${error.error.fix ?? ''}` : 'That sample could not be loaded.')
    } finally {
      setLoadingSample(null)
    }
  }

  return (
    <div className="mx-auto max-w-[720px] pt-4 text-center">
      <h1 className="display rise-in text-[44px] leading-[1.02] sm:text-[56px]">
        Drop a meeting.
        <br />
        <span className="text-orange-ink">Get the minutes.</span>
      </h1>
      <p className="rise-in mx-auto mt-4 max-w-[520px] text-lg text-muted [animation-delay:80ms]">
        Transcript, fixed jargon and a clean list of who does what.
      </p>

      <form onSubmit={handleSubmit} className="rise-in mt-9 flex flex-col gap-4 text-left [animation-delay:160ms]">
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`flex flex-col items-center gap-3.5 rounded-[28px] border-[2.5px] border-dashed px-6 pt-9 pb-8 text-center transition-all ${
            dragging ? 'scale-[1.01] border-orange bg-orange-track' : 'border-line-strong bg-orange-soft'
          }`}
        >
          <SoundBars height={88} excited={dragging} />
          <p className="display mt-1 text-2xl">{dragging ? 'Let it go!' : 'Drop your recording here'}</p>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="btn-outline focus-ring min-h-12 border-ink px-6 text-base font-bold"
          >
            Browse files
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".flac,.m4a,.mp3,.mp4,.mpeg,.mpga,.ogg,.wav,.webm"
            aria-label="Meeting recording"
            className="hidden"
            onChange={(event) => {
              choose(event.target.files?.[0])
              event.target.value = '' // allow choosing the same file again
            }}
          />
          <p className="text-[13.5px] text-muted">MP3, WAV, M4A and more · up to 2 hours</p>
        </div>

        {file && (
          <div className="pop-in flex items-center gap-3 rounded-2xl border-2 border-line bg-ground px-4 py-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-orange-soft text-orange-ink">
              <AudioFileIcon size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{file.name}</p>
              <p className="text-[13px] text-muted">{formatSize(file.size)} · ready</p>
            </div>
            <button
              type="button"
              aria-label="Remove file"
              onClick={() => setFile(null)}
              className="focus-ring flex size-11 cursor-pointer items-center justify-center rounded-full text-muted hover:bg-orange-soft"
            >
              <CloseIcon />
            </button>
          </div>
        )}
        {problem && (
          <p role="alert" className="pop-in rounded-2xl border-2 border-danger-line bg-danger-soft px-4 py-3 text-[15px] text-danger-ink">
            {problem}
          </p>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="glossary" className="text-[15px] font-semibold">
            Words we should know <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="glossary"
            type="text"
            value={glossary}
            onChange={(event) => setGlossary(event.target.value)}
            placeholder="e.g. Kubernetes, Project Atlas, Priya"
            className="min-h-[52px] rounded-2xl border-2 border-line bg-ground px-[18px] text-base text-ink placeholder:text-faint focus:border-orange focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={!file || uploading}
          className="display focus-ring flex min-h-[60px] cursor-pointer items-center justify-center gap-2.5 rounded-full bg-orange text-xl text-ink shadow-[0_7px_0_var(--color-orange-deep)] transition-all hover:-translate-y-0.5 hover:shadow-[0_9px_0_var(--color-orange-deep)] active:translate-y-1 active:shadow-[0_3px_0_var(--color-orange-deep)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
        >
          {uploading ? 'Uploading…' : 'Make my minutes'}
          {!uploading && <ArrowRightIcon size={22} strokeWidth={2.6} />}
        </button>
      </form>

      {samples.length > 0 && (
        <div className="rise-in mt-11 [animation-delay:240ms]">
          <p className="mb-3 text-[15px] text-muted">No recording handy? Try one of ours:</p>
          <div className="flex flex-wrap justify-center gap-2.5">
            {samples.map((sample, i) => (
              <button
                key={sample.id}
                type="button"
                disabled={uploading || loadingSample !== null}
                onClick={() => trySample(sample)}
                className="focus-ring flex min-h-12 cursor-pointer items-center gap-2.5 rounded-full border-2 border-line bg-ground py-0 pr-[18px] pl-2 font-semibold transition-transform hover:-translate-y-0.5 hover:border-orange disabled:cursor-wait disabled:opacity-60"
              >
                <span className={`flex size-8 items-center justify-center rounded-full ${SAMPLE_TINTS[i % SAMPLE_TINTS.length]}`}>
                  {loadingSample === sample.id ? (
                    <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                      <path d="M7 4.5v15l13-7.5z" />
                    </svg>
                  )}
                </span>
                {sample.title} <span className="font-medium text-muted">{formatTime(sample.seconds).replace(/^0/, '')}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
