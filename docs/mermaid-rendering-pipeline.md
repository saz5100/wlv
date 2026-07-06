# Mermaid Rendering Pipeline — Post-Processing Reference

## Overview

The GCSE CS website uses `beautiful-mermaid` (Node.js) to render Mermaid diagram source to SVG, then applies a post-processing pipeline to enhance the output. The renderer lives at `app/mermaid-renderer/render.js` and is called from `app/mermaid_renderer.py`.

## Pipeline Steps (in order)

### 0. Spacing Config

Before rendering, `nodeSpacing: 60` and `rankSpacing: 80` are injected into the Mermaid source via `%%{init: ...}%%` directive. This gives comfortable spacing between nodes and ranks.

### 1. Strip Inline Width/Height

The SVG's inline `width` and `height` attributes are removed so CSS can control sizing responsively.

### 2. Replace Style Block

The auto-generated Mermaid `<style>` block is replaced with a custom one that uses CSS custom properties (`--bm-bg`, `--bm-fg`, etc.). This enables automatic light/dark theme switching — the page defines these variables for both themes, and the SVG inherits them.

**Style customisations:**
- Font: Inter (Google Fonts import)
- Edge stroke width: 2.5 (thicker arrows)
- Edge label font: 13px, weight 600
- Node label font: 14px, line-height 1.4

### 3. Remove Edge Label Backgrounds

Edge label `<rect>` backgrounds are stripped so labels appear on a transparent background (no black/white squares behind text).

### 4. Emoji DX Compensation

**Problem:** Emoji characters (🔧, 🖥️, 💾, etc.) on the left side of node labels have visual weight that makes the text look off-centre to the right.

**Solution:** For any node whose text content contains emoji characters (U+1F000+ or U+2600–U+27BF), a `dx="-2"` attribute is added to the `<text>` element. This shifts the **entire text block** (all lines) left by 2 SVG units, visually balancing the emoji's weight.

**Tuning history (Lesson 1 — Architecture of the CPU):**
| Value | Result |
|-------|--------|
| `dx="12"` | Too far right (wrong direction) |
| `dx="-12"` | Too far left |
| `dx="-8"` | Still too far left |
| `dx="-6"` | Closer but still off |
| `dx="-4"` | Nearly there |
| `dx="-2"` | ✅ **Perfect — locked in** |

**Key insight:** The emoji is on the **left** side, so the text needs to shift **left** (negative `dx`), not right.

### 5. Node Padding (12px)

**Problem:** Text inside node rects was cramped against the edges.

**Solution:** Each node's `<rect>` is expanded by 12px on all sides:
- Width increases by 24px (2 × 12px)
- Height increases by 24px (2 × 12px)
- X/Y shift by -12px (up-left) to keep the rect centred on the original position
- Rounded corners applied: `rx="10" ry="10"`

**Edge connection adjustment:** After expanding rects, edge `<polyline>` endpoints are recalculated:
- Start point Y → source node's new bottom edge (original Y + original H + 12px)
- End point Y → target node's new top edge (original Y - 12px)
- This ensures arrows connect to the padded rect boundaries, not the old positions

## Colour System

The renderer defines two colour palettes (dark/light) as fallback values in the SVG `<style>` block. The actual colours come from CSS custom properties set by the page:

| CSS Variable | Dark Fallback | Light Fallback |
|---|---|---|
| `--bg` | `#0f172a` | `#ffffff` |
| `--fg` | `#e2e8f0` | `#0f172a` |
| `--accent` | `#22d3ee` | `#0891b2` |
| `--line` | `#64748b` | `#64748b` |
| `--muted` | `#cbd5e1` | `#475569` |
| `--surface` | `#1e293b` | `#f8fafc` |
| `--border` | `#334155` | `#e2e8f0` |

## Key Files

| File | Purpose |
|---|---|
| `app/mermaid-renderer/render.js` | Node.js renderer + post-processing pipeline |
| `app/mermaid-renderer/package.json` | Dependencies (beautiful-mermaid) |
| `app/mermaid_renderer.py` | Python wrapper that calls render.js |
| `app/static/css/style.css` | Defines `--bm-*` CSS custom properties for both themes |

## Usage

```bash
# Pipe mermaid source
echo "graph TD; A-->B" | node render.js

# Or read from file
node render.js diagram.mmd
```

The Python wrapper (`mermaid_renderer.py`) handles calling this from the FastAPI app, passing the mermaid source and returning the processed SVG.
