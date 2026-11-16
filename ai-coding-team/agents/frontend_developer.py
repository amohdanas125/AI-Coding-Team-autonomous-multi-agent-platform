"""Frontend Developer agent: takes the PM spec plus the Backend Developer's
api_contract (schemas.BACKEND_OUTPUT_SCHEMA's api_contract field - NOT its
source code) and generates a working React frontend
(schemas.FRONTEND_OUTPUT_SCHEMA) that calls those exact endpoints.

Internally makes ONE call per page plus ONE "skeleton" call, instead of a
single call for the whole frontend - same reason and pattern as
agents/backend_developer.py: a single call for a multi-page app can
exceed a free-tier token limit (seen directly on Groq: 11301 tokens
requested for a 5-page/11-endpoint app against an 8000 limit).
generate_frontend()'s external signature and return shape are UNCHANGED
by this.

Runs on Gemini, not Groq - per-page calls were still tight against Groq's
8000-token TPM ceiling even after splitting, since api_contract alone
could be sizeable on a many-endpoint app. Only this agent moved; PM and
Backend Developer stayed on Groq, since neither had the same problem.
"""
import json

from groq_client import call_agent
from schemas import FRONTEND_PAGE_OUTPUT_SCHEMA, FRONTEND_SKELETON_OUTPUT_SCHEMA

PAGE_SYSTEM_PROMPT = """You are the Frontend Developer agent in a multi-agent system that builds modern, tactile CRUD web apps in React using a modern Neomorphism (Soft UI) design system. You will be given ONE page from a larger app - its name, route, description, and primary_entity - plus the scoped api_contract (endpoints this page needs), reference_lookups for any picker fields, and whether the app requires auth. Generate the React component for THIS page only.

Tech stack - use exactly this:
- A single functional component using hooks (useState, useEffect, useNavigate, useParams, Link)
- Import the shared API helper as `import { apiFetch } from '../api'` - it already handles the base URL, the auth token, and 401 redirects. NEVER call fetch() directly - always go through apiFetch(path, options).
- The shared CSS (src/index.css) provides a complete tactile Neomorphism (Soft UI) design system with extruded dual-shadow cards and inset form controls. Use them to make the page visually stunning:
  - Neomorphic Surfaces & Cards: .hero-banner, .stats-grid, .stat-card, .stat-icon, .stat-val, .stat-label, .grid-cards, .app-card, .card-cover, .card-body, .card-title, .card-meta, .card-footer, .card-badge, .neu-card
  - Inset Controls & Search: .search-wrapper, .search-input, .search-icon, .form-group, .form-label, .form-input, .form-select, .form-textarea, .neu-input
  - Neomorphic Buttons & Pills: .btn-primary, .btn-accent, .btn-secondary, .btn-danger, .neu-btn, .filter-pills, .filter-pill (.active), .badge (.badge-primary, .badge-success, .badge-warning, .badge-danger)
  - Detail & Relational Views: .detail-header, .detail-title, .detail-meta, .items-grid, .item-card, .item-info, .item-desc, .item-footer, .item-price, .qty-control, .btn-qty, .qty-number
  - Floating Drawers & Modals: .cart-floating-bar, .cart-summary, .cart-count-badge, .cart-total, .btn-checkout, .modal-overlay, .modal-box, .modal-header, .modal-title, .modal-close
  - Auth, Alerts & Empty States: .auth-container, .auth-card, .auth-tabs, .auth-tab (.active), .demo-credentials-box, .alert, .alert-success, .alert-error, .empty-state, .empty-state-icon, .btn-secondary

Page Implementation Patterns:
1. Listing / Dashboard Pages (e.g. Workouts, Books, Products, Tasks):
   - At the top, always render 2-4 KPI Stat Cards (.stats-grid with .stat-card) summarizing key metrics (e.g., Total Records, Active / Completed Items, Streaks or Highlights) with an emoji icon (.stat-icon), numeric value (.stat-val), and label (.stat-label).
   - Render a neomorphic hero section (.hero-banner) with a real-time search filter input (.search-input) that filters the list instantly by text.
   - Optional category filter pills (.filter-pills > .filter-pill) to filter items by category or status.
   - Render items in a responsive grid (.grid-cards) of tactile cards (.app-card) with an emoji banner (.card-cover), title (.card-title), metadata (.card-meta), category badge (.card-badge), and a CTA button or Link to its detail route.
2. Detail & Relational Pages (e.g. WorkoutDetail, BookDetail, OrderDetail, route like /:entity/:id):
   - Fetch the parent record via GET /:entity/:id.
   - If related child records exist in api_contract (e.g. exercises for a workout, items for an order, reviews for a book), fetch them, filter for this parent's id, and render them in a tactile .items-grid of .item-card components.
   - Include interactive actions: e.g. quantity selectors, status updates, or a "Add Item" button that opens an embossed modal or form.
3. Creation / Management & Forms:
   - Use soft inset inputs (.form-input, .form-select) with clear labels (.form-label).
   - If any field is a reference to another entity (found in reference_lookups), fetch the options from its list_endpoint and render a dropdown <select className="form-select"> so users choose real records rather than typing IDs.
4. Login / Register Pages (e.g. LoginPage):
   - Render .auth-container and .auth-card with segmented neomorphic tabs for Sign In vs Create Account.
   - Include a "One-Click Fill Demo Credentials" button that fills 'alice@example.com' / 'Password123!' for instant testing.
   - On login, save data.token to localStorage.setItem('token', data.token) and navigate to '/'.

File to produce, exactly this one path:
- src/pages/<page name exactly as given>.jsx - a default-exported component implementing this page.

CRITICAL FORMATTING:
- Never backslash-escape single quotes inside string literals (write 'Do not', never \\'Do not\\').
- Output must be strictly conforming JSON without invalid escape sequences matching FRONTEND_PAGE_OUTPUT_SCHEMA."""

SKELETON_SYSTEM_PROMPT = """You are the Frontend Developer agent, generating the shared skeleton files for a small React (Vite) app - NOT any individual page, those already exist as separately generated files named src/pages/<page name>.jsx for every page name you're given.

Tech stack - use exactly this, no substitutions:
- React with Vite as the build tool, react-router-dom for routing
- Native browser fetch inside the one shared API helper - no axios or other HTTP libraries anywhere
- Plain CSS, one small stylesheet - this is a functional demo, not a design showcase. No UI framework or component library.

Files to produce - use exactly these paths, one entry in `files` per file:
- package.json - react, react-dom, react-router-dom as dependencies; vite and @vitejs/plugin-react as devDependencies; "dev" and "build" scripts.
- vite.config.js - standard Vite + React plugin config. Do NOT set server.port to 3000 or to any value matching the backend API's port - this config is for the dev server that serves the frontend's OWN files, which must run on a different port than the backend it calls. Leave the dev server port at Vite's own default (5173) unless there's a specific reason to change it.
- index.html - Vite's entry HTML, loading /src/main.jsx as a module.
- src/main.jsx - mounts <App /> inside a BrowserRouter.
- src/App.jsx - renders a clean top navigation bar with the app title and Links to the app pages (and a Login/Logout button reading from localStorage 'token'), wrapping the page components in a clean centered `<main className="main-content">` containing <Routes>, one <Route> per page you're given, importing each page's component from './pages/<page name>' and matching that page's route.
- src/api.js - export a single apiFetch(path, options) function: reads a token from localStorage under the key 'token', attaches "Authorization: Bearer <token>" header on every request when present, and on a 401 response clears token and redirects to /login. Base URL is import.meta.env.VITE_API_BASE with fallback 'http://localhost:3000'. Parses and returns the response body data (and attaches data.json = async () => data; data.ok = true; when data is an object/array so callers can use either direct data or res.json()). Check response.ok and throw Error with useful message on failure. Every page imports and uses this helper.
- src/index.css - a clean, modern CSS stylesheet: system font family, a sticky top navbar (.navbar, .nav-container, .brand-logo, .nav-links), a centered container (.main-content with max-width: 1080px; margin: 0 auto; padding: 2rem;), modern table styling with borders/padding/hover states on tr, form styling with readable labels, styled inputs with focus borders, and clean primary-colored buttons. Keep it self-contained without external dependencies.

setup_notes: a short string - anything a developer should know before running this.

Keep it minimal and correct. If something is ambiguous, make the simplest reasonable choice and note it in setup_notes. The output must be strictly conforming JSON without invalid escape sequences."""


def _build_vite_config_js() -> str:
    return """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173
  }
});
"""


def _build_index_html(app_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{app_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""


def _build_main_jsx() -> str:
    return """import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
"""


def _build_index_css() -> str:
    """Deterministic tactile Neomorphism (Soft UI) design system stylesheet - NOT an LLM call.
    Rule #1 of project architecture: Anything a program can compute, compute
    in Python rather than asking an LLM. Guarantees that every generated
    frontend immediately looks attractive and responsive with zero token burn."""
    return """/* ========================================================
   TACTILE NEOMORPHISM (SOFT UI) DESIGN SYSTEM
   Autonomous Multi-Agent Generated Frontend Engine
   ======================================================== */
:root {
  /* Canvas & Soft Surfaces */
  --bg: #e6ecf5;
  --bg-subtle: #edf2f9;
  --surface: #e6ecf5;
  --surface-raised: #e9eff8;
  --text: #1e293b;
  --text-muted: #64748b;
  --text-light: #94a3b8;

  /* Primary Accent & Vibrancy */
  --primary: #4f46e5;
  --primary-hover: #4338ca;
  --primary-light: #e0e7ff;
  --primary-glow: rgba(79, 70, 229, 0.3);
  --accent-cyan: #06b6d4;
  --accent-emerald: #10b981;
  --accent-rose: #f43f5e;
  --accent-amber: #f59e0b;

  /* Dual Neomorphic Shadows */
  --neu-flat: 8px 8px 18px #c2c8d4, -8px -8px 18px #ffffff;
  --neu-flat-sm: 4px 4px 10px #c2c8d4, -4px -4px 10px #ffffff;
  --neu-flat-lg: 14px 14px 28px #bcc3cf, -14px -14px 28px #ffffff;
  --neu-inset: inset 4px 4px 8px #c2c8d4, inset -4px -4px 8px #ffffff;
  --neu-inset-sm: inset 2px 2px 5px #c2c8d4, inset -2px -2px 5px #ffffff;
  --neu-hover: 12px 12px 24px #bcc3cf, -12px -12px 24px #ffffff;
  --neu-pressed: inset 5px 5px 10px #c2c8d4, inset -5px -5px 10px #ffffff;

  /* Border Radii */
  --radius-sm: 10px;
  --radius: 18px;
  --radius-lg: 26px;
  --radius-full: 9999px;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* --- Sticky Neomorphic Navbar --- */
.navbar {
  background: rgba(230, 236, 245, 0.94);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 4px 20px rgba(194, 200, 212, 0.55);
  border-bottom: 1px solid rgba(255, 255, 255, 0.7);
}

.nav-container {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0.9rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-logo {
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--primary);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  letter-spacing: -0.02em;
  background: var(--bg);
  padding: 0.35rem 0.9rem;
  border-radius: var(--radius-full);
  box-shadow: var(--neu-flat-sm);
  transition: all 0.2s ease;
}

.brand-logo:hover {
  box-shadow: var(--neu-hover);
  color: var(--primary-hover);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.nav-links a {
  color: var(--text-muted);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.92rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-full);
  transition: all 0.2s ease;
}

.nav-links a:hover {
  color: var(--primary);
  box-shadow: var(--neu-flat-sm);
}

.nav-links a.active {
  color: var(--primary);
  box-shadow: var(--neu-inset-sm);
  font-weight: 700;
}

.btn-nav {
  background: var(--bg);
  color: var(--primary) !important;
  padding: 0.55rem 1.35rem !important;
  border-radius: var(--radius-full) !important;
  font-size: 0.9rem !important;
  font-weight: 700 !important;
  border: none;
  cursor: pointer;
  text-decoration: none;
  box-shadow: var(--neu-flat-sm);
  transition: all 0.2s ease;
}

.btn-nav:hover {
  box-shadow: var(--neu-hover);
  transform: translateY(-1px);
}

.btn-nav:active {
  box-shadow: var(--neu-pressed);
}

/* --- Main Layout Container --- */
.main-content {
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
  padding: 2.25rem 1.5rem 5rem;
  flex: 1;
}

/* --- Neomorphic Hero Section --- */
.hero-banner {
  background: var(--bg);
  border-radius: var(--radius-lg);
  padding: 3rem 2rem;
  margin-bottom: 2.5rem;
  box-shadow: var(--neu-flat-lg);
  border: 1px solid rgba(255, 255, 255, 0.7);
  text-align: center;
  position: relative;
  overflow: hidden;
}

.hero-banner h1 {
  font-size: 2.6rem;
  font-weight: 800;
  margin: 0 0 0.85rem 0;
  color: var(--text);
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, #1e293b 0%, #4338ca 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-banner p {
  font-size: 1.15rem;
  color: var(--text-muted);
  max-width: 620px;
  margin: 0 auto 1.75rem;
  line-height: 1.6;
}

/* --- Inset Search Control --- */
.search-wrapper {
  max-width: 500px;
  margin: 0 auto;
  position: relative;
}

.search-input {
  width: 100%;
  padding: 1rem 1.25rem 1rem 3.1rem;
  font-size: 1rem;
  font-family: inherit;
  border-radius: var(--radius-full);
  border: none;
  background: var(--bg);
  box-shadow: var(--neu-inset);
  color: var(--text);
  outline: none;
  transition: all 0.2s ease;
}

.search-input:focus {
  box-shadow: var(--neu-inset), 0 0 0 2px var(--primary-glow);
}

.search-icon {
  position: absolute;
  left: 1.15rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.2rem;
  color: var(--text-light);
  pointer-events: none;
}

/* --- KPI / Summary Stats Grid --- */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2.5rem;
}

.stat-card {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 1.5rem;
  box-shadow: var(--neu-flat);
  border: 1px solid rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  gap: 1.25rem;
  transition: all 0.25s ease;
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--neu-hover);
}

.stat-icon {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: var(--bg);
  box-shadow: var(--neu-flat-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6rem;
  flex-shrink: 0;
}

.stat-val {
  font-size: 1.9rem;
  font-weight: 800;
  color: var(--text);
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.stat-label {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 0.35rem;
}

/* --- Category Filter Pills --- */
.filter-pills {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 2rem;
  align-items: center;
}

.filter-pill {
  background: var(--bg);
  border: none;
  border-radius: var(--radius-full);
  padding: 0.55rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  font-family: inherit;
  color: var(--text-muted);
  box-shadow: var(--neu-flat-sm);
  cursor: pointer;
  transition: all 0.2s ease;
}

.filter-pill:hover {
  color: var(--primary);
  box-shadow: var(--neu-hover);
}

.filter-pill.active {
  box-shadow: var(--neu-pressed);
  color: var(--primary);
  font-weight: 800;
}

/* --- Section Headers --- */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.75rem;
}

.section-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: var(--text);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  letter-spacing: -0.02em;
}

/* --- Neomorphic Card Grids (Universal & Food Aliases) --- */
.grid-cards,
.restaurant-grid,
.menu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 2rem;
  margin-bottom: 2.5rem;
}

.app-card,
.restaurant-card,
.menu-card,
.neu-card {
  background: var(--bg);
  border: 1px solid rgba(255, 255, 255, 0.65);
  border-radius: var(--radius);
  padding: 1.5rem;
  box-shadow: var(--neu-flat);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
  position: relative;
  overflow: hidden;
}

.app-card:hover,
.restaurant-card:hover,
.menu-card:hover,
.neu-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--neu-hover);
  text-decoration: none;
}

.card-cover {
  height: 130px;
  background: var(--bg);
  border-radius: var(--radius-sm);
  box-shadow: var(--neu-inset-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3.5rem;
  position: relative;
  margin-bottom: 1.25rem;
}

.card-badge,
.card-cuisine-badge {
  position: absolute;
  bottom: 0.75rem;
  right: 0.75rem;
  background: var(--bg);
  color: var(--primary);
  font-weight: 800;
  font-size: 0.75rem;
  padding: 0.3rem 0.75rem;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  box-shadow: var(--neu-flat-sm);
}

.card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-title {
  font-size: 1.3rem;
  font-weight: 800;
  color: var(--text);
  margin: 0 0 0.5rem 0;
  letter-spacing: -0.01em;
}

.card-meta,
.card-address {
  color: var(--text-muted);
  font-size: 0.92rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 1.25rem;
  flex: 1;
}

.card-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 1rem;
  border-top: 1px solid rgba(194, 200, 212, 0.35);
  font-weight: 700;
  font-size: 0.92rem;
  color: var(--primary);
}

/* --- Neomorphic Buttons --- */
.neu-btn,
.btn-primary,
.btn-checkout,
.btn-add {
  background: var(--bg);
  color: var(--primary);
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 700;
  font-size: 0.95rem;
  font-family: inherit;
  padding: 0.75rem 1.5rem;
  box-shadow: var(--neu-flat-sm);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  text-decoration: none;
  transition: all 0.2s ease;
}

.neu-btn:hover,
.btn-primary:hover,
.btn-checkout:hover,
.btn-add:hover {
  color: var(--primary-hover);
  box-shadow: var(--neu-hover);
  transform: translateY(-1px);
}

.neu-btn:active,
.btn-primary:active,
.btn-checkout:active,
.btn-add:active {
  box-shadow: var(--neu-pressed);
  transform: scale(0.98);
}

.btn-accent {
  background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
  color: #ffffff !important;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 700;
  font-size: 0.95rem;
  font-family: inherit;
  padding: 0.75rem 1.6rem;
  box-shadow: 6px 6px 14px rgba(79, 70, 229, 0.35), -6px -6px 14px #ffffff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  text-decoration: none;
  transition: all 0.2s ease;
}

.btn-accent:hover {
  box-shadow: 8px 8px 18px rgba(79, 70, 229, 0.5), -8px -8px 18px #ffffff;
  transform: translateY(-2px);
}

.btn-accent:active {
  box-shadow: inset 4px 4px 8px rgba(0, 0, 0, 0.2);
  transform: scale(0.98);
}

.btn-secondary {
  background: var(--bg);
  color: var(--text-muted);
  border: none;
  font-weight: 700;
  font-family: inherit;
  padding: 0.65rem 1.35rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  box-shadow: var(--neu-flat-sm);
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  color: var(--text);
  box-shadow: var(--neu-hover);
}

.btn-secondary:active {
  box-shadow: var(--neu-pressed);
}

.btn-danger {
  background: var(--bg);
  color: var(--accent-rose);
  border: none;
  font-weight: 700;
  font-family: inherit;
  padding: 0.65rem 1.35rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  box-shadow: var(--neu-flat-sm);
  transition: all 0.2s ease;
}

.btn-danger:hover {
  box-shadow: var(--neu-hover);
}

.btn-danger:active {
  box-shadow: var(--neu-pressed);
}

/* --- Inset Form Controls --- */
.form-group {
  margin-bottom: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--text);
}

.form-input,
.form-select,
.form-textarea,
.neu-input {
  width: 100%;
  padding: 0.85rem 1.15rem;
  font-size: 0.95rem;
  font-family: inherit;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--bg);
  box-shadow: var(--neu-inset);
  color: var(--text);
  outline: none;
  transition: all 0.2s ease;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus,
.neu-input:focus {
  box-shadow: var(--neu-inset), 0 0 0 2px var(--primary-glow);
}

/* --- Stepper Controls (Quantity / Counters) --- */
.qty-control {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.btn-qty {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg);
  color: var(--primary);
  border: none;
  font-size: 1.2rem;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  box-shadow: var(--neu-flat-sm);
  transition: all 0.15s ease;
}

.btn-qty:hover {
  box-shadow: var(--neu-hover);
  color: var(--primary-hover);
}

.btn-qty:active {
  box-shadow: var(--neu-pressed);
}

.qty-number {
  font-weight: 800;
  font-size: 1.1rem;
  min-width: 28px;
  text-align: center;
}

/* --- Detail & Relational Views --- */
.detail-header,
.restaurant-header {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 2.25rem;
  margin-bottom: 2.5rem;
  box-shadow: var(--neu-flat);
  border: 1px solid rgba(255, 255, 255, 0.7);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1.5rem;
}

.detail-title,
.restaurant-info h1 {
  font-size: 2.2rem;
  font-weight: 800;
  margin: 0 0 0.5rem 0;
  color: var(--text);
  letter-spacing: -0.02em;
}

.detail-meta,
.restaurant-meta {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  color: var(--text-muted);
  font-size: 0.95rem;
}

.cuisine-tag {
  background: var(--bg);
  color: var(--primary);
  font-weight: 800;
  font-size: 0.8rem;
  padding: 0.35rem 0.85rem;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  box-shadow: var(--neu-flat-sm);
}

.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.75rem;
  margin-bottom: 3rem;
}

.item-card {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 1.5rem;
  box-shadow: var(--neu-flat);
  border: 1px solid rgba(255, 255, 255, 0.6);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: all 0.2s ease;
}

.item-card:hover {
  box-shadow: var(--neu-hover);
}

.item-info h3,
.menu-info h3 {
  margin: 0 0 0.5rem 0;
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--text);
}

.item-desc,
.menu-desc {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin: 0 0 1.25rem 0;
  min-height: 2.7rem;
}

.item-footer,
.menu-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 1rem;
  border-top: 1px solid rgba(194, 200, 212, 0.4);
}

.item-price,
.menu-price {
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--primary);
}

/* --- Floating Bar Drawer --- */
.cart-floating-bar {
  position: fixed;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg);
  color: var(--text);
  padding: 1rem 2rem;
  border-radius: var(--radius-full);
  box-shadow: var(--neu-flat-lg);
  border: 1px solid rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  z-index: 99;
  width: 90%;
  max-width: 620px;
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slideUp {
  from { transform: translate(-50%, 100%); opacity: 0; }
  to { transform: translate(-50%, 0); opacity: 1; }
}

.cart-summary {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.cart-count-badge {
  background: var(--primary);
  color: white;
  font-weight: 800;
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-full);
  font-size: 0.85rem;
}

.cart-total {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text);
}

/* --- Neomorphic Badges --- */
.badge,
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.85rem;
  border-radius: var(--radius-full);
  font-size: 0.8rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg);
  box-shadow: var(--neu-flat-sm);
}

.badge-primary,
.status-badge.confirmed,
.status-badge.shipped {
  color: var(--primary);
}

.badge-success,
.status-badge.delivered,
.status-badge.completed {
  color: #059669;
}

.badge-warning,
.status-badge.pending,
.status-badge.placed {
  color: #d97706;
}

.badge-danger,
.status-badge.cancelled {
  color: #dc2626;
}

/* --- Authentication Card --- */
.auth-container {
  max-width: 460px;
  margin: 3rem auto;
}

.auth-card {
  background: var(--bg);
  border-radius: var(--radius-lg);
  padding: 2.5rem;
  box-shadow: var(--neu-flat-lg);
  border: 1px solid rgba(255, 255, 255, 0.8);
}

.auth-tabs {
  display: flex;
  background: var(--bg);
  box-shadow: var(--neu-inset);
  border-radius: var(--radius-full);
  padding: 5px;
  margin-bottom: 2rem;
}

.auth-tab {
  flex: 1;
  text-align: center;
  padding: 0.75rem 0;
  font-weight: 700;
  font-size: 0.95rem;
  font-family: inherit;
  color: var(--text-muted);
  border: none;
  background: none;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all 0.2s ease;
}

.auth-tab.active {
  background: var(--bg);
  box-shadow: var(--neu-flat-sm);
  color: var(--primary);
  font-weight: 800;
}

.demo-credentials-box {
  background: var(--bg);
  box-shadow: var(--neu-inset-sm);
  border-radius: var(--radius-sm);
  padding: 1.1rem;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.demo-credentials-box button {
  background: var(--bg);
  color: var(--primary);
  font-size: 0.82rem;
  font-weight: 700;
  font-family: inherit;
  padding: 0.45rem 0.9rem;
  border-radius: var(--radius-full);
  border: none;
  cursor: pointer;
  margin-top: 0.75rem;
  box-shadow: var(--neu-flat-sm);
  transition: all 0.2s ease;
}

.demo-credentials-box button:hover {
  box-shadow: var(--neu-hover);
}

.demo-credentials-box button:active {
  box-shadow: var(--neu-pressed);
}

/* --- Alerts & Empty States --- */
.alert {
  padding: 1rem 1.25rem;
  border-radius: var(--radius-sm);
  font-size: 0.92rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
  background: var(--bg);
  box-shadow: var(--neu-inset-sm);
}

.alert-success {
  color: #059669;
}

.alert-error {
  color: #dc2626;
}

.empty-state {
  text-align: center;
  padding: 3.5rem 1.5rem;
  background: var(--bg);
  border-radius: var(--radius);
  box-shadow: var(--neu-inset);
  color: var(--text-muted);
}

.empty-state-icon {
  font-size: 3.2rem;
  margin-bottom: 1rem;
}
"""


def _relevant_endpoints(page: dict, api_contract: list, spec_endpoints: list, relationships: list | None = None) -> list:
    """Filter api_contract down to entries whose path maps to this page's
    primary_entity, using spec_endpoints (PM_SPEC_SCHEMA's 'endpoints',
    which carries 'entity' - api_contract itself doesn't). Also includes
    directly related child entities (from relationships) for detail pages,
    so pages like RestaurantDetailPage receive /menuitems in their contract.
    Falls back to the full contract if no match is found."""
    entity = page.get("primary_entity")
    if not entity:
        return api_contract

    entity_by_path = {ep["path"]: ep["entity"] for ep in spec_endpoints}

    relevant_entities = {entity}
    is_detail_or_has_child = ":" in page.get("route", "") or "detail" in page.get("name", "").lower()
    if relationships and is_detail_or_has_child:
        for rel in relationships:
            if rel.get("from_entity") == entity:
                relevant_entities.add(rel.get("to_entity"))

    desc_lower = (page.get("description") or "").lower()
    for ep in spec_endpoints:
        ep_entity = ep.get("entity", "")
        if ep_entity and ep_entity.lower() in desc_lower:
            relevant_entities.add(ep_entity)

    matches = [
        ep for ep in api_contract
        if entity_by_path.get(ep["path"]) in relevant_entities
    ]
    return matches if matches else api_contract


def _find_list_endpoint_for_entity(entity_name: str, full_api_contract: list, spec_endpoints: list) -> str | None:
    """Find the GET list-endpoint path (no :id segment) for a given entity,
    using spec_endpoints to bridge entity names to api_contract paths -
    same bridging problem _relevant_endpoints solves, reused here so a
    reference field's dropdown knows exactly where to fetch its options
    from, instead of the model having to guess."""
    entity_by_path = {ep["path"]: ep["entity"] for ep in spec_endpoints}
    for ep in full_api_contract:
        if ep["method"] == "GET" and entity_by_path.get(ep["path"]) == entity_name and ":" not in ep["path"]:
            return ep["path"]
    return None


def _reference_field_lookups(scoped_contract: list, full_api_contract: list, spec_endpoints: list) -> dict:
    """For every is_reference field in this page's scoped contract, resolve
    where to fetch that referenced entity's records from. Deliberately
    looked up against full_api_contract, not scoped_contract - the
    referenced entity's own list endpoint (e.g. GET /restaurants, needed
    to populate an Order page's restaurant picker) was very likely
    filtered OUT of scoped_contract by _relevant_endpoints, since it
    belongs to a different entity than this page's own primary_entity.
    Confirmed live as the root cause of a generated Order form sending a
    restaurant NAME as free text - Frontend Developer had no way to know
    the field needed a real _id, or where to get one, without this."""
    lookups = {}
    for ep in scoped_contract:
        for field in ep.get("request_body_fields", []):
            if field.get("is_reference") and field.get("references_entity"):
                list_endpoint = _find_list_endpoint_for_entity(
                    field["references_entity"], full_api_contract, spec_endpoints
                )
                if list_endpoint:
                    lookups[field["name"]] = {
                        "references_entity": field["references_entity"],
                        "list_endpoint": list_endpoint,
                    }
    return lookups


def generate_page(page: dict, api_contract: list, spec_endpoints: list, auth_required: bool, relationships: list | None = None) -> dict:
    """Generate one page's component. Internal helper - see
    generate_frontend() for the public interface."""
    scoped_contract = _relevant_endpoints(page, api_contract, spec_endpoints, relationships=relationships)
    reference_lookups = _reference_field_lookups(scoped_contract, api_contract, spec_endpoints)
    print(f"  [{page['name']}] scoped api_contract: {len(scoped_contract)}/{len(api_contract)} endpoints"
          + (f", reference lookups: {list(reference_lookups.keys())}" if reference_lookups else ""))
    user_prompt = json.dumps(
        {
            "page": page,
            "api_contract": scoped_contract,
            "reference_lookups": reference_lookups,
            "auth_required": auth_required,
        },
        indent=2,
    )
    return call_agent(
        system_prompt=PAGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=FRONTEND_PAGE_OUTPUT_SCHEMA,
        schema_name="frontend_page_output",
        max_tokens=6000,  # was 2500
    )


def generate_frontend_skeleton(app_name: str, auth_required: bool, pages: list) -> dict:
    """Generate the shared package.json/vite/main/App/api/css files.
    Internal helper - see generate_frontend() for the public interface."""
    minimal_pages = [{"name": p["name"], "route": p["route"]} for p in pages]
    user_prompt = json.dumps(
        {"app_name": app_name, "auth_required": auth_required, "pages": minimal_pages},
        indent=2,
    )
    return call_agent(
        system_prompt=SKELETON_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=FRONTEND_SKELETON_OUTPUT_SCHEMA,
        schema_name="frontend_skeleton_output",
        max_tokens=5000,
    )


def generate_frontend(spec: dict, api_contract: list) -> dict:
    """Generate a full frontend from a PM spec and a Backend Developer
    api_contract. Returns a dict shaped like schemas.FRONTEND_OUTPUT_SCHEMA,
    same as always - internally makes several smaller calls (one per page,
    one for the skeleton) instead of one big one. Call spacing is handled
    automatically inside gemini_client.call_agent. See module docstring.

    Deliberately takes api_contract as its own argument rather than the
    whole backend output - passing the generated source code here would
    defeat the point of having a contract in the first place."""
    all_files = []

    for page in spec["pages"]:
        result = generate_page(
            page,
            api_contract,
            spec["endpoints"],
            spec["auth_required"],
            relationships=spec.get("relationships"),
        )
        all_files.extend(result["files"])

    skeleton = generate_frontend_skeleton(spec["app_name"], spec["auth_required"], spec["pages"])
    for f in skeleton["files"]:
        # Unescape any literal escaped newlines or quotes if LLM double-escaped
        if isinstance(f.get("content"), str) and "\n" not in f["content"] and r"\n" in f["content"]:
            f["content"] = f["content"].replace(r"\n", "\n").replace(r'\"', '"')

        if f["path"] == "src/index.css":
            f["content"] = _build_index_css()
        elif f["path"] == "vite.config.js":
            f["content"] = _build_vite_config_js()
        elif f["path"] == "index.html":
            f["content"] = _build_index_html(spec.get("app_name", "App"))
        elif f["path"] == "src/main.jsx":
            f["content"] = _build_main_jsx()
        elif f["path"] == "package.json":
            # Sanitize package.json content to eliminate any literal escaped quotes (\") produced by LLMs
            try:
                clean_content = f["content"].replace('\\"', '"')
                parsed_json = json.loads(clean_content)
                parsed_json.setdefault("type", "module")
                f["content"] = json.dumps(parsed_json, indent=2)
            except Exception:
                pass
    all_files.extend(skeleton["files"])

    return {
        "files": all_files,
        "setup_notes": skeleton["setup_notes"],
    }
