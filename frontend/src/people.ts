// Colours and initials for people (owners and speakers).

// Friendly chip colours for people, in order. Unnamed speakers ("Speaker 2") use stone.
const PEOPLE_COLOURS = [
  { soft: 'bg-sky-soft', ink: 'text-sky-ink', solid: 'bg-sky-ink' },
  { soft: 'bg-mint-soft', ink: 'text-mint-ink', solid: 'bg-mint-ink' },
  { soft: 'bg-orange-soft', ink: 'text-orange-ink', solid: 'bg-orange-ink' },
  { soft: 'bg-sun-soft', ink: 'text-sun-ink', solid: 'bg-sun-ink' },
]
const STONE = { soft: 'bg-stone-soft', ink: 'text-stone-ink', solid: 'bg-stone-ink' }

export function isSpeakerLabel(name: string): boolean {
  return /^Speaker \d+$/.test(name)
}

// Colours handed out in order, so people on the same page get different colours.
const assigned = new Map<string, number>()

/** Give these people colours in this order (call once per meeting, before rendering them). */
export function assignPeopleColours(names: string[]): void {
  assigned.clear()
  for (const name of names) {
    const key = name.toLowerCase()
    if (!isSpeakerLabel(name) && !assigned.has(key)) assigned.set(key, assigned.size)
  }
}

/** The same person always gets the same colour on the page. */
export function personColour(name: string) {
  if (isSpeakerLabel(name)) return STONE
  const key = name.toLowerCase()
  if (!assigned.has(key)) assigned.set(key, assigned.size)
  return PEOPLE_COLOURS[(assigned.get(key) ?? 0) % PEOPLE_COLOURS.length]
}

/** "Priya" -> "P"; "Speaker 3" -> "3". */
export function initial(name: string): string {
  return isSpeakerLabel(name) ? name.split(' ')[1] : name.trim()[0]?.toUpperCase() ?? '?'
}
