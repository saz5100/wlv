# Lesson 1 — Architecture of the CPU: Configuration & Standards Reference

> **Purpose:** This document captures every CSS, layout, accessibility, and behavioural setting applied to Lesson 1 during the 2026-07-03 overhaul. These settings serve as the **canonical standard** for all other lessons and interactive widgets across the GCSE CS site.

---

## 1. Mermaid Diagram Standards

### 1.1 Sizing & Centring

```css
.lesson-content .mermaid-rendered svg {
  max-width: 700px !important;
  width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}
```

| Property | Value | Rationale |
|----------|-------|-----------|
| `max-width` | `700px` | Prevents diagrams from stretching beyond readable width; increased from 500px to improve text readability in TD chain diagrams |
| `width` | `100%` | Allows scaling down on mobile viewports |
| `display` | `block` | Required for `margin: 0 auto` centring to work |
| `margin` | `0 auto` | Centres the diagram horizontally in its container |

**⚠️ Important:** The `!important` flag is required because the mermaid renderer (`render.js`) injects an inline `style="height:auto"` on the `<svg>` element. Without `!important`, the inline style takes precedence over the CSS rule.

**⚠️ LR Conversion Risk:** Converting TD to LR can break the renderer — the `addNodePadding` function in `render.js` doesn't handle LR arrow syntax properly. Always test both directions before committing to LR. If LR breaks, restore TD immediately and clear the renderer cache.

### 1.2 Renderer Fix (render.js)

**File:** `app/mermaid-renderer/render.js` (line 152)

The renderer was injecting `style="max-width:100%;height:auto"` on every SVG, which overrode the CSS `max-width: 500px`. Fixed by removing `max-width:100%`:

```javascript
// Before (broken):
result = result.replace('<svg', '<svg width="100%" style="max-width:100%;height:auto"');

// After (fixed):
result = result.replace('<svg', '<svg width="100%" style="height:auto"');
```

### 1.3 Colour Scheme (Site-Wide Standard)

All mermaid diagrams should use these classDef colours for consistency:

| Class | Fill | Stroke | Used For |
|-------|------|--------|----------|
| `:::addr` | `#7c3aed` (purple) | `#6d28d9` | Address registers (PC, MAR) |
| `:::mem` | `#2563eb` (blue) | `#1d4ed8` | Memory (RAM) |
| `:::data` | `#16a34a` (green) | `#15803d` | Data registers (MDR, ACC) |
| `:::cir` | `#ea580c` (orange) | `#c2410c` | Current Instruction Register |
| `:::cu` | `#d97706` (amber) | `#b45309` | Control Unit |
| `:::alu` | `#dc2626` (red) | `#b91c1c` | Arithmetic Logic Unit |

**Key rule:** Each component type must have a **unique colour**. CIR and CU were previously both amber — CIR was changed to orange to distinguish them.

### 1.4 Layout Direction

- **TD (top-down):** Use for hierarchical/chain diagrams (fetch-execute cycle, sorting algorithms)
- **LR (left-right):** Use for comparison/flow diagrams (embedded vs general-purpose, linear search)

**Mobile note:** TD diagrams can be very tall (~1,800px). Consider splitting into multiple diagrams or using `max-height` with `overflow-y: auto` for very long chains.

---

## 2. Interactive Widget Standards

### 2.1 Widget Container

```css
.wc-widget {
  background: var(--c-surface);
  border-radius: var(--r-xl);
  padding: 1.75rem 1.5rem;
  border: 1px solid var(--c-border);
  max-width: 920px;
  width: 100%;
  margin: 1.5rem auto;
  color: var(--c-text);
  font-family: inherit;
  box-sizing: border-box;
  min-height: 400px;
}
```

All interactive widgets should use CSS custom properties (`--c-surface`, `--c-border`, `--c-text`, etc.) for theme consistency.

### 2.2 Description Box — Minimum Height (Critical)

```css
.wc-desc {
  min-height: 15rem;  /* 240px — prevents button jumping */
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
```

| Property | Value | Rationale |
|----------|-------|-----------|
| `min-height` | `15rem` (240px) | Prevents the Back/Play/Forward buttons from jumping when step text varies in length |
| `overflow-y` | `auto` | Allows longer step descriptions to scroll within the fixed-height box |
| `justify-content` | `center` | Vertically centres the step text within the box |

**⚠️ This was originally `height: 15rem` as an inline style, then incorrectly changed to `min-height: 8rem` during refactoring. The original 15rem value was restored after checking git history.**

### 2.3 Step Dots

```css
.wc-dot {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 2px solid var(--c-border);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}
```

**Mobile override (≤768px):**
```css
.wc-dot {
  width: 40px;
  height: 40px;
  font-size: 0.85rem;
}
```

Apple HIG minimum tap target is 44×44px — 40×40px is a compromise. Consider 44×44px if feasible.

### 2.4 Step Text Sizing

```css
.wc-step-title { font-size: 1rem; font-weight: 700; }    /* Desktop */
.wc-step-text  { font-size: 0.9rem; line-height: 1.6; }   /* Desktop */

/* Mobile (≤768px) */
.wc-step-title { font-size: 1rem; }
.wc-step-text  { font-size: 0.9rem; }
```

### 2.5 Control Buttons

```css
.wc-btn {
  font-size: 0.8rem;
  padding: 0.4rem 0.6rem;
  border-radius: 0.5rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.wc-btn-primary {
  background: #3b82f6;
  color: #ffffff;
  padding: 0.4rem 0.8rem;
  font-weight: 700;
}

.wc-btn-danger {
  background: #ef4444;
  color: #ffffff;
  padding: 0.4rem 0.8rem;
  font-weight: 700;
}
```

**Mobile (≤768px):**
```css
.wc-btn { font-size: 0.9rem; padding: 0.5rem 0.75rem; }
```

### 2.6 Speed Controls

```css
.wc-speed-btn {
  font-size: 0.75rem;
  padding: 4px 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  font-weight: 600;
  cursor: pointer;
}

.wc-speed-btn.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
  font-weight: 700;
}
```

**Mobile (≤768px):**
```css
.wc-speed-btn { font-size: 0.85rem; padding: 6px 16px; }
```

---

## 3. Interactive Labelling Diagram Standards

### 3.1 Container

```css
.match-section { margin: 1.5rem 0; }
.match-section h2 { font-size: 1.2rem; font-weight: 700; color: var(--c-heading); margin-bottom: 0.5rem; }
.match-desc { font-size: 0.8125rem; color: var(--c-text-secondary); margin-bottom: 0.75rem; }
.match-diagram { text-align: center; background: #0d1225; border: 1px solid rgba(34,211,238,0.1); border-radius: var(--r-lg); padding: 1.25rem; overflow-x: auto; margin-bottom: 1rem; }
.match-diagram svg { max-width: 500px; width: 100%; }
.match-clickable { cursor: pointer; }
.match-status { font-size: 0.8125rem; }
```

**Mobile (≤768px):**
```css
.match-desc { font-size: 0.9rem; }
.match-status { font-size: 0.9rem; }
```

### 3.2 SVG Text Sizing

All SVG `<text>` elements in labelling diagrams should use **absolute font-size values** (not CSS-dependent) since they're inside SVGs:

| Element | Desktop | Mobile |
|---------|---------|--------|
| Main title (e.g. "CPU") | 16px | 16px |
| Clickable labels ("❓ Click to label") | **14px** | 14px |
| Hint text ("Decodes instructions") | **12px** | 12px |
| Status text | CSS class | CSS class |
| "Buses → Memory" | **12px** | 12px |
| Stage labels ("Stage 1") | **12px** | 12px |

**⚠️ These are hardcoded in the SVG — CSS cannot override them.** They must be set directly in the `<text font-size="...">` attribute.

### 3.3 "Buses → Memory" Positioning

The "Buses → Memory" label and its dashed line must be positioned **below all clickable boxes**, not inside any of them:

```html
<!-- Cache box bottom: y=250 -->
<line x1="50" y1="300" x2="350" y2="300" stroke="#64748b" stroke-width="2" stroke-dasharray="4,3"/>
<line x1="200" y1="250" x2="200" y2="300" stroke="#64748b" stroke-width="1.5" stroke-dasharray="3,2"/>
<text x="200" y="288" text-anchor="middle" fill="#94a3b8" font-size="12">Buses → Memory</text>
```

| Element | Y-position | Notes |
|---------|------------|-------|
| Cache box bottom | 250 | Bottom of the lowest clickable area |
| Connector line | 250 → 300 | Vertical dashed line from Cache to dashed rule |
| Label text | 288 | Centred between Cache bottom and dashed rule |
| Dashed rule | 300 | Horizontal line spanning all 4 boxes (x: 50→350) |
| Status text | 320 | Below everything |

**Colour:** `#94a3b8` (was `#64748b` — changed for better contrast on dark background)

---

## 4. Mobile Responsiveness Standards

### 4.1 Breakpoint

```css
@media (max-width: 768px) { ... }
```

**Changed from `500px` to `768px`** because:
- iPhone SE is 375px (breakpoint fires ✅)
- iPad portrait is 768px (breakpoint fires ✅)
- Compact desktop windows (500-768px) were previously missed ❌

### 4.2 Font Size Bumps at ≤768px

| Element | Desktop | Mobile |
|---------|---------|--------|
| `.lesson-content` base | 14px | **17px** |
| h2 | 24px | **21px** |
| h3 | 20px | **18px** |
| h4 | 18px | **16px** |
| Table cells | 13px | **14px** |
| `.wc-step-text` | 0.8rem | **0.9rem** |
| `.wc-step-title` | 0.85rem | **1rem** |
| `.wc-dot` | 0.75rem / 34px | **0.85rem / 40px** |
| `.wc-btn` | 0.8rem | **0.9rem** |
| `.wc-speed-btn` | 0.75rem | **0.85rem** |
| `.wc-cpu-label` | 0.7rem | **0.8rem** |
| `.wc-reg-val` | 0.7rem | **0.8rem** |
| `.wc-ram-cell` | 0.75rem | **0.85rem** |
| `.match-desc` | 0.8125rem | **0.9rem** |
| `.match-status` | 0.8125rem | **0.9rem** |

### 4.3 Table Mobile Layout

```css
@media (max-width: 768px) {
  .lesson-content table,
  .lesson-content table tbody,
  .lesson-content table tr,
  .lesson-content table th,
  .lesson-content table td { display: block; }
  .lesson-content table thead { display: none; }
  .lesson-content table tr {
    padding: 10px;
    margin-bottom: 8px;
    border-radius: 10px;
    outline: 2px solid rgba(34,211,238,0.15);
  }
  .lesson-content table td {
    padding: 4px 0;
    border-bottom: none !important;
    word-break: break-word;
  }
}
```

Requires `data-label` attributes on each `<td>` for the card-style layout to show column headers.

---

## 4.5 Callout Box Sizing (key-term & exam-tip)

```css
.key-term {
  font-size: 12px;
  line-height: 1.6;
  background: rgba(8,41,73,0.7);
  border-left: 4px solid var(--c-accent);
  border-radius: 0 10px 10px 0;
  padding: 14px 18px;
  margin: 20px 0;
}
.light-theme .key-term { background: rgba(236,254,255,0.7); }

.exam-tip {
  font-size: 12px;
  line-height: 1.6;
  background: rgba(73,8,8,0.4);
  border-left: 4px solid var(--c-rose);
  border-radius: 0 10px 10px 0;
  padding: 14px 18px;
  margin: 20px 0;
}
.light-theme .exam-tip { background: rgba(254,242,242,0.7); }
```

| Property | Value | Rationale |
|----------|-------|-----------|
| `font-size` | `12px` | Compact enough to not disrupt content flow, large enough to read on mobile |
| `border-left` | `4px` accent/rose | Colour-coded by type — cyan for insights, rose for exam warnings |
| `padding` | `14px 18px` | Generous internal spacing for readability |
| `margin` | `20px 0` | Clear separation from surrounding content |

**⚠️ These are set in `style.css` (not inline) and apply site-wide to all lessons.**

---

## 5. Accessibility Standards

### 5.1 Focus Styles

```css
:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 2px;
}
:focus:not(:focus-visible) {
  outline: none;
}
```

### 5.2 Screen Reader Utility

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

### 5.3 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

### 5.4 ARIA Landmarks

| Element | Attribute | Value |
|---------|-----------|-------|
| `<nav>` (main) | `aria-label` | `"Main navigation"` |
| `<nav>` (mobile) | `aria-label` | `"Mobile navigation menu"` |
| `<main>` | `role` | `"main"` |
| `<footer>` | `role` | `"contentinfo"` |
| Dropdowns | `aria-label` | `"Learn submenu"` / `"Practise submenu"` |
| Theme toggle | `aria-label` | `"Toggle theme"` |

---

## 6. Theme Meta Tags

```html
<meta name="theme-color" content="#080b14" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
```

---

## 7. CSS Versioning

The CSS cache-buster in `base.html` should be bumped on every deployment:

```html
<link rel="stylesheet" href="/static/css/style.css?v=67">
```

**Current version:** `v=68` (as of 2026-07-04)

### Version History

| Version | Date | Changes |
|---------|------|---------|
| v=52 | 2026-07-03 | Initial state before overhaul |
| v=53–59 | 2026-07-03 | CSS syntax fix, focus styles, sr-only, ARIA, reduced-motion, theme-color |
| v=60 | 2026-07-03 | Widget CSS classes added for L3-L21 |
| v=61 | 2026-07-03 | Widget description box min-height: 10rem |
| v=62 | 2026-07-03 | Widget description box min-height: 15rem (restored) |
| v=63 | 2026-07-03 | Labelling diagram CSS classes, Buses→Memory centred |
| v=64 | 2026-07-03 | Buses→Memory colour #94a3b8, Repeats label colour fix |
| v=65 | 2026-07-03 | Mobile text size bumps (widget, match-desc) |
| v=66 | 2026-07-03 | SVG text sizes bumped (10px→12px, 13px→14px) |
| v=67 | 2026-07-03 | Breakpoint widened 500px→768px, table cells 14px, widget internal labels |
| v=68 | 2026-07-04 | Mermaid max-width 500px→700px, quiz nav consistency (Style A disabled), Buses→Memory y=288/300 |
| v=69 | 2026-07-04 | Widget Back/Forward buttons now use Style A disabled (consistent with quiz nav) |
| v=70 | 2026-07-04 | Mermaid max-width 500px→700px |
| v=71 | 2026-07-04 | Mermaid container max-height 500px with overflow-y |
| v=72 | 2026-07-04 | Widget padding 1rem→0.75rem, min-height 350px→300px, diagram 220px→120px |
| v=73 | 2026-07-04 | Widget desc box 6rem, step-text 0.75rem, header h2 1.1rem, step-label 0.8rem |
| v=74 | 2026-07-04 | Mermaid max-height 500px→900px |
| v=75 | 2026-07-04 | key-term 12px, exam-tip 12px, widget sizing tightened |
| v=76 | 2026-07-04 | Widget flow 170px→100px, CPU padding/width reduced, diagram padding 1.25rem→0.5rem |
| v=77 | 2026-07-04 | Widget reg padding 8px→4px, RAM padding/width reduced, arrow 2rem→1.25rem, gaps tightened |
| v=78 | 2026-07-04 | Widget stepper gap 8px→5px, dots 34px→26px, desc padding 1rem→0.5rem, btn 0.8rem→0.7rem |
| v=79 | 2026-07-04 | Added `.wc-btn:disabled` style, removed transitions from reg/part/ram-cell/arrow (fix jitter) |
| v=80 | 2026-07-04 | Flow gap 4px→12px, flex-wrap nowrap (fixed gap between CPU & RAM) |
| v=81 | 2026-07-04 | CPU/RAM fixed 120px width with flex-shrink:0 |
| v=82 | 2026-07-04 | Arrow area fixed 60px width with flex-shrink:0 (fixed gap between shapes) |

---

## 8. Deployment Commands

```bash
# Build
cd /d/Users/shaza/Documents/Optimus/gcse-ocr-computer-science
docker compose build app

# Recreate and start
docker compose stop app && docker compose rm -f app && docker compose create app && docker compose start app

# Clear mermaid renderer cache (after mermaid source changes)
docker compose exec app python -c "from mermaid_renderer import clear_cache; clear_cache(); print('Cache cleared')"

# Run Python inside container
docker compose exec app python -c "your code here"
```

---

## 11. Quiz Navigation Standards

### 11.1 Boundary Button Behaviour

Both Previous and Next buttons use **Style A — Disabled (greyed out)** at boundaries:

```css
.quiz-nav-btn:disabled { opacity: 0.3; cursor: default; }
```

| Position | Previous Button | Next Button |
|----------|---------------|-------------|
| Q1 (start) | `disabled` — greyed out, visible | Active |
| Q2–Q7 | Active | Active |
| Q8 (end) | Active | `disabled` — greyed out, visible |

**JS logic (lesson.html line 1394-1395):**
```javascript
document.getElementById('quizPrevBtn').disabled = (idx === 0);
document.getElementById('quizNextBtn').disabled = (idx === tabs.length - 1);
```

**⚠️ Do NOT use `display: none` to hide boundary buttons** — it causes layout shifts and inconsistent UX. The Submit button still appears on the last question via `display` toggle.

---

## 12. Common Pitfalls (Extended)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Subagent strips JS from widget | Widget renders but doesn't respond to clicks | Always verify `<script>` tag is present after widget refactoring |
| Subagent leaves duplicate `class` attrs | Widget elements don't render (browser ignores invalid HTML) | Run deduplication: `content.replace(/class="([^"]+)" class="\1"/g, 'class="$1"')` |
| Mermaid renderer cache stale | Old diagram shows after source change | Clear cache: `clear_cache()` |
| Inline `max-width:100%` on SVG | CSS `max-width` is overridden | Fix in `render.js` — remove `max-width:100%` from inline style |
| Breakpoint too narrow (500px) | Mobile fixes don't activate on tablets/compact desktop | Use `768px` breakpoint instead |
| SVG text too small (10px) | Unreadable on phone | Hardcode `font-size="12"` or `font-size="14"` in SVG — CSS can't override |
| **LR conversion breaks renderer** | Mermaid diagram disappears (0 SVGs) | Restore TD in DB, clear renderer cache, increase max-width instead |
| **Quiz nav inconsistency** | Previous disabled at start, Next vanishes at end | Remove `display: none` line, use `disabled` attribute on both |

---

## 10. Audit Checklist for New Lessons

When creating or fixing a lesson, check:

- [ ] Mermaid diagram capped at 500px, centred
- [ ] Mermaid colours follow the standard palette (addr=purple, mem=blue, data=green, etc.)
- [ ] Widget has `min-height: 15rem` on description box
- [ ] Widget step dots are 34×34px (40×40px on mobile)
- [ ] All SVG text is at least 12px (14px for labels)
- [ ] "Buses → Memory" style labels are below all clickable boxes
- [ ] Mobile breakpoint is 768px (not 500px)
- [ ] Table cells have `data-label` attributes
- [ ] `:focus-visible` styles are applied
- [ ] ARIA landmarks are present on nav, main, footer
- [ ] `theme-color` meta tags are present
- [ ] `prefers-reduced-motion` media query is present
- [ ] CSS cache-buster is bumped
- [ ] Mermaid renderer cache is cleared after diagram changes
- [ ] No duplicate `class` attributes in widget HTML
- [ ] Widget JS is present and functional
