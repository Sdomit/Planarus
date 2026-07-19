import { useState } from 'react'

// Shared copy-to-clipboard button for the Integrations cards. Sticky "Copied ✓"
// (no timer — matches the one-time key-reveal modal) keeps the affordance clear.
export default function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      className="btn btn-outline btn-xs"
      onClick={() => void navigator.clipboard?.writeText(text).then(() => setCopied(true), () => {})}
    >
      {copied ? 'Copied ✓' : label}
    </button>
  )
}
