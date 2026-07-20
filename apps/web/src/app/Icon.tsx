// Thin wrapper over the forma icon sprite (mounted once in index.html).
// Usage: <Icon name="plus" /> or <Icon name="search" className="ic-14" />
// ponytail: `ic` is always applied so a typo'd size class (ic-16, ic-17…) falls
// back to 16px instead of the browser's unsized-svg default of 300x150. The
// real .ic-14/18/20/32 modifiers are declared after .ic, so they still win.
export function Icon({ name, className = '' }: { name: string; className?: string }) {
  return (
    <svg className={`ic ${className}`} aria-hidden="true">
      <use href={`#icon-${name}`} />
    </svg>
  )
}
