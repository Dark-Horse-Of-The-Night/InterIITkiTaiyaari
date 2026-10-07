import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/** Shared audio state: the results page, to-dos and transcript all use the same player. */
export interface Player {
  available: boolean
  src: string | undefined
  setAudio: (element: HTMLAudioElement | null) => void // pass as the <audio> element's ref
  time: number
  duration: number
  playing: boolean
  rate: number
  toggle: () => void
  seek: (seconds: number, play?: boolean) => void
  cycleRate: () => void
}

const RATES = [1, 1.5, 2]

/** Plays the uploaded file straight from the browser (nothing is re-downloaded). */
export function usePlayer(file: File | null): Player {
  const [audio, setAudioState] = useState<HTMLAudioElement | null>(null) // for subscribing to its events
  const element = useRef<HTMLAudioElement | null>(null) // for play/pause/seek from event handlers
  const setAudio = useCallback((node: HTMLAudioElement | null) => {
    element.current = node
    setAudioState(node)
  }, [])
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const src = useMemo(
    () => (file && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : undefined),
    [file],
  )

  useEffect(() => () => {
    if (src) URL.revokeObjectURL(src)
  }, [src])

  useEffect(() => {
    if (!audio) return
    const onTime = () => setTime(audio.currentTime)
    const onMeta = () => setDuration(audio.duration || 0)
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
    }
  }, [audio])

  return {
    available: Boolean(src),
    src,
    setAudio,
    time,
    duration,
    playing,
    rate,
    toggle: () => {
      const node = element.current
      if (!node) return
      if (node.paused) safePlay(node)
      else node.pause()
    },
    seek: (seconds, play = true) => {
      setTime(seconds)
      const node = element.current
      if (!node) return
      node.currentTime = seconds
      if (play) safePlay(node)
    },
    cycleRate: () => {
      const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length]
      if (element.current) element.current.playbackRate = next
      setRate(next)
    },
  }
}

/** play() returns a promise in browsers (rejected if autoplay is blocked); some environments return nothing. */
function safePlay(node: HTMLAudioElement): void {
  try {
    const result = node.play() as Promise<void> | undefined
    result?.catch(() => {})
  } catch {
    // playback not supported here
  }
}
