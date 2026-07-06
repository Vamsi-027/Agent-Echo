# Agent Echo UI Redesign — Cycle 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard shell with a dark glassmorphism design — new CSS design tokens, gradient mesh background, left sidebar navigation, Lucide icons, animation keyframes, and a glass toast/snackbar system that replaces the existing `showNotionToast()`.

**Architecture:** All changes are in `dashboard.html` only. Four sequenced tasks: (1) CSS tokens + head deps, (2) new CSS layer (gradient + sidebar + animations + toast), (3) HTML restructure (header → sidebar, main-container → content-area), (4) JS wiring (switchTab, status updates, showToast, Lucide init). Each task leaves the page functional — no broken intermediate states.

**Tech Stack:** Chart.js (CDN, unchanged), Lucide Icons (CDN, new), Google Fonts Inter + JetBrains Mono, vanilla CSS + JS.

## Global Constraints

- Touch only `dashboard.html` — no other files
- All new CSS custom properties live in `:root` — never hardcode a value that already has a variable
- Include backward-compat token aliases so existing panel CSS (--bg-card, --border-color, --radius-card, --font-main, etc.) continues to work without modification in Cycle 1
- Do not rename or remove existing tab panel IDs (`panel-overview`, `panel-activity`, `panel-drafts`, `panel-queue`, `panel-analytics`, `panel-chat`)
- Do not rename or remove: `fetchSystemData`, `updateHUD`, `buildOverviewChart`, `buildPerformanceChart`, `renderDrafts`, `renderQueue`, `renderActivity`, `renderLogs`, `loadChatSessions`
- `switchTab(tabId, btnElement)` signature unchanged — only its internal `.nav-btn` selector changes to `.nav-item`
- `showToast(message, type, duration)` replaces `showNotionToast(message, type)` — same call-site shape, `type` values identical (`'success'`, `'error'`, `'warning'`, `'info'`)
- Lucide icon names used: `zap`, `layout-dashboard`, `activity`, `file-text`, `clock`, `bar-chart-2`, `message-square`, `check-circle`, `alert-circle`, `alert-triangle`, `info`, `x`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `dashboard.html` | Modify | `<head>`: update Google Fonts link, add Lucide CDN |
| `dashboard.html` | Modify | `<style>`: replace `:root`, remove 11 obsolete rules, add ~200 lines new CSS |
| `dashboard.html` | Modify | `<body>`: replace `<header>` + `<div class="main-container">` opening with app-shell + sidebar + content-area; replace closing `</div>` + `<footer>` with `</main></div>`; add `#toast-container` |
| `dashboard.html` | Modify | `<script>`: update `switchTab()`, update `fetchSystemData()` status block + active-tab detection, add `showToast()`/`dismissToast()`/`TOAST_ICONS`, remove `showNotionToast()`, replace 10 call sites |

---

## Task 1: CSS Foundation — Design Tokens + Head Dependencies

**Files:**
- Modify: `dashboard.html` — `<head>` section and `:root` CSS block

**Interfaces:**
- Produces: all CSS custom properties consumed by Tasks 2, 3, 4 and by existing panel CSS

- [ ] **Step 1: Update the Google Fonts `<link>` tag**

Find (around line 10):
```html
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
```

Replace with:
```html
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Add Lucide CDN script after the Chart.js script tag**

Find (around line 12):
```html
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

Replace with:
```html
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
```

- [ ] **Step 3: Replace the entire `:root { ... }` block**

Find the block starting with `        :root {` and ending with the matching `        }` (lines 14–52 in the current file). Replace the entire block with:

```css
        :root {
            /* === Dark Glassmorphism Design Tokens === */

            /* Background */
            --bg-base: #080810;
            --bg-orb-1: rgba(99, 102, 241, 0.18);
            --bg-orb-2: rgba(139, 92, 246, 0.14);
            --bg-orb-3: rgba(14, 165, 233, 0.10);

            /* Glass surfaces */
            --glass-1: rgba(255, 255, 255, 0.04);
            --glass-2: rgba(255, 255, 255, 0.06);
            --glass-3: rgba(255, 255, 255, 0.10);
            --glass-4: rgba(255, 255, 255, 0.15);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-border-strong: rgba(255, 255, 255, 0.14);
            --blur-sm: blur(10px) saturate(180%);
            --blur-md: blur(20px) saturate(180%);
            --blur-lg: blur(40px) saturate(200%);

            /* Accent palette */
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-light: rgba(99, 102, 241, 0.15);
            --primary-glow: 0 0 24px rgba(99, 102, 241, 0.35);
            --violet: #8b5cf6;
            --sky: #0ea5e9;
            --emerald: #10b981;
            --success: #10b981;
            --amber: #f59e0b;
            --warning: #f59e0b;
            --rose: #f43f5e;
            --danger: #f43f5e;

            /* Text */
            --text-primary: rgba(255, 255, 255, 0.95);
            --text-secondary: rgba(255, 255, 255, 0.60);
            --text-muted: rgba(255, 255, 255, 0.35);

            /* Typography */
            --font-display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
            --font-body: 'Inter', -apple-system, sans-serif;
            --font-mono: 'SF Mono', 'JetBrains Mono', Menlo, 'Courier New', monospace;

            /* Shape */
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --radius-full: 9999px;
            --sidebar-width: 220px;

            /* Motion */
            --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
            --transition-base: 220ms cubic-bezier(0.4, 0, 0.2, 1);
            --transition-slow: 360ms cubic-bezier(0.4, 0, 0.2, 1);

            /* Shadows */
            --shadow-glass: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06);
            --shadow-glass-hover: 0 12px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.10);
            --shadow-glow-primary: 0 0 24px rgba(99, 102, 241, 0.35);
            --shadow-glow-emerald: 0 0 20px rgba(16, 185, 129, 0.30);

            /* === Backward-compat aliases (keep existing panel CSS working) === */
            --bg-card: var(--glass-2);
            --sidebar-bg: var(--glass-1);
            --border-color: var(--glass-border);
            --border-hover: var(--glass-border-strong);
            --radius-card: var(--radius-md);
            --radius-btn: var(--radius-sm);
            --radius-pill: var(--radius-full);
            --font-main: var(--font-body);
            --transition-speed: var(--transition-base);
            --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.4);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
            --shadow-lg: var(--shadow-glass);
            --shadow-glow: var(--shadow-glow-primary);
            --success-hover: #059669;
            --success-light: rgba(16, 185, 129, 0.12);
            --warning-light: rgba(245, 158, 11, 0.12);
            --danger-light: rgba(239, 68, 68, 0.12);
            --primary-glow: var(--shadow-glow-primary);
        }
```

- [ ] **Step 4: Remove the 11 obsolete CSS rule blocks**

Remove each of these rule blocks entirely from the `<style>` section (they are replaced by sidebar CSS in Task 2):

1. `header { ... }` — the old sticky top bar
2. `.logo-section { ... }`
3. `.logo-indicator { ... }`
4. `.logo-title { ... }`
5. `.header-nav { ... }`
6. `.nav-btn { ... }`
7. `.nav-btn:hover { ... }`
8. `.nav-btn.active { ... }`
9. `.system-status { ... }` — the old pill badge
10. `.main-container { ... }`
11. `footer { ... }`

- [ ] **Step 5: Visual verification**

Start the server: `python dashboard_server.py`
Open `http://localhost:8080`.

Expected:
- Page loads without JS errors in the browser console
- Fonts shift (Inter loads in place of Plus Jakarta Sans)
- The header/nav visually looks unstyled — that's correct, the HTML is unchanged but its CSS is removed. This will be fixed in Task 3.
- All existing tab panels still switch correctly.

- [ ] **Step 6: Commit**

```bash
git add dashboard.html
git commit -m "style: replace design tokens with glassmorphism system, update fonts + Lucide CDN"
```

---

## Task 2: CSS Layer — Gradient Mesh, Sidebar, Animations, Toast

**Files:**
- Modify: `dashboard.html` — `<style>` block, insert new rules after the `:root` block

**Interfaces:**
- Consumes: all CSS custom properties from Task 1
- Produces: `.app-shell`, `.sidebar`, `.content-area`, `.nav-item`, `.sidebar-logo`, `.sidebar-divider`, `.sidebar-status`, `.status-dot`, `.sidebar-nav`, `#toast-container`, `.toast`, `.toast-success`, `.toast-error`, `.toast-warning`, `.toast-info`, animation keyframes `fadeInUp`/`slideInRight`/`scaleIn`/`slideInFromBottom`/`slideOutToRight`/`pulseDot`/`shimmer`/`progressBar`, utility classes `.anim-fade-in-up`/`.anim-slide-in-right`/`.anim-scale-in`

- [ ] **Step 1: Update `body` rule for dark background and font**

Find the existing `body { ... }` block and replace it with:

```css
        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-body);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

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

- [ ] **Step 2: Add app shell layout CSS**

Insert directly after the `body::before { ... }` block:

```css
        /* === App Shell === */
        .app-shell {
            display: flex;
            min-height: 100vh;
        }

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

        .content-area {
            margin-left: var(--sidebar-width);
            flex: 1;
            min-height: 100vh;
            padding: 32px 36px;
            overflow-y: auto;
        }

        /* === Sidebar Components === */
        .sidebar-logo {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px 12px;
        }

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

        .logo-icon svg {
            width: 14px;
            height: 14px;
            stroke: #ffffff;
        }

        .logo-text {
            font-family: var(--font-display);
            font-weight: 700;
            font-size: 0.95rem;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }

        .sidebar-divider {
            height: 1px;
            background: var(--glass-border);
            margin: 8px 4px;
            flex-shrink: 0;
        }

        .sidebar-nav {
            display: flex;
            flex-direction: column;
            gap: 2px;
            flex: 1;
        }

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

        .nav-item:hover {
            background: var(--glass-2);
            color: var(--text-primary);
        }

        .nav-item.active {
            background: var(--glass-3);
            color: var(--text-primary);
            font-weight: 600;
            border-left-color: var(--primary);
            box-shadow: var(--shadow-glass);
        }

        .nav-item.active svg {
            color: var(--primary);
            stroke: var(--primary);
        }

        .nav-item svg {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }

        .sidebar-status {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--emerald);
            flex-shrink: 0;
            animation: pulseDot 2s ease infinite;
        }

        .status-label {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--text-secondary);
        }
```

- [ ] **Step 3: Add animation keyframes and utility classes**

Insert after the sidebar CSS block:

```css
        /* === Animation Keyframes === */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(12px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @keyframes slideInRight {
            from { opacity: 0; transform: translateX(16px); }
            to   { opacity: 1; transform: translateX(0); }
        }

        @keyframes scaleIn {
            from { opacity: 0; transform: scale(0.95); }
            to   { opacity: 1; transform: scale(1); }
        }

        @keyframes slideInFromBottom {
            from { opacity: 0; transform: translateY(24px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @keyframes slideOutToRight {
            from { opacity: 1; transform: translateX(0); }
            to   { opacity: 0; transform: translateX(24px); }
        }

        @keyframes pulseDot {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.4; }
        }

        @keyframes shimmer {
            from { background-position: -400px 0; }
            to   { background-position:  400px 0; }
        }

        @keyframes progressBar {
            from { width: 100%; }
            to   { width: 0%; }
        }

        /* === Animation Utilities === */
        .anim-fade-in-up     { animation: fadeInUp     280ms var(--transition-base) both; }
        .anim-slide-in-right { animation: slideInRight 200ms var(--transition-base) both; }
        .anim-scale-in       { animation: scaleIn      240ms var(--transition-base) both; }

        /* Stagger: JS sets style="--stagger: N" (0-indexed) */
        [style*="--stagger"] { animation-delay: calc(var(--stagger, 0) * 60ms); }
```

- [ ] **Step 4: Add toast/snackbar CSS**

Insert after the animation utilities block:

```css
        /* === Toast / Snackbar === */
        #toast-container {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            align-items: flex-end;
            pointer-events: none;
        }

        .toast {
            pointer-events: all;
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 14px 16px;
            min-width: 300px;
            max-width: 400px;
            background: var(--glass-3);
            backdrop-filter: var(--blur-md);
            -webkit-backdrop-filter: var(--blur-md);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-glass);
            border-left: 4px solid var(--primary);
            position: relative;
            overflow: hidden;
            animation: slideInFromBottom 300ms var(--transition-base) both;
        }

        .toast.toast-success { border-left-color: var(--emerald); }
        .toast.toast-error   { border-left-color: var(--rose); }
        .toast.toast-warning { border-left-color: var(--amber); }
        .toast.toast-info    { border-left-color: var(--primary); }

        .toast-icon { width: 16px; height: 16px; flex-shrink: 0; margin-top: 1px; }
        .toast-icon.toast-success svg { stroke: var(--emerald); }
        .toast-icon.toast-error   svg { stroke: var(--rose); }
        .toast-icon.toast-warning svg { stroke: var(--amber); }
        .toast-icon.toast-info    svg { stroke: var(--primary); }

        .toast-message {
            flex: 1;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.4;
        }

        .toast-close {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-muted);
            padding: 0;
            line-height: 1;
            transition: color var(--transition-fast);
            flex-shrink: 0;
        }

        .toast-close:hover { color: var(--text-primary); }
        .toast-close svg { width: 14px; height: 14px; }

        .toast-progress {
            position: absolute;
            bottom: 0;
            left: 0;
            height: 2px;
            background: currentColor;
            opacity: 0.35;
        }
```

- [ ] **Step 5: Visual verification**

Reload `http://localhost:8080`.

Expected:
- Dark gradient mesh background is visible (three soft color orbs on near-black)
- The old unstyled header is still there (will be replaced in Task 3) — expected
- No JS errors in console
- All tab panels still switch

- [ ] **Step 6: Commit**

```bash
git add dashboard.html
git commit -m "style: add glassmorphism CSS — gradient mesh, sidebar shell, animations, toast"
```

---

## Task 3: HTML Restructure — Sidebar + Content Area

**Files:**
- Modify: `dashboard.html` — `<body>` section (lines ~1266–1502)

**Interfaces:**
- Consumes: all CSS classes from Task 2 (`.app-shell`, `.sidebar`, `.nav-item`, etc.)
- Produces: DOM elements `#sidebar`, `#content-area`, `#toast-container`, `.nav-item` buttons, `#system-status` with `.status-dot` + `.status-label` children — consumed by Task 4 JS

- [ ] **Step 1: Replace `<header>...</header>` and the `<div class="main-container">` opening line**

Find this exact block (lines 1266–1284):
```html
    <header>
        <div class="logo-section">
            <div class="logo-indicator">✦</div>
            <h1 class="logo-title">Agent Echo</h1>
        </div>
        <nav class="header-nav">
            <button class="nav-btn active" onclick="switchTab('overview', this)"><span>📊</span> Overview</button>
            <button class="nav-btn" onclick="switchTab('activity', this)"><span>📝</span> Activity</button>
            <button class="nav-btn" onclick="switchTab('drafts', this)"><span>📄</span> Drafts</button>
            <button class="nav-btn" onclick="switchTab('queue', this)"><span>📅</span> Queue</button>
            <button class="nav-btn" onclick="switchTab('analytics', this)"><span>📈</span> Metrics</button>
            <button class="nav-btn" onclick="switchTab('chat', this)"><span>💬</span> Chat</button>
        </nav>
        <div class="system-status" id="system-status">
            <span>● Active</span>
        </div>
    </header>

    <div class="main-container">
```

Replace with:
```html
    <div class="app-shell">
        <nav class="sidebar" id="sidebar">
            <div class="sidebar-logo">
                <div class="logo-icon"><i data-lucide="zap"></i></div>
                <span class="logo-text">Agent Echo</span>
            </div>
            <div class="sidebar-divider"></div>
            <div class="sidebar-nav">
                <button class="nav-item active" onclick="switchTab('overview', this)">
                    <i data-lucide="layout-dashboard"></i>
                    <span>Overview</span>
                </button>
                <button class="nav-item" onclick="switchTab('activity', this)">
                    <i data-lucide="activity"></i>
                    <span>Activity</span>
                </button>
                <button class="nav-item" onclick="switchTab('drafts', this)">
                    <i data-lucide="file-text"></i>
                    <span>Drafts</span>
                </button>
                <button class="nav-item" onclick="switchTab('queue', this)">
                    <i data-lucide="clock"></i>
                    <span>Queue</span>
                </button>
                <button class="nav-item" onclick="switchTab('analytics', this)">
                    <i data-lucide="bar-chart-2"></i>
                    <span>Analytics</span>
                </button>
                <button class="nav-item" onclick="switchTab('chat', this)">
                    <i data-lucide="message-square"></i>
                    <span>Chat</span>
                </button>
            </div>
            <div class="sidebar-divider"></div>
            <div class="sidebar-status" id="system-status">
                <span class="status-dot"></span>
                <span class="status-label">CONNECTED</span>
            </div>
        </nav>
        <main class="content-area" id="content-area">
```

- [ ] **Step 2: Replace the main-container closing div + footer**

Find this exact block (lines ~1498–1502):
```html
    </div>

    <footer>
        Agent Echo // Localtime: <span id="footer-time"></span>
    </footer>
```

Replace with:
```html
        </main>
    </div>
```

- [ ] **Step 3: Add the toast container before `<script>`**

Find the line `    <script>` (the opening of the main script block, around line 1504).

Insert immediately before it:
```html
    <div id="toast-container" aria-live="polite" aria-atomic="false"></div>

```

- [ ] **Step 4: Visual verification**

Reload `http://localhost:8080`.

Expected:
- Dark gradient background visible
- Left sidebar renders with logo (Lucide zap icon + "Agent Echo"), 6 nav items with Lucide icons, status dot at bottom
- Overview tab active (highlighted nav item)
- Clicking nav items switches tabs correctly (even though `switchTab()` still references `.nav-btn` — the click still fires since the onclick handler passes `this` directly)
- No JS errors in console
- HUD stat cards visible in the content area

- [ ] **Step 5: Commit**

```bash
git add dashboard.html
git commit -m "feat: restructure HTML — app-shell + left sidebar + content area, remove footer"
```

---

## Task 4: JS Wiring — Lucide Init, switchTab, Status Updates, showToast

**Files:**
- Modify: `dashboard.html` — `<script>` block

**Interfaces:**
- Consumes: `.nav-item` DOM elements from Task 3, `#system-status` with `.status-dot` / `.status-label` children from Task 3, `#toast-container` from Task 3, `lucide` global from Lucide CDN (Task 1)
- Produces: `showToast(message, type, duration)` replaces `showNotionToast(message, type)` at 10 call sites

- [ ] **Step 1: Call `lucide.createIcons()` on DOMContentLoaded**

Find the last two lines of the `<script>` block before `</script>`:
```javascript
        // Initialize dashboard sync loop
        fetchSystemData();
        setInterval(fetchSystemData, 5000); // Poll database state every 5 seconds
        loadChatSessions();
```

Replace with:
```javascript
        // Initialize dashboard sync loop
        fetchSystemData();
        setInterval(fetchSystemData, 5000); // Poll database state every 5 seconds
        loadChatSessions();

        // Initialize Lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
```

- [ ] **Step 2: Update `switchTab()` to target `.nav-item` instead of `.nav-btn`**

Find the existing `switchTab` function:
```javascript
        function switchTab(tabId, btnElement = null) {
            // Update active nav buttons
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            if (btnElement) {
                btnElement.classList.add('active');
            } else {
                document.querySelectorAll('.nav-btn').forEach(btn => {
                    if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabId)) {
                        btn.classList.add('active');
                    }
                });
            }

            // Update active panel display
            document.querySelectorAll('.tab-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            document.getElementById(`panel-${tabId}`).classList.add('active');

            // Trigger chart rebuilds if relevant
            if (tabId === 'overview') {
                setTimeout(buildOverviewChart, 100);
            } else if (tabId === 'analytics') {
                setTimeout(buildPerformanceChart, 100);
            } else if (tabId === 'chat') {
                loadChatSessions();
            }
        }
```

Replace with:
```javascript
        function switchTab(tabId, btnElement = null) {
            document.querySelectorAll('.nav-item').forEach(btn => {
                btn.classList.remove('active');
            });
            if (btnElement) {
                btnElement.classList.add('active');
            } else {
                document.querySelectorAll('.nav-item').forEach(btn => {
                    if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(`'${tabId}'`)) {
                        btn.classList.add('active');
                    }
                });
            }

            document.querySelectorAll('.tab-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            document.getElementById(`panel-${tabId}`).classList.add('active');

            if (tabId === 'overview') {
                setTimeout(buildOverviewChart, 100);
            } else if (tabId === 'analytics') {
                setTimeout(buildPerformanceChart, 100);
            } else if (tabId === 'chat') {
                loadChatSessions();
            }
        }
```

- [ ] **Step 3: Update `fetchSystemData()` active-tab detection and status DOM update**

Inside `fetchSystemData()`, find the active-tab detection block:
```javascript
                // Check active tab to reload charts
                const activeNav = document.querySelector('.nav-btn.active');
                if (activeNav) {
                    const activeTabName = activeNav.innerText.toLowerCase();
                    if (activeTabName.includes('overview')) {
                        buildOverviewChart();
                    } else if (activeTabName.includes('analytics')) {
                        buildPerformanceChart();
                    }
                }

                document.getElementById('system-status').innerText = "● CONNECTED";
                document.getElementById('system-status').style.color = "var(--success)";
                document.getElementById('system-status').style.background = "var(--success-light)";
                document.getElementById('system-status').style.borderColor = "rgba(16, 185, 129, 0.1)";
            } catch (err) {
                console.error("Error synchronizing system data:", err);
                document.getElementById('system-status').innerText = "▲ OFFLINE";
                document.getElementById('system-status').style.color = "var(--danger)";
                document.getElementById('system-status').style.background = "var(--danger-light)";
                document.getElementById('system-status').style.borderColor = "rgba(239, 68, 68, 0.1)";
            }
```

Replace with:
```javascript
                // Check active tab to reload charts
                const activeNav = document.querySelector('.nav-item.active');
                if (activeNav) {
                    const onclick = activeNav.getAttribute('onclick') || '';
                    if (onclick.includes("'overview'")) buildOverviewChart();
                    else if (onclick.includes("'analytics'")) buildPerformanceChart();
                }

                const dot = document.querySelector('#system-status .status-dot');
                const label = document.querySelector('#system-status .status-label');
                if (dot) { dot.style.background = 'var(--emerald)'; dot.style.boxShadow = '0 0 6px var(--emerald)'; }
                if (label) label.textContent = 'CONNECTED';
            } catch (err) {
                console.error("Error synchronizing system data:", err);
                const dot = document.querySelector('#system-status .status-dot');
                const label = document.querySelector('#system-status .status-label');
                if (dot) { dot.style.background = 'var(--rose)'; dot.style.boxShadow = 'none'; }
                if (label) label.textContent = 'OFFLINE';
            }
```

- [ ] **Step 4: Add `showToast()` and `dismissToast()`, replacing `showNotionToast()`**

Find the existing `showNotionToast` function:
```javascript
        function showNotionToast(message, type = 'info') {
            const existing = document.getElementById('notion-active-toast');
            if (existing) {
                existing.remove();
            }
            ...
        }
```

Replace the entire `showNotionToast` function with:
```javascript
        const TOAST_ICONS = {
            success: 'check-circle',
            error:   'alert-circle',
            warning: 'alert-triangle',
            info:    'info',
        };

        function showToast(message, type = 'info', duration = 4000) {
            const container = document.getElementById('toast-container');
            if (!container) return;

            while (container.children.length >= 3) {
                dismissToast(container.firstElementChild);
            }

            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.innerHTML = `
                <span class="toast-icon toast-${type}"><i data-lucide="${TOAST_ICONS[type] || 'info'}"></i></span>
                <span class="toast-message">${message}</span>
                <button class="toast-close" onclick="dismissToast(this.parentElement)" aria-label="Dismiss">
                    <i data-lucide="x"></i>
                </button>
                <div class="toast-progress" style="animation: progressBar ${duration}ms linear forwards;"></div>
            `;

            container.appendChild(toast);
            if (typeof lucide !== 'undefined') lucide.createIcons({ nodes: [toast] });

            toast._dismissTimer = setTimeout(() => dismissToast(toast), duration);
        }

        function dismissToast(toast) {
            if (!toast || !toast.isConnected) return;
            clearTimeout(toast._dismissTimer);
            toast.style.animation = 'slideOutToRight 250ms ease forwards';
            setTimeout(() => toast.remove(), 250);
        }
```

- [ ] **Step 5: Replace all 10 `showNotionToast(` call sites with `showToast(`**

Find and replace every occurrence of `showNotionToast(` with `showToast(` throughout the `<script>` block. There are exactly 10 occurrences:

```
Line ~1686: showNotionToast("Conversation deleted successfully.", "success")
Line ~2353: showNotionToast(data.message || "Post updated successfully!", "success")
Line ~2355: showNotionToast('Error: ' + ((data && data.error) || 'Failed action'), "error")
Line ~2359: showNotionToast('Network error processing post update.', "error")
Line ~2374: showNotionToast("Draft approved and queued!", "success")
Line ~2376: showNotionToast("Failed: " + (data.error || "Approval failed"), "error")
Line ~2379: showNotionToast("Network error approving draft.", "error")
Line ~2394: showNotionToast("Draft deleted.", "success")
Line ~2396: showNotionToast("Failed: " + (data.error || "Delete failed"), "error")
Line ~2399: showNotionToast("Network error deleting draft.", "error")
Line ~2418: showNotionToast("Scheduled post cancelled and returned to drafts.", "success")
Line ~2420: showNotionToast('Failed to cancel scheduled post: ' + (data.error || 'Unknown error'), "error")
Line ~2424: showNotionToast('Network error cancelling scheduled post.', "error")
```

Run a find+replace: replace ALL instances of `showNotionToast(` → `showToast(`. This is safe as a global replace — the function signature is compatible.

- [ ] **Step 6: Remove `.notion-toast` CSS and `@keyframes toastSlideIn`**

Find and remove these two CSS blocks from the `<style>` section:

```css
        .notion-toast {
            position: fixed;
            ...
        }
```

```css
        @keyframes toastSlideIn {
            from { transform: translateY(20px) scale(0.95); opacity: 0; }
            to { transform: translateY(0) scale(1); opacity: 1; }
        }
```

- [ ] **Step 7: Visual verification — full feature check**

Reload `http://localhost:8080`.

Expected:
- Sidebar logo shows Lucide zap icon (not a question-mark placeholder)
- All 6 nav items show Lucide icons
- Clicking each nav item: active item gets the glass highlight + indigo left border; previous active item reverts
- Click "Approve & Queue" on any draft → glass toast slides up from bottom-right with green left border and check-circle icon
- Click "Delete" on any draft → toast appears with rose left border
- Open browser console, run `showToast('Test info', 'info')` → indigo toast appears
- Run `showToast('Done!', 'success')` four times in rapid succession → only 3 toasts visible at once (oldest dismissed as 4th arrives)
- Status dot at bottom of sidebar is emerald + pulsing
- If you disconnect the internet and wait for a poll tick → status dot turns rose, label reads "OFFLINE"
- No JS errors in console

- [ ] **Step 8: Commit**

```bash
git add dashboard.html
git commit -m "feat: wire Lucide icons, sidebar nav, glass toast system — Cycle 1 complete"
```

---

## Self-Review

**Spec coverage:**
- [x] Design tokens (all variables, backward-compat aliases) — Task 1 Step 3
- [x] Google Fonts: Inter + JetBrains Mono — Task 1 Step 1
- [x] Lucide CDN — Task 1 Step 2
- [x] Gradient mesh background (`body::before`) — Task 2 Step 1
- [x] App shell layout (`.app-shell`, `.sidebar`, `.content-area`) — Task 2 Step 2
- [x] Sidebar logo with zap icon — Task 3 Step 1
- [x] 6 nav items with Lucide icons and correct tab IDs — Task 3 Step 1
- [x] `.nav-item` active + hover states with left border — Task 2 Step 2
- [x] `.status-dot` + `.status-label` at sidebar bottom — Task 2 Step 2 + Task 3 Step 1
- [x] All 8 animation keyframes — Task 2 Step 3
- [x] Utility classes + stagger support — Task 2 Step 3
- [x] `#toast-container` CSS — Task 2 Step 4
- [x] `#toast-container` HTML — Task 3 Step 3
- [x] `showToast()` + `dismissToast()` + `TOAST_ICONS` — Task 4 Step 4
- [x] Replace `showNotionToast()` at all 10 call sites — Task 4 Step 5
- [x] Remove `.notion-toast` CSS + `@keyframes toastSlideIn` — Task 4 Step 6
- [x] `switchTab()` updated to `.nav-item` — Task 4 Step 2
- [x] `fetchSystemData()` active-tab detection updated — Task 4 Step 3
- [x] `fetchSystemData()` status DOM update for new structure — Task 4 Step 3
- [x] `lucide.createIcons()` on DOMContentLoaded — Task 4 Step 1
- [x] `lucide.createIcons({ nodes: [toast] })` inside `showToast()` — Task 4 Step 4
- [x] Success criteria #1–6 all covered by Task 4 Step 7 verification

**Placeholder scan:** No TBDs. All CSS values are exact. All JS code is complete.

**Type/name consistency:**
- `showToast(message, type, duration)` defined Task 4 Step 4, called at 10 sites Task 4 Step 5 — signatures match
- `dismissToast(toast)` defined Task 4 Step 4, called inside showToast + inline onclick — consistent
- `.nav-item` defined Task 2 Step 2, used in HTML Task 3 Step 1, targeted in JS Task 4 Steps 2+3 — consistent
- `#system-status .status-dot` / `.status-label` defined Task 2 Step 2, present in HTML Task 3 Step 1, queried in JS Task 4 Step 3 — consistent
- `TOAST_ICONS` constant defined before `showToast()` in same step — consistent
