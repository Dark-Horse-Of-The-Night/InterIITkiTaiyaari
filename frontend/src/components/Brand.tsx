// Brand pieces: the logo, the sound-bar mascot, the faded sound-wave background, person chips.

import { initial, personColour } from '../people'

const BAR_HEIGHTS = [0.5, 0.8, 1, 0.7, 0.42]

/** Five rounded bars. `motion`: gentle sway (idle), quick bounce (working), or none. */
export function SoundBars({ height = 92, motion = 'sway', excited = false }: {
  height?: number
  motion?: 'sway' | 'bounce' | 'none'
  excited?: boolean // e.g. a file is being dragged over: bars move faster
}) {
  const width = Math.round(height / 5)
  return (
    <div className="flex items-end justify-center" style={{ height, gap: Math.round(width / 2) }} aria-hidden>
      {BAR_HEIGHTS.map((h, i) => (
        <span
          key={i}
          className={motion === 'sway' ? 'bar-sway' : motion === 'bounce' ? 'bar-bounce' : ''}
          style={{
            width,
            height: height * h,
            borderRadius: width,
            background: 'var(--color-orange-bright)',
            animationDelay: `${-[0.2, 0.6, 1.1, 0.9, 0.4][i]}s`,
            animationDuration: excited ? '0.5s' : undefined,
          }}
        />
      ))}
    </div>
  )
}

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex h-[26px] items-end gap-[3px]" aria-hidden>
        {[12, 22, 16, 26, 10].map((h, i) => (
          <span key={i} className="w-[5px] rounded-[3px] bg-orange-bright" style={{ height: h }} />
        ))}
      </span>
      <span className="display text-xl">Meeting Assistant</span>
    </span>
  )
}

/** Flowing sound-wave lines behind every page, faded right back. */
export function WaveBackground() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 1440 900"
      preserveAspectRatio="none"
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full opacity-[0.09]"
    >
      <g fill="none" stroke="var(--color-orange-deep)" strokeWidth="2.5" strokeLinecap="round">
        <path d="M0 210 C 120 150, 240 270, 360 210 S 600 150, 720 210 S 960 270, 1080 210 S 1320 150, 1440 210" />
        <path d="M0 250 C 160 200, 320 300, 480 250 S 800 200, 960 250 S 1280 300, 1440 250" />
        <path d="M0 640 C 90 560, 180 720, 270 640 S 450 560, 540 640 S 720 720, 810 640 S 990 560, 1080 640 S 1260 720, 1440 640" />
        <path d="M0 690 C 140 640, 280 740, 420 690 S 700 640, 840 690 S 1120 740, 1260 690 S 1400 660, 1440 690" />
        <path d="M0 740 C 200 700, 400 780, 600 740 S 1000 700, 1200 740 S 1380 770, 1440 740" />
      </g>
    </svg>
  )
}

/** A small round avatar + name chip. */
export function PersonChip({ name, suffix }: { name: string; suffix?: string }) {
  const colour = personColour(name)
  return (
    <span className={`chip pl-1 ${colour.soft} ${colour.ink}`}>
      <span className={`flex size-5 items-center justify-center rounded-full text-[11px] text-white ${colour.solid}`} aria-hidden>
        {initial(name)}
      </span>
      {name}
      {suffix && <span className="font-medium opacity-80">{suffix}</span>}
    </span>
  )
}
