# Glassmorphism Redesign — Cycle 2: Component Layer Design

**Date:** 2026-07-06
**Scope:** `dashboard.html` — CSS + JS chart functions only
**Depends on:** Cycle 1 foundation (tokens, sidebar, animations, toast) — commit `45c055a`
**Goal:** Adapt all existing components to the dark glassmorphism theme by replacing hardcoded light values and updating Chart.js configuration.

---

## Context

Cycle 1 established the token system and shell. The backward-compat aliases (`--bg-card`, `--border-color`, etc.) mean token-using CSS already renders correctly on dark. The remaining issues are:

1. ~12 component rules with hardcoded light hex values (`#f8fafc`, `#f1f5f9`, `#ffffff`, `#e2e8f0`, `#cbd5e1`)
2. Chart.js grid/tick/tooltip/legend colors tuned for a light canvas
3. Missing `backdrop-filter` on card surfaces (they use the glass token for background but don't blur)

No new components, no layout changes, no JS logic changes beyond chart color values.

---

## Section 1: Glass Surfaces

### Card surface upgrade

Add `backdrop-filter: var(--blur-sm); -webkit-backdrop-filter: var(--blur-sm);` to:
- `.hud-card`
- `.panel-card`
- `.draft-card`
- `.queue-item`
- `.timeline-card`
- `.analytics-stat-chip`

These elements already use `--bg-card` (aliased to `var(--glass-2)`) and `--border-color` (aliased to `var(--glass-border)`), so the glass surface tint is already correct — they just need the blur activated.

### Hardcoded light background replacements

| Selector | Property | Old value | New value |
|---|---|---|---|
| `.draft-meta-chip` | `background` | `#f1f5f9` | `var(--glass-1)` |
| `.draft-content` | `background` | `#f8fafc` | `var(--glass-1)` |
| `.draft-media-box` | `background` | `#f8fafc` | `var(--glass-1)` |
| `.event-details-formatted` | `background` | `#f8fafc` | `var(--glass-1)` |
| `.event-code` | `background` | `#f1f5f9` | `var(--glass-2)` |

### Analytics stat chip accent direction

Change from top border to left border to match the sidebar nav active indicator style:

```css
/* Old */
.analytics-stat-chip.accent-orange { border-top: 4px solid var(--primary); }
.analytics-stat-chip.accent-amber  { border-top: 4px solid var(--warning); }
.analytics-stat-chip.accent-green  { border-top: 4px solid var(--success); }
.analytics-stat-chip.accent-neutral { border-top: 4px solid var(--text-secondary); }

/* New */
.analytics-stat-chip.accent-orange  { border-left: 4px solid var(--primary); }
.analytics-stat-chip.accent-amber   { border-left: 4px solid var(--amber); }
.analytics-stat-chip.accent-green   { border-left: 4px solid var(--emerald); }
.analytics-stat-chip.accent-neutral { border-left: 4px solid var(--text-muted); }
```

### Timeline source badge colors

Current alpha of `0.08` is invisible on dark. Bump alpha to `0.18` and lighten text to pastel equivalents readable on dark:

```css
/* New */
.timeline-source.git      { background: rgba(99, 102, 241, 0.18); color: #a5b4fc; }
.timeline-source.note     { background: rgba(168, 85, 247, 0.18); color: #d8b4fe; }
.timeline-source.browser  { background: rgba(249, 115, 22, 0.18); color: #fdba74; }
.timeline-source.file     { background: rgba(16, 185, 129, 0.18); color: #6ee7b7; }
.timeline-source.calendar { background: rgba(239, 68, 68, 0.18);  color: #fca5a5; }
```

### Status badge text colors

Brighten to remain legible on dark surfaces:

```css
/* New */
.status-badge.pending_review { background: var(--warning-light); color: #fbbf24; }
.status-badge.approved       { background: var(--success-light);  color: #34d399; }
.status-badge.published      { background: var(--primary-light);  color: #a5b4fc; }
.status-badge.rejected       { background: var(--danger-light);   color: #f87171; }
```

---

## Section 2: Interactive Components

### Chat sidebar

```css
.chat-sidebar {
    background: var(--glass-1);
    backdrop-filter: var(--blur-sm);
    -webkit-backdrop-filter: var(--blur-sm);
    border-right: 1px solid var(--glass-border);
    /* remove: background: #f8fafc */
}
```

### Session list items

```css
.session-item:hover  { background: var(--glass-2); }
.session-item.active { background: var(--glass-3); border-color: var(--glass-border); }
```

Remove the hardcoded `background: #ffffff` and `background: #e2e8f0`.

### Scrollbars (chat)

```css
.chat-session-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); }
.chat-messages::-webkit-scrollbar-thumb     { background-color: rgba(255,255,255,0.15); }
```

### Chat agent bubble

```css
.chat-bubble-container.agent {
    background: var(--glass-2);
    color: var(--text-primary);
    /* remove: background: #f1f5f9 */
}
```

### Filter select

```css
.filter-select {
    background: var(--glass-2);
    color: var(--text-primary);
    border: 1px solid var(--glass-border);
    color-scheme: dark;
    /* keep: existing padding, radius, font, transition */
}
.filter-select option {
    background: #1a1a2e;
    color: var(--text-primary);
}
```

### Confirm-no button

```css
.confirm-no { background: var(--glass-2); color: var(--text-secondary); }
```

### Global content-area scrollbar

Add to stylesheet (applies to the main scrollable area):

```css
.content-area::-webkit-scrollbar       { width: 5px; }
.content-area::-webkit-scrollbar-track { background: transparent; }
.content-area::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
```

---

## Section 3: Charts

Both `buildOverviewChart()` and `buildPerformanceChart()` update the same set of Chart.js options:

### Color constants (apply to both charts)

```javascript
const CHART_DARK = {
    grid:         'rgba(255,255,255,0.06)',
    ticks:        'rgba(255,255,255,0.50)',
    legend:       'rgba(255,255,255,0.60)',
    tooltipBg:    'rgba(15,15,25,0.92)',
    tooltipBorder:'rgba(255,255,255,0.10)',
    tooltipTitle: 'rgba(255,255,255,0.95)',
    tooltipBody:  'rgba(255,255,255,0.65)',
};
```

Define this object once, at the top of each function (it's small and local — no module-level variable needed).

### Scale options (both charts)

```javascript
scales: {
    y: {
        grid:  { color: CHART_DARK.grid },
        ticks: { color: CHART_DARK.ticks, font: { family: 'Inter', size: 11 } }
    },
    x: {
        grid:  { display: false },
        ticks: { color: CHART_DARK.ticks, font: { family: 'Inter', size: 11 } }
    }
}
```

### Plugin options (both charts)

```javascript
plugins: {
    legend: {
        labels: {
            color:    CHART_DARK.legend,
            boxWidth: 10,
            padding:  16,
            font:     { family: 'Inter', size: 11 }
        }
    },
    tooltip: {
        backgroundColor: CHART_DARK.tooltipBg,
        borderColor:     CHART_DARK.tooltipBorder,
        borderWidth:     1,
        titleColor:      CHART_DARK.tooltipTitle,
        bodyColor:       CHART_DARK.tooltipBody,
        padding:         10,
        cornerRadius:    6,
        titleFont:       { family: 'Inter' },
        bodyFont:        { family: 'Inter' }
    }
}
```

### Overview chart dataset colors

The overview bar chart currently uses hardcoded hex dataset colors. Update to be readable on dark canvas:

- Primary dataset: keep `var(--primary)` / `rgba(99,102,241,0.2)` — already dark-friendly
- If the chart uses a hardcoded `#6366f1` directly: no change needed (same value)

### Performance chart (already partially dark)

`buildPerformanceChart()` was rebuilt in Cycle 1 with line colors `#d96b43`, `#b45309`, `#15803d` — these read well on dark. Only the grid/tick/tooltip/legend values need updating per the table above.

---

## Files Changed

- `dashboard.html` only
  - CSS: ~20 property updates and 5 new rules
  - JS: color values inside `buildOverviewChart()` and `buildPerformanceChart()`

---

## Out of Scope

- No new chart types or data changes
- No changes to HUD layout, tab structure, or panel arrangement
- No changes to `recent-logs-list` (already dark-themed)
- No changes to Lucide icon rendering
- No changes to toast system
