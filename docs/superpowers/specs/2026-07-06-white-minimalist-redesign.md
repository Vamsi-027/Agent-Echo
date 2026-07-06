# White Minimalist Redesign — Google Developer Docs Style

**Date:** 2026-07-06
**Scope:** `dashboard.html` — CSS + JS chart functions only
**Replaces:** Dark glassmorphism theme (Cycles 1–2)
**Goal:** Convert the entire UI to a clean, white, minimalist aesthetic modeled on Google Developer Docs. No blur, no gradient mesh, no glassmorphism — flat surfaces, subtle borders, and Google Blue as the accent color.

---

## Context

Cycles 1 and 2 established a complete dark glassmorphism token system. All components now reference CSS custom properties (`var(--text-primary)`, `var(--bg-card)`, `var(--border-color)`, etc.) rather than hardcoded hex values, with only a small set of exceptions. This means the re-theme can be done surgically: replace `:root` token values, remove the gradient mesh and blur declarations, and fix the small set of remaining hardcoded dark values.

**Single source of truth:** `dashboard.html` only. No backend changes, no JS logic changes beyond Chart.js color constants.

---

## Section 1: Design Token System

Replace the full `:root` block with a Google-palette light system. All custom property **names** stay identical so downstream component CSS continues to work without modification.

### New token values

```css
:root {
    /* === Google Developer Docs Light Theme === */

    /* Background */
    --bg-base:   #f8f9fa;
    --bg-card:   #ffffff;
    --bg-hover:  #f1f3f4;

    /* Glass tokens — repurposed as flat surface tints (no blur applied) */
    --glass-1:        rgba(0, 0, 0, 0.02);
    --glass-2:        rgba(0, 0, 0, 0.04);
    --glass-3:        rgba(0, 0, 0, 0.06);
    --glass-4:        rgba(0, 0, 0, 0.08);
    --glass-border:   #e8eaed;
    --glass-border-strong: #bdc1c6;
    --blur-sm: none;
    --blur-md: none;
    --blur-lg: none;

    /* Accent — Google Blue */
    --primary:        #1967d2;
    --primary-hover:  #185abc;
    --primary-light:  rgba(25, 103, 210, 0.08);
    --primary-glow:   rgba(25, 103, 210, 0.12);
    --violet:  #7b57c8;
    --sky:     #1a73e8;
    --emerald: #137333;
    --amber:   #ea8600;
    --rose:    #c5221f;

    /* Semantic */
    --success:        #137333;
    --success-hover:  #0d652d;
    --success-light:  rgba(19, 115, 51, 0.08);
    --warning:        #ea8600;
    --warning-light:  rgba(234, 134, 0, 0.08);
    --danger:         #c5221f;
    --danger-light:   rgba(197, 34, 31, 0.08);

    /* Text */
    --text-primary:   #202124;
    --text-secondary: #5f6368;
    --text-muted:     #80868b;

    /* Typography */
    --font-display: -apple-system, BlinkMacSystemFont, "Google Sans", "Segoe UI", sans-serif;
    --font-body:    'Inter', -apple-system, sans-serif;
    --font-mono:    'JetBrains Mono', 'SF Mono', Menlo, 'Courier New', monospace;

    /* Shape — unchanged */
    --radius-sm:   8px;
    --radius-md:   12px;
    --radius-lg:   16px;
    --radius-xl:   20px;
    --radius-full: 9999px;
    --sidebar-width: 220px;

    /* Motion — unchanged */
    --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
    --transition-base: 220ms cubic-bezier(0.4, 0, 0.2, 1);
    --transition-slow: 360ms cubic-bezier(0.4, 0, 0.2, 1);

    /* Shadows — Google Material (very subtle) */
    --shadow-sm:    0 1px 2px rgba(60,64,67,0.20), 0 1px 3px rgba(60,64,67,0.10);
    --shadow-md:    0 1px 3px rgba(60,64,67,0.30), 0 4px 8px rgba(60,64,67,0.12);
    --shadow-lg:    0 4px 6px rgba(60,64,67,0.20), 0 8px 24px rgba(60,64,67,0.12);
    --shadow-glass: 0 1px 3px rgba(60,64,67,0.20), 0 4px 8px rgba(60,64,67,0.10);
    --shadow-glass-hover: 0 2px 6px rgba(60,64,67,0.25), 0 6px 16px rgba(60,64,67,0.14);
    --shadow-glow-primary: 0 0 0 3px rgba(25, 103, 210, 0.12);
    --shadow-glow-emerald: 0 0 0 3px rgba(19, 115, 51, 0.12);

    /* Backward-compat aliases */
    --sidebar-bg:     #ffffff;
    --border-color:   #e8eaed;
    --border-hover:   #bdc1c6;
    --radius-card:    var(--radius-md);
    --radius-btn:     var(--radius-sm);
    --radius-pill:    var(--radius-full);
    --font-main:      var(--font-body);
    --transition-speed: var(--transition-base);
    --shadow-glow:    var(--shadow-glow-primary);
}
```

---

## Section 2: Layout Shell

### Body background

Replace `body { background-color: var(--bg-base); }` — the new `--bg-base` is `#f8f9fa`, so this resolves automatically from the token change.

### Remove gradient mesh

Delete the entire `body::before` rule:

```css
/* DELETE this entire rule: */
body::before {
    content: '';
    position: fixed;
    inset: 0;
    z-index: -1;
    pointer-events: none;
    background: radial-gradient(...) ...;
}
```

Also remove `--bg-orb-1`, `--bg-orb-2`, `--bg-orb-3` token declarations (no longer used after mesh removal).

### Sidebar

Replace the current `.sidebar` rule. New values:

```css
.sidebar {
    width: var(--sidebar-width);
    background: #ffffff;
    border-right: 1px solid #e8eaed;
    display: flex;
    flex-direction: column;
    height: 100vh;
    position: sticky;
    top: 0;
    flex-shrink: 0;
    z-index: 100;
    /* remove: backdrop-filter, background gradient */
}
```

### Sidebar logo

```css
.sidebar-logo {
    padding: 20px 16px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid #e8eaed;
}
.logo-icon {
    width: 28px; height: 28px;
    background: #1967d2;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    color: #ffffff;
    /* remove: gradient, glow shadow */
}
.logo-text {
    font-size: 0.92rem;
    font-weight: 700;
    color: #202124;
    letter-spacing: -0.2px;
}
```

### Sidebar navigation

```css
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    margin: 2px 8px;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 500;
    color: #5f6368;
    transition: all var(--transition-fast);
    /* remove: border-left glow, background gradient */
    border-left: 3px solid transparent;
}
.nav-item:hover {
    background: #f1f3f4;
    color: #202124;
    border-left-color: transparent;
}
.nav-item.active {
    background: rgba(25, 103, 210, 0.10);
    color: #1967d2;
    font-weight: 600;
    border-left: 3px solid #1967d2;
    /* remove: box-shadow glow */
}
.nav-item .nav-icon {
    color: inherit;
    opacity: 1;
    /* remove: filter drop-shadow */
}
```

### Sidebar status section

```css
.sidebar-status {
    padding: 12px 16px;
    border-top: 1px solid #e8eaed;
    font-size: 0.72rem;
    color: #80868b;
}
```

### Remove all backdrop-filter declarations

Every element that received `backdrop-filter` in Cycles 1–2 must have it removed:
- `.hud-card`, `.panel-card`, `.draft-card`, `.queue-item`, `.timeline-card`, `.analytics-stat-chip`
- `.chat-sidebar`
- `.toast`

Set each to `backdrop-filter: none` (or remove the property). The `-webkit-backdrop-filter` companion lines must also be removed.

---

## Section 3: Component & Chart Updates

### Remaining hardcoded dark values

These CSS rules use hardcoded rgba-dark values (not tokens) and must be updated:

| Selector | Property | Old value | New value |
|---|---|---|---|
| `.chat-action-btn` | `background` | `#ffffff` | `#ffffff` ✓ (already correct in light theme) |
| `.chat-action-btn:hover` | `background` | `#f8fafc` | `#f1f3f4` |
| `.chat-card-content` | `background` | `#f8fafc` | `#f8f9fa` |
| `.chat-card-badge` | `background` | `#f1f5f9` | `#f1f3f4` |
| `.attachment-chip-display` | `background` | `#ffffff` | `#ffffff` ✓ |
| `.modal-close-btn:hover` | `background` | `#f1f5f9` | `#f1f3f4` |
| `.modal-input, .modal-textarea` | `background` | `#f8fafc` | `#f8f9fa` |
| `.modal-input:focus, .modal-textarea:focus` | `background` | `#ffffff` | `#ffffff` ✓ |

### Sidebar nav text — remove dark rgba

Current `.nav-item` uses `rgba(255,255,255,0.55)` for inactive color. Replace with `#5f6368`.
Current `.nav-item.active` uses `rgba(255,255,255,0.95)`. Replace with `#1967d2`.

### Chat bubble — user bubble

```css
.chat-bubble-container.user {
    background: #1967d2;   /* Google Blue instead of indigo */
    color: #ffffff;
}
```

### Chat bubble meta — user

```css
.chat-bubble-meta.user { color: rgba(255,255,255,0.80); }   /* white on blue bubble */
```

### Session list items

```css
.session-item:hover  { background: #f1f3f4; }
.session-item.active { background: rgba(25,103,210,0.08); border-color: rgba(25,103,210,0.20); }
```

### Filter select option

```css
.filter-select option { background: #ffffff; color: #202124; }
```

### Status badges

```css
.status-badge.pending_review { background: rgba(234,134,0,0.10);  color: #ea8600; }
.status-badge.approved       { background: rgba(19,115,51,0.10);  color: #137333; }
.status-badge.published      { background: rgba(25,103,210,0.10); color: #1967d2; }
.status-badge.rejected       { background: rgba(197,34,31,0.10);  color: #c5221f; }
```

### Timeline source badges

```css
.timeline-source.git      { background: rgba(25,103,210,0.10);  color: #1967d2; }
.timeline-source.note     { background: rgba(123,87,200,0.10);  color: #7b57c8; }
.timeline-source.browser  { background: rgba(234,134,0,0.10);   color: #ea8600; }
.timeline-source.file     { background: rgba(19,115,51,0.10);   color: #137333; }
.timeline-source.calendar { background: rgba(197,34,31,0.10);   color: #c5221f; }
```

### Analytics stat chip accents

```css
.analytics-stat-chip.accent-orange  { border-left: 4px solid #1967d2; }
.analytics-stat-chip.accent-amber   { border-left: 4px solid #ea8600; }
.analytics-stat-chip.accent-green   { border-left: 4px solid #137333; }
.analytics-stat-chip.accent-neutral { border-left: 4px solid #80868b; }
```

### Scrollbars — switch to light

```css
.content-area::-webkit-scrollbar-thumb        { background: rgba(0,0,0,0.15); }
.chat-session-list::-webkit-scrollbar-thumb   { background: rgba(0,0,0,0.15); }
.chat-messages::-webkit-scrollbar-thumb       { background: rgba(0,0,0,0.15); }
```

### Confirm-no button

```css
.confirm-no { background: #f1f3f4; color: #5f6368; }
```

### Overview chart dataset color

The `buildOverviewChart()` bar dataset uses `#6366f1` (indigo). Update to `#1967d2` (Google Blue) to match the new primary color.

### JS inline styles — draft/queue cards

In `renderDrafts()` and `renderQueue()`, two `.draft-card` template strings use inline `background: #ffffff`. In the new theme `#ffffff` is correct — **no change needed**.

The media preview containers use `background: #f8fafc` inline — update to `background: #f8f9fa`.

### Chart.js — light theme

Define `CHART_LIGHT` constant in both `buildOverviewChart()` and `buildPerformanceChart()`:

```javascript
const CHART_LIGHT = {
    grid:          'rgba(0,0,0,0.08)',
    ticks:         '#5f6368',
    legend:        '#5f6368',
    tooltipBg:     'rgba(255,255,255,0.97)',
    tooltipBorder: '#e8eaed',
    tooltipTitle:  '#202124',
    tooltipBody:   '#5f6368',
};
```

Apply to both charts using the same scale/plugin option structure already in place (replace `CHART_DARK` references with `CHART_LIGHT`).

### Performance chart dataset colors

Update line colors to work on a white canvas:
- Line 1: `#1967d2` (Google Blue)
- Line 2: `#ea8600` (Google Amber)
- Line 3: `#137333` (Google Green)

Dataset point border: `#ffffff` — unchanged, still correct.

---

## Files Changed

- `dashboard.html` only
  - CSS: `:root` token block (full replacement), `body::before` removal, `body` bg, sidebar rules, nav item rules, ~15 hardcoded-value replacements, all `backdrop-filter` removals
  - JS: `CHART_DARK` → `CHART_LIGHT` constant in both chart functions; performance chart dataset colors

---

## Out of Scope

- No layout or structural changes
- No new components
- No changes to `dashboard_server.py`
- Dark terminal logs panel (`.recent-logs-list`) stays dark — intentional
- No changes to animation keyframes (they are neutral and work in both themes)
