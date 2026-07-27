// Types for the one extension module the web test suite imports. The extension
// itself is plain JS with no build step (#107); this exists so `tsc -b` in
// apps/web can typecheck the contract test that guards it against drift.

export declare const APP_URL: string
export declare const MAX_TEXT: number
export declare const CAPTURE_TYPES: ReadonlyArray<{ type: string; label: string }>
export declare const OPEN_APPROVALS_FRAGMENT: string

export declare function captureUrl(
  appUrl: string,
  clip: { type: string; text?: string; url?: string; title?: string },
): string | null

export declare function openApprovalsUrl(appUrl: string): string
