// Small inline stroke icons. Decorative: hidden from screen readers (buttons carry their own labels).

import type { ReactNode, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 18, children, strokeWidth = 2, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}

export const WaveIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 10v4" /><path d="M8 6v12" /><path d="M12 9v6" /><path d="M16 4v16" /><path d="M20 10v4" /></Icon>
)
export const UploadIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 15V4" /><path d="M7.5 8.5 12 4l4.5 4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></Icon>
)
export const AudioFileIcon = (p: IconProps) => (
  <Icon {...p}><path d="M9 18V6l10-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" /></Icon>
)
export const CloseIcon = (p: IconProps) => (
  <Icon {...p}><path d="M6 6l12 12" /><path d="M18 6 6 18" /></Icon>
)
export const ArrowRightIcon = (p: IconProps) => (
  <Icon {...p}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></Icon>
)
export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}><path d="m9 6 6 6-6 6" /></Icon>
)
export const CheckIcon = (p: IconProps) => (
  <Icon {...p}><path d="M5 12.5 9.5 17 19 7.5" /></Icon>
)
export const ClockIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>
)
export const InfoIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></Icon>
)
export const ShieldIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="m9 12 2 2 4-4" /></Icon>
)
export const DownloadIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 4v11" /><path d="M7.5 10.5 12 15l4.5-4.5" /><path d="M5 20h14" /></Icon>
)
export const PlusIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 5v14" /><path d="M5 12h14" /></Icon>
)
export const AlertIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5" /><path d="M12 16h.01" /></Icon>
)
