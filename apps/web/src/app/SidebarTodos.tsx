import { useCallback, useEffect, useState } from 'react'
import { api, type Todo } from '../api/client'
import { buildTodoTree, type TodoNode } from './todoTree'
import { Icon } from './Icon'

interface RowProps {
  node: TodoNode
  depth: number
  onToggle: (t: Todo) => void
  onAddChild: (parentId: string) => void
  onRename: (t: Todo) => void
  onDelete: (t: TodoNode) => void
}

function TodoRow({ node, depth, onToggle, onAddChild, onRename, onDelete }: RowProps) {
  return (
    <>
      <div className="ab-todo-row" style={{ paddingLeft: 8 + depth * 14 }}>
        <input
          type="checkbox"
          className="ab-todo-check"
          checked={node.done}
          onChange={() => onToggle(node)}
          aria-label={node.done ? `Mark "${node.label}" not done` : `Mark "${node.label}" done`}
        />
        <span
          className={`ab-todo-label${node.done ? ' done' : ''}`}
          onDoubleClick={() => onRename(node)}
          title="Double-click to rename"
        >
          {node.label}
        </span>
        <button type="button" className="ab-todo-act" title="Add sub-todo" onClick={() => onAddChild(node.id)}>+</button>
        <button type="button" className="ab-todo-act" title="Delete" onClick={() => onDelete(node)}>×</button>
      </div>
      {node.children.map((c) => (
        <TodoRow key={c.id} node={c} depth={depth + 1}
          onToggle={onToggle} onAddChild={onAddChild} onRename={onRename} onDelete={onDelete} />
      ))}
    </>
  )
}

export function SidebarTodos({ projectId, captureLabel }: { projectId: string; captureLabel?: string }) {
  const [todos, setTodos] = useState<Todo[]>([])
  const [collapsed, setCollapsed] = useState(false)
  // #106: a `todo` clip lands in the add box, not straight in the list — the
  // human still presses Add, so a fragment can never write on page load.
  const [newLabel, setNewLabel] = useState(captureLabel ?? '')

  const refresh = useCallback(() => {
    api.todos.list(projectId).then(setTodos).catch(() => { /* keep last */ })
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const addTop = (e: React.FormEvent) => {
    e.preventDefault()
    const label = newLabel.trim()
    if (!label) return
    api.todos.create(projectId, { label }).then(() => { setNewLabel(''); refresh() })
  }
  const addChild = (parentId: string) => {
    const label = window.prompt('Sub-todo')?.trim()
    if (label) api.todos.create(projectId, { label, parent_id: parentId }).then(refresh)
  }
  const toggle = (t: Todo) => { void api.todos.update(t.id, { done: !t.done }).then(refresh) }
  const rename = (t: Todo) => {
    const label = window.prompt('Edit todo', t.label)?.trim()
    if (label && label !== t.label) api.todos.update(t.id, { label }).then(refresh)
  }
  const remove = (t: TodoNode) => {
    const msg = t.children.length
      ? `Delete "${t.label}" and its ${t.children.length} sub-item(s)?`
      : `Delete "${t.label}"?`
    if (window.confirm(msg)) api.todos.remove(t.id).then(refresh)
  }

  const tree = buildTodoTree(todos)
  const openCount = todos.filter((t) => !t.done).length

  return (
    <section className="ab-todos" aria-label="Todos">
      <button
        type="button"
        className="ab-todos-head"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((c) => !c)}
      >
        <Icon name="chevron-down" className={`ic-14 ab-todos-chev${collapsed ? ' collapsed' : ''}`} />
        <span className="ab-todos-title">Todos</span>
        {openCount > 0 && <span className="ab-todos-count">{openCount}</span>}
      </button>
      {!collapsed && (
        <>
          <div className="ab-todos-list">
            {tree.length === 0 ? (
              <div className="ab-todos-empty">No todos yet</div>
            ) : (
              tree.map((n) => (
                <TodoRow key={n.id} node={n} depth={0}
                  onToggle={toggle} onAddChild={addChild} onRename={rename} onDelete={remove} />
              ))
            )}
          </div>
          <form className="ab-todos-add" onSubmit={addTop}>
            <input
              className="ab-todos-input"
              value={newLabel}
              placeholder="Add a todo…"
              aria-label="Add a todo"
              onChange={(e) => setNewLabel(e.target.value)}
            />
          </form>
        </>
      )}
    </section>
  )
}
