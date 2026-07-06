#!/usr/bin/env node
import { renderMermaidSVG } from "beautiful-mermaid";
import { readFileSync } from "fs";

const DARK = {
  bg:"#0f172a", fg:"#e2e8f0", accent:"#22d3ee", line:"#64748b",
  muted:"#cbd5e1", surface:"#1e293b", border:"#334155",
};

const LIGHT = {
  bg:"#ffffff", fg:"#0f172a", accent:"#0891b2", line:"#64748b",
  muted:"#475569", surface:"#f8fafc", border:"#e2e8f0",
};

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on("data", (c) => chunks.push(c));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString()));
    process.stdin.on("error", reject);
  });
}

function buildStyleBlock(dark, light) {
  return `<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  text { font-family: 'Inter', system-ui, sans-serif; }
  svg {
    --bg: var(--bm-bg, ${dark.bg});
    --fg: var(--bm-fg, ${dark.fg});
    --accent: var(--bm-accent, ${dark.accent});
    --line: var(--bm-line, ${dark.line});
    --muted: var(--bm-muted, ${dark.muted});
    --surface: var(--bm-surface, ${dark.surface});
    --border: var(--bm-border, ${dark.border});
    --_text: var(--bm-fg, ${dark.fg});
    --_text-sec: var(--bm-muted, ${dark.muted});
    --_text-muted: var(--bm-muted, ${dark.muted});
    --_text-faint: #334155;
    --_line: var(--bm-line, ${dark.line});
    --_arrow: #cbd5e1;
    --_node-fill: var(--bm-surface, ${dark.surface});
    --_node-stroke: var(--bm-border, ${dark.border});
    --_group-fill: var(--bm-bg, ${dark.bg});
    --_group-hdr: #1e293b;
    --_inner-stroke: #475569;
    --_key-badge: #1e293b;
  }
  .edgePath .path { stroke-width: 1.5; }
  .edgeLabel { font-size: 10px; font-weight: 400; }
  .node .label { font-size: 11px; line-height: 1.3; }
</style>`;
}

function hasEmoji(text) {
  for (let i = 0; i < text.length; i++) {
    const cp = text.codePointAt(i);
    if (cp && cp > 0x1F000) return true;
    if (cp && cp >= 0x2600 && cp <= 0x27BF) return true;
  }
  return false;
}

function addEmojiDx(svg) {
  return svg.replace(/<g class="node"[^>]*>[\s\S]*?<\/g>/g, function(node) {
    const textContent = node.replace(/<[^>]+>/g, '');
    if (!hasEmoji(textContent)) return node;
    const textMatch = node.match(/(<text[^>]*)(>)/);
    if (textMatch && !/dx="/.test(textMatch[1])) {
      return node.replace(/(<text[^>]*)>/, '$1 dx="-1">');
    }
    return node;
  });
}

function addNodePadding(svg, pad) {
  const nodeRects = {};

  svg = svg.replace(/<g class="node"[^>]*>[\s\S]*?<\/g>/g, function(node) {
    const idMatch = node.match(/data-id="(\w+)"/);
    const id = idMatch ? idMatch[1] : null;
    if (!id) return node;

    const rectMatch = node.match(/<rect([^>]*)>/);
    if (!rectMatch) return node;

    const attrs = rectMatch[1];
    let x = parseFloat((/x="([\d.]+)"/.exec(attrs) || [])[1]);
    let y = parseFloat((/y="([\d.]+)"/.exec(attrs) || [])[1]);
    let w = parseFloat((/width="([\d.]+)"/.exec(attrs) || [])[1]);
    let h = parseFloat((/height="([\d.]+)"/.exec(attrs) || [])[1]);
    if (isNaN(x) || isNaN(y) || isNaN(w) || isNaN(h)) return node;

    nodeRects[id] = { x, y, w, h };

    const newRect = `<rect x="${(x - pad).toFixed(2)}" y="${(y - pad).toFixed(2)}" width="${(w + 2 * pad).toFixed(2)}" height="${(h + 2 * pad).toFixed(2)}" rx="6" ry="6" fill="${(attrs.match(/fill="([^"]+)"/) || [])[1] || 'var(--_node-fill)'}" stroke="${(attrs.match(/stroke="([^"]+)"/) || [])[1] || 'var(--_node-stroke)'}" stroke-width="${(attrs.match(/stroke-width="([\d.]+)"/) || [])[1] || '0.5'}" />`;
    return node.replace(/<rect[^>]*\/>/, newRect);
  });

  svg = svg.replace(/<polyline class="edge"[^>]*\/>/g, function(edge) {
    const from = edge.match(/data-from="(\w+)"/);
    const to = edge.match(/data-to="(\w+)"/);
    if (!from || !to) return edge;

    const fromRect = nodeRects[from[1]];
    const toRect = nodeRects[to[1]];
    if (!fromRect || !toRect) return edge;

    const fromBottom = fromRect.y + fromRect.h + pad;
    const toTop = toRect.y - pad;

    const ptsMatch = edge.match(/points="([^"]+)"/);
    if (!ptsMatch) return edge;

    const pts = ptsMatch[1].split(' ');
    if (pts.length < 2) return edge;

    const first = pts[0].split(',');
    const last = pts[pts.length - 1].split(',');

    first[1] = fromBottom.toFixed(1);
    last[1] = toTop.toFixed(1);

    pts[0] = first.join(',');
    pts[pts.length - 1] = last.join(',');

    return edge.replace(/points="[^"]+"/, `points="${pts.join(' ')}"`);
  });

  return svg;
}

async function main() {
  const source = await readStdin().catch(() => {
    const f = process.argv[2];
    if (f && !f.startsWith("--")) return readFileSync(f, "utf-8");
    return "";
  });
  if (!source.trim()) { console.error("No source"); process.exit(1); }

  const spacedSource = `%%{init: {'nodeSpacing': 50, 'rankSpacing': 50}}%%\n${source}`;

  let svg = renderMermaidSVG(spacedSource, {
    bg: "var(--bg)", fg: "var(--fg)", accent: "var(--accent)",
    line: "var(--line)", muted: "var(--muted)", surface: "var(--surface)",
    border: "var(--border)", transparent: true,
  });

  svg = svg.replace(/(<svg[^>]*>)/, function(m) {
    let result = m.replace(/\s(width|height)="[^"]*"/g, '');
    if (!/width="100%"/.test(result)) {
      result = result.replace('<svg', '<svg width="100%" style="height:auto"');
    }
    return result;
  });
  svg = svg.replace(/<style>[\s\S]*?<\/style>/, buildStyleBlock(DARK, LIGHT));

  // Remove edge label background rects
  svg = svg.replace(/<g class="edge-label"[^>]*>[\s\S]*?<\/g>/g, function(match) {
    return match.replace(/<rect[^>]*\/>\s*/g, '');
  });

  // Position edge labels to the right of vertical lines
  svg = svg.replace(/(<text[^>]*font-size="11"[^>]*)(>)/g, function(m, pre, post) {
    let result = pre;
    result = result.replace('text-anchor="middle"', 'text-anchor="start"');
    if (!/dx="/.test(result)) {
      result += ' dx="6"';
    }
    return result + post;
  });
  svg = svg.replace(/(<text[^>]*font-size="11"[^>]*>[\s\S]*?<\/text>)/g, function(textBlock) {
    return textBlock.replace(/(<tspan[^>]*)(>)/g, function(m, pre, post) {
      if (!/dx="/.test(pre)) {
        return pre + ' dx="6"' + post;
      }
      return m;
    });
  });

  // Emoji dx compensation
  svg = addEmojiDx(svg);

  // Add 8px padding inside node rects + update edge connections
  svg = addNodePadding(svg, 8);

  process.stdout.write(svg);
}
main();
