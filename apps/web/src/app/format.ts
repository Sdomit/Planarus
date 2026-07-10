/** Locale-formatted timestamp; falls back to the raw string if unparseable. */
export function fmtTimestamp(ts: string): string {
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toLocaleString()
}
