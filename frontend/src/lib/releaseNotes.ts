/** Release notes are the CHANGELOG's Markdown: headings, (nested) bullets and paragraphs, hard-wrapped at ~120
 * characters. Only that small subset is read; everything else is shown as text. */

export type NotesBlock =
  | { kind: "heading"; text: string }
  | { kind: "item"; level: number; text: string }
  | { kind: "paragraph"; text: string };

export type InlinePart = { text: string; bold?: boolean; code?: boolean };

const HEADING = /^#{1,6}\s+(.*)$/;
const ITEM = /^(\s*)[-*]\s+(.*)$/;

/** Blocks of the notes; a wrapped line continues the block above it. */
export function parseNotes(notes: string): NotesBlock[] {
  const blocks: NotesBlock[] = [];
  let open: NotesBlock | null = null;
  for (const raw of notes.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      open = null;
      continue;
    }
    const heading = HEADING.exec(line);
    const item = ITEM.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", text: heading[1] ?? "" });
      open = null;
    } else if (item) {
      const indent = item[1] ?? "";
      const block: NotesBlock = { kind: "item", level: Math.min(2, Math.floor(indent.length / 2)), text: item[2] ?? "" };
      blocks.push(block);
      open = block;
    } else if (open) {
      open.text += ` ${line.trim()}`;
    } else {
      open = { kind: "paragraph", text: line.trim() };
      blocks.push(open);
    }
  }
  return blocks;
}

/** **bold** and `code` inside a block. */
export function parseInline(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) });
    parts.push(m[1] !== undefined ? { text: m[1], bold: true } : { text: m[2] ?? "", code: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
