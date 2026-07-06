# Audience Performance Chart Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Analytics tab in `dashboard.html` to a dashboard-like layout: 4 stat chips (Total Impressions, Avg Reactions, Avg Comments, Published Posts) above a polished Chart.js line chart with gradient fills, smoother curves, and a proper empty state.

**Architecture:** All changes are confined to the single file `dashboard.html`. CSS additions go inside the existing `<style>` block. HTML for the Analytics tab panel is replaced in-place. Two JS functions are changed: `buildPerformanceChart()` is rewritten, and a new `buildAnalyticsStats()` helper is added directly before it. No backend changes.

**Tech Stack:** Chart.js (already loaded via CDN), vanilla JS, CSS custom properties already defined in `:root`.

## Global Constraints

- Touch only `dashboard.html` — no other files
- Preserve all existing CSS custom properties (`var(--primary)`, `var(--warning)`, `var(--success)`, `var(--text-muted)`, etc.) — never hardcode colors that already have a variable
- Do not rename or remove `performanceChartInstance`, `buildPerformanceChart`, or `chart-performance` — other code references them
- `buildOverviewChart()` must remain unchanged
- The server must be running (`python dashboard_server.py`) to load `/api/data` during visual verification

---

## File Map

| File | Action | What changes |
|---|---|---|
| `dashboard.html` | Modify | CSS block: add `.analytics-stat-grid`, `.analytics-stat-chip`, `.stat-label`, `.stat-value` |
| `dashboard.html` | Modify | HTML: replace `#panel-analytics` content with stat grid + `#analytics-chart-area` wrapper |
| `dashboard.html` | Modify | JS: add `buildAnalyticsStats()` before `buildPerformanceChart()` |
| `dashboard.html` | Modify | JS: rewrite `buildPerformanceChart()` — gradient fills, tension 0.4, tooltip, legend, empty state guard |

---

## Task 1: Add Stat Chip CSS

**Files:**
- Modify: `dashboard.html` (inside the `<style>` block, after the `.chart-container` rule at line ~232)

**Interfaces:**
- Produces: `.analytics-stat-grid`, `.analytics-stat-chip`, `.stat-label`, `.stat-value`, `.accent-orange`, `.accent-amber`, `.accent-green`, `.accent-neutral` — consumed by Task 2 HTML

- [ ] **Step 1: Locate insertion point**

Open `dashboard.html`. Find this block (around line 228):
```css
        .chart-container {
            position: relative;
            height: 320px;
            width: 100%;
        }
```

- [ ] **Step 2: Insert the stat chip CSS immediately after `.chart-container`**

Add this block directly after the closing `}` of `.chart-container`:
```css
        /* Analytics Stat Chips */
        .analytics-stat-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 24px;
        }

        .analytics-stat-chip {
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px 18px;
        }

        .analytics-stat-chip.accent-orange { border-left: 3px solid var(--primary); }
        .analytics-stat-chip.accent-amber  { border-left: 3px solid var(--warning); }
        .analytics-stat-chip.accent-green  { border-left: 3px solid var(--success); }
        .analytics-stat-chip.accent-neutral { border-left: 3px solid var(--text-muted); }

        .stat-label {
            font-size: 0.7rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.2;
        }
```

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "style: add analytics stat chip CSS classes"
```

---

## Task 2: Replace Analytics Tab HTML

**Files:**
- Modify: `dashboard.html` (the `#panel-analytics` div, around line 1005–1015)

**Interfaces:**
- Consumes: CSS classes from Task 1 (`.analytics-stat-grid`, `.analytics-stat-chip`, etc.)
- Produces: DOM elements `#stat-impressions`, `#stat-reactions`, `#stat-comments`, `#stat-published`, `#analytics-chart-area` — consumed by Task 3 JS

- [ ] **Step 1: Locate the existing Analytics tab panel**

Find this block (around line 1005):
```html
        <!-- TAB 5: ANALYTICS -->
        <div id="panel-analytics" class="tab-panel">
            <div class="panel-card">
                <div class="panel-header">
                    <div class="panel-title">Audience Performance</div>
                </div>
                <div class="chart-container">
                    <canvas id="chart-performance"></canvas>
                </div>
            </div>
        </div>
```

- [ ] **Step 2: Replace it entirely with the new structure**

```html
        <!-- TAB 5: ANALYTICS -->
        <div id="panel-analytics" class="tab-panel">
            <div class="panel-card">
                <div class="panel-header">
                    <div class="panel-title">Audience Performance</div>
                </div>
                <div class="analytics-stat-grid">
                    <div class="analytics-stat-chip accent-orange">
                        <div class="stat-label">Total Impressions</div>
                        <div class="stat-value" id="stat-impressions">—</div>
                    </div>
                    <div class="analytics-stat-chip accent-amber">
                        <div class="stat-label">Avg Reactions</div>
                        <div class="stat-value" id="stat-reactions">—</div>
                    </div>
                    <div class="analytics-stat-chip accent-green">
                        <div class="stat-label">Avg Comments</div>
                        <div class="stat-value" id="stat-comments">—</div>
                    </div>
                    <div class="analytics-stat-chip accent-neutral">
                        <div class="stat-label">Published Posts</div>
                        <div class="stat-value" id="stat-published">—</div>
                    </div>
                </div>
                <div id="analytics-chart-area">
                    <div class="chart-container">
                        <canvas id="chart-performance"></canvas>
                    </div>
                </div>
            </div>
        </div>
```

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat: restructure analytics tab with stat chip row and chart area wrapper"
```

---

## Task 3: Add buildAnalyticsStats() Helper

**Files:**
- Modify: `dashboard.html` (JS section — insert the new function immediately before the existing `function buildPerformanceChart()`, around line 1701)

**Interfaces:**
- Consumes: `state.performance` (array of `{impressions, reactions, comments, recorded_at}`), `state.stats.published_count` (number)
- Consumes: DOM elements `#stat-impressions`, `#stat-reactions`, `#stat-comments`, `#stat-published`, `#analytics-chart-area` from Task 2
- Produces: `buildAnalyticsStats()` function — called by `buildPerformanceChart()` in Task 4

- [ ] **Step 1: Locate the insertion point**

Find the line that reads:
```javascript
        function buildPerformanceChart() {
```

- [ ] **Step 2: Insert buildAnalyticsStats() directly before that line**

```javascript
        function buildAnalyticsStats() {
            const perf = state.performance;
            const noData = perf.length === 0;

            document.getElementById('stat-impressions').textContent = noData
                ? '—'
                : perf.reduce((s, p) => s + (p.impressions || 0), 0).toLocaleString();

            document.getElementById('stat-reactions').textContent = noData
                ? '—'
                : Math.round(perf.reduce((s, p) => s + (p.reactions || 0), 0) / perf.length);

            document.getElementById('stat-comments').textContent = noData
                ? '—'
                : Math.round(perf.reduce((s, p) => s + (p.comments || 0), 0) / perf.length);

            document.getElementById('stat-published').textContent =
                (state.stats.published_count != null) ? state.stats.published_count : '—';

            const chartArea = document.getElementById('analytics-chart-area');
            if (noData) {
                chartArea.innerHTML = '<div class="empty-state" style="padding: 48px 0; text-align: center; font-style: italic;">No performance data yet — publish your first post to see audience metrics here.</div>';
            } else if (!document.getElementById('chart-performance')) {
                chartArea.innerHTML = '<div class="chart-container"><canvas id="chart-performance"></canvas></div>';
            }
        }

```

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat: add buildAnalyticsStats helper for stat chips and empty state"
```

---

## Task 4: Rewrite buildPerformanceChart()

**Files:**
- Modify: `dashboard.html` — replace the entire existing `buildPerformanceChart()` function body

**Interfaces:**
- Consumes: `buildAnalyticsStats()` from Task 3
- Consumes: `state.performance`, `performanceChartInstance` (module-level singleton already declared)
- Produces: rendered Chart.js chart in `#chart-performance`

- [ ] **Step 1: Find the existing function**

Find the block that begins:
```javascript
        function buildPerformanceChart() {
            const ctx = document.getElementById('chart-performance').getContext('2d');
            if (performanceChartInstance) {
                performanceChartInstance.destroy();
            }
```
...and ends at the closing `}` before `let messageIdCounter = 0;` (around line 1779).

- [ ] **Step 2: Replace the entire function with the polished version**

```javascript
        function buildPerformanceChart() {
            if (performanceChartInstance) {
                performanceChartInstance.destroy();
                performanceChartInstance = null;
            }

            buildAnalyticsStats();

            if (state.performance.length === 0) return;

            const canvas = document.getElementById('chart-performance');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const h = canvas.offsetHeight || 320;

            function makeGradient(r, g, b) {
                const grad = ctx.createLinearGradient(0, 0, 0, h);
                grad.addColorStop(0, `rgba(${r},${g},${b},0.18)`);
                grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
                return grad;
            }

            const sorted = [...state.performance].sort(
                (a, b) => new Date(a.recorded_at) - new Date(b.recorded_at)
            );
            const labels     = sorted.map(p => p.recorded_at ? p.recorded_at.substring(5, 10) : '');
            const impressions = sorted.map(p => p.impressions || 0);
            const reactions   = sorted.map(p => p.reactions  || 0);
            const comments    = sorted.map(p => p.comments   || 0);

            performanceChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'Impressions',
                            data: impressions,
                            borderColor: '#d96b43',
                            backgroundColor: makeGradient(217, 107, 67),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        },
                        {
                            label: 'Reactions',
                            data: reactions,
                            borderColor: '#b45309',
                            backgroundColor: makeGradient(180, 83, 9),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        },
                        {
                            label: 'Comments',
                            data: comments,
                            borderColor: '#15803d',
                            backgroundColor: makeGradient(21, 128, 61),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: {
                            grid: { color: '#ede9e2' },
                            ticks: { color: '#5c564f', font: { family: 'Inter', size: 11 } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#5c564f', font: { family: 'Inter', size: 11 } }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 10,
                                padding: 16,
                                font: { family: 'Inter', size: 11 },
                                color: '#5c564f'
                            }
                        },
                        tooltip: {
                            backgroundColor: '#ffffff',
                            borderColor: '#e8e4dc',
                            borderWidth: 1,
                            titleColor: '#191919',
                            bodyColor: '#5c564f',
                            padding: 10,
                            cornerRadius: 6,
                            titleFont: { family: 'Inter' },
                            bodyFont: { family: 'Inter' }
                        }
                    }
                }
            });
        }
```

- [ ] **Step 3: Visual verification — empty state**

Start the server if not running:
```bash
python dashboard_server.py
```
Open `http://localhost:8080` in Chrome. Click the **Analytics** tab.

Expected with no performance data:
- 4 stat chips visible, all showing `—`
- No chart canvas — instead the italic message: *"No performance data yet — publish your first post to see audience metrics here."*
- No JavaScript errors in the browser console

- [ ] **Step 4: Visual verification — with data**

Seed a performance log row to test the chart path:
```bash
sqlite3 linkedin_agent.db "
INSERT OR IGNORE INTO published_posts (draft_id, linkedin_post_urn, published_at)
SELECT id, 'urn:test:' || id, datetime('now') FROM drafts LIMIT 1;
INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, recorded_at)
SELECT 'urn:test:' || d.id, 420, 18, 5, datetime('now')
FROM drafts d LIMIT 1;
INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, recorded_at)
SELECT 'urn:test:' || d.id, 680, 27, 9, datetime('now', '-3 days')
FROM drafts d LIMIT 1;
"
```

Reload `http://localhost:8080`, click **Analytics**.

Expected:
- Stat chips show real numbers (Total Impressions ≥ 1000, Avg Reactions/Comments non-zero, Published Posts ≥ 1)
- Chart renders with 3 smooth lines, each with a subtle gradient fill below
- Legend at bottom shows Impressions / Reactions / Comments
- Hovering a data point shows a white tooltip with all 3 values
- No flat zero lines, no JavaScript errors

- [ ] **Step 5: Commit**

```bash
git add dashboard.html
git commit -m "feat: polish audience performance chart — gradient fills, stat chips, empty state"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] 4 stat chips (Impressions, Reactions, Comments, Published Posts) — Task 2 HTML + Task 3 JS
- [x] Stat chips show `—` when no data — Task 3 `buildAnalyticsStats()`
- [x] Empty state message when no data — Task 3 `buildAnalyticsStats()`
- [x] Gradient fills — Task 4 `makeGradient()`
- [x] `tension: 0.4` — Task 4 dataset options
- [x] `pointRadius: 3`, `pointHoverRadius: 6`, `pointBorderColor: '#ffffff'` — Task 4
- [x] X-axis grid removed — Task 4 `x.grid.display: false`
- [x] Y-axis grid lightened to `#ede9e2` — Task 4
- [x] Legend at bottom, smaller — Task 4 `plugins.legend`
- [x] Tooltip white background, border, Inter font — Task 4 `plugins.tooltip`
- [x] Accent left borders on chips matching chart colors — Task 1 CSS

**Placeholder scan:** No TBDs, no "implement later", no "add validation" vagueness — all steps contain exact code.

**Type consistency:** `buildAnalyticsStats` defined in Task 3, called in Task 4. DOM ids (`stat-impressions`, `stat-reactions`, `stat-comments`, `stat-published`, `analytics-chart-area`, `chart-performance`) defined in Task 2, consumed in Tasks 3 and 4. `performanceChartInstance` used identically in Task 4 as in the original code.
