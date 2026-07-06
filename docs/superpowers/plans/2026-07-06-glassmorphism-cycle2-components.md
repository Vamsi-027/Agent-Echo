# Glassmorphism Redesign Cycle 2: Component Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt all existing dashboard components to the dark glassmorphism theme by replacing hardcoded light hex values, activating `backdrop-filter` on card surfaces, and updating Chart.js color configuration.

**Architecture:** All changes are in `dashboard.html` only. Three independent tasks: (1) glass surface CSS — card blur + hardcoded light value replacements, (2) interactive component CSS — chat sidebar, session items, inputs, scrollbars, (3) JS chart colors — `buildOverviewChart()` and `buildPerformanceChart()` dark palette. No layout, structure, or logic changes in any task.

**Tech Stack:** Vanilla CSS, Chart.js (already loaded), no new dependencies.

## Global Constraints

- Touch only `dashboard.html` — no other files
- Do not change any layout properties (display, flex, grid, gap, padding, margin, width, height) — only color/background/border-color/backdrop-filter changes
- Do not rename any CSS class or JS function
- All `rgba()` values must be written out explicitly — do not use CSS variable references where literal rgba is required (Chart.js receives JS strings, not CSS variables)
- `backdrop-filter` must always be accompanied by `-webkit-backdrop-filter` with the same value
- No HTML changes — only `<style>` and `<script>` block modifications

---

## File Map

| File | Action | What changes |
|---|---|---|
| `dashboard.html` | Modify | `<style>`: ~25 property updates across Task 1 + Task 2 |
| `dashboard.html` | Modify | `<script>`: color values inside `buildOverviewChart()` and `buildPerformanceChart()` |

---

## Task 1: Glass Surface Upgrade

**Files:**
- Modify: `dashboard.html` — `<style>` block only

**Interfaces:**
- Consumes: CSS custom properties `--blur-sm`, `--glass-1`, `--glass-2`, `--glass-border` (all defined in Cycle 1 `:root`)
- Produces: card surfaces with active `backdrop-filter`, corrected surface colors, legible timeline/status badges

- [ ] **Step 1: Add `backdrop-filter` to all card surfaces**

Find and update each of these 6 rules by adding two properties after the existing `box-shadow` line:

**`.hud-card`** (line 331):
```css
        .hud-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 24px;
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            transition: all var(--transition-speed) cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            cursor: pointer;
        }
```

**`.panel-card`** (line 389):
```css
        .panel-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 24px;
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
        }
```

**`.analytics-stat-chip`** (line 445):
```css
        .analytics-stat-chip {
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 16px 20px;
            background: var(--bg-card);
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            transition: all var(--transition-speed);
        }
```

**`.timeline-card`** (line 563):
```css
        .timeline-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 20px;
            transition: all var(--transition-speed);
            position: relative;
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
        }
```

**`.draft-card`** (line 651):
```css
        .draft-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            transition: all var(--transition-speed);
        }
```

**`.queue-item`** (line 760):
```css
        .queue-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-card);
            padding: 20px 24px;
            box-shadow: var(--shadow-sm);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            transition: all var(--transition-speed);
        }
```

- [ ] **Step 2: Replace hardcoded light backgrounds on nested surfaces**

Find and update each rule:

**`.event-details-formatted`** (line 614) — change `background: #f8fafc` to `background: rgba(255,255,255,0.04)`:
```css
        .event-details-formatted {
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 8px;
        }
```

**`.event-code`** (line 632) — change `background: #f1f5f9` to `background: rgba(255,255,255,0.06)`:
```css
        .event-code {
            font-family: var(--font-mono);
            font-size: 0.75rem;
            background: rgba(255,255,255,0.06);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--text-primary);
        }
```

**`.draft-meta-chip`** (line 700) — change `background: #f1f5f9` to `background: rgba(255,255,255,0.04)`:
```css
        .draft-meta-chip {
            font-size: 0.72rem;
            font-weight: 600;
            background: rgba(255,255,255,0.04);
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
        }
```

**`.draft-content`** (line 710) — change `background: #f8fafc` to `background: rgba(255,255,255,0.04)`:
```css
        .draft-content {
            font-size: 0.82rem;
            color: var(--text-primary);
            line-height: 1.5;
            background: rgba(255,255,255,0.04);
            padding: 14px;
            border-radius: var(--radius-btn);
            max-height: 150px;
            overflow-y: auto;
            white-space: pre-wrap;
            border: 1px solid var(--border-color);
            font-family: var(--font-main);
        }
```

**`.draft-media-box`** (line 732) — change `background: #f8fafc` to `background: rgba(255,255,255,0.04)`:
```css
        .draft-media-box {
            font-size: 0.78rem;
            background: rgba(255,255,255,0.04);
            border: 1px dashed var(--border-color);
            padding: 10px 12px;
            border-radius: var(--radius-btn);
            color: var(--text-secondary);
            font-weight: 500;
        }
```

- [ ] **Step 3: Fix analytics stat chip accent direction (border-top → border-left)**

Find lines 459–462:
```css
        .analytics-stat-chip.accent-orange { border-top: 4px solid var(--primary); }
        .analytics-stat-chip.accent-amber  { border-top: 4px solid var(--warning); }
        .analytics-stat-chip.accent-green  { border-top: 4px solid var(--success); }
        .analytics-stat-chip.accent-neutral { border-top: 4px solid var(--text-secondary); }
```

Replace with:
```css
        .analytics-stat-chip.accent-orange  { border-left: 4px solid var(--primary); }
        .analytics-stat-chip.accent-amber   { border-left: 4px solid var(--amber); }
        .analytics-stat-chip.accent-green   { border-left: 4px solid var(--emerald); }
        .analytics-stat-chip.accent-neutral { border-left: 4px solid var(--text-muted); }
```

- [ ] **Step 4: Fix timeline source badge colors for dark readability**

Find lines 595–599:
```css
        .timeline-source.git { background: rgba(99, 102, 241, 0.08); color: #4f46e5; }
        .timeline-source.note { background: rgba(168, 85, 247, 0.08); color: #9333ea; }
        .timeline-source.browser { background: rgba(249, 115, 22, 0.08); color: #ea580c; }
        .timeline-source.file { background: rgba(16, 185, 129, 0.08); color: #059669; }
        .timeline-source.calendar { background: rgba(239, 68, 68, 0.08); color: #dc2626; }
```

Replace with:
```css
        .timeline-source.git      { background: rgba(99, 102, 241, 0.18); color: #a5b4fc; }
        .timeline-source.note     { background: rgba(168, 85, 247, 0.18); color: #d8b4fe; }
        .timeline-source.browser  { background: rgba(249, 115, 22, 0.18);  color: #fdba74; }
        .timeline-source.file     { background: rgba(16, 185, 129, 0.18);  color: #6ee7b7; }
        .timeline-source.calendar { background: rgba(239, 68, 68, 0.18);   color: #fca5a5; }
```

- [ ] **Step 5: Fix status badge text colors for dark readability**

Find lines 689–692:
```css
        .status-badge.pending_review { background: var(--warning-light); color: #d97706; }
        .status-badge.approved { background: var(--success-light); color: var(--success-hover); }
        .status-badge.published { background: var(--primary-light); color: var(--primary-hover); }
        .status-badge.rejected { background: var(--danger-light); color: #dc2626; }
```

Replace with:
```css
        .status-badge.pending_review { background: var(--warning-light); color: #fbbf24; }
        .status-badge.approved       { background: var(--success-light);  color: #34d399; }
        .status-badge.published      { background: var(--primary-light);  color: #a5b4fc; }
        .status-badge.rejected       { background: var(--danger-light);   color: #f87171; }
```

- [ ] **Step 6: Visual verification**

Start the server if not running: `python dashboard_server.py`
Open `http://localhost:8080`.

Expected:
- HUD stat cards, panel cards, timeline cards, draft cards, queue items all have a subtle blur/glass shimmer visible against the gradient background
- Activity tab: timeline source badges (git, note, browser, file, calendar) are clearly readable — pastel text on semi-transparent tinted backgrounds
- Drafts tab: draft meta chips, content area, media box all use near-black glass surfaces instead of white/light gray
- Analytics tab: stat chip accent is on the left edge (not top)
- Draft/queue status badges are clearly readable (bright amber/green/violet/red on dark)
- No console errors

- [ ] **Step 7: Commit**

```bash
git add dashboard.html
git commit -m "style: glass surface upgrade — backdrop-filter on cards, dark surface replacements, badge colors"
```

---

## Task 2: Interactive Component Darkening

**Files:**
- Modify: `dashboard.html` — `<style>` block only

**Interfaces:**
- Consumes: `--glass-1`, `--glass-2`, `--glass-3`, `--glass-border`, `--blur-sm` from Cycle 1 `:root`
- Produces: dark chat sidebar, dark session items, dark agent bubbles, dark filter dropdowns, dark scrollbars

- [ ] **Step 1: Darken the chat sidebar and session list scrollbar**

Find `.chat-sidebar` (line 821):
```css
        .chat-sidebar {
            width: 220px;
            flex-shrink: 0;
            background: #f8fafc;
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
```

Replace with:
```css
        .chat-sidebar {
            width: 220px;
            flex-shrink: 0;
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            border-right: 1px solid var(--glass-border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
```

Find line 862:
```css
        .chat-session-list::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 2px; }
```

Replace with:
```css
        .chat-session-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 2px; }
```

- [ ] **Step 2: Darken session item hover and active states**

Find lines 876–883:
```css
        .session-item:hover {
            background: #e2e8f0;
        }
        .session-item.active {
            background: #ffffff;
            border-color: var(--border-color);
            box-shadow: var(--shadow-sm);
        }
```

Replace with:
```css
        .session-item:hover {
            background: rgba(255,255,255,0.06);
        }
        .session-item.active {
            background: rgba(255,255,255,0.10);
            border-color: var(--glass-border);
            box-shadow: var(--shadow-sm);
        }
```

- [ ] **Step 3: Fix confirm-no button**

Find line 945:
```css
        .confirm-no { background: #fff; color: var(--text-secondary); }
```

Replace with:
```css
        .confirm-no { background: rgba(255,255,255,0.06); color: var(--text-secondary); }
```

- [ ] **Step 4: Darken chat messages scrollbar and agent bubble**

Find line 977:
```css
        .chat-messages::-webkit-scrollbar-thumb { background-color: #cbd5e1; border-radius: 2px; }
```

Replace with:
```css
        .chat-messages::-webkit-scrollbar-thumb { background-color: rgba(255,255,255,0.15); border-radius: 2px; }
```

Find `.chat-bubble-container.agent` (line 997) — it currently has `background: #f1f5f9`. Read the full rule and update:
```css
        .chat-bubble-container.agent {
            align-self: flex-start;
            background: rgba(255,255,255,0.06);
            color: var(--text-primary);
            border-radius: 12px 12px 12px 2px;
            padding: 12px 18px;
            max-width: 85%;
        }
```

- [ ] **Step 5: Update filter-select for dark appearance**

Find `.filter-select` (line 532):
```css
        .filter-select {
            padding: 6px 14px;
            border-radius: var(--radius-btn);
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-secondary);
            outline: none;
            cursor: pointer;
            transition: all var(--transition-speed);
            box-shadow: var(--shadow-sm);
        }
```

Replace with:
```css
        .filter-select {
            padding: 6px 14px;
            border-radius: var(--radius-btn);
            border: 1px solid var(--glass-border);
            background: rgba(255,255,255,0.06);
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-primary);
            outline: none;
            cursor: pointer;
            transition: all var(--transition-speed);
            box-shadow: var(--shadow-sm);
            color-scheme: dark;
        }
```

Add a new rule immediately after the existing `.filter-select option` or after `.filter-select:focus` — insert after line 553:
```css
        .filter-select option {
            background: #1a1a2e;
            color: rgba(255,255,255,0.90);
        }
```

- [ ] **Step 6: Add global content-area scrollbar styling**

Insert after the `.sidebar-status` CSS block (after line ~270, before `.anim-fade-in-up`), adding these new rules:
```css
        /* Content area scrollbar */
        .content-area::-webkit-scrollbar       { width: 5px; }
        .content-area::-webkit-scrollbar-track { background: transparent; }
        .content-area::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
```

- [ ] **Step 7: Visual verification**

Reload `http://localhost:8080`. Click the **Chat** tab.

Expected:
- Chat sidebar is dark glass (not white/light gray)
- Session items: hover shows subtle dark tint, active item shows slightly brighter glass
- Chat agent reply bubble is dark glass (not light gray)
- Chat messages scrollbar is dark
- Switch to **Activity** tab: filter dropdown (source, status) has dark background, white text, dark dropdown menu
- Scrollbar in the main content area is thin and translucent dark
- No console errors

- [ ] **Step 8: Commit**

```bash
git add dashboard.html
git commit -m "style: darken interactive components — chat sidebar, session items, agent bubbles, filter selects, scrollbars"
```

---

## Task 3: Chart Dark Theme

**Files:**
- Modify: `dashboard.html` — `<script>` block only (two functions)

**Interfaces:**
- Consumes: `buildOverviewChart()` at line 2641, `buildPerformanceChart()` at line 2720 — both are standalone JS functions with no shared state except `eventsChartInstance` and `performanceChartInstance` module-level vars
- Produces: both charts render with dark grid, dark tick labels, dark legend, and dark-glass tooltip

- [ ] **Step 1: Update `buildOverviewChart()` chart colors**

Find the `options` block inside `buildOverviewChart()` (lines 2673–2690):
```javascript
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            grid: { color: '#e5e2d9' },
                            ticks: { color: '#57534e', font: { family: 'Inter' } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#57534e', font: { family: 'Inter' } }
                        }
                    },
                    plugins: {
                        legend: { display: false }
                    }
                }
```

Replace with:
```javascript
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            grid: { color: 'rgba(255,255,255,0.06)' },
                            ticks: { color: 'rgba(255,255,255,0.50)', font: { family: 'Inter' } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: 'rgba(255,255,255,0.50)', font: { family: 'Inter' } }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(15,15,25,0.92)',
                            borderColor:     'rgba(255,255,255,0.10)',
                            borderWidth:     1,
                            titleColor:      'rgba(255,255,255,0.95)',
                            bodyColor:       'rgba(255,255,255,0.65)',
                            padding:         10,
                            cornerRadius:    6,
                            titleFont:       { family: 'Inter' },
                            bodyFont:        { family: 'Inter' }
                        }
                    }
                }
```

- [ ] **Step 2: Update `buildPerformanceChart()` chart colors**

Find the `scales` block inside `buildPerformanceChart()` (lines 2800–2830):
```javascript
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
```

Replace with:
```javascript
                    scales: {
                        y: {
                            grid: { color: 'rgba(255,255,255,0.06)' },
                            ticks: { color: 'rgba(255,255,255,0.50)', font: { family: 'Inter', size: 11 } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: 'rgba(255,255,255,0.50)', font: { family: 'Inter', size: 11 } }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 10,
                                padding: 16,
                                font: { family: 'Inter', size: 11 },
                                color: 'rgba(255,255,255,0.60)'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15,15,25,0.92)',
                            borderColor:     'rgba(255,255,255,0.10)',
                            borderWidth:     1,
                            titleColor:      'rgba(255,255,255,0.95)',
                            bodyColor:       'rgba(255,255,255,0.65)',
                            padding:         10,
                            cornerRadius:    6,
                            titleFont:       { family: 'Inter' },
                            bodyFont:        { family: 'Inter' }
                        }
                    }
```

- [ ] **Step 3: Visual verification — Overview chart**

Reload `http://localhost:8080`. The Overview tab loads by default.

Expected:
- Bar chart (Events by Source) has dark grid lines (barely visible against dark bg) and white/translucent tick labels
- Hovering a bar shows a near-black tooltip with white title and body text
- No console errors

- [ ] **Step 4: Visual verification — Analytics chart**

Click **Analytics** tab (or seed data first if needed):

```bash
sqlite3 linkedin_agent.db "
INSERT OR IGNORE INTO published_posts (draft_id, linkedin_post_urn, published_at)
SELECT id, 'urn:test:' || id, datetime('now') FROM drafts LIMIT 1;
INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, recorded_at)
SELECT 'urn:test:' || d.id, 420, 18, 5, datetime('now') FROM drafts d LIMIT 1;
" 2>/dev/null || true
```

Expected:
- Performance line chart has dark grid, white-tinted tick labels, white legend labels at bottom
- Hovering a data point shows a near-black glass tooltip

- [ ] **Step 5: Commit**

```bash
git add dashboard.html
git commit -m "style: update Chart.js to dark theme — grid, ticks, legend, tooltip colors"
```

---

## Self-Review

**Spec coverage:**
- [x] `backdrop-filter` on `.hud-card`, `.panel-card`, `.analytics-stat-chip`, `.timeline-card`, `.draft-card`, `.queue-item` — Task 1 Step 1
- [x] `.draft-meta-chip` `#f1f5f9` → `rgba(255,255,255,0.04)` — Task 1 Step 2
- [x] `.draft-content` `#f8fafc` → `rgba(255,255,255,0.04)` — Task 1 Step 2
- [x] `.draft-media-box` `#f8fafc` → `rgba(255,255,255,0.04)` — Task 1 Step 2
- [x] `.event-details-formatted` `#f8fafc` → `rgba(255,255,255,0.04)` — Task 1 Step 2
- [x] `.event-code` `#f1f5f9` → `rgba(255,255,255,0.06)` — Task 1 Step 2
- [x] Analytics stat chip accent direction `border-top` → `border-left` with `--amber`/`--emerald`/`--text-muted` — Task 1 Step 3
- [x] Timeline source badge alpha 0.08→0.18, pastel text colors — Task 1 Step 4
- [x] Status badge text colors brightened — Task 1 Step 5
- [x] `.chat-sidebar` `#f8fafc` → glass + `backdrop-filter` — Task 2 Step 1
- [x] `.chat-session-list` scrollbar `#cbd5e1` → `rgba(255,255,255,0.15)` — Task 2 Step 1
- [x] `.session-item:hover` `#e2e8f0` → `rgba(255,255,255,0.06)` — Task 2 Step 2
- [x] `.session-item.active` `#ffffff` → `rgba(255,255,255,0.10)` — Task 2 Step 2
- [x] `.confirm-no` `#fff` → `rgba(255,255,255,0.06)` — Task 2 Step 3
- [x] `.chat-messages` scrollbar `#cbd5e1` → `rgba(255,255,255,0.15)` — Task 2 Step 4
- [x] `.chat-bubble-container.agent` `#f1f5f9` → `rgba(255,255,255,0.06)` — Task 2 Step 4
- [x] `.filter-select` dark appearance + `color-scheme: dark` + `.filter-select option` dark — Task 2 Step 5
- [x] `.content-area` scrollbar — Task 2 Step 6
- [x] `buildOverviewChart()` grid/ticks + tooltip dark colors — Task 3 Step 1
- [x] `buildPerformanceChart()` grid/ticks/legend/tooltip dark colors — Task 3 Step 2
- [x] `recent-logs-list` already dark — explicitly out of scope ✓

**Placeholder scan:** No TBDs. All CSS values are exact rgba() literals or CSS custom property references. All JS strings are literal rgba() values (not CSS variable references, which Chart.js cannot resolve).

**Type consistency:** No shared interfaces between tasks — each task is independently applied to `dashboard.html`. No function signatures changed.
