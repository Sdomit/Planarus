import {
  createContext, forwardRef, lazy, Suspense, useCallback, useContext, useEffect, useImperativeHandle,
  useMemo, useRef, useState, type ReactNode,
} from 'react'
import {
  useEditor, useEditorState, EditorContent, ReactNodeViewRenderer, ReactRenderer,
  NodeViewWrapper, NodeViewContent,
} from '@tiptap/react'
import type { ChainedCommands, Editor, NodeViewProps } from '@tiptap/core'
import { Extension, Node, mergeAttributes } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { Placeholder } from '@tiptap/extensions'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import { TaskList, TaskItem } from '@tiptap/extension-list'
import Image from '@tiptap/extension-image'
import { TextStyle } from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import Mention from '@tiptap/extension-mention'
import { Details, DetailsSummary, DetailsContent } from '@tiptap/extension-details'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import DragHandle from '@tiptap/extension-drag-handle-react'
import { Suggestion, type SuggestionOptions } from '@tiptap/suggestion'
import { MarkdownSerializer } from 'prosemirror-markdown'
import { api, type Doc, type DocSummary, type EntityConnection } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { Icon } from './Icon'
import { Menu, MenuItem } from './Menu'
import { usePresence } from './usePresence'
import { agoLabel } from './date'
import { isAllowedImageSrc, isAllowedLink, markdownTitle, markdownUrl } from './uri-policy'
import { ConnectionProvider, EntityConnections, type ConnectionTarget } from './EntityConnections'
import { buildConnectionTargets, docToTarget } from './connectionTargets'
import { ReferencedBy } from './ReferencedBy'
import { buildDocTree, docAncestors, type DocNode } from './docTree'
import {
  KIND_ICON, filterEntities,
  taskToRef, decisionToRef, riskToRef, blockerToRef, milestoneToRef, phaseToRef, stageToRef, docToRef,
  type EntityKind, type EntityRef,
} from './canvasCards'
import './docs-panel.css'

// Excalidraw is heavy (~1MB) and pulls in browser-only modules that crash under
// jsdom at import time — lazy-load it so it's fetched only when a canvas opens.
const CanvasEditor = lazy(() =>
  import('./CanvasEditor').then((m) => ({ default: m.CanvasEditor })),
)

// ---------------------------------------------------------------------------
// ProseMirror → Markdown serializer (Tiptap camelCase node/mark names)
// ---------------------------------------------------------------------------

/** Every character CommonMark treats as a line ending. `\r` alone counts, which
 *  a `/\r?\n/` normalisation misses. U+2028/U+2029 are included because they end
 *  a line for some downstream readers even though CommonMark itself ignores them. */
const LINE_ENDINGS = new RegExp('[\r\n\u2028\u2029]+', 'g')

/** Escape a string for use as inline markdown on a single line.
 *
 *  `state.esc()` handles the emphasis/link punctuation but leaves line endings
 *  alone, and the serializer's `write()` emits them raw without re-applying the
 *  current block delimiter. Collapsing them first is what keeps a crafted
 *  attribute inside the construct it belongs to. */
function mdInline(state: { esc: (s: string) => string }, raw: string): string {
  return state.esc(String(raw ?? '').replace(LINE_ENDINGS, ' '))
}

/** Build a `planarus://<type>/<id>` destination from untrusted node attrs.
 *
 *  `markdownUrl()` angle-wraps and percent-encodes, but a pointy-bracket
 *  destination cannot contain a line ending per CommonMark — so a newline in
 *  `targetId` broke the link outright and everything after it became live
 *  markdown. Ids here are opaque prefixed slugs (`tsk_…`, `doc_…`), so anything
 *  outside that shape is dropped rather than escaped. */
const REF_TOKEN = /^[A-Za-z0-9_.:-]+$/
function planarusHref(rawType: unknown, rawId: unknown): string {
  const type = typeof rawType === 'string' && REF_TOKEN.test(rawType) ? rawType : 'unknown'
  const id = typeof rawId === 'string' && REF_TOKEN.test(rawId) ? rawId : ''
  return markdownUrl(`planarus://${type}/${id}`)
}

const _docSerializer = new MarkdownSerializer(
  {
    doc(state, node) { state.renderContent(node) },
    paragraph(state, node) { state.renderInline(node); state.closeBlock(node) },
    text(state, node) { state.text(node.text ?? '') },
    heading(state, node) {
      state.write(state.repeat('#', node.attrs.level as number) + ' ')
      state.renderInline(node); state.closeBlock(node)
    },
    blockquote(state, node) { state.wrapBlock('> ', null, node, () => state.renderContent(node)) },
    bulletList(state, node) { state.renderList(node, '  ', () => '* ') },
    orderedList(state, node) {
      const start = (node.attrs.start as number) || 1
      state.renderList(node, '  ', (i: number) => `${start + i}. `)
    },
    listItem(state, node) { state.renderContent(node) },
    // GFM task list: "- [ ] item" / "- [x] item". The checkbox state lives on
    // the item, so taskList supplies the "- " bullet and taskItem the "[x] ".
    taskList(state, node) { state.renderList(node, '  ', () => '- ') },
    taskItem(state, node) {
      state.write(`[${node.attrs.checked ? 'x' : ' '}] `)
      state.renderContent(node)
    },
    codeBlock(state, node) {
      state.write('```' + ((node.attrs.language as string) || '') + '\n')
      state.text(node.textContent, false); state.ensureNewLine()
      state.write('```'); state.closeBlock(node)
    },
    hardBreak(state, node, parent, index) {
      for (let i = index + 1; i < parent.childCount; i++) {
        if (parent.child(i).type !== node.type) { state.write('\\\n'); return }
      }
    },
    horizontalRule(state, node) {
      state.write((node.attrs.markup as string) || '---'); state.closeBlock(node)
    },
    // Block image → ![alt](src "title"). #118: alt is escaped so a "]" can't
    // break the syntax, and src/title go through the shared encoders — a src
    // holding a space or an unbalanced ")" would otherwise close the link early
    // and spill the rest of the URL into the exported document as prose.
    image(state, node) {
      const alt = state.esc((node.attrs.alt as string) || '')
      const title = node.attrs.title ? ` "${markdownTitle(node.attrs.title as string)}"` : ''
      state.write(`![${alt}](${markdownUrl(node.attrs.src as string)}${title})`)
      state.closeBlock(node)
    },
    // #138 plan 23/24: mention and childPage both serialize to the same
    // `planarus://<type>/<id>` scheme, so markdown_cache/search/AI reads see
    // references and nesting uniformly.
    //
    // Every attribute below is treated as hostile. These nodes' attrs are set by
    // `parseHTML` from `data-*` on pasted HTML, and by any `content_json` write
    // — including the MCP `doc.update` propose path — so none of them has been
    // through `isAllowedLink`, unlike the link mark #118 hardened. `state.esc()`
    // alone is not enough: it escapes ``` ` * \ ~ [ ] _ ``` and, at
    // startOfLine=false, nothing else — a newline passes straight through
    // `write()` and frees everything after it to be read as fresh markdown.
    mention(state, node) {
      const label = mdInline(state, (node.attrs.label as string) || (node.attrs.targetId as string) || '')
      state.write(`[${label}](${planarusHref(node.attrs.targetType, node.attrs.targetId)})`)
    },
    childPage(state, node) {
      const title = mdInline(state, (node.attrs.title as string) || 'Untitled')
      state.write(`[${title}](${planarusHref('doc', node.attrs.docId)})`)
      state.closeBlock(node)
    },
    callout(state, node) {
      // Allowlisted rather than escaped: the icon is a closed set we define, so
      // anything else is forged. Unescaped, a newline here escaped the
      // blockquote entirely — `write()` does not re-apply the "> " delimiter
      // mid-string — letting pasted HTML forge headings and links into
      // markdown_cache, which feeds disk exports, the context pack and MCP reads.
      const raw = node.attrs.icon as string
      const icon = CALLOUT_ICONS.includes(raw) ? raw : CALLOUT_ICONS[0]
      state.wrapBlock('> ', null, node, () => {
        state.write(`${icon} `)
        state.renderContent(node)
      })
    },
    details(state, node) { state.renderContent(node); state.closeBlock(node) },
    detailsSummary(state, node) {
      // An empty summary would otherwise serialize to a bare "****".
      if (node.textContent.trim() === '') { state.closeBlock(node); return }
      state.write('**'); state.renderInline(node); state.write('**'); state.closeBlock(node)
    },
    detailsContent(state, node) { state.renderContent(node) },
    // GFM table. Cells hold block content (typically one paragraph) in Tiptap;
    // flattened to plain text via textContent, since a table cell can hold
    // neither block structure nor a literal "|" or line ending in GFM.
    // tableHeader and tableCell are read directly here rather than dispatched
    // through the serializer map (no entries for them below).
    table(state, node) { state.renderContent(node); state.closeBlock(node) },
    tableRow(state, node, _parent, index) {
      state.write('|')
      node.forEach(cell => {
        // esc() as well as the pipe/line-ending normalisation: without it, cell
        // text typed as the literal characters "[x](https://evil.test)" became a
        // real link in the export that the document never contained — and no
        // isAllowedLink gate exists anywhere on this path.
        state.write(` ${mdInline(state, cell.textContent).replace(/\|/g, '\\|')} |`)
      })
      state.ensureNewLine()
      if (index === 0) {
        state.write('|' + ' --- |'.repeat(node.childCount))
        state.ensureNewLine()
      }
    },
  },
  {
    bold:      { open: '**', close: '**', mixable: true, expelEnclosingWhitespace: true },
    italic:    { open: '*',  close: '*',  mixable: true, expelEnclosingWhitespace: true },
    strike:    { open: '~~', close: '~~', mixable: true, expelEnclosingWhitespace: true },
    code:      { open: '`',  close: '`',  escape: false, expelEnclosingWhitespace: true },
    // No native Markdown syntax → inline HTML (renders in GFM). Highlight uses
    // the "==" convention supported by Pandoc/many renderers.
    highlight:   { open: '==',    close: '==',     mixable: true, expelEnclosingWhitespace: true },
    underline:   { open: '<u>',   close: '</u>',   mixable: true, expelEnclosingWhitespace: true },
    subscript:   { open: '<sub>', close: '</sub>', mixable: true, expelEnclosingWhitespace: true },
    superscript: { open: '<sup>', close: '</sup>', mixable: true, expelEnclosingWhitespace: true },
    // Font color rides on the textStyle mark → inline <span> (renders in GFM,
    // round-trips back via TextStyle's parseHTML). Empty when it carries no color.
    textStyle: {
      open: (_state, mark) => (mark.attrs.color ? `<span style="color:${mark.attrs.color as string}">` : ''),
      close: (_state, mark) => (mark.attrs.color ? '</span>' : ''),
    },
    link: {
      open: (_state, _mark, _parent, _index) => '[',
      close: (_state, mark) =>
        `](${markdownUrl(mark.attrs.href as string)}` +
        `${mark.attrs.title ? ` "${markdownTitle(mark.attrs.title as string)}"` : ''})`,
    },
  },
  // Belt-and-suspenders: an unhandled node type (one this file's own map
  // missed, or one a future Tiptap extension bump adds) falls back to
  // rendering its content instead of throwing "Token type X not supported"
  // out of the autosave loop — which would otherwise brick every future save
  // of that document, not just skip that one node's markdown.
  { strict: false },
)

export function serializeToMarkdown(doc: any): string {
  return _docSerializer.serialize(doc)
}

/** #118: the image node has no `isAllowedUri` equivalent, so the policy is
 *  applied where the attribute becomes an actual `src`. A document stored before
 *  the policy existed still loads and still shows its alt text — it just does not
 *  get to make the browser fetch whatever it points at. */
const SafeImage = Image.extend({
  addAttributes() {
    const parent = this.parent?.() ?? {}
    return {
      ...parent,
      src: {
        ...(parent as Record<string, object>).src,
        renderHTML: (attrs: Record<string, unknown>) => {
          const src = typeof attrs.src === 'string' ? attrs.src : ''
          return isAllowedImageSrc(src) ? { src } : {}
        },
      },
    }
  },
})

// ---------------------------------------------------------------------------
// #138 — Notion-style editor: @mentions, the "/" menu, and inline sub-pages
// ---------------------------------------------------------------------------

/** One shared floating list for both the "@" mention picker and the "/" block
 * menu — same keyboard nav, same positioning (via @tiptap/suggestion's
 * `props.mount`, which owns Floating UI so neither caller has to). */
// `icon` is a node, not a string, so the "/" menu can pass a lucide <Icon /> while
// the "@" menu keeps the KIND_ICON glyph it shares with the canvas cards.
interface SuggestionItem { key: string; label: string; icon?: ReactNode; sub?: string }
interface SuggestionListRef { onKeyDown: (props: { event: KeyboardEvent }) => boolean }
interface SuggestionListProps<T extends SuggestionItem> { items: T[]; command: (item: T) => void }

function createSuggestionList<T extends SuggestionItem>() {
  return forwardRef<SuggestionListRef, SuggestionListProps<T>>(function SuggestionList({ items, command }, ref) {
    const [selected, setSelected] = useState(0)
    useEffect(() => { setSelected(0) }, [items])

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }) => {
        const n = items.length
        if (n === 0) return false
        if (event.key === 'ArrowDown') { setSelected(i => (i + 1) % n); return true }
        if (event.key === 'ArrowUp') { setSelected(i => (i - 1 + n) % n); return true }
        if (event.key === 'Enter') { command(items[selected]); return true }
        return false
      },
    }), [items, selected, command])

    if (items.length === 0) return <div className="dp-suggest-menu dp-suggest-empty">No results</div>
    return (
      <div className="dp-suggest-menu" role="listbox">
        {items.map((item, i) => (
          <button type="button" key={item.key} role="option" aria-selected={i === selected}
            className={`dp-suggest-item${i === selected ? ' active' : ''}`}
            onMouseEnter={() => setSelected(i)}
            // A mousedown on the popup blurs the editor before `onClick` fires,
            // collapsing the pending suggestion range — run the command now.
            onMouseDown={e => { e.preventDefault(); command(item) }}>
            {item.icon && <span className="dp-suggest-icon">{item.icon}</span>}
            <span className="dp-suggest-label">{item.label}</span>
            {item.sub && <span className="dp-suggest-sub">{item.sub}</span>}
          </button>
        ))}
      </div>
    )
  })
}

const MentionSuggestionList = createSuggestionList<SuggestionItem & { targetType: EntityKind; targetId: string }>()
const SlashSuggestionList = createSuggestionList<SuggestionItem & { run: (editor: Editor, range: { from: number; to: number }) => void }>()

function suggestionRenderer<T extends SuggestionItem>(Component: ReturnType<typeof createSuggestionList<T>>) {
  return () => {
    let component: ReactRenderer<SuggestionListRef, SuggestionListProps<T>> | null = null
    let unmount: (() => void) | null = null
    return {
      onStart(props: { editor: Editor; items: T[]; command: (item: T) => void; mount: (el: HTMLElement) => () => void }) {
        component = new ReactRenderer(Component, { props: { items: props.items, command: props.command }, editor: props.editor })
        unmount = props.mount(component.element)
      },
      onUpdate(props: { items: T[]; command: (item: T) => void }) {
        component?.updateProps({ items: props.items, command: props.command })
      },
      onKeyDown(props: { event: KeyboardEvent }) {
        return component?.ref?.onKeyDown(props) ?? false
      },
      onExit() {
        unmount?.()
        component?.destroy()
        component = null
        unmount = null
      },
    }
  }
}

// --- @mention (plan 23) -------------------------------------------------------

/** The kinds a mention may target.
 *
 * Deliberately the same six as `CONNECTION_ENTITY_TYPES` (plan 25), not plan
 * 23's wider list: every kind here has a "Referenced by" panel on its detail
 * view, so a mention is readable from both ends. `blocker` and `stage` were
 * offered by the picker but have no detail surface to show backlinks on, which
 * made mentioning them write-only. Add them back alongside their panel. */
const MENTION_KINDS: EntityKind[] = ['task', 'decision', 'risk', 'milestone', 'phase', 'doc']

async function loadMentionableEntities(projectId: string): Promise<EntityRef[]> {
  // allSettled, not all: one unavailable list shouldn't blank the whole picker.
  const res = await Promise.allSettled([
    api.tasks.list(projectId), api.decisions.list(projectId), api.risks.list(projectId),
    api.blockers.list(projectId), api.milestones.list(projectId), api.phases.list(projectId),
    api.stages.list(projectId), api.docs.list(projectId),
  ])
  const adapters = [taskToRef, decisionToRef, riskToRef, blockerToRef, milestoneToRef, phaseToRef, stageToRef, docToRef]
  return res.flatMap((r, i) =>
    r.status === 'fulfilled' ? (r.value as unknown[]).map(adapters[i] as (x: unknown) => EntityRef) : [],
  )
}

/** Mention node attrs, replacing the stock `id` with a typed `(targetType,
 * targetId)` pair — `mention_service._extract_targets` parses exactly this
 * shape out of `content_json` server-side. */
interface PlanarusMentionAttrs extends Record<string, any> {
  targetType: EntityKind | null
  targetId: string | null
  label: string | null
  mentionSuggestionChar: string
}

export const PlanarusMention = Mention.extend<import('@tiptap/extension-mention').MentionOptions<any, PlanarusMentionAttrs>>({
  addAttributes() {
    return {
      targetType: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-target-type'),
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.targetType ? { 'data-target-type': attrs.targetType as string } : {},
      },
      targetId: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-target-id'),
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.targetId ? { 'data-target-id': attrs.targetId as string } : {},
      },
      label: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-label'),
        renderHTML: (attrs: Record<string, unknown>) => (attrs.label ? { 'data-label': attrs.label as string } : {}),
      },
      // Kept from the stock node: addKeyboardShortcuts' Backspace handler reads it.
      mentionSuggestionChar: {
        default: '@',
        parseHTML: (el: HTMLElement) => el.getAttribute('data-mention-suggestion-char'),
        renderHTML: (attrs: Record<string, unknown>) => ({ 'data-mention-suggestion-char': attrs.mentionSuggestionChar as string }),
      },
    }
  },
  renderText({ node }) {
    return `@${(node.attrs.label as string) ?? (node.attrs.targetId as string)}`
  },
  renderHTML({ node, HTMLAttributes }) {
    const icon = KIND_ICON[(node.attrs.targetType as EntityKind) ?? 'doc'] ?? ''
    return [
      'span',
      mergeAttributes({ 'data-type': 'mention', class: 'dp-mention' }, HTMLAttributes),
      `${icon} ${(node.attrs.label as string) ?? (node.attrs.targetId as string)}`,
    ]
  },
})

// --- childPage (plan 24) -------------------------------------------------------

interface DocEditorCtx {
  /** Every doc in the project, keyed by id — live titles + tombstone detection. */
  docIndex: Map<string, DocSummary>
  /** False until the index has actually loaded. "Not loaded" and "confirmed
   *  deleted" look identical in an empty Map, and rendering the second while the
   *  first is true told the user their sub-pages were gone on every doc open. */
  docIndexReady: boolean
  onOpenDoc: (docId: string) => void
  /** Soft-detach: parent_doc_id → null. Never deletes the child (plan 24's rule). */
  onDetachChild: (docId: string) => void
  /** False in the read-only view: node views still open their target, but the
   *  controls that would change the document are not offered. */
  editing: boolean
}
const DocEditorContext = createContext<DocEditorCtx>({
  docIndex: new Map(), docIndexReady: false, onOpenDoc: () => {}, onDetachChild: () => {}, editing: false,
})

function ChildPageView({ node, deleteNode }: NodeViewProps) {
  const { docIndex, docIndexReady, onOpenDoc, onDetachChild, editing } = useContext(DocEditorContext)
  const docId = node.attrs.docId as string
  const live = docIndex.get(docId)
  // The server can't cheaply rewrite this doc's JSON when the child is deleted
  // elsewhere, so reconciliation happens here, at render (plan 24). Only claim
  // a page is gone once the index has loaded and still doesn't list it.
  const tombstoned = docIndexReady && !live
  const fallbackTitle = (node.attrs.title as string) || 'Untitled'

  return (
    <NodeViewWrapper className={`dp-childpage${tombstoned ? ' dp-childpage-gone' : ''}`} contentEditable={false}>
      {tombstoned ? (
        <span className="dp-childpage-open dp-childpage-tombstone">
          <Icon name="file-text" className="dp-childpage-icon ic-14" />
          <span className="dp-childpage-title">This page was deleted</span>
        </span>
      ) : (
        // Before the index lands, the node's own denormalized title carries the
        // row — the link stays live rather than flickering through a tombstone.
        <button type="button" className="dp-childpage-open" onClick={() => onOpenDoc(docId)}>
          <Icon name="file-text" className="dp-childpage-icon ic-14" />
          <span className="dp-childpage-title">{live?.title || fallbackTitle}</span>
        </button>
      )}
      {editing && (
        <button type="button" className="dp-childpage-detach" title="Remove from this page (keeps the page itself)"
          aria-label="Remove sub-page link"
          // Detach whenever the child might still exist. Skipping it on an
          // unloaded index would orphan a live child: node gone from the body,
          // parent_doc_id still pointing here.
          onClick={() => { if (!tombstoned) onDetachChild(docId); deleteNode() }}>
          <Icon name="x" className="ic-14" />
        </button>
      )}
    </NodeViewWrapper>
  )
}

export const ChildPage = Node.create({
  name: 'childPage',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      docId: { default: null },
      title: { default: '' },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-type="child-page"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes({ 'data-type': 'child-page' }, HTMLAttributes)]
  },
  addNodeView() {
    return ReactNodeViewRenderer(ChildPageView)
  },
})

// --- callout (plan 24) ---------------------------------------------------------

// The emoji stays the stored + serialized value: it is what `data-icon` holds in
// every doc already written, what the allowlist below is built around, and the
// only thing a markdown export can carry. The UI renders the lucide equivalent,
// so the editor shows a drawn icon without a migration over existing docs.
const CALLOUT_ICONS = ['💡', '⚠️', '📌', '✅', '❗']
const CALLOUT_ICON_NAME: Record<string, string> = {
  '💡': 'lightbulb', '⚠️': 'alert-triangle', '📌': 'pin', '✅': 'circle-check', '❗': 'circle-alert',
}

function CalloutView({ node, updateAttributes }: NodeViewProps) {
  const { editing } = useContext(DocEditorContext)
  const icon = (node.attrs.icon as string) || CALLOUT_ICONS[0]
  const cycleIcon = () => {
    const i = CALLOUT_ICONS.indexOf(icon)
    updateAttributes({ icon: CALLOUT_ICONS[(i + 1) % CALLOUT_ICONS.length] })
  }
  return (
    <NodeViewWrapper className="dp-callout">
      <button type="button" className="dp-callout-icon" contentEditable={false} title="Change icon"
        disabled={!editing} onClick={cycleIcon}>
        <Icon name={CALLOUT_ICON_NAME[icon] ?? CALLOUT_ICON_NAME[CALLOUT_ICONS[0]]} className="ic-18" />
      </button>
      <NodeViewContent className="dp-callout-body" />
    </NodeViewWrapper>
  )
}

export const Callout = Node.create({
  name: 'callout',
  group: 'block',
  content: 'block+',
  defining: true,
  addAttributes() {
    return {
      icon: {
        default: CALLOUT_ICONS[0],
        // Allowlisted at the boundary as well as at serialize time: `data-icon`
        // comes off pasted HTML, so this keeps a forged value out of the node
        // rather than only out of the markdown projection.
        parseHTML: (el: HTMLElement) => {
          const raw = el.getAttribute('data-icon')
          return raw && CALLOUT_ICONS.includes(raw) ? raw : CALLOUT_ICONS[0]
        },
        renderHTML: (attrs: Record<string, unknown>) => ({ 'data-icon': attrs.icon as string }),
      },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-type="callout"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes({ 'data-type': 'callout' }, HTMLAttributes), 0]
  },
  addNodeView() {
    return ReactNodeViewRenderer(CalloutView)
  },
})

// --- "/" slash menu (plan 24) ---------------------------------------------------

interface SlashItem extends SuggestionItem {
  run: (editor: Editor, range: { from: number; to: number }) => void
}

/** Block types that already exist (text/H1-4/quote/divider/lists/task list) plus
 * the three Phase-A additions (toggle/callout/table). "Page" and "Convert to
 * page" need a doc-create API call, so DocEditor appends those two itself. */
const SLASH_ITEMS: SlashItem[] = [
  { key: 'text', label: 'Text', icon: <Icon name="pilcrow" />, run: (e, r) => { e.chain().focus().deleteRange(r).setParagraph().run() } },
  { key: 'h1', label: 'Heading 1', icon: <Icon name="heading-1" />, run: (e, r) => { e.chain().focus().deleteRange(r).setNode('heading', { level: 1 }).run() } },
  { key: 'h2', label: 'Heading 2', icon: <Icon name="heading-2" />, run: (e, r) => { e.chain().focus().deleteRange(r).setNode('heading', { level: 2 }).run() } },
  { key: 'h3', label: 'Heading 3', icon: <Icon name="heading-3" />, run: (e, r) => { e.chain().focus().deleteRange(r).setNode('heading', { level: 3 }).run() } },
  { key: 'h4', label: 'Heading 4', icon: <Icon name="heading-4" />, run: (e, r) => { e.chain().focus().deleteRange(r).setNode('heading', { level: 4 }).run() } },
  { key: 'quote', label: 'Quote', icon: <Icon name="quote" />, run: (e, r) => { e.chain().focus().deleteRange(r).setBlockquote().run() } },
  { key: 'divider', label: 'Divider', icon: <Icon name="minus" />, run: (e, r) => { e.chain().focus().deleteRange(r).setHorizontalRule().run() } },
  { key: 'bullet', label: 'Bullet list', icon: <Icon name="list" />, run: (e, r) => { e.chain().focus().deleteRange(r).toggleBulletList().run() } },
  { key: 'ordered', label: 'Numbered list', icon: <Icon name="list-ordered" />, run: (e, r) => { e.chain().focus().deleteRange(r).toggleOrderedList().run() } },
  { key: 'checklist', label: 'Task list', icon: <Icon name="list-todo" />, run: (e, r) => { e.chain().focus().deleteRange(r).toggleTaskList().run() } },
  { key: 'toggle', label: 'Toggle', icon: <Icon name="chevron-right" />, run: (e, r) => { e.chain().focus().deleteRange(r).setDetails().run() } },
  {
    key: 'callout', label: 'Callout', icon: <Icon name="lightbulb" />,
    run: (e, r) => { e.chain().focus().deleteRange(r).insertContent({ type: 'callout', content: [{ type: 'paragraph' }] }).run() },
  },
  { key: 'table', label: 'Table', icon: <Icon name="table" />, run: (e, r) => { e.chain().focus().deleteRange(r).insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run() } },
]

const SlashCommand = Extension.create({
  name: 'slashCommand',
  addOptions() {
    return { suggestion: { char: '/', startOfLine: false } as Partial<SuggestionOptions<SlashItem, SlashItem>> }
  },
  addProseMirrorPlugins() {
    return [
      Suggestion<SlashItem, SlashItem>({
        editor: this.editor,
        command: ({ editor, range, props }) => props.run(editor, range),
        ...this.options.suggestion,
      }),
    ]
  },
})

const DOC_TYPES = ['note', 'spec', 'research', 'plan', 'reference', 'canvas', 'other'] as const

// A doc_type-locked panel (Notes) reuses this whole surface; only the wording changes.
// ponytail: two forms is all the copy needs — no i18n/pluralization lib for "doc"/"note".
function nouns(docType?: string) {
  const noun = docType ?? 'doc'
  return { noun, Noun: noun[0].toUpperCase() + noun.slice(1) }
}

// ---------------------------------------------------------------------------
// Doc list view
// ---------------------------------------------------------------------------

/** Swatch keys, mirroring DOC_COLORS in apps/api/app/core/constants.py. */
const NOTE_COLORS = ['yellow', 'orange', 'red', 'green', 'teal', 'blue', 'purple', 'gray'] as const

/** Keep-style swatch row. 'default' is the sentinel that clears the colour server-side. */
function NoteColors(
  { doc, onChanged, onStale }: { doc: DocSummary; onChanged: (d: Doc) => void; onStale: () => void },
) {
  const pick = (key: string) => {
    if ((doc.color ?? 'default') === key) return
    api.docs.update(doc.id, { color: key, version: doc.version })
      .then(onChanged)
      // Almost always a 409 from a concurrent edit — refetch so the row stops lying.
      .catch(onStale)
  }
  return (
    <div className="ab-notecard-colors">
      <button type="button" className="ab-swatch" title="No colour"
        aria-label="No colour" aria-pressed={!doc.color} onClick={() => pick('default')} />
      {NOTE_COLORS.map(c => (
        <button key={c} type="button" className="ab-swatch" data-color={c}
          title={c} aria-label={c} aria-pressed={doc.color === c} onClick={() => pick(c)} />
      ))}
    </div>
  )
}

/**
 * Keep's "Take a note…" bar: type a title, press Enter, land in the editor.
 * ponytail: a plain input, not an expanding inline rich-text composer — the
 * editor is one keystroke away and already does everything.
 */
function NoteComposer(
  { projectId, docType, onCreated }: { projectId: string; docType: string; onCreated: (d: Doc) => void },
) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = () => {
    const t = title.trim()
    if (!t || busy) return
    setBusy(true); setError(null)
    api.docs.create(projectId, { title: t, doc_type: docType })
      .then(d => { setTitle(''); onCreated(d) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="ab-note-composer">
      <input className="input" type="text" value={title} disabled={busy}
        placeholder={`Take a ${nouns(docType).noun}…`} aria-label={`New ${nouns(docType).noun} title`}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); create() } }} />
      <button type="button" className="btn btn-solid btn-sm" disabled={!title.trim() || busy}
        onClick={create}>{busy ? 'Adding…' : 'Add'}</button>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

interface DocListProps {
  projectId: string
  onSelect: (doc: DocSummary) => void
  onNew: () => void
  onClose?: () => void
  docType?: string
  /** Drops a deleted doc from the loaded connection target list, if any. */
  onRemoved?: (docId: string) => void
}

/** One tree row + its children, indented and collapsible. Native HTML5 DnD
 * drives drag-to-reparent — the server (validate_parent) is what actually
 * enforces same-project/no-cycle; a rejected drop just re-syncs from `reload`. */
function DocTreeRow({
  node, depth, onSelect, collapsed, toggleCollapsed, onReparent, dragOverId, setDragOverId,
}: {
  node: DocNode
  depth: number
  onSelect: (doc: DocSummary) => void
  collapsed: Set<string>
  toggleCollapsed: (id: string) => void
  onReparent: (childId: string, newParentId: string) => void
  dragOverId: string | null
  setDragOverId: (id: string | null) => void
}) {
  const isCollapsed = collapsed.has(node.id)
  const hasChildren = node.children.length > 0
  return (
    <div className="dp-tree-node">
      <div className={`ab-docitem dp-tree-row${dragOverId === node.id ? ' dp-tree-drop-target' : ''}`}
        role="button" tabIndex={0} data-color={node.color ?? undefined}
        style={{ paddingLeft: `calc(var(--space-4) + ${depth} * var(--space-5))` }}
        draggable
        onDragStart={e => e.dataTransfer.setData('text/planarus-doc-id', node.id)}
        onDragOver={e => {
          if (!e.dataTransfer.types.includes('text/planarus-doc-id')) return
          e.preventDefault(); setDragOverId(node.id)
        }}
        onDragLeave={() => setDragOverId(null)}
        onDrop={e => {
          e.preventDefault(); setDragOverId(null)
          const draggedId = e.dataTransfer.getData('text/planarus-doc-id')
          if (draggedId && draggedId !== node.id) onReparent(draggedId, node.id)
        }}
        onClick={() => onSelect(node)}
        onKeyDown={e => e.key === 'Enter' && onSelect(node)}>
        {hasChildren ? (
          <button type="button" className="dp-tree-caret" aria-label={isCollapsed ? `Expand ${node.title}` : `Collapse ${node.title}`}
            onClick={e => { e.stopPropagation(); toggleCollapsed(node.id) }}>
            <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} className="ic-14" />
          </button>
        ) : <span className="dp-tree-caret-spacer" aria-hidden="true" />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="ab-doc-name">{node.title}</div>
          <div className="ab-doc-meta">
            <span className="badge badge-neutral badge-sm">{node.doc_type}</span>
          </div>
        </div>
        <StatusBadge kind="docstatus" value={node.status} />
      </div>
      {!isCollapsed && node.children.map(child => (
        <DocTreeRow key={child.id} node={child} depth={depth + 1} onSelect={onSelect}
          collapsed={collapsed} toggleCollapsed={toggleCollapsed} onReparent={onReparent}
          dragOverId={dragOverId} setDragOverId={setDragOverId} />
      ))}
    </div>
  )
}

function DocList({ projectId, onSelect, onNew, onClose, docType, onRemoved }: DocListProps) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')      // debounced copy of `search`
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  const { noun, Noun } = nouns(docType)

  // Debounce so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search), 200)
    return () => clearTimeout(t)
  }, [search])

  const reload = useCallback(() => {
    setError(null)
    api.docs.list(projectId, { ...(docType ? { doc_type: docType } : {}), q: query })
      .then(setDocs)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, docType, query])

  useEffect(() => { setLoading(true); reload() }, [reload])

  const searching = query.trim().length > 0
  // #138: an indented, collapsible tree replaces the flat list — but only when
  // browsing. A search's matches are usually scattered without their ancestors
  // in the result set, so it stays a flat "here's what matched" list.
  const tree = useMemo(() => buildDocTree(docs), [docs])
  const toggleCollapsed = (id: string) => setCollapsed(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const reparent = (childId: string, newParentId: string) => {
    const child = docs.find(d => d.id === childId)
    if (!child || child.id === newParentId || child.parent_doc_id === newParentId) return
    api.docs.update(childId, { parent_doc_id: newParentId, version: child.version })
      .then(updated => setDocs(prev => prev.map(d => (d.id === updated.id ? { ...d, ...updated } : d))))
      .catch(reload) // most likely a 422 (cycle/cross-project) or 409 — resync rather than leave a stale row
  }

  // Keep-ish: an always-present composer instead of a button that swaps the view.
  const composer = docType ? (
    <NoteComposer projectId={projectId} docType={docType} onCreated={onSelect} />
  ) : null

  const searchBox = (
    <input className="input dp-search" type="search" value={search}
      placeholder={`Search ${noun}s…`} aria-label={`Search ${noun}s`}
      onChange={e => setSearch(e.target.value)} />
  )

  if (error) return <p className="dp-state dp-error">{error}</p>

  return (
    <div>
      <div className="dp-list-header">
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          {docs.length} {docs.length === 1 ? noun : `${noun}s`}
        </div>
        {searchBox}
        {!docType && <button className="btn btn-solid btn-sm" onClick={onNew}>+ New {Noun}</button>}
        {onClose && (
          <button type="button" className="btn btn-ghost btn-sm" title={`Close ${noun}s`} aria-label={`Close ${noun}s`}
            onClick={onClose}><Icon name="x" className="ic-14" /></button>
        )}
      </div>
      {composer}
      {loading ? <p className="dp-state">Loading {noun}s…</p>
        : searching && docs.length === 0 ? (
        <p className="dp-state">No {noun}s match “{query}”.</p>
      ) : docs.length === 0 ? (
        <div className="ab-empty">
          <div className="ab-empty-art">
            <Icon name="file" className="ic-32" />
          </div>
          <h3>No {noun}s yet</h3>
          <p>{docType === 'note'
            ? 'Jot down anything — meeting notes, ideas, snippets.'
            : 'Create your first doc to capture specs, plans, or research.'}</p>
          {/* Notes already have the composer directly above — no second button. */}
          {!docType && <button className="btn btn-solid btn-sm" onClick={onNew}>Create a {noun}</button>}
        </div>
      ) : docType ? (
        // Google-Keep-style card grid — the locked-type (Notes) view only; Docs keeps its list.
        <div className="ab-notegrid">
          {docs.map(d => (
            <div key={d.id} className="ab-notecard" data-color={d.color ?? undefined}>
              {/* Only this region opens the note, so the swatch buttons below
                  aren't nested inside a role="button". */}
              <div className="ab-notecard-open" role="button" tabIndex={0}
                onClick={() => onSelect(d)}
                onKeyDown={e => e.key === 'Enter' && onSelect(d)}>
                <div className="ab-notecard-title">{d.title}</div>
                {d.excerpt?.trim()
                  ? <div className="ab-notecard-body">{d.excerpt}</div>
                  : <div className="ab-notecard-body ab-notecard-empty">Empty {noun}</div>}
              </div>
              <div className="ab-notecard-foot">
                <StatusBadge kind="docstatus" value={d.status} />
                <span className="ab-notecard-date">{agoLabel(d.updated_at)}</span>
              </div>
              <div className="ab-notecard-tools">
                <NoteColors doc={d} onStale={reload} onChanged={updated =>
                  setDocs(prev => prev.map(x => (x.id === updated.id ? { ...x, ...updated } : x)))} />
                <button type="button" className="ab-note-del" title={`Delete ${noun}`}
                  aria-label={`Delete ${d.title}`}
                  onClick={() => {
                    if (!window.confirm(`Delete “${d.title}”? This can't be undone.`)) return
                    api.docs.remove(d.id)
                      .then(() => { setDocs(prev => prev.filter(x => x.id !== d.id)); onRemoved?.(d.id) })
                      .catch(reload)
                  }}>
                  <Icon name="trash" className="ic-14" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : searching ? (
        <div className="ab-doclist">
          {docs.map(d => (
            <div key={d.id} className="ab-docitem" role="button" tabIndex={0}
              data-color={d.color ?? undefined}
              onClick={() => onSelect(d)}
              onKeyDown={e => e.key === 'Enter' && onSelect(d)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ab-doc-name">{d.title}</div>
                <div className="ab-doc-meta">
                  <span className="badge badge-neutral badge-sm">{d.doc_type}</span>
                </div>
              </div>
              <StatusBadge kind="docstatus" value={d.status} />
            </div>
          ))}
        </div>
      ) : (
        <div className="ab-doclist dp-doc-tree">
          {tree.map(node => (
            <DocTreeRow key={node.id} node={node} depth={0} onSelect={onSelect}
              collapsed={collapsed} toggleCollapsed={toggleCollapsed} onReparent={reparent}
              dragOverId={dragOverId} setDragOverId={setDragOverId} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create doc form
// ---------------------------------------------------------------------------

interface CreateDocFormProps {
  projectId: string
  onCreated: (doc: Doc) => void
  onCancel: () => void
  lockedType?: string
  /** #106: first line of a captured clip, prefilled as the title. */
  initialTitle?: string
}

function CreateDocForm({ projectId, onCreated, onCancel, lockedType, initialTitle = '' }: CreateDocFormProps) {
  const [title, setTitle] = useState(initialTitle)
  const [docType, setDocType] = useState<string>(lockedType ?? 'note')
  const { Noun } = nouns(lockedType)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true); setError(null)
    // A 'canvas' doc is an Excalidraw whiteboard; any other type is a Tiptap doc.
    const editor_format = docType === 'canvas' ? 'excalidraw' : undefined
    api.docs.create(projectId, { title: title.trim(), doc_type: docType, editor_format })
      .then(onCreated)
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false))
  }

  return (
    <div>
      <div className="dp-list-header">
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
          New {lockedType ?? 'document'}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      <form className="dp-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label className="form-label">Title</label>
          <input className="input" type="text" placeholder={`${Noun} title`} value={title}
            onChange={e => setTitle(e.target.value)} required autoFocus />
        </div>
        {!lockedType && (
          <div className="form-field">
            <label className="form-label">Type</label>
            <select className="input select" value={docType} onChange={e => setDocType(e.target.value)}>
              {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="dp-form-actions">
          <button type="submit" disabled={saving || !title.trim()} className="btn btn-solid btn-sm">
            {saving ? 'Creating…' : 'Create'}
          </button>
          <button type="button" className="btn btn-outline btn-sm" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tiptap toolbar
// ---------------------------------------------------------------------------

/**
 * Row/column controls for the table block. Mounted only while the caret is
 * inside a table: ProseMirror's table commands act on the cell holding the
 * selection, so anywhere else they are dead buttons.
 *
 * The `useEditorState` subscription is what makes that reactive — `useEditor`
 * is configured without `shouldRerenderOnTransaction`, so clicking into a table
 * moves the selection without re-rendering the toolbar on its own.
 *
 * ponytail: one kebab of word labels, no icon row. Adding and deleting by hand
 * is what the hover handles on the table are for; this is the path that works
 * without a pointer, plus the operations the handles don't carry.
 */
function TableTools({ editor }: { editor: Editor }) {
  const inTable = useEditorState({ editor, selector: ({ editor }) => editor.isActive('table') })
  if (!inTable) return null
  const cmd = (fn: (c: ChainedCommands) => ChainedCommands) => () => { fn(editor.chain().focus()).run() }
  return (
    <>
      <span className="ab-tdiv" />
      <Menu label="Table options">
        <MenuItem onClick={cmd(c => c.addColumnAfter())}>Add column right</MenuItem>
        <MenuItem onClick={cmd(c => c.addColumnBefore())}>Add column left</MenuItem>
        <MenuItem onClick={cmd(c => c.addRowAfter())}>Add row below</MenuItem>
        <MenuItem onClick={cmd(c => c.addRowBefore())}>Add row above</MenuItem>
        <MenuItem onClick={cmd(c => c.toggleHeaderRow())}>Toggle header row</MenuItem>
        <MenuItem danger onClick={cmd(c => c.deleteColumn())}>Delete column</MenuItem>
        <MenuItem danger onClick={cmd(c => c.deleteRow())}>Delete row</MenuItem>
        <MenuItem danger onClick={cmd(c => c.deleteTable())}>Delete table</MenuItem>
      </Menu>
    </>
  )
}

/** How far outside the table the handles sit, plus room to travel to them. */
const HANDLE_REACH = 44

/**
 * Notion-style handles on whichever table the pointer is over: a "+" past the
 * right edge (column at the end), a "+" under the bottom edge (row at the end),
 * and a "✕" over the hovered column and row.
 *
 * Every handle sits *outside* the table, so reaching one means leaving the cell
 * that summoned it — and a table is full-width, so it usually means leaving the
 * prose column too. Hence the two rules that keep them alive: a pointer still
 * within HANDLE_REACH of the table keeps them, and leaving the host clears them
 * on a short timer that hovering a handle cancels. Clearing on the first
 * non-cell mouse move is what made them vanish mid-approach.
 *
 * ponytail: rects are read at render, so a scroll under a shown handle leaves it
 * behind until the next mouse move. The alternative is a scroll listener + rAF
 * per table; the drag-handle menu already lives with the same trade.
 */
function TableHandles({ editor, hostRef }: { editor: Editor; hostRef: { current: HTMLDivElement | null } }) {
  const [cell, setCell] = useState<HTMLTableCellElement | null>(null)
  const leaveTimer = useRef<number | null>(null)
  const cancelLeave = useCallback(() => {
    if (leaveTimer.current !== null) { clearTimeout(leaveTimer.current); leaveTimer.current = null }
  }, [])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const onMove = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('.dp-tbl-handles')) return   // the dot and both buttons
      cancelLeave()
      setCell(prev => {
        const next = (target?.closest('td, th') ?? null) as HTMLTableCellElement | null
        if (next) return next === prev ? prev : next
        const rect = prev?.closest('table')?.getBoundingClientRect()
        const near = !!rect
          && e.clientX >= rect.left - HANDLE_REACH && e.clientX <= rect.right + HANDLE_REACH
          && e.clientY >= rect.top - HANDLE_REACH && e.clientY <= rect.bottom + HANDLE_REACH
        return near ? prev : null
      })
    }
    const onLeave = () => {
      cancelLeave()
      leaveTimer.current = window.setTimeout(() => setCell(null), 400)
    }
    host.addEventListener('mousemove', onMove)
    host.addEventListener('mouseleave', onLeave)
    return () => {
      cancelLeave()
      host.removeEventListener('mousemove', onMove)
      host.removeEventListener('mouseleave', onLeave)
    }
  }, [hostRef, cancelLeave])

  const table = cell?.closest('table')
  if (!cell || !table) return null
  const tRect = table.getBoundingClientRect()
  const cRect = cell.getBoundingClientRect()

  // Every table command acts on the cell holding the selection, so a handle
  // first drops the caret into the hovered cell — posAtDOM(cell, 0) lands on its
  // first paragraph, and +1 is inside it, where a text selection is legal.
  // No .focus() in the chain: that would scroll the fresh selection into view,
  // yanking the page away from the table the pointer is still on. The bare DOM
  // focus afterwards is what keeps Ctrl+Z aimed at the editor rather than at the
  // button that was just clicked.
  const runInCell = (fn: (c: ChainedCommands) => ChainedCommands) => () => {
    const pos = editor.view.posAtDOM(cell, 0)
    if (pos < 0) return
    fn(editor.chain().setTextSelection(pos + 1)).run()
    editor.view.dom.focus({ preventScroll: true })
    setCell(null)   // whatever was under the pointer may not exist any more
  }

  const handle = (label: string, icon: string, onClick: () => void) => (
    <button type="button" className={`dp-tbl-handle${icon === 'x' ? ' danger' : ''}`}
      title={label} aria-label={label}
      onMouseDown={e => e.preventDefault()} onClick={onClick}>
      <Icon name={icon} />
    </button>
  )

  // One cluster per axis, parked on the edge nearest the hovered column and row.
  // Each is a dot until the pointer reaches it, then opens into "+" (insert
  // beside this column/row) and "✕" (drop it) — CSS does the swap, so nothing
  // here re-renders on the way in. Anchored by transform rather than by
  // subtracting half a width, since that width changes when it opens.
  return (
    <>
      <div className="dp-tbl-handles dp-tbl-col" onMouseEnter={cancelLeave}
        style={{ top: tRect.top - 19, left: cRect.left + cRect.width / 2 }}>
        <span className="dp-tbl-dot" aria-hidden="true" />
        {handle('Add column right', 'plus', runInCell(c => c.addColumnAfter()))}
        {handle('Delete column', 'x', runInCell(c => c.deleteColumn()))}
      </div>
      <div className="dp-tbl-handles dp-tbl-row" onMouseEnter={cancelLeave}
        style={{ top: cRect.top + cRect.height / 2, left: tRect.left - 6 }}>
        <span className="dp-tbl-dot" aria-hidden="true" />
        {handle('Add row below', 'plus', runInCell(c => c.addRowAfter()))}
        {handle('Delete row', 'x', runInCell(c => c.deleteRow()))}
      </div>
    </>
  )
}

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null

  // Prompt for a URL; empty input removes the link. extendMarkRange lets the
  // command act on the whole link even when the cursor is just inside it.
  const setLink = () => {
    const prev = editor.getAttributes('link').href as string | undefined
    const url = window.prompt('Link URL', prev ?? 'https://')
    if (url === null) return // cancelled
    const chain = editor.chain().focus().extendMarkRange('link')
    if (url.trim() === '') { chain.unsetLink().run(); return }
    // #118: the same rule the server enforces, applied while the author is still
    // here to fix it — otherwise the refusal arrives as a 422 on the next save,
    // long after they typed it.
    if (!isAllowedLink(url.trim(), { allowRelative: true })) {
      window.alert('Links must be http(s), mailto:, or a path within this app.')
      return
    }
    chain.setLink({ href: url.trim() }).run()
  }

  // Insert an image by URL; prompt for alt text (accessibility).
  const addImage = () => {
    const url = window.prompt('Image URL')
    if (!url || !url.trim()) return
    if (!isAllowedImageSrc(url.trim())) {
      window.alert('Image sources must be http(s) or a base64 data URI (png, jpeg, gif, webp, avif).')
      return
    }
    const alt = window.prompt('Alt text (describe the image)') ?? ''
    editor.chain().focus().setImage({ src: url.trim(), alt }).run()
  }

  return (
    // Prevent a toolbar button's mousedown from blurring the editor and
    // collapsing the selection — otherwise toggleBold/Italic/etc. apply to an
    // empty cursor instead of the selected text. The color <input> is exempt so
    // its native picker still opens.
    <div className="ab-toolbar" role="toolbar" aria-label="Editor toolbar"
      onMouseDown={(e) => { if ((e.target as HTMLElement).closest('button')) e.preventDefault() }}>
      {/* StarterKit's history plugin covers every transaction the editor makes —
          typing, the "/" menu, the drag handle, the table handles. Ctrl+Z does
          the same thing; these are here for when focus sits on a button. */}
      <button type="button" title="Undo (Ctrl+Z)" aria-label="Undo"
        className="ab-tbtn" onClick={() => editor.chain().focus().undo().run()}><Icon name="undo" /></button>
      <button type="button" title="Redo (Ctrl+Shift+Z)" aria-label="Redo"
        className="ab-tbtn" onClick={() => editor.chain().focus().redo().run()}><Icon name="redo" /></button>
      <span className="ab-tdiv" />
      <button type="button" title="Bold" aria-label="Bold"
        className={`ab-tbtn${editor.isActive('bold') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBold().run()}><Icon name="bold" /></button>
      <button type="button" title="Italic" aria-label="Italic"
        className={`ab-tbtn${editor.isActive('italic') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleItalic().run()}><Icon name="italic" /></button>
      <button type="button" title="Underline" aria-label="Underline"
        className={`ab-tbtn${editor.isActive('underline') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleUnderline().run()}><Icon name="underline" /></button>
      <button type="button" title="Strikethrough" aria-label="Strikethrough"
        className={`ab-tbtn${editor.isActive('strike') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleStrike().run()}><Icon name="strikethrough" /></button>
      <button type="button" title="Highlight" aria-label="Highlight"
        className={`ab-tbtn${editor.isActive('highlight') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHighlight().run()}><Icon name="highlight" /></button>
      <button type="button" title="Subscript" aria-label="Subscript"
        className={`ab-tbtn${editor.isActive('subscript') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleSubscript().run()}><Icon name="subscript" /></button>
      <button type="button" title="Superscript" aria-label="Superscript"
        className={`ab-tbtn${editor.isActive('superscript') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleSuperscript().run()}><Icon name="superscript" /></button>
      <span className="ab-tdiv" />
      <button type="button" title="Heading 1" aria-label="Heading 1"
        className={`ab-tbtn${editor.isActive('heading', { level: 1 }) ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}><Icon name="heading-1" /></button>
      <button type="button" title="Heading 2" aria-label="Heading 2"
        className={`ab-tbtn${editor.isActive('heading', { level: 2 }) ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}><Icon name="heading-2" /></button>
      <span className="ab-tdiv" />
      <button type="button" title="Bullet list" aria-label="Bullet list"
        className={`ab-tbtn${editor.isActive('bulletList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBulletList().run()}><Icon name="list" /></button>
      <button type="button" title="Ordered list" aria-label="Ordered list"
        className={`ab-tbtn${editor.isActive('orderedList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}><Icon name="list-ordered" /></button>
      <button type="button" title="Task list" aria-label="Task list"
        className={`ab-tbtn${editor.isActive('taskList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleTaskList().run()}><Icon name="list-todo" /></button>
      <button type="button" title="Blockquote" aria-label="Blockquote"
        className={`ab-tbtn${editor.isActive('blockquote') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}><Icon name="quote" /></button>
      <button type="button" title="Code block" aria-label="Code block"
        className={`ab-tbtn${editor.isActive('codeBlock') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}><Icon name="code" /></button>
      <span className="ab-tdiv" />
      <button type="button" title="Link" aria-label="Link"
        className={`ab-tbtn${editor.isActive('link') ? ' active' : ''}`}
        onClick={setLink}><Icon name="link" /></button>
      <button type="button" title="Image" aria-label="Image"
        className="ab-tbtn"
        onClick={addImage}><Icon name="image" /></button>
      <input type="color" className="ab-tcolor" title="Font color" aria-label="Font color"
        value={(editor.getAttributes('textStyle').color as string) || '#000000'}
        onChange={(e) => editor.chain().focus().setColor(e.target.value).run()} />
      <TableTools editor={editor} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Markdown preview (safe — uses pre, NOT dangerouslySetInnerHTML)
// ---------------------------------------------------------------------------

function MarkdownPreview({ markdown }: { markdown: string }) {
  if (!markdown) return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', padding: 'var(--space-6) var(--space-8)', margin: 0 }}>No markdown content yet.</p>
  return <pre className="dp-md-preview">{markdown}</pre>
}

// ---------------------------------------------------------------------------
// Doc editor
// ---------------------------------------------------------------------------

/**
 * Turn a pasted/dropped image into an inline data URI.
 *
 * ponytail: data URIs, no upload endpoint and no blob store — the note IS the
 * image's home. The ceiling is real though: content_json is capped at 2 MB
 * server-side, so anything sizeable is downscaled first, and a single image that
 * still won't fit is rejected here rather than failing the save later. Upgrade
 * path if notes become image-heavy: a real upload endpoint + /media/{id} refs.
 */
const IMAGE_PASSTHROUGH_BYTES = 400 * 1024   // small enough to embed untouched
const IMAGE_MAX_EDGE = 1400
const IMAGE_MAX_DATA_URL = 1_200_000         // ~1.2 MB of base64, inside the 2 MB doc cap

function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result as string)
    fr.onerror = () => reject(new Error('Could not read the image'))
    fr.readAsDataURL(file)
  })
}

async function imageToDataUrl(file: File): Promise<string> {
  if (file.size <= IMAGE_PASSTHROUGH_BYTES) return readAsDataUrl(file)

  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, IMAGE_MAX_EDGE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  // JPEG: a pasted screenshot as PNG is several times larger for no visible gain.
  const out = canvas.toDataURL('image/jpeg', 0.8)
  if (out.length > IMAGE_MAX_DATA_URL) {
    throw new Error('That image is too large to embed — resize it and try again.')
  }
  return out
}

// #118: an SVG is a document, not a raster — it would be inlined as a data URI
// and become a markup surface we then have to sanitize. The server refuses one,
// so accepting it here would only produce a save that fails.
const imageFilesOf = (dt: DataTransfer | null | undefined): File[] =>
  Array.from(dt?.files ?? []).filter(
    f => f.type.startsWith('image/') && f.type !== 'image/svg+xml',
  )

interface DocEditorProps {
  docId: string
  onBack: () => void
  onRemoved?: (docId: string) => void
  /** Opens another doc in this same editor view — a childPage click, a
   * "Referenced by" backlink, or a breadcrumb ancestor. */
  onOpenDoc?: (docId: string) => void
  /** Open armed for editing instead of read-only — set for a doc created a
   * click ago, which has nothing to read yet. */
  startEditing?: boolean
}
type SaveState = 'saved' | 'unsaved' | 'saving' | 'conflict' | 'error'

function DocEditor({ docId, onBack, onRemoved, onOpenDoc, startEditing }: DocEditorProps) {
  const [doc, setDoc] = useState<Doc | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  // A doc opens read-only: links, mention chips and sub-pages are meant to be
  // followed far more often than the prose is rewritten, and a caret sitting in
  // someone's text is one stray keystroke away from an edit nobody asked for.
  // "Edit" arms the editor; the load effect below re-arms the lock on every
  // in-place doc switch, since DocEditor is not remounted for those.
  const [editing, setEditing] = useState(!!startEditing)
  // Read by that per-doc effect, which must not re-run when the prop settles
  // back to false after the created doc has been opened.
  const startEditingRef = useRef(!!startEditing)
  startEditingRef.current = !!startEditing
  const [exportMsg, setExportMsg] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  // Every doc in this project, keyed by id (plan 24: live childPage titles +
  // tombstone detection; also feeds the breadcrumb). Loaded once per project,
  // alongside the doc itself — DocEditor persists across in-place doc switches
  // (childPage/backlink/breadcrumb navigation swaps `docId` without remounting,
  // same pattern the load effect below already relies on).
  const [docIndex, setDocIndex] = useState<Map<string, DocSummary>>(new Map())
  const [docIndexReady, setDocIndexReady] = useState(false)
  // Read by `detachChild`, which must stay a stable callback and must not read
  // the index from inside a setState updater (updaters have to be pure).
  const docIndexRef = useRef(docIndex)
  docIndexRef.current = docIndex
  const versionRef = useRef<number>(1)
  const docRef = useRef<Doc | null>(null)
  const titleRef = useRef('')
  // Read by `flushPendingSave`, which must not itself depend on these — it runs
  // from an effect cleanup keyed only on `docId`.
  const saveStateRef = useRef<SaveState>('saved')
  const lockedByOtherRef = useRef(false)
  // Paste/drop handlers are built once inside useEditor, before `editor` exists.
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null)
  // The mention picker's entity list, loaded lazily on first "@" and cached for
  // this editor's lifetime — same philosophy as CanvasEditor's `entitiesLoaded`.
  // Keyed on the project it was loaded for. DocsPanel is not keyed on projectId
  // in Layout.tsx, so switching projects changes `projectId` in place without
  // remounting DocEditor — an unkeyed cache then offered the previous project's
  // entities, and inserting one produced a chip whose target `sync_mentions`
  // silently drops, i.e. a mention that renders forever and never backlinks.
  const entitiesRef = useRef<{ projectId: string; entities: EntityRef[] } | null>(null)

  // P11.2 soft-lock (dormant in local mode — the presence surface 404s).
  const { lockedByOther, editorName } = usePresence(docId, true)
  saveStateRef.current = saveState
  lockedByOtherRef.current = lockedByOther

  /** New child Doc + insert a childPage node in its place. `titleText` is the
   * already-typed line for "Convert to page"; omitted for a blank "Page". */
  const createChildPage = useCallback(
    (chainEditor: Editor, range: { from: number; to: number }, titleText?: string) => {
      const parent = docRef.current
      if (!parent) return
      const title = titleText?.trim() || 'Untitled'
      // `range` is a position snapshot, and a network round-trip happens before
      // it is used. Track it through every transaction applied meanwhile, or a
      // keystroke landing mid-flight makes `deleteRange` eat the wrong span.
      const startState = chainEditor.state
      const rangeFrom = startState.tr.mapping.map(range.from)
      api.docs.create(parent.project_id, { title, doc_type: parent.doc_type, parent_doc_id: parent.id })
        .then(child => {
          setDocIndex(prev => new Map(prev).set(child.id, child))
          if (chainEditor.isDestroyed) return
          // Re-map through everything that happened during the request.
          const mapping = chainEditor.state.tr.mapping
          const from = mapping.map(rangeFrom)
          const to = mapping.map(range.to)
          chainEditor.chain().focus()
            .deleteRange({ from: Math.min(from, to), to: Math.max(from, to) })
            .insertContent({ type: 'childPage', attrs: { docId: child.id, title: child.title } })
            .run()
        })
        .catch((e: Error) => {
          // Silent failure left the literal "/page" text sitting in the document
          // with no indication anything had gone wrong.
          setSaveError(`Could not create the sub-page: ${e.message}`)
          setSaveState('error')
        })
    },
    [],
  )

  /**
   * Soft-detach only — never deletes the child (plan 24's rule).
   *
   * Reads the version outside any setState updater: updaters must be pure, and
   * React invokes them twice in StrictMode, which fired the PATCH twice (the
   * second 409ing into a swallowed catch). On a genuine 409 — the child's
   * version moved because it was edited after the index was loaded — refetch
   * and retry once, rather than silently leaving the child parented to a
   * document whose body no longer references it.
   */
  const detachChild = useCallback((childId: string) => {
    const known = docIndexRef.current.get(childId)
    if (!known) return
    const apply = (updated: Doc | DocSummary) =>
      setDocIndex(p => new Map(p).set(childId, updated as DocSummary))

    api.docs.update(childId, { parent_doc_id: null, version: known.version })
      .then(apply)
      .catch(async (e: Error) => {
        if (!e.message.startsWith('409')) {
          setSaveError(`Could not detach the sub-page: ${e.message}`)
          setSaveState('error')
          return
        }
        try {
          const fresh = await api.docs.get(childId)
          apply(await api.docs.update(childId, { parent_doc_id: null, version: fresh.version }))
        } catch (retry: unknown) {
          setSaveError(
            `The sub-page could not be detached and is still nested: ${
              retry instanceof Error ? retry.message : String(retry)
            }`,
          )
          setSaveState('error')
        }
      })
  }, [])

  // Memoized so the array is reference-stable across re-renders. @tiptap/react
  // reference-compares `extensions` on every render and calls editor.setOptions
  // whenever any entry differs, which tears down and rebuilds every ProseMirror
  // plugin — including the "@"/"/" suggestion plugins. A fresh array literal
  // (built directly inside useEditor's options) is a new object on every
  // keystroke via onUpdate → setSaveState → re-render, which was destroying the
  // suggestion popup's view moments after it opened. The array only closes over
  // stable refs/setState below, so an empty dep list is correct.
  const extensions = useMemo(() => [
      // StarterKit v3 bundles Link + Underline; configure/enable them here
      // rather than adding second extensions (which triggers duplicate-name warnings).
      StarterKit.configure({
        link: {
          openOnClick: false,
          autolink: true,
          HTMLAttributes: { rel: 'noopener noreferrer nofollow', target: '_blank' },
          // #118: an explicit policy rather than the extension's default. Tiptap
          // 3.28 fixed its own URI validation, but a library default is not
          // something to depend on for a security property — and this must agree
          // with what the server stores, which the default knows nothing about.
          isAllowedUri: (url: string) => isAllowedLink(url, { allowRelative: true }),
        },
      }),
      // The only discoverability the "/" and "@" menus have: an empty line says
      // what opens them. showOnlyCurrent (default) keeps it to the focused line.
      Placeholder.configure({ placeholder: "Type '/' for blocks, '@' to mention" }),
      TextStyle,
      Color,
      Highlight,
      Subscript,
      Superscript,
      TaskList,
      TaskItem.configure({ nested: true }),
      SafeImage,
      // #138 plan 24: toggle / callout / table blocks.
      Details, DetailsSummary, DetailsContent,
      Table.configure({ resizable: false }), TableRow, TableHeader, TableCell,
      Callout,
      ChildPage,
      // #138 plan 23: "@" entity mentions. Tiptap's Mention typing ties the
      // suggestion item type to the node's own attrs type (MentionOptions's
      // second generic), which is stricter than the small display-only shape
      // this suggestion actually needs — cast at this one well-understood
      // boundary rather than widening PlanarusMentionAttrs to fit a UI concern.
      PlanarusMention.configure({
        suggestion: {
          char: '@',
          items: async ({ query }: { query: string }) => {
            const pid = docRef.current?.project_id
            if (!pid) return []
            if (entitiesRef.current?.projectId !== pid) {
              entitiesRef.current = { projectId: pid, entities: await loadMentionableEntities(pid) }
            }
            const cached = entitiesRef.current.entities
            return filterEntities(cached.filter(e => (MENTION_KINDS as string[]).includes(e.kind)), query)
              .slice(0, 20)
              .map(e => ({ key: `${e.kind}:${e.id}`, label: e.title, icon: KIND_ICON[e.kind], sub: e.status, targetType: e.kind, targetId: e.id }))
          },
          command: ({ editor: cmdEditor, range, props }: {
            editor: Editor; range: { from: number; to: number }
            props: { targetType: EntityKind; targetId: string; label: string }
          }) => {
            cmdEditor.chain().focus().insertContentAt(range, [
              { type: 'mention', attrs: { targetType: props.targetType, targetId: props.targetId, label: props.label } },
              { type: 'text', text: ' ' },
            ]).run()
          },
          render: suggestionRenderer(MentionSuggestionList),
        } as never,
      }),
      // #138 plan 24: "/" block menu, incl. the two doc-creating commands.
      SlashCommand.configure({
        suggestion: {
          items: ({ query }) => {
            const pageItems: SlashItem[] = [
              { key: 'page', label: 'Page', icon: <Icon name="file-text" />, sub: 'Create a sub-page', run: (e, r) => createChildPage(e, r) },
              {
                key: 'convert-to-page', label: 'Convert to page', icon: <Icon name="file-text" />, sub: 'Turn this line into a sub-page',
                run: (e, r) => {
                  const paraStart = e.state.doc.resolve(r.from).start()
                  const titleText = e.state.doc.textBetween(paraStart, r.from)
                  createChildPage(e, { from: paraStart, to: r.to }, titleText)
                },
              },
            ]
            const q = query.toLowerCase()
            return [...SLASH_ITEMS, ...pageItems].filter(i => !q || i.label.toLowerCase().includes(q))
          },
          render: suggestionRenderer(SlashSuggestionList),
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    ], [])

  // Same reference-stability requirement as `extensions` above: `editorProps` is
  // compared by identity too, so a fresh object literal here would re-trigger
  // the same plugin-rebuild-on-every-keystroke bug. `onOpenDoc` is a prop (not
  // guaranteed stable across parent renders), so it's read through a ref rather
  // than closed over directly, the same indirection `editorRef` already uses.
  const onOpenDocRef = useRef(onOpenDoc)
  onOpenDocRef.current = onOpenDoc

  const editorProps = useMemo(() => ({
    // Images arrive as files on both paths, so both share one handler. Returning
    // false for anything else leaves ProseMirror's native text paste/drop alone —
    // which is what makes dragging plain text in already work.
    handlePaste: (_view: Editor['view'], event: ClipboardEvent) => insertImages(imageFilesOf(event.clipboardData)),
    handleDrop: (view: Editor['view'], event: Event) => {
      const files = imageFilesOf((event as DragEvent).dataTransfer)
      if (files.length === 0) return false
      // Drop where the pointer is, not at the caret — otherwise the image lands
      // wherever you last typed, and a selected node gets replaced outright.
      const at = view.posAtCoords({
        left: (event as DragEvent).clientX,
        top: (event as DragEvent).clientY,
      })
      return insertImages(files, at?.pos)
    },
    // Mention chips have no real href (they're not a Link mark), so
    // click-to-navigate rides a plain ProseMirror click handler instead.
    handleClickOn: (_view: Editor['view'], _pos: number, node: NodeViewProps['node']) => {
      if (node.type.name !== 'mention' || !onOpenDocRef.current) return false
      if (node.attrs.targetType !== 'doc') return false
      onOpenDocRef.current(node.attrs.targetId as string)
      return true
    },
  }), [])

  const editor = useEditor({
    extensions,
    content: '',
    onUpdate: () => setSaveState('unsaved'),
    editorProps,
    // A non-empty `deps` array switches @tiptap/react from "re-diff every
    // option on every render, call editor.setOptions() on any identity
    // mismatch" to "only recreate the editor if deps changed" — deps are
    // compared by value, not by array identity, so this literal (recreated
    // each render, but always equal by content) opts in to that mode
    // permanently without ever actually recreating the editor. Without it,
    // `editorProps`/`extensions` still being reference-stable wasn't enough:
    // useEditor was calling setOptions() on every keystroke regardless
    // (deps.length === 0 always takes the compare-and-sync path), tearing
    // down and rebuilding every ProseMirror plugin — including the "@"/"/"
    // suggestion ones — mid-interaction.
  }, ['doc-editor'])
  editorRef.current = editor
  // Host for the table hover handles. The scroll wrapper, not the prose column
  // inside it: a table runs the full width of the prose, so the handles hanging
  // off its edges would otherwise sit outside the element listening for them.
  const tableHostRef = useRef<HTMLDivElement>(null)
  // The block currently under the drag handle (hover, not click) — read at
  // click time to build the "turn into / duplicate / delete" menu.
  const dragNodeRef = useRef<{ pos: number; typeName: string } | null>(null)
  const [dragMenuPos, setDragMenuPos] = useState<number | null>(null)
  // @tiptap/extension-drag-handle-react re-registers its whole ProseMirror
  // plugin (unregisterPlugin + registerPlugin) whenever `onNodeChange`'s
  // identity changes — a plain inline arrow function here was doing that on
  // every keystroke (onUpdate → setSaveState → re-render), and re-registering
  // one plugin reconfigures the editor's *entire* plugin set, tearing down and
  // rebuilding every other plugin view mid-interaction — including the "@"/"/"
  // suggestion ones, which is what was closing the popup moments after it
  // opened. Same fix as `extensions`/`editorProps` above: keep it stable.
  const onDragNodeChange = useCallback(({ node, pos }: { node: NodeViewProps['node'] | null; pos: number }) => {
    dragNodeRef.current = node ? { pos, typeName: node.type.name } : null
  }, [])

  const duplicateNodeAt = (pos: number) => {
    const node = editorRef.current?.state.doc.nodeAt(pos)
    if (!node || !editorRef.current) return
    editorRef.current.chain().focus().insertContentAt(pos + node.nodeSize, node.toJSON()).run()
  }

  /** True = we took the files. Insertion is async; the handlers must answer now. */
  function insertImages(files: File[], at?: number): boolean {
    if (files.length === 0) return false
    void (async () => {
      let pos = at
      for (const file of files) {
        try {
          const src = await imageToDataUrl(file)
          const node = { type: 'image', attrs: { src, alt: file.name } }
          // Explicit position for the first dropped file; the caret has moved past
          // it by the time the next one lands, so the rest just follow the cursor.
          if (pos != null) editorRef.current?.chain().focus().insertContentAt(pos, node).run()
          else editorRef.current?.chain().focus().setImage({ src, alt: file.name }).run()
          pos = undefined
        } catch (e: unknown) {
          setSaveError(e instanceof Error ? e.message : String(e))
          setSaveState('error')
        }
      }
    })()
    return true
  }

  useEffect(() => {
    const armed = editing && !lockedByOther
    editor?.setEditable(armed)
    // Pressing Edit should put the caret in the prose — otherwise it takes a
    // second click to start typing, and the toolbar appears to do nothing.
    if (armed) editor?.commands.focus()
  }, [editor, editing, lockedByOther])

  // Following a link is an in-place doc switch, not a remount, so the read-only
  // default has to be re-applied per doc rather than only on mount. Keyed on
  // docId alone: `editor` can be recreated by Tiptap, and that must not throw
  // away an edit session the reader is in the middle of.
  useEffect(() => { setEditing(startEditingRef.current) }, [docId])

  useEffect(() => {
    // #138 made in-place doc switching common (childPage / breadcrumb /
    // backlink / mention chip), so two loads can now be in flight at once.
    // Without this guard an out-of-order resolution leaves the editor showing
    // document A while `docId` is already B.
    let cancelled = false
    setLoading(true); setLoadError(null)
    api.docs.get(docId)
      .then(d => {
        if (cancelled) return
        setDoc(d); docRef.current = d; versionRef.current = d.version
        setTitle(d.title); titleRef.current = d.title
        // `editor` is a closed-over snapshot; Tiptap can recreate its own Editor
        // instance between this effect firing and the fetch resolving (#183
        // step 3c surfaced this via the faster initialDocId mount path, with no
        // click delay to mask it) — an already-destroyed one throws from its own
        // `commands` getter rather than being a safe no-op.
        if (editor && !editor.isDestroyed) {
          let parsed: object | null = null
          try { parsed = JSON.parse(d.content_json) } catch { /* ignore */ }
          // emitUpdate:false — the default fires onUpdate, marking a freshly
          // opened document dirty. It survives today only because the
          // setSaveState('saved') below wins the same React batch; anything
          // awaited between the two would make every doc *open* autosave,
          // bumping version and updated_by for a read.
          // addToHistory:false — loading a document is not an edit. Left in the
          // undo stack, the first Ctrl+Z after opening a doc replaces the body
          // with the empty document the editor started on, and the autosave then
          // writes that emptiness back. The meta rides the chain's shared
          // transaction, which is the only way to reach setContent's own tr.
          if (parsed) {
            editor.chain().setMeta('addToHistory', false)
              .setContent(parsed as never, { emitUpdate: false }).run()
          }
        }
        setSaveState('saved')
      })
      .catch((e: Error) => { if (!cancelled) setLoadError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [docId, editor])

  // The project's full doc list, for childPage titles/tombstones and the
  // breadcrumb — loaded once per project (DocEditor persists across in-place
  // doc switches), not per doc.
  //
  // Rebuilt from scratch per project rather than merged: DocsPanel is not keyed
  // on projectId in Layout.tsx, so switching projects changes `projectId` in
  // place and a merged index would keep serving the previous project's titles.
  useEffect(() => {
    const pid = doc?.project_id
    if (!pid) return
    let cancelled = false
    setDocIndexReady(false)
    api.docs.list(pid)
      .then(list => {
        if (cancelled) return
        setDocIndex(new Map(list.map(d => [d.id, d])))
        setDocIndexReady(true)
      })
      // Deliberately leaves `docIndexReady` false on failure. The guard used to
      // be a ref set *before* the request, so one transient error meant the
      // index was never retried and every sub-page showed as deleted for the
      // rest of the session. Staying not-ready keeps the links live and lets a
      // later project change retry.
      .catch(() => {})
    return () => { cancelled = true }
  }, [doc?.project_id])

  const save = useCallback(async () => {
    if (!editor || !docRef.current) return
    const contentJson = JSON.stringify(editor.getJSON())
    const markdownCache = serializeToMarkdown(editor.state.doc)
    const nextTitle = titleRef.current.trim()
    setSaveState('saving'); setSaveError(null)
    try {
      const updated = await api.docs.update(docRef.current.id, {
        version: versionRef.current,
        content_json: contentJson,
        markdown_cache: markdownCache,
        // Only when it actually changed — an empty box must not blank the title.
        ...(nextTitle && nextTitle !== docRef.current.title ? { title: nextTitle } : {}),
      })
      setDoc(updated); docRef.current = updated; versionRef.current = updated.version
      // Edits made *during* the request would otherwise be marked clean and sit
      // unsaved until the next keystroke.
      const settled =
        JSON.stringify(editor.getJSON()) === contentJson && titleRef.current.trim() === nextTitle
      setSaveState(settled ? 'saved' : 'unsaved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setSaveState('conflict')
      else { setSaveState('error'); setSaveError(msg) }
    }
  }, [editor])

  // Autosave: one debounced write per pause in typing. 'conflict' and 'error' are
  // deliberately excluded — retrying on a loop would hammer a doomed request.
  useEffect(() => {
    if (saveState !== 'unsaved' || lockedByOther) return
    const t = setTimeout(() => { void save() }, 900)
    return () => clearTimeout(t)
  }, [saveState, save, lockedByOther])

  /**
   * Write the current buffer out without touching component state.
   *
   * The autosave effect above is keyed on `saveState`, not `docId`. #138 added
   * four ways to change `docId` *in place* — a childPage click, a breadcrumb
   * ancestor, a "Referenced by" backlink, and a doc-typed mention chip — and on
   * that path the load effect resolves, calls `setSaveState('saved')`, and the
   * effect's cleanup clears the still-pending timer. The edit made in the
   * previous 900 ms was silently discarded, with no error and no dirty marker.
   *
   * Deliberately not `save()`: that one writes `setDoc`/`docRef`/`versionRef`
   * when it resolves, and by then those describe the document we navigated *to*
   * — so awaiting the old doc's response would clobber the new doc's identity.
   * Fire-and-forget against a captured snapshot instead.
   */
  const flushPendingSave = useCallback(() => {
    const leaving = docRef.current
    if (!editor || editor.isDestroyed || !leaving) return
    if (saveStateRef.current !== 'unsaved' || lockedByOtherRef.current) return
    const nextTitle = titleRef.current.trim()
    void api.docs.update(leaving.id, {
      version: versionRef.current,
      content_json: JSON.stringify(editor.getJSON()),
      markdown_cache: serializeToMarkdown(editor.state.doc),
      ...(nextTitle && nextTitle !== leaving.title ? { title: nextTitle } : {}),
    }).catch(() => {
      // Nothing useful to show: this editor is already displaying another
      // document. A 409 here means someone else wrote first, and their version
      // wins — the same outcome the autosave path reaches.
    })
  }, [editor])

  // Runs before the load effect for the *next* docId, while docRef/versionRef
  // still describe the one being left. Also covers unmount (Back, panel close).
  useEffect(() => () => flushPendingSave(), [docId, flushPendingSave])

  const rename = (next: string) => {
    setTitle(next); titleRef.current = next
    if (next.trim() && next.trim() !== docRef.current?.title) setSaveState('unsaved')
  }

  const remove = () => {
    if (!docRef.current) return
    if (!window.confirm(`Delete “${docRef.current.title}”? This can't be undone.`)) return
    const removedId = docRef.current.id
    api.docs.remove(removedId)
      .then(() => { onRemoved?.(removedId); onBack() })
      .catch((e: Error) => { setSaveError(e.message); setSaveState('error') })
  }

  // A colour PATCH bumps the doc version server-side, so adopt the new version
  // here or the next content save 409s against a version we just invalidated.
  // Unsaved editor content is untouched: only the load effect ever sets content.
  const applyColor = useCallback((updated: Doc) => {
    setDoc(updated); docRef.current = updated; versionRef.current = updated.version
  }, [])

  const exportMarkdown = useCallback(async () => {
    if (!doc) return
    setExportMsg(null)
    try {
      const res = await api.docs.exportMarkdown(doc.id)
      setExportMsg(res.was_changed ? `Exported to ${res.export_path}` : 'No changes (file up-to-date)')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setExportMsg('The exported file was changed outside Planarus. Review it before exporting again.')
      else setExportMsg(`Export failed: ${msg}`)
    }
  }, [doc])

  // Memoized: an inline object literal here is a new value on every render, and
  // `saveState` flips on every keystroke — which re-rendered every ChildPageView
  // in the document as the user typed.
  const docEditorCtx = useMemo<DocEditorCtx>(
    () => ({
      docIndex,
      docIndexReady,
      onOpenDoc: (id: string) => onOpenDocRef.current?.(id),
      onDetachChild: detachChild,
      editing,
    }),
    [docIndex, docIndexReady, detachChild, editing],
  )

  // Breadcrumb: walk parent_doc_id via the already-loaded index, plus the live
  // `doc` itself (its own parent may be fresher than whatever the bulk load saw).
  const breadcrumb = useMemo(() => {
    if (!doc) return []
    const idMap = new Map(docIndex)
    idMap.set(doc.id, doc)
    return docAncestors(doc.id, idMap)
  }, [doc, docIndex])

  if (loading) return <p className="dp-state">Loading doc…</p>
  if (loadError) return <p className="dp-state dp-error">{loadError}</p>
  if (!doc) return <p className="dp-state dp-error">Doc not found.</p>

  const saveLabel =
    saveState === 'saving'  ? 'Saving…' :
    saveState === 'saved'   ? 'Saved' :
    saveState === 'unsaved' ? 'Unsaved changes' :
    // No glyph: `.dp-save-label.conflict` already carries the danger colour.
    saveState === 'conflict' ? 'Updated elsewhere — refresh to reload' :
    `Error: ${saveError ?? 'unknown'}`

  return (
    <div className="ab-editor" data-color={doc.color ?? undefined}>
      {breadcrumb.length > 0 && (
        <nav className="dp-breadcrumb" aria-label="Doc ancestry">
          {breadcrumb.map(ancestor => (
            <span key={ancestor.id} className="dp-breadcrumb-item">
              <button type="button" className="dp-breadcrumb-link" onClick={() => onOpenDoc?.(ancestor.id)}>
                {ancestor.title}
              </button>
              <span className="dp-breadcrumb-sep" aria-hidden="true">/</span>
            </span>
          ))}
        </nav>
      )}
      <div className="dp-editor-nav" style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)' }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to list">
          <Icon name="arrow-left" className="ic-14" /> Back
        </button>
        {/* The title is the note's section heading — edit in place, autosaved. */}
        <input className="dp-title-input" type="text" value={title} disabled={lockedByOther || !editing}
          aria-label="Title" placeholder="Untitled — name this page"
          onChange={e => rename(e.target.value)}
          onBlur={() => { if (!title.trim()) rename(doc.title) }} />
        <StatusBadge kind="docstatus" value={doc.status} />
        {/* Swatches only where the colour is actually rendered — the Notes grid. */}
        {doc.doc_type === 'note' && !lockedByOther && (
          <NoteColors doc={doc} onChanged={applyColor} onStale={() => setSaveState('conflict')} />
        )}
        {lockedByOther && (
          <span
            className="badge badge-warning badge-sm"
            title="Someone else holds the edit lock; this doc is read-only until they leave"
          >
            <Icon name="lock" className="ic-14" /> {editorName} is editing — read-only
          </span>
        )}
      </div>

      {editing && <EditorToolbar editor={editor} />}

      <div className="dp-tiptap-wrap" ref={tableHostRef}>
        {showPreview
          ? <MarkdownPreview markdown={doc.markdown_cache} />
          : (
            <DocEditorContext.Provider
              value={docEditorCtx}
            >
              {/* Mention chips are plain spans, opened by ProseMirror's
                  handleClickOn — and prosemirror-view only routes clicks to that
                  handler while the view is editable. Read mode therefore needs
                  its own listener, or every "@doc" chip goes dead exactly where
                  following it matters most. One delegated handler on the
                  wrapper, rather than a node view per chip. */}
              <div className="ab-prose"
                onClick={editing ? undefined : (e) => {
                  const chip = (e.target as HTMLElement).closest('[data-type="mention"]')
                  if (!chip || chip.getAttribute('data-target-type') !== 'doc') return
                  const target = chip.getAttribute('data-target-id')
                  if (target) onOpenDocRef.current?.(target)
                }}>
                {editor && editing && <TableHandles editor={editor} hostRef={tableHostRef} />}
                {editor && editing && (
                  <DragHandle editor={editor} onNodeChange={onDragNodeChange}>
                    <span className="dp-drag-handle" role="button" tabIndex={0} aria-label="Block menu"
                      onClick={() => setDragMenuPos(dragNodeRef.current?.pos ?? null)}>
                      <Icon name="grip" className="ic-14" />
                    </span>
                  </DragHandle>
                )}
                {dragMenuPos !== null && editor && (
                  <div className="dp-drag-menu" role="menu" onMouseLeave={() => setDragMenuPos(null)}
                    style={(() => {
                      const rect = editor.view.coordsAtPos(dragMenuPos)
                      return { position: 'fixed', top: rect.bottom + 4, left: rect.left }
                    })()}>
                    <p className="dp-drag-menu-lbl">Turn into</p>
                    <button type="button" onClick={() => { editor.chain().focus().setNodeSelection(dragMenuPos).setParagraph().run(); setDragMenuPos(null) }}>Text</button>
                    <button type="button" onClick={() => { editor.chain().focus().setNodeSelection(dragMenuPos).setNode('heading', { level: 1 }).run(); setDragMenuPos(null) }}>Heading 1</button>
                    <button type="button" onClick={() => { editor.chain().focus().setNodeSelection(dragMenuPos).setNode('heading', { level: 2 }).run(); setDragMenuPos(null) }}>Heading 2</button>
                    <button type="button" onClick={() => { editor.chain().focus().setNodeSelection(dragMenuPos).setBlockquote().run(); setDragMenuPos(null) }}>Quote</button>
                    <p className="dp-drag-menu-lbl">Block</p>
                    <button type="button" onClick={() => { duplicateNodeAt(dragMenuPos); setDragMenuPos(null) }}>Duplicate</button>
                    <button type="button" className="dp-danger"
                      onClick={() => { editor.chain().focus().setNodeSelection(dragMenuPos).deleteSelection().run(); setDragMenuPos(null) }}>
                      Delete
                    </button>
                  </div>
                )}
                <EditorContent editor={editor} className="dp-tiptap" />
              </div>
            </DocEditorContext.Provider>
          )
        }
      </div>

      <div className="dp-statusbar">
        <span className={`dp-save-label ${editing ? saveState : 'saved'}`}>
          {editing ? saveLabel : 'Read-only — links are clickable'}
        </span>
        {doc.updated_by_display && (
          <span className="dp-edited-by" style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
            Last edited by {doc.updated_by_display}
          </span>
        )}
        <button type="button" className="btn btn-outline btn-xs" disabled={lockedByOther}
          onClick={() => {
            // Leaving edit mode is the natural "I'm done" moment; the idle
            // autosave would get there eventually, but not before a navigation.
            if (editing && saveStateRef.current === 'unsaved') save()
            setEditing(e => !e)
          }}>
          {editing ? 'Done' : 'Edit'}
        </button>
        {editing && (
          <button type="button" className="btn btn-outline btn-xs"
            onClick={save} disabled={saveState === 'saving' || saveState === 'saved'}>Save</button>
        )}
        <button type="button" className="btn btn-ghost btn-xs"
          onClick={() => setShowPreview(p => !p)}>
          {showPreview ? 'Editor' : 'Preview'}
        </button>
        <button type="button" className="btn btn-ghost btn-xs" onClick={() => exportMarkdown()}>
          Export Markdown
        </button>
        <button type="button" className="btn btn-ghost btn-xs dp-danger" onClick={remove}>
          Delete
        </button>
      </div>
      {exportMsg && <p className="dp-export-msg">{exportMsg}</p>}
      {/* Plan 25's "Document — referenced by an item; related to". Rendered
          below the statusbar so it never sits between the prose and its save
          state. Returns null until the panel's target list has loaded. */}
      <div className="dp-connections-wrap">
        <EntityConnections
          projectId={doc.project_id}
          entityType="doc"
          entityId={doc.id}
          label={doc.title}
        />
        {/* #138 plan 23 — the read side of an @mention: which docs mention this one. */}
        <ReferencedBy projectId={doc.project_id} entityType="doc" entityId={doc.id} onOpenDoc={onOpenDoc} />
      </div>
    </div>
  )
}

/**
 * Load the project's connection graph and the labels its endpoints render with.
 *
 * Deliberately lazy and panel-level, not per-doc: the cost is paid once when the
 * first document opens, and switching documents afterwards costs nothing. The
 * Docs panel holds none of these collections otherwise, which is the one real
 * difference from Planning — there the same data is already on screen, so its
 * connection section adds no request at all.
 *
 * `ready` exists because `ConnectionProvider` prunes any connection whose
 * endpoints are missing from `targets`. Mounting it against a half-loaded target
 * list would read every connection as dangling and delete the lot from local
 * state — so the provider is not mounted until both halves have landed.
 */
function useDocConnections(projectId: string, enabled: boolean) {
  const [connections, setConnections] = useState<EntityConnection[]>([])
  const [targets, setTargets] = useState<ConnectionTarget[]>([])
  const [ready, setReady] = useState(false)
  const loadedFor = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled || loadedFor.current === projectId) return
    loadedFor.current = projectId
    let cancelled = false
    // try//catch around the whole batch, not `.catch()` per call: a missing api
    // namespace throws *synchronously* at property access, before any promise
    // exists for `.catch` to attach to, so per-call handlers never see it. The
    // connections section is supplementary context — if any of this fails it
    // must stay unmounted, never take the editor down with it.
    void (async () => {
      try {
        const [conns, phases, tasks, milestones, decisions, risks, docs] = await Promise.all([
          api.connections.list(projectId),
          api.phases.list(projectId),
          api.tasks.list(projectId),
          api.milestones.list(projectId),
          api.decisions.list(projectId),
          api.risks.list(projectId),
          api.docs.list(projectId),
        ])
        if (cancelled) return
        setConnections(conns)
        setTargets(buildConnectionTargets({ phases, tasks, milestones, decisions, risks, docs }))
        setReady(true)
      } catch {
        // Leave `ready` false: no provider, no section, editor unaffected.
      }
    })()
    return () => { cancelled = true }
  }, [projectId, enabled])

  // Exposed so a doc create/delete elsewhere in this panel can merge into the
  // loaded target list directly (Codex #173 P2) instead of leaving it stale
  // until the whole panel remounts on a project switch. A full re-fetch would
  // also work but costs seven requests to add or remove one row.
  return { connections, setConnections, targets, setTargets, ready }
}

// ---------------------------------------------------------------------------
// Root panel
// ---------------------------------------------------------------------------

/** `docType` locks the panel to one type — the Notes view is this panel with docType="note". */
interface DocsPanelProps {
  projectId: string
  onClose: () => void
  docType?: string
  /** #106: a `doc` clip opens straight into the create form, titled. */
  captureTitle?: string
  /** #183 step 3: the nested /docs/:docSlug route. ProjectRoute resolves the
   *  slug to an id (docs have no by-slug read endpoint); this panel still
   *  needs `editor_format` to pick Tiptap vs. Excalidraw, so it looks the doc
   *  up once more here rather than pushing that lookup onto the router. */
  initialDocId?: string
  onDocSelected?: (id: string | null) => void
}

export default function DocsPanel({ projectId, onClose, docType, captureTitle, initialDocId, onDocSelected }: DocsPanelProps) {
  const [view, setView] = useState<'list' | 'new' | 'editor'>(captureTitle ? 'new' : 'list')
  const [selected, setSelected] = useState<{ id: string; format: string } | null>(null)
  // The one doc this panel just created — the only one that opens in edit mode.
  const [createdId, setCreatedId] = useState<string | null>(null)

  // Fetched only once a document is actually open — browsing the list costs
  // nothing extra.
  const conn = useDocConnections(projectId, view === 'editor')

  useEffect(() => {
    if (!initialDocId) return
    let cancelled = false
    api.docs.get(initialDocId).then(d => {
      if (cancelled) return
      setSelected({ id: d.id, format: d.editor_format })
      setView('editor')
    // A deleted/unresolvable doc id fails silently (stays on whatever view is
    // already showing) rather than surfacing a broken editor — matching how
    // TasksList's initialTaskId simply finds nothing to open.
    }).catch(() => {})
    return () => { cancelled = true }
  }, [initialDocId])

  const handleSelect = (doc: DocSummary) => {
    setSelected({ id: doc.id, format: doc.editor_format }); setView('editor')
    onDocSelected?.(doc.id)
  }
  const handleCreated = (doc: Doc) => {
    // Merges the new doc into the already-loaded target list so it is
    // immediately selectable as a connection endpoint from any other open
    // document, rather than staying invisible until the panel remounts.
    if (conn.ready) conn.setTargets(prev => [...prev, docToTarget(doc)])
    // Docs open read-only, but a document created one click ago has nothing to
    // read — land in the editor, armed.
    setCreatedId(doc.id)
    setSelected({ id: doc.id, format: doc.editor_format }); setView('editor')
    onDocSelected?.(doc.id)
  }
  const goBack = () => { setView('list'); setSelected(null); onDocSelected?.(null) }
  // Dropping the target lets ConnectionProvider's own prune effect (keyed on
  // `targets`) clean up any connection that pointed at it — no separate
  // connections-side update needed.
  const handleRemoved = (docId: string) => {
    conn.setTargets(prev => prev.filter(t => !(t.entityType === 'doc' && t.id === docId)))
  }
  // #138: open another doc while staying in the editor view — a childPage
  // click, a "Referenced by" backlink, or a breadcrumb ancestor. DocEditor
  // persists across the docId change (same pattern initialDocId already uses).
  const openDocById = useCallback((id: string) => {
    api.docs.get(id).then(d => {
      setSelected({ id: d.id, format: d.editor_format }); setView('editor')
      onDocSelected?.(d.id)
    }).catch(() => {})
  }, [onDocSelected])

  return (
    <div className="dp-panel">
      {view === 'list' && <DocList projectId={projectId} onSelect={handleSelect} onNew={() => setView('new')} onClose={onClose} docType={docType} onRemoved={handleRemoved} />}
      {view === 'new' && <CreateDocForm projectId={projectId} onCreated={handleCreated} onCancel={() => setView('list')} lockedType={docType} initialTitle={captureTitle} />}
      {/* Mounted unconditionally, and `ready` carries the loading state instead.
          Wrapping the editor only once loaded would change the element type at
          this position and remount it — see ConnectionProvider's `ready` doc. */}
      <ConnectionProvider
        connections={conn.connections}
        setConnections={conn.setConnections}
        targets={conn.targets}
        ready={conn.ready}
      >
        {view === 'editor' && selected && (
          selected.format === 'excalidraw'
            ? <Suspense fallback={<p className="dp-state">Loading canvas…</p>}>
                <CanvasEditor docId={selected.id} onBack={goBack} />
              </Suspense>
            : <DocEditor docId={selected.id} onBack={goBack} onRemoved={handleRemoved} onOpenDoc={openDocById}
                startEditing={selected.id === createdId} />
        )}
      </ConnectionProvider>
    </div>
  )
}
