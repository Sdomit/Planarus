import {
  ArrowLeft, Bell, Bold, Calendar, Check, ChevronDown, ChevronRight, CircleAlert,
  CircleCheck, Clock, Code, Columns, Edit2, ExternalLink, File, FileText, Folder,
  Grid, GripVertical, Heading1, Heading2, Heading3, Heading4, Highlighter, Image,
  Inbox, Info, Italic, Layers, Lightbulb, Link, List, ListOrdered, ListTodo, Lock,
  MessageCircle, Minus, Moon, MoreHorizontal, Palette, Pilcrow, Pin, Plus, Quote,
  Search, Settings, Strikethrough, Subscript, Sun, Superscript, Table, TriangleAlert,
  Trash2, Underline, Users, X, Zap,
  type LucideIcon,
} from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  'alert-triangle': TriangleAlert,
  'arrow-left': ArrowLeft,
  bell: Bell,
  bold: Bold,
  calendar: Calendar,
  check: Check,
  'chevron-down': ChevronDown,
  'chevron-right': ChevronRight,
  'circle-alert': CircleAlert,
  'circle-check': CircleCheck,
  clock: Clock,
  code: Code,
  columns: Columns,
  edit: Edit2,
  external: ExternalLink,
  file: File,
  'file-text': FileText,
  folder: Folder,
  grid: Grid,
  grip: GripVertical,
  'heading-1': Heading1,
  'heading-2': Heading2,
  'heading-3': Heading3,
  'heading-4': Heading4,
  highlight: Highlighter,
  image: Image,
  inbox: Inbox,
  info: Info,
  italic: Italic,
  layers: Layers,
  lightbulb: Lightbulb,
  link: Link,
  list: List,
  'list-ordered': ListOrdered,
  'list-todo': ListTodo,
  lock: Lock,
  message: MessageCircle,
  minus: Minus,
  moon: Moon,
  more: MoreHorizontal,
  palette: Palette,
  pilcrow: Pilcrow,
  pin: Pin,
  plus: Plus,
  quote: Quote,
  search: Search,
  settings: Settings,
  strikethrough: Strikethrough,
  subscript: Subscript,
  sun: Sun,
  superscript: Superscript,
  table: Table,
  trash: Trash2,
  underline: Underline,
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
