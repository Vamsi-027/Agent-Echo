# White Minimalist Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Agent Echo dashboard from dark glassmorphism to a clean white minimalist theme matching Google Developer Docs style, with Google Blue (`#1967d2`) as the accent color.

**Architecture:** All changes are in `dashboard.html` only. The CSS token system (`:root`) is replaced entirely — every component that already uses `var()` tokens flips automatically. A small set of hardcoded dark values and the Chart.js color constants are patched in subsequent tasks. No layout structure changes, no new components, no backend changes.

**Tech Stack:** Vanilla CSS custom properties, Chart.js 4.x, Lucide icons (unchanged)

## Global Constraints

- Modify `dashboard.html` only — no other files
- All custom property **names** stay identical — only values change; do not rename any `--variable`
- The dark terminal logs panel (`.recent-logs-list` with `background: #0f172a`) stays dark — do not touch it
- Animation keyframe rules stay unchanged — they are theme-neutral
- No new HTML elements; no new JS logic beyond replacing chart color constants
- Verification: read file sections to confirm correct values — no browser or server startup

---

### Task 1: Replace Design Token System & Remove Gradient Mesh

**Files:**
- Modify: `dashboard.html` — `:root` block (lines 15–96) and `body::before` rule (lines 115–126)

**Interfaces:**
- Produces: complete Google-palette light `:root`; `body::before` deleted; `body { background-color: var(--bg-base) }` resolves to `#f8f9fa` automatically

- [ ] **Step 1: Replace the entire `:root` block**

Find the block that opens with `:root {` and contains `/* === Dark Glassmorphism Design Tokens === */`. Replace everything from the opening `:root {` through its closing `}` with:

```css
        :root {
            /* === Google Developer Docs Light Theme === */

            /* Background */
            --bg-base:   #f8f9fa;
            --bg-card:   #ffffff;
            --bg-hover:  #f1f3f4;

            /* Glass tokens — repurposed as flat surface tints (no blur) */
            --glass-1:             rgba(0, 0, 0, 0.02);
            --glass-2:             rgba(0, 0, 0, 0.04);
            --glass-3:             rgba(0, 0, 0, 0.06);
            --glass-4:             rgba(0, 0, 0, 0.08);
            --glass-border:        #e8eaed;
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
            --success:       #137333;
            --success-hover: #0d652d;
            --success-light: rgba(19, 115, 51, 0.08);
            --warning:       #ea8600;
            --warning-light: rgba(234, 134, 0, 0.08);
            --danger:        #c5221f;
            --danger-light:  rgba(197, 34, 31, 0.08);

            /* Text */
            --text-primary:   #202124;
            --text-secondary: #5f6368;
            --text-muted:     #80868b;

            /* Typography */
            --font-display: -apple-system, BlinkMacSystemFont, "Google Sans", "Segoe UI", sans-serif;
            --font-body:    'Inter', -apple-system, sans-serif;
            --font-mono:    'JetBrains Mono', 'SF Mono', Menlo, 'Courier New', monospace;

            /* Shape */
            --radius-sm:     8px;
            --radius-md:     12px;
            --radius-lg:     16px;
            --radius-xl:     20px;
            --radius-full:   9999px;
            --sidebar-width: 220px;

            /* Motion */
            --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
            --transition-base: 220ms cubic-bezier(0.4, 0, 0.2, 1);
            --transition-slow: 360ms cubic-bezier(0.4, 0, 0.2, 1);

            /* Shadows — Google Material */
            --shadow-sm:           0 1px 2px rgba(60,64,67,0.20), 0 1px 3px rgba(60,64,67,0.10);
            --shadow-md:           0 1px 3px rgba(60,64,67,0.30), 0 4px 8px rgba(60,64,67,0.12);
            --shadow-lg:           0 4px 6px rgba(60,64,67,0.20), 0 8px 24px rgba(60,64,67,0.12);
            --shadow-glass:        0 1px 3px rgba(60,64,67,0.20), 0 4px 8px rgba(60,64,67,0.10);
            --shadow-glass-hover:  0 2px 6px rgba(60,64,67,0.25), 0 6px 16px rgba(60,64,67,0.14);
            --shadow-glow-primary: 0 0 0 3px rgba(25, 103, 210, 0.12);
            --shadow-glow-emerald: 0 0 0 3px rgba(19, 115, 51, 0.12);

            /* Backward-compat aliases */
            --sidebar-bg:       #ffffff;
            --border-color:     #e8eaed;
            --border-hover:     #bdc1c6;
            --radius-card:      var(--radius-md);
            --radius-btn:       var(--radius-sm);
            --radius-pill:      var(--radius-full);
            --font-main:        var(--font-body);
            --transition-speed: var(--transition-base);
            --shadow-glow:      var(--shadow-glow-primary);
        }
```

- [ ] **Step 2: Delete the `body::before` gradient mesh rule**

Find and delete this entire rule:

```css
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            z-index: -1;
            pointer-events: none;
            background:
                radial-gradient(ellipse 80% 80% at 0% 0%,   var(--bg-orb-1) 0%, transparent 55%),
                radial-gradient(ellipse 60% 60% at 100% 0%,  var(--bg-orb-2) 0%, transparent 55%),
                radial-gradient(ellipse 70% 70% at 50% 100%, var(--bg-orb-3) 0%, transparent 55%),
                var(--bg-base);
        }
```

Delete the entire block including the surrounding blank lines.

- [ ] **Step 3: Verify**

Read lines 15–130 of `dashboard.html`. Confirm:
- `--bg-base: #f8f9fa;` is present
- `--primary: #1967d2;` is present
- `--text-primary: #202124;` is present
- `--bg-orb-1` is absent
- `body::before` block is absent

- [ ] **Step 4: Commit**

```bash
git add dashboard.html
git commit -m "style: replace dark glassmorphism tokens with Google Developer Docs light palette"
```

---

### Task 2: Sidebar, Navigation & Remove All Backdrop-Filter

**Files:**
- Modify: `dashboard.html` — `.sidebar`, `.sidebar-logo`, `.logo-icon`, `.logo-text`, `.nav-item*`, `.sidebar-status` CSS rules; remove all `backdrop-filter` declarations

**Interfaces:**
- Consumes: `--primary: #1967d2`, `--text-primary: #202124`, `--text-secondary: #5f6368` from Task 1
- Produces: white sidebar with Google-style nav active state; zero `backdrop-filter` declarations in stylesheet

- [ ] **Step 1: Replace the `.sidebar` rule**

Find:
```css
        .sidebar {
            width: var(--sidebar-width);
            min-height: 100vh;
            position: fixed;
            top: 0;
            left: 0;
            display: flex;
            flex-direction: column;
            background: var(--glass-1);
            backdrop-filter: var(--blur-md);
            -webkit-backdrop-filter: var(--blur-md);
            border-right: 1px solid var(--glass-border);
            padding: 20px 12px;
            z-index: 50;
            gap: 4px;
        }
```

Replace with:
```css
        .sidebar {
            width: var(--sidebar-width);
            min-height: 100vh;
            position: fixed;
            top: 0;
            left: 0;
            display: flex;
            flex-direction: column;
            background: #ffffff;
            border-right: 1px solid #e8eaed;
            padding: 20px 12px;
            z-index: 50;
            gap: 4px;
        }
```

- [ ] **Step 2: Replace `.sidebar-logo`, `.logo-icon`, `.logo-text`**

Find `.sidebar-logo`:
```css
        .sidebar-logo {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px 12px;
        }
```

Replace with:
```css
        .sidebar-logo {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px 16px;
            border-bottom: 1px solid #e8eaed;
            margin-bottom: 8px;
        }
```

Find `.logo-icon`:
```css
        .logo-icon {
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--primary), var(--violet));
            border-radius: var(--radius-sm);
            box-shadow: var(--shadow-glow-primary);
            flex-shrink: 0;
            color: #ffffff;
        }
```

Replace with:
```css
        .logo-icon {
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #1967d2;
            border-radius: var(--radius-sm);
            flex-shrink: 0;
            color: #ffffff;
        }
```

Find `.logo-text`:
```css
        .logo-text {
            font-family: var(--font-display);
            font-weight: 700;
            font-size: 0.95rem;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }
```

Replace with:
```css
        .logo-text {
            font-family: var(--font-display);
            font-weight: 700;
            font-size: 0.92rem;
            color: #202124;
            letter-spacing: -0.2px;
        }
```

- [ ] **Step 3: Replace nav item rules**

Find the base `.nav-item` rule:
```css
        .nav-item {
            display: flex;
            align-items: center;
            gap: 10px;
            width: 100%;
            padding: 10px 12px;
            border: none;
            border-left: 3px solid transparent;
            border-radius: var(--radius-md);
            background: transparent;
            color: var(--text-secondary);
            font-family: var(--font-body);
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all var(--transition-fast);
            text-align: left;
        }
```

Replace with:
```css
        .nav-item {
            display: flex;
            align-items: center;
            gap: 10px;
            width: 100%;
            padding: 8px 12px;
            border: none;
            border-left: 3px solid transparent;
            border-radius: var(--radius-sm);
            background: transparent;
            color: #5f6368;
            font-family: var(--font-body);
            font-size: 0.82rem;
            font-weight: 500;
            cursor: pointer;
            transition: all var(--transition-fast);
            text-align: left;
        }
```

Find `.nav-item:hover`:
```css
        .nav-item:hover {
            background: var(--glass-2);
            color: var(--text-primary);
        }
```

Replace with:
```css
        .nav-item:hover {
            background: #f1f3f4;
            color: #202124;
        }
```

Find `.nav-item.active`:
```css
        .nav-item.active {
            background: var(--glass-3);
            color: var(--text-primary);
            font-weight: 600;
            border-left-color: var(--primary);
            box-shadow: var(--shadow-glass);
        }
```

Replace with:
```css
        .nav-item.active {
            background: rgba(25, 103, 210, 0.10);
            color: #1967d2;
            font-weight: 600;
            border-left-color: #1967d2;
        }
```

Find `.nav-item.active svg`:
```css
        .nav-item.active svg {
            color: var(--primary);
            stroke: var(--primary);
        }
```

Replace with:
```css
        .nav-item.active svg {
            color: #1967d2;
            stroke: #1967d2;
        }
```

- [ ] **Step 4: Replace `.sidebar-status`**

Find:
```css
        .sidebar-status {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
        }
```

Replace with:
```css
        .sidebar-status {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            border-top: 1px solid #e8eaed;
            font-size: 0.72rem;
            color: #80868b;
        }
```

- [ ] **Step 5: Remove all `backdrop-filter` declarations**

Run:
```bash
grep -n "backdrop-filter:" dashboard.html
```

For every line the grep returns (excluding any inside a comment), delete that line and its companion `-webkit-backdrop-filter:` line. These appear on elements: `.hud-card`, `.panel-card`, `.draft-card`, `.queue-item`, `.timeline-card`, `.analytics-stat-chip`, `.chat-sidebar`, `.toast`. Remove only the two `backdrop-filter` / `-webkit-backdrop-filter` lines from each rule; leave all other properties in those rules intact.

After editing, run again:
```bash
grep -n "backdrop-filter:" dashboard.html
```

Expected: empty output (no matches).

- [ ] **Step 6: Verify**

Read the `.sidebar` rule in the file. Confirm `background: #ffffff` and `border-right: 1px solid #e8eaed` are present, no `backdrop-filter` lines.

Read the `.nav-item.active` rule. Confirm `background: rgba(25, 103, 210, 0.10)`, `color: #1967d2`, `border-left-color: #1967d2`.

- [ ] **Step 7: Commit**

```bash
git add dashboard.html
git commit -m "style: white sidebar, Google-style nav active state, remove all backdrop-filter"
```

---

### Task 3: Component Light Conversions

**Files:**
- Modify: `dashboard.html` — CSS `<style>` block only

**Interfaces:**
- Consumes: token values from Task 1; no dependency on Task 2

- [ ] **Step 1: User chat bubble**

Find `.chat-bubble-container.user` (has `background: var(--primary)` currently — which now resolves to `#1967d2` from Task 1, correct). Update only the `box-shadow` to use Google Blue:

```css
        .chat-bubble-container.user {
            align-self: flex-end;
            background: var(--primary);
            color: #ffffff;
            border-radius: 12px 12px 2px 12px;
            padding: 10px 16px;
            box-shadow: 0 2px 8px rgba(25, 103, 210, 0.15);
        }
```

Find `.chat-bubble-meta.user { text-align: right; color: #e0e7ff; }`. Replace:
```css
        .chat-bubble-meta.user { text-align: right; color: rgba(255,255,255,0.80); }
```

- [ ] **Step 2: Chat card surfaces**

Find `.chat-card-content` (has `background: #f8fafc`). Replace the background value:
```css
        .chat-card-content {
            font-size: 0.82rem;
            color: var(--text-primary);
            line-height: 1.5;
            background: #f8f9fa;
            padding: 12px 14px;
            border-radius: var(--radius-btn);
            border: 1px solid var(--border-color);
            white-space: pre-wrap;
            font-family: var(--font-main);
        }
```

Find `.chat-card-badge` (has `background: #f1f5f9`). Replace:
```css
        .chat-card-badge {
            background: #f1f3f4;
            padding: 2px 8px;
            border-radius: var(--radius-pill);
            border: 1px solid var(--border-color);
            font-weight: 600;
        }
```

- [ ] **Step 3: Chat action buttons**

Find `.chat-action-btn` base rule (has `background: #ffffff`). Replace:
```css
        .chat-action-btn {
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-btn);
            padding: 6px 14px;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all var(--transition-speed);
            box-shadow: var(--shadow-sm);
        }
```

Find `.chat-action-btn:hover` (has `background: #f8fafc`). Replace:
```css
        .chat-action-btn:hover {
            color: var(--text-primary);
            border-color: var(--border-hover);
            background: #f1f3f4;
        }
```

- [ ] **Step 4: Attachment chip display**

Find `.attachment-chip-display` (has `background: #ffffff`). Replace background with `#f8f9fa`:
```css
        .attachment-chip-display {
            font-size: 0.72rem;
            padding: 4px 10px;
            background: #f8f9fa;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-secondary);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 4px;
        }
```

- [ ] **Step 5: Session list items**

Find `.session-item:hover` (has `background: rgba(255,255,255,0.06)`). Replace:
```css
        .session-item:hover {
            background: #f1f3f4;
        }
```

Find `.session-item.active` (has `background: rgba(255,255,255,0.10)`). Replace:
```css
        .session-item.active {
            background: rgba(25, 103, 210, 0.08);
            border-color: rgba(25, 103, 210, 0.20);
            box-shadow: var(--shadow-sm);
        }
```

- [ ] **Step 6: Scrollbars**

Find `.chat-session-list::-webkit-scrollbar-thumb` (has `background: rgba(255,255,255,0.15)`). Replace:
```css
        .chat-session-list::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 2px; }
```

Find `.chat-messages::-webkit-scrollbar-thumb` (has `background-color: rgba(255,255,255,0.15)`). Replace:
```css
        .chat-messages::-webkit-scrollbar-thumb { background-color: rgba(0,0,0,0.15); border-radius: 2px; }
```

Find `.content-area::-webkit-scrollbar-thumb` (has `background: rgba(255,255,255,0.12)`). Replace:
```css
        .content-area::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 3px; }
```

- [ ] **Step 7: Status badges**

Find the four `.status-badge.*` rules. Replace all four:
```css
        .status-badge.pending_review { background: rgba(234,134,0,0.10);   color: #ea8600; }
        .status-badge.approved       { background: rgba(19,115,51,0.10);   color: #137333; }
        .status-badge.published      { background: rgba(25,103,210,0.10);  color: #1967d2; }
        .status-badge.rejected       { background: rgba(197,34,31,0.10);   color: #c5221f; }
```

- [ ] **Step 8: Timeline source badges**

Find the five `.timeline-source.*` rules. Replace all five:
```css
        .timeline-source.git      { background: rgba(25,103,210,0.10);  color: #1967d2; }
        .timeline-source.note     { background: rgba(123,87,200,0.10);  color: #7b57c8; }
        .timeline-source.browser  { background: rgba(234,134,0,0.10);   color: #ea8600; }
        .timeline-source.file     { background: rgba(19,115,51,0.10);   color: #137333; }
        .timeline-source.calendar { background: rgba(197,34,31,0.10);   color: #c5221f; }
```

- [ ] **Step 9: Analytics stat chip accents**

Find the four `.analytics-stat-chip.accent-*` rules. Replace all four:
```css
        .analytics-stat-chip.accent-orange  { border-left: 4px solid #1967d2; }
        .analytics-stat-chip.accent-amber   { border-left: 4px solid #ea8600; }
        .analytics-stat-chip.accent-green   { border-left: 4px solid #137333; }
        .analytics-stat-chip.accent-neutral { border-left: 4px solid #80868b; }
```

- [ ] **Step 10: Confirm-no button**

Find `.confirm-no { background: rgba(255,255,255,0.06); color: var(--text-secondary); }`. Replace:
```css
        .confirm-no { background: #f1f3f4; color: var(--text-secondary); }
```

- [ ] **Step 11: Filter-select option**

Find `.filter-select option` (has `background: #080810`). Replace:
```css
        .filter-select option {
            background: #ffffff;
            color: #202124;
        }
```

- [ ] **Step 12: Modal inputs and close button**

Find `.modal-close-btn:hover` (has `background: #f1f5f9`). Replace:
```css
        .modal-close-btn:hover {
            color: var(--text-primary);
            background: #f1f3f4;
        }
```

Find `.modal-input, .modal-textarea` (has `background: #f8fafc`). Replace the background value only:
```css
        .modal-input, .modal-textarea {
            width: 100%;
            padding: 10px 14px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-btn);
            font-family: inherit;
            font-size: 0.85rem;
            color: var(--text-primary);
            background: #f8f9fa;
            transition: all var(--transition-speed);
            box-sizing: border-box;
        }
```

Find `.modal-input:focus, .modal-textarea:focus` (has `background: #ffffff`). Update `box-shadow` to use the new glow token:
```css
        .modal-input:focus, .modal-textarea:focus {
            outline: none;
            border-color: var(--primary);
            background: #ffffff;
            box-shadow: 0 0 0 3px var(--primary-glow);
        }
```

- [ ] **Step 13: JS inline styles — media preview containers**

In the `getMediaHtml()` function, find the image preview template string (contains `background: #f8fafc; display: flex; justify-content: center`). Replace `background: #f8fafc` with `background: #f8f9fa`:

```javascript
<div class="draft-media-preview-container" style="margin-top: 10px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); background: #f8f9fa; display: flex; justify-content: center; align-items: center; padding: 6px;">
```

Find the video preview template string (contains `background: #f8fafc; padding: 4px`). Replace `background: #f8fafc` with `background: #f8f9fa`:

```javascript
<div class="draft-media-preview-container" style="margin-top: 10px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); background: #f8f9fa; padding: 4px;">
```

- [ ] **Step 14: Verify no residual dark-rgba values**

Run:
```bash
grep -n "rgba(255,255,255" dashboard.html | grep -v "recent-logs\|0\.80\|0\.97\|0\.90"
```

Expected: zero matches outside `.recent-logs-list` context (which is intentionally dark). Fix any remaining occurrences found.

- [ ] **Step 15: Commit**

```bash
git add dashboard.html
git commit -m "style: convert all components to light theme — badges, cards, modals, buttons, scrollbars"
```

---

### Task 4: Chart.js Light Theme

**Files:**
- Modify: `dashboard.html` — `buildOverviewChart()` and `buildPerformanceChart()` JS functions only

**Interfaces:**
- Consumes: nothing from earlier tasks (chart colors are JS constants, not CSS tokens)
- Produces: both charts render with Google-palette colors on white canvas

- [ ] **Step 1: Update `buildOverviewChart()`**

Find the `buildOverviewChart()` function. It currently has a bar dataset with:
```javascript
                    datasets: [{
                        label: 'Events Count',
                        data: data,
                        backgroundColor: '#d96b43',
                        hoverBackgroundColor: '#c85a32',
                        borderRadius: 4
                    }]
```

Replace the dataset colors:
```javascript
                    datasets: [{
                        label: 'Events Count',
                        data: data,
                        backgroundColor: 'rgba(25,103,210,0.15)',
                        hoverBackgroundColor: 'rgba(25,103,210,0.25)',
                        borderColor: '#1967d2',
                        borderWidth: 1,
                        borderRadius: 4
                    }]
```

Then find the `scales` options inside `buildOverviewChart()`:
```javascript
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
```

Replace with:
```javascript
                    scales: {
                        y: {
                            grid: { color: 'rgba(0,0,0,0.08)' },
                            ticks: { color: '#5f6368', font: { family: 'Inter' } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#5f6368', font: { family: 'Inter' } }
                        }
                    },
```

Then find the `tooltip` plugin options inside `buildOverviewChart()`:
```javascript
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
```

Replace with:
```javascript
                        tooltip: {
                            backgroundColor: 'rgba(255,255,255,0.97)',
                            borderColor:     '#e8eaed',
                            borderWidth:     1,
                            titleColor:      '#202124',
                            bodyColor:       '#5f6368',
                            padding:         10,
                            cornerRadius:    6,
                            titleFont:       { family: 'Inter' },
                            bodyFont:        { family: 'Inter' }
                        }
```

- [ ] **Step 2: Update `buildPerformanceChart()`**

Find the three line datasets inside `buildPerformanceChart()`. They currently use `borderColor: '#d96b43'`, `borderColor: '#b45309'`, `borderColor: '#15803d'` and `makeGradient(217,107,67)`, `makeGradient(180,83,9)`, `makeGradient(21,128,61)`.

Replace the first dataset (Impressions):
```javascript
                        {
                            label: 'Impressions',
                            data: impressions,
                            borderColor: '#1967d2',
                            backgroundColor: makeGradient(25, 103, 210),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#1967d2',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        },
```

Replace the second dataset (Reactions):
```javascript
                        {
                            label: 'Reactions',
                            data: reactions,
                            borderColor: '#ea8600',
                            backgroundColor: makeGradient(234, 134, 0),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#ea8600',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        },
```

Replace the third dataset (Comments):
```javascript
                        {
                            label: 'Comments',
                            data: comments,
                            borderColor: '#137333',
                            backgroundColor: makeGradient(19, 115, 51),
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#137333',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2,
                            fill: true
                        }
```

Find the `scales` options inside `buildPerformanceChart()`:
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
```

Replace with:
```javascript
                    scales: {
                        y: {
                            grid: { color: 'rgba(0,0,0,0.08)' },
                            ticks: { color: '#5f6368', font: { family: 'Inter', size: 11 } }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#5f6368', font: { family: 'Inter', size: 11 } }
                        }
                    },
```

Find the `legend` and `tooltip` plugin options inside `buildPerformanceChart()`:
```javascript
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
```

Replace with:
```javascript
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 10,
                                padding: 16,
                                font: { family: 'Inter', size: 11 },
                                color: '#5f6368'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(255,255,255,0.97)',
                            borderColor:     '#e8eaed',
                            borderWidth:     1,
                            titleColor:      '#202124',
                            bodyColor:       '#5f6368',
                            padding:         10,
                            cornerRadius:    6,
                            titleFont:       { family: 'Inter' },
                            bodyFont:        { family: 'Inter' }
                        }
```

- [ ] **Step 3: Verify**

Run:
```bash
grep -n "rgba(255,255,255,0.06)\|rgba(255,255,255,0.50)\|rgba(255,255,255,0.60)\|rgba(15,15,25" dashboard.html | grep -v "recent-logs"
```

Expected: empty output. Fix any remaining matches.

- [ ] **Step 4: Commit**

```bash
git add dashboard.html
git commit -m "style: Chart.js light theme — Google Blue/Amber/Green datasets, light grid and tooltips"
```
