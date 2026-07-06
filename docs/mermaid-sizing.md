# Mermaid Diagram Sizing

## Approach: Source-Level Parameters (No CSS Transforms)

Mermaid diagrams are sized entirely via **source-level parameters** in `render.js` — no CSS `<g transform>`, no viewBox manipulation, no media-query container constraints.

## How It Works

### 1. Init Directive (render.js line 141)

```js
const spacedSource = `%%{init: {'nodeSpacing': 50, 'rankSpacing': 50}}%%\n${source}`;
```

- **`nodeSpacing: 50`** — horizontal gap between nodes (default: 100)
- **`rankSpacing: 50`** — vertical gap between ranks (default: 80)

### 2. Style Block (render.js lines 24–53)

Generated inline `<style>` inside the SVG:

| CSS Rule | Value | Purpose |
|----------|-------|---------|
| `.edgePath .path` | `stroke-width: 1.5` | Thinner edge lines |
| `.edgeLabel` | `font-size: 10px; font-weight: 600` | Compact edge labels |
| `.node .label` | `font-size: 11px; line-height: 1.3` | Compact node labels |

### 3. Node Padding (render.js line 185)

```js
svg = addNodePadding(svg, 8);
```

- **`pad: 8`** — 8px padding inside each node rect (default: 12)
- Also updates edge connection points to match the new rect boundaries

### 4. Edge Label Positioning (render.js lines 163–179)

- Edge labels with `font-size="11"` get `text-anchor="start"` + `dx="6"` so they sit to the right of vertical lines
- `<tspan>` elements inherit the same `dx="6"` for consistent wrapping

### 5. Emoji Compensation (render.js line 182)

- Nodes containing emoji get `dx="-1"` to centre the text properly

### 6. SVG Container (render.js lines 149–155)

- `width="100%"` with `style="max-width:100%;height:auto"` — SVG fills its container
- No fixed width/height attributes

### 7. CSS Container (lesson.html)

```css
.lesson-content .mermaid-rendered {
  margin: 20px auto;
  overflow-x: auto;
  max-width: 100%;
  display: flex;
  justify-content: center;
}
```

- **No media queries** — the diagram is always `max-width: 100%` of its container
- The mermaid source parameters handle compactness at all viewport sizes

## Parameter Reference

| File | Line | Parameter | Value | Effect |
|------|------|-----------|-------|--------|
| `render.js` | 141 | `nodeSpacing` | 50 | Horizontal node gap |
| `render.js` | 141 | `rankSpacing` | 50 | Vertical rank gap |
| `render.js` | 49 | `.edgePath .path` stroke-width | 1.5 | Edge line thickness |
| `render.js` | 50 | `.edgeLabel` font-size | 10px | Edge label text size |
| `render.js` | 51 | `.node .label` font-size | 11px | Node label text size |
| `render.js` | 96 | `rx`/`ry` | 6px | Node corner radius |
| `render.js` | 96 | `stroke-width` | 0.5 | Node border thickness |
| `render.js` | 185 | `addNodePadding` pad | 8px | Internal node padding |
| `render.js` | 168 | edge label `dx` | 6px | Rightward offset from line |
| `render.js` | 70 | emoji `dx` | -1 | Emoji centering offset |

## Tuning Guide

To make diagrams **smaller**:
- Decrease `nodeSpacing` and `rankSpacing` (line 141)
- Decrease font sizes in `buildStyleBlock` (lines 50–51)
- Decrease `pad` in `addNodePadding` (line 185)

To make diagrams **larger**:
- Increase the above values
