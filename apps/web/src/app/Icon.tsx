import {
  Bell, Calendar, Check, ChevronDown, Clock, Code, Columns, Edit2,
  ExternalLink, File, Folder, Grid, Inbox, Info, Layers, MessageCircle,
  Moon, MoreHorizontal, Palette, Plus, Search, Settings, Sun, Table,
  Trash2, Users, X, Zap,
  type LucideIcon,
} from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  bell: Bell,
  calendar: Calendar,
  check: Check,
  'chevron-down': ChevronDown,
  clock: Clock,
  code: Code,
  columns: Columns,
  edit: Edit2,
  external: ExternalLink,
  file: File,
  folder: Folder,
  grid: Grid,
  inbox: Inbox,
  info: Info,
  layers: Layers,
  message: MessageCircle,
  moon: Moon,
  more: MoreHorizontal,
  palette: Palette,
  plus: Plus,
  search: Search,
  settings: Settings,
  sun: Sun,
  table: Table,
  trash: Trash2,
  users: Users,
  x: X,
  zap: Zap,
}

// Thin wrapper over lucide-react (ISC-licensed, tracked via package.json).
// Usage: <Icon name="plus" /> or <Icon name="search" className="ic-14" />
// ponytail: `ic` is always applied so a typo'd size class (ic-16, ic-17…) falls
// back to 16px instead of the browser's unsized-svg default of 300x150. The
// real .ic-14/18/20/32 modifiers are declared after .ic, so they still win.
export function Icon({ name, className = '' }: { name: string; className?: string }) {
  const Cmp = ICONS[name]
  if (!Cmp) return null
  return <Cmp className={`ic ${className}`} aria-hidden="true" />
}
