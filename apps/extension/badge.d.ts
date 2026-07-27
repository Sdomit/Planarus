// Types for the badge module the web test suite imports (#108). Same reason
// as capture-url.d.ts: the extension is plain JS with no build step, so this
// exists only so `tsc -b` in apps/web can typecheck the contract test.

export declare const EXTERNAL_BASE: string
export declare const POLL_MINUTES: number
export declare const MAX_BACKOFF_MINUTES: number

export declare function nextDelayMinutes(consecutiveFailures: number): number
export declare function badgeText(count: number): string

export type FetchLike = (url: string, init?: { headers?: Record<string, string> }) => Promise<{
  ok: boolean
  status: number
  json: () => Promise<unknown>
}>

export declare function fetchPendingTotal(
  apiUrl: string | undefined,
  apiKey: string | undefined,
  fetchImpl: FetchLike,
): Promise<{ ok: boolean; count: number }>
