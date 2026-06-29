// Thin wrapper over the forma icon sprite (mounted once in index.html).
// Usage: <Icon name="plus" /> or <Icon name="search" className="ic-14" />
export function Icon({ name, className = 'ic' }: { name: string; className?: string }) {
  return (
    <svg className={className} aria-hidden="true">
      <use href={`#icon-${name}`} />
    </svg>
  )
}
