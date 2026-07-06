# Audience Performance Chart — Polish Design

**Date:** 2026-07-06  
**Scope:** `dashboard.html` — Analytics tab only  
**Goal:** Make the Audience Performance chart feel professional and dashboard-like without changing data or structure elsewhere.

---

## Layout

Single `panel-card` on the Analytics tab with three stacked zones:

1. **Panel header** — "Audience Performance" title (existing `.panel-header` / `.panel-title`)
2. **Stat chip row** — 4 equal-width chips: Total Impressions, Avg Reactions, Avg Comments, Published Posts
3. **Chart area** — Chart.js line chart with gradient fills, or empty state message if no data

---

## Stat Chips

**New CSS classes:** `.analytics-stat-grid`, `.analytics-stat-chip`

- Grid: 4 equal columns, `12px` gap, `margin-bottom: 24px`
- Each chip: `border: 1px solid var(--border-color)`, `border-radius: 8px`, `padding: 16px`
- Label: `0.7rem`, `letter-spacing: 0.05em`, `text-transform: uppercase`, `color: var(--text-muted)`
- Value: `1.5rem`, `font-weight: 600`, `color: var(--text-primary)`
- Accent dot or left border to color-code each chip to its chart line:
  - Impressions → terracotta (`var(--primary)` = `#d96b43`)
  - Reactions → amber (`var(--warning)` = `#b45309`)
  - Comments → green (`var(--success)` = `#15803d`)
  - Published Posts → neutral (`var(--text-secondary)`)
- When no data: value displays `—` (em dash)

Computed values from `state.performance`:
- **Total Impressions:** `SUM(impressions)`
- **Avg Reactions:** `AVG(reactions)` rounded to nearest integer
- **Avg Comments:** `AVG(comments)` rounded to nearest integer
- **Published Posts:** `state.stats.published_count` (already in stats payload)

---

## Chart Styling

**Type:** `line` (unchanged)

**Colors** (matching existing design system):
| Metric | Line color | Gradient top | Gradient bottom |
|---|---|---|---|
| Impressions | `#d96b43` | `rgba(217,107,67,0.18)` | `rgba(217,107,67,0)` |
| Reactions | `#b45309` | `rgba(180,83,9,0.15)` | `rgba(180,83,9,0)` |
| Comments | `#15803d` | `rgba(21,128,61,0.13)` | `rgba(21,128,61,0)` |

**Gradient fill:** `ctx.createLinearGradient(0, 0, 0, chartHeight)` per dataset; assigned to `backgroundColor`.

**Dataset options:**
- `tension: 0.4` (was `0.1`)
- `borderWidth: 2` (unchanged)
- `pointRadius: 3`, `pointHoverRadius: 6`
- `pointBorderColor: '#ffffff'`, `pointBorderWidth: 2` on hover
- `fill: true`

**Scales:**
- Y-axis: grid color `#ede9e2` (lighter than current `#e5e2d9`)
- X-axis: `grid.display: false` (remove vertical grid lines)
- Both axes: `ticks.color: var(--text-secondary)`, font Inter 11px

**Legend:**
- `position: 'bottom'`
- `labels.boxWidth: 10`, `labels.padding: 16`, `labels.font.size: 11`
- `labels.color: var(--text-secondary)`

**Tooltip:**
- Use built-in Chart.js tooltip with `mode: 'index'`, `intersect: false` — shows all 3 values on hover
- `bodyFont.family: 'Inter'`, `titleFont.family: 'Inter'`
- `backgroundColor: '#ffffff'`, `borderColor: var(--border-color)`, `borderWidth: 1`
- `titleColor: var(--text-primary)`, `bodyColor: var(--text-secondary)`
- `padding: 10`, `cornerRadius: 6`

---

## Empty State

When `state.performance.length === 0`:
- Stat chips show `—` for all metric values
- Replace `<canvas>` with a centered `.empty-state` div:  
  `"No performance data yet — publish your first post to see audience metrics here."`
- Use existing `.empty-state` CSS class (color: `var(--text-muted)`, italic)

When data is present but sparse (1–2 points): chart renders normally; gradient fills still apply.

---

## Files Changed

- `dashboard.html` — only file touched
  - CSS: add `.analytics-stat-grid`, `.analytics-stat-chip` inside `<style>`
  - HTML: replace Analytics tab panel contents
  - JS: rewrite `buildPerformanceChart()` and add `buildAnalyticsStats()` helper

---

## Out of Scope

- No new API endpoints
- No breakdown table (can be added later)
- No time-range filter / date picker
- No changes to other tabs
