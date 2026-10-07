import { useEffect, useState } from 'react'

import { formatTime } from '../format'
import type { Player } from '../usePlayer'

/** Play/pause, a waveform you can click to jump, and a speed button. */
export default function AudioPlayer({ player, file, fallbackDuration }: { player: Player; file: File | null; fallbackDuration: number }) {
  const peaks = usePeaks(file)
  const { setAudio, src } = player
  const duration = player.duration || fallbackDuration
  const progress = duration ? player.time / duration : 0
  return (
    <section aria-label="Audio player" className="flex flex-wrap items-center gap-3.5 rounded-full bg-orange-soft py-3 pr-4 pl-3">
      <audio ref={setAudio} src={src} preload="metadata" />
      <button
        type="button"
        onClick={player.toggle}
        aria-label={player.playing ? 'Pause' : 'Play'}
        className="focus-ring flex size-12 shrink-0 cursor-pointer items-center justify-center rounded-full bg-orange text-ink transition-transform hover:scale-105 active:scale-95"
      >
        {player.playing ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <rect x="6" y="5" width="4" height="14" rx="1.5" />
            <rect x="14" y="5" width="4" height="14" rx="1.5" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M7 4.5v15l13-7.5z" />
          </svg>
        )}
      </button>
      <span className="w-10 font-mono text-[13px]">{formatTime(player.time).replace(/^0/, '')}</span>
      <div className="relative flex h-9 min-w-[180px] flex-1 items-center gap-[3px]">
        {peaks.map((peak, i) => (
          <span
            key={i}
            aria-hidden
            className={`flex-1 rounded-sm transition-colors ${i / peaks.length < progress ? 'bg-orange-deep' : 'bg-orange-track'}`}
            style={{ height: `${Math.max(14, peak * 100)}%` }}
          />
        ))}
        <input
          type="range"
          aria-label="Seek"
          min={0}
          max={duration || 1}
          step={0.1}
          value={Math.min(player.time, duration || 1)}
          onChange={(event) => player.seek(Number(event.target.value), player.playing)}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        />
      </div>
      <span className="w-10 font-mono text-[13px] text-muted">{formatTime(duration).replace(/^0/, '')}</span>
      <button
        type="button"
        onClick={player.cycleRate}
        aria-label={`Playback speed ${player.rate}×`}
        className="focus-ring min-h-8 cursor-pointer rounded-full border-2 border-line bg-ground px-2.5 text-[13px] font-bold"
      >
        {player.rate}×
      </button>
    </section>
  )
}

const BARS = 56

/** Loudness of the recording in BARS slices (decoded in the browser). Falls back to a gentle pattern. */
function usePeaks(file: File | null): number[] {
  const [peaks, setPeaks] = useState<number[]>(() => Array.from({ length: BARS }, (_, i) => 0.35 + 0.3 * Math.abs(Math.sin(i * 1.7))))
  useEffect(() => {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!file || !AudioCtx) return
    let cancelled = false
    const context = new AudioCtx()
    file
      .arrayBuffer()
      .then((buffer) => context.decodeAudioData(buffer))
      .then((audio) => {
        const data = audio.getChannelData(0)
        const size = Math.floor(data.length / BARS)
        // Average loudness (RMS) per slice, stretched between the quietest and loudest slice,
        // so pauses dip and busy stretches stand tall.
        const raw = Array.from({ length: BARS }, (_, i) => {
          let sum = 0
          let n = 0
          for (let j = i * size; j < (i + 1) * size; j += 32) {
            sum += data[j] * data[j]
            n += 1
          }
          return Math.sqrt(sum / (n || 1))
        })
        const low = Math.min(...raw)
        const high = Math.max(...raw)
        const span = high - low || 1
        if (!cancelled) setPeaks(raw.map((v) => 0.15 + 0.85 * ((v - low) / span)))
      })
      .catch(() => {}) // keep the fallback pattern
      .finally(() => void context.close())
    return () => {
      cancelled = true
    }
  }, [file])
  return peaks
}
