# Agent Echo UI Redesign — Cycle 1: Foundation

**Date:** 2026-07-06
**Scope:** `dashboard.html` only — design system tokens, gradient background, sidebar layout shell, Lucide icon integration, animation utilities, toast/snackbar system
**Part of:** 4-cycle full glassmorphism redesign
**Goal:** Ship the new dark glassmorphism shell immediately — gradient background, left sidebar nav, typography upgrade, animation primitives, toast system — so all subsequent cycles build on a stable foundation.

---

## Overview of 4-Cycle Redesign

| Cycle | Scope |
|---|---|
| **1 — Foundation** | Design tokens, gradient mesh bg, sidebar shell, fonts, Lucide, animation utilities, toast system |
| **2 — Component Layer** | Glass cards, buttons, badges, modals, skeletons |
| **3 — Tab Content** | All 6 tabs rebuilt with new components |
| **4 — Motion Polish** | Countup animations, card stagger, tab transitions, active nav slider |

---

## Aesthetic Direction

**Style:** Glassmorphism on an animated dark gradient mesh — Apple macOS/iOS aesthetic applied to a developer tool dashboard.

**References:** macOS Sonoma widgets, Vercel dark dashboard, Linear dark mode, Raycast.

---

## Section 1 — Design Tokens

All values live in `:root` in `dashboard.html`'s `<style>` block, replacing the existing `:root`. No inline hex values for anything already in a variable.

### Background

```css
--bg-base: #080810;
--bg-orb-1: rgba(99, 102, 241, 0.18);   /* indigo, top-left */
--bg-orb-2: rgba(139, 92, 246, 0.14);   /* violet, top-right */
--bg-orb-3: rgba(14, 165, 233, 0.10);   /* sky, bottom-center */
```

### Glass Surfaces (4 depth levels)

```css
--glass-1: rgba(255, 255, 255, 0.04);   /* sidebar, subtlest */
--glass-2: rgba(255, 255, 255, 0.06);   /* base cards */
--glass-3: rgba(255, 255, 255, 0.10);   /* elevated cards, modals */
--glass-4: rgba(255, 255, 255, 0.15);   /* hover states, active elements */
--glass-border: rgba(255, 255, 255, 0.08);
--glass-border-strong: rgba(255, 255, 255, 0.14);
--blur-sm: blur(10px) saturate(180%);
--blur-md: blur(20px) saturate(180%);
--blur-lg: blur(40px) saturate(200%);
```

### Accent Palette

```css
--primary: #6366f1;                      /* indigo */
--primary-hover: #4f46e5;
--primary-light: rgba(99, 102, 241, 0.15);
--primary-glow: 0 0 24px rgba(99, 102, 241, 0.35);
--violet: #8b5cf6;
--sky: #0ea5e9;
--emerald: #10b981;
--amber: #f59e0b;
--rose: #f43f5e;
```

### Text (white-on-dark opacity scale)

```css
--text-primary: rgba(255, 255, 255, 0.95);
--text-secondary: rgba(255, 255, 255, 0.60);
--text-muted: rgba(255, 255, 255, 0.35);
```

### Typography

```css
--font-display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
--font-body: 'Inter', -apple-system, sans-serif;
--font-mono: 'SF Mono', 'JetBrains Mono', Menlo, 'Courier New', monospace;
```

Google Fonts `<link>` updated to load:
`Inter:wght@400;500;600;700` and `JetBrains+Mono:wght@400;500` only — remove Plus Jakarta Sans.

### Shape + Motion

```css
--radius-sm: 8px;
--radius-md: 12px;
--radius-lg: 16px;
--radius-xl: 20px;
--radius-full: 9999px;
--sidebar-width: 220px;
--transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-base: 220ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-slow: 360ms cubic-bezier(0.4, 0, 0.2, 1);
```

### Shadows

```css
--shadow-glass: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06);
--shadow-glass-hover: 0 12px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.10);
--shadow-glow-primary: 0 0 24px rgba(99, 102, 241, 0.35);
--shadow-glow-emerald: 0 0 20px rgba(16, 185, 129, 0.30);
```

---

## Section 2 — Gradient Mesh Background

A `body::before` pseudo-element covers the full viewport, fixed, `z-index: -1`:

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

`body` background: `var(--bg-base)` (fallback, no gradient on body itself).

No CSS animation on the gradient in Cycle 1 — ambient orb motion is Cycle 4.

---

## Section 3 — Layout Shell

### HTML Structure Change

Replace the existing `<header>` + `<div class="main-container">` structure with:

```html
<div class="app-shell">
  <nav class="sidebar" id="sidebar">
    <!-- logo, nav items, status -->
  </nav>
  <main class="content-area" id="content-area">
    <!-- HUD stats row + tab panels (unchanged content) -->
  </main>
</div>
```

The existing footer is removed — status moves into the sidebar bottom.

### Sidebar CSS

```css
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
}

.content-area {
    margin-left: var(--sidebar-width);
    flex: 1;
    min-height: 100vh;
    padding: 32px 36px;
    overflow-y: auto;
}
```

### Sidebar Sections

**Logo area** (top):
```html
<div class="sidebar-logo">
  <div class="logo-icon">
    <i data-lucide="zap" style="width:14px;height:14px;"></i>
  </div>
  <span class="logo-text">Agent Echo</span>
</div>
<div class="sidebar-divider"></div>
```

Logo icon: `28×28px`, `background: linear-gradient(135deg, var(--primary), var(--violet))`, `border-radius: var(--radius-sm)`, `box-shadow: var(--shadow-glow-primary)`, icon stroke `#fff`.

Logo text: `font-family: var(--font-display)`, `font-weight: 700`, `font-size: 0.95rem`, `color: var(--text-primary)`, `letter-spacing: -0.3px`.

**Nav items** (middle, `flex: 1`):
```html
<nav class="sidebar-nav">
  <button class="nav-item active" onclick="switchTab('overview', this)">
    <i data-lucide="layout-dashboard"></i>
    <span>Overview</span>
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
</nav>
```

Nav item CSS:
```css
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 12px;
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all var(--transition-fast);
    text-align: left;
    border-left: 3px solid transparent;
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

.nav-item.active i,
.nav-item.active svg {
    color: var(--primary);
}

.nav-item i,
.nav-item svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
}
```

**Status chip** (bottom):
```html
<div class="sidebar-divider"></div>
<div class="sidebar-status" id="system-status">
  <span class="status-dot"></span>
  <span class="status-label">CONNECTED</span>
</div>
```

Status dot: `8px` circle, `background: var(--emerald)`, `animation: pulseDot 2s ease infinite`.
Status label: `font-size: 0.72rem`, `font-weight: 700`, `letter-spacing: 0.08em`, `text-transform: uppercase`, `color: var(--text-secondary)`.
Disconnected state: dot `var(--rose)`, label "OFFLINE".

Sidebar divider: `height: 1px`, `background: var(--glass-border)`, `margin: 12px 4px`.

---

## Section 4 — Animation Utilities

### CSS Keyframes (added to `<style>` block)

```css
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
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
    50%       { opacity: 0.7; box-shadow: 0 0 0 4px transparent; }
}

@keyframes shimmer {
    from { background-position: -400px 0; }
    to   { background-position: 400px 0; }
}

@keyframes progressBar {
    from { width: 100%; }
    to   { width: 0%; }
}
```

### Utility Classes

```css
.anim-fade-in-up    { animation: fadeInUp    280ms var(--transition-base) both; }
.anim-slide-in-right { animation: slideInRight 200ms var(--transition-base) both; }
.anim-scale-in      { animation: scaleIn     240ms var(--transition-base) both; }
```

Stagger: JS sets `style="--stagger: N"` (0-based index). Classes use:
```css
[style*="--stagger"] { animation-delay: calc(var(--stagger, 0) * 60ms); }
```

---

## Section 5 — Toast/Snackbar System

### HTML (added once, near `</body>`)

```html
<div id="toast-container" aria-live="polite" aria-atomic="false"></div>
```

CSS:
```css
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
.toast-message { flex: 1; font-size: 0.85rem; font-weight: 500; color: var(--text-primary); line-height: 1.4; }
.toast-close {
    background: none; border: none; cursor: pointer;
    color: var(--text-muted); padding: 0; line-height: 1;
    transition: color var(--transition-fast);
}
.toast-close:hover { color: var(--text-primary); }

.toast-progress {
    position: absolute;
    bottom: 0; left: 0;
    height: 2px;
    background: currentColor;
    opacity: 0.4;
}
```

### JS `showToast()` function

```javascript
const TOAST_ICONS = {
    success: 'check-circle',
    error:   'alert-circle',
    warning: 'alert-triangle',
    info:    'info',
};

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');

    // Cap at 3 visible toasts
    while (container.children.length >= 3) {
        dismissToast(container.firstElementChild);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i data-lucide="${TOAST_ICONS[type] || 'info'}" class="toast-icon"></i>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="dismissToast(this.parentElement)" aria-label="Close">
            <i data-lucide="x" style="width:14px;height:14px;"></i>
        </button>
        <div class="toast-progress" style="animation: progressBar ${duration}ms linear forwards;"></div>
    `;

    container.appendChild(toast);
    lucide.createIcons({ nodes: [toast] });

    const timer = setTimeout(() => dismissToast(toast), duration);
    toast._dismissTimer = timer;
}

function dismissToast(toast) {
    if (!toast || !toast.isConnected) return;
    clearTimeout(toast._dismissTimer);
    toast.style.animation = 'slideOutToRight 250ms ease forwards';
    setTimeout(() => toast.remove(), 250);
}
```

`showToast` replaces all `alert()` calls in the existing JS.

---

## Files Changed

- `dashboard.html` — only file touched
  - `<head>`: update Google Fonts link, add Lucide CDN script
  - `<style>`: replace `:root`, add gradient bg, sidebar CSS, animation keyframes, utility classes, toast CSS
  - `<body>`: replace `<header>` + `<main>` with `<div class="app-shell">`, add `#toast-container`
  - `<script>`: add `showToast()`, `dismissToast()`, call `lucide.createIcons()` on DOMContentLoaded, update `switchTab()` to set `.active` on `.nav-item` elements, replace existing `alert()` calls with `showToast()`

---

## Out of Scope (Cycle 2+)

- HUD stat card glass treatment → Cycle 2
- Draft/Queue/Analytics/Chat panel redesign → Cycle 3
- Modal glass redesign → Cycle 2
- Countup animations, card stagger → Cycle 4
- Ambient gradient orb motion → Cycle 4

---

## Success Criteria

1. Page loads with dark gradient mesh background visible
2. Left sidebar shows logo, 5 nav items with Lucide icons, status chip at bottom
3. All 6 existing tab panels still work (content unchanged, just repositioned)
4. `showToast('Test', 'success')` in console shows a glass toast bottom-right
5. No JavaScript errors in browser console
6. `lucide.createIcons()` runs without errors on page load
