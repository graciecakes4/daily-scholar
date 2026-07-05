'use client';

/**
 * ChipListEditor — bubble-style editor for a string[] field.
 *
 * Existing items render as chips. Clicking a chip selects it (click again
 * to deselect); a small toolbar then offers Edit / Delete for that one
 * selection, rather than per-chip icon buttons cluttering every bubble.
 * A separate dashed "+ Add" chip reveals a text input with a filtered
 * suggestion dropdown — recommendations only ever show up here, not
 * while editing an existing chip, since edits are a deliberate one-off
 * correction rather than a search.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

interface ChipListEditorProps {
  items: string[];
  onChange: (next: string[]) => void;
  suggestions?: string[];
  addPlaceholder?: string;
  monospace?: boolean;
  emptyHint?: string;
}

const MAX_SUGGESTIONS = 8;

export default function ChipListEditor({
  items,
  onChange,
  suggestions = [],
  addPlaceholder = 'Add…',
  monospace = false,
  emptyHint,
}: ChipListEditorProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [adding, setAdding] = useState(false);
  const [addValue, setAddValue] = useState('');
  const [highlightIdx, setHighlightIdx] = useState(0);

  const addInputRef = useRef<HTMLInputElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding) addInputRef.current?.focus();
  }, [adding]);

  useEffect(() => {
    if (editing) editInputRef.current?.focus();
  }, [editing]);

  const filteredSuggestions = useMemo(() => {
    const q = addValue.trim().toLowerCase();
    if (!q) return [];
    const have = new Set(items.map(i => i.toLowerCase()));
    return suggestions
      .filter(s => !have.has(s.toLowerCase()) && s.toLowerCase().includes(q))
      .slice(0, MAX_SUGGESTIONS);
  }, [addValue, suggestions, items]);

  function selectChip(idx: number) {
    setSelected(prev => (prev === idx ? null : idx));
    setEditing(false);
    setAdding(false);
    setAddValue('');
  }

  function startEdit() {
    if (selected === null) return;
    setEditValue(items[selected]);
    setEditing(true);
  }

  function saveEdit() {
    if (selected === null) return;
    const v = editValue.trim();
    if (!v) return;
    const next = [...items];
    next[selected] = v;
    onChange(next);
    setEditing(false);
  }

  function cancelEdit() {
    setEditing(false);
  }

  function deleteSelected() {
    if (selected === null) return;
    onChange(items.filter((_, i) => i !== selected));
    setSelected(null);
    setEditing(false);
  }

  function commitAdd(value: string) {
    const v = value.trim();
    if (!v) return;
    const have = new Set(items.map(i => i.toLowerCase()));
    if (!have.has(v.toLowerCase())) {
      onChange([...items, v]);
    }
    setAddValue('');
    setHighlightIdx(0);
    addInputRef.current?.focus();
  }

  function openAdd() {
    setAdding(true);
    setSelected(null);
    setEditing(false);
  }

  function closeAdd() {
    setAdding(false);
    setAddValue('');
  }

  function handleAddKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIdx(i => Math.min(i + 1, Math.max(filteredSuggestions.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredSuggestions.length > 0 && highlightIdx < filteredSuggestions.length) {
        commitAdd(filteredSuggestions[highlightIdx]);
      } else {
        commitAdd(addValue);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeAdd();
    }
  }

  const fontCls = monospace ? 'font-mono' : '';

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {items.length === 0 && !adding && emptyHint && (
          <span className="text-xs text-muted italic">{emptyHint}</span>
        )}
        {items.map((item, idx) => (
          <button
            key={`${item}-${idx}`}
            type="button"
            onClick={() => selectChip(idx)}
            aria-pressed={selected === idx}
            className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs border transition-colors ${fontCls} ${
              selected === idx
                ? 'bg-gold-dark text-white border-ink'
                : 'bg-paper-3 text-ink-2 border-rule hover:bg-rule'
            }`}
          >
            {item}
          </button>
        ))}
        {!adding && (
          <button
            type="button"
            onClick={openAdd}
            className="inline-flex items-center px-2.5 py-1 rounded-full text-xs border border-dashed border-rule text-muted hover:border-muted hover:text-ink-2"
          >
            + Add
          </button>
        )}
      </div>

      {selected !== null && !editing && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted">Selected:</span>
          <span className={`text-ink-2 ${fontCls}`}>{items[selected]}</span>
          <button
            type="button"
            onClick={startEdit}
            className="px-2 py-1 rounded bg-paper-3 text-ink-2 hover:bg-rule"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={deleteSelected}
            className="px-2 py-1 rounded text-rust hover:bg-rust/5"
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="px-2 py-1 text-muted hover:text-ink-2"
          >
            Cancel
          </button>
        </div>
      )}

      {selected !== null && editing && (
        <div className="flex items-center gap-2">
          <input
            ref={editInputRef}
            type="text"
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); saveEdit(); }
              if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
            }}
            className={`bg-paper text-ink flex-grow max-w-xs px-2.5 py-1 border border-rule rounded text-xs focus:outline-none focus:border-ink ${fontCls}`}
          />
          <button
            type="button"
            onClick={saveEdit}
            disabled={!editValue.trim()}
            className="px-2 py-1 rounded bg-gold-dark text-white text-xs hover:bg-[#734f14] disabled:opacity-50"
          >
            Save
          </button>
          <button
            type="button"
            onClick={cancelEdit}
            className="px-2 py-1 text-xs text-muted hover:text-ink-2"
          >
            Cancel
          </button>
        </div>
      )}

      {adding && (
        <div className="relative max-w-xs">
          <div className="flex items-center gap-2">
            <input
              ref={addInputRef}
              type="text"
              value={addValue}
              onChange={e => { setAddValue(e.target.value); setHighlightIdx(0); }}
              onKeyDown={handleAddKeyDown}
              placeholder={addPlaceholder}
              className={`bg-paper text-ink flex-grow px-2.5 py-1 border border-rule rounded text-xs focus:outline-none focus:border-ink ${fontCls}`}
            />
            <button
              type="button"
              onClick={() => commitAdd(addValue)}
              disabled={!addValue.trim()}
              className="px-2 py-1 rounded bg-gold-dark text-white text-xs hover:bg-[#734f14] disabled:opacity-50"
            >
              Add
            </button>
            <button
              type="button"
              onClick={closeAdd}
              className="px-1.5 py-1 text-muted hover:text-ink-2 text-xs"
              title="Done adding"
            >
              Done
            </button>
          </div>
          {filteredSuggestions.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-paper-2 border border-rule rounded shadow-lg max-h-48 overflow-auto">
              {filteredSuggestions.map((s, i) => (
                <li key={s}>
                  <button
                    type="button"
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => commitAdd(s)}
                    className={`w-full text-left px-2.5 py-1.5 text-xs ${fontCls} ${
                      i === highlightIdx ? 'bg-paper-3 text-ink' : 'text-ink-2 hover:bg-paper'
                    }`}
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
