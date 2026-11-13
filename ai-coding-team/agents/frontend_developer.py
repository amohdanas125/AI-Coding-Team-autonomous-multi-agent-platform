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

PAGE_SYSTEM_PROMPT = """You are the Frontend Developer agent in a multi-agent system that builds modern, attractive CRUD web apps in React. You will be given ONE page from a larger app - its name, route, description, and primary_entity - plus the scoped api_contract (endpoints this page needs), reference_lookups for any picker fields, and whether the app requires auth. Generate the React component for THIS page only.

Tech stack - use exactly this:
- A single functional component using hooks (useState, useEffect, useNavigate, useParams, Link)
- Import the shared API helper as `import { apiFetch } from '../api'` - it already handles the base URL, the auth token, and 401 redirects. NEVER call fetch() directly - always go through apiFetch(path, options).
- The shared CSS (src/index.css) already provides a complete, modern design system with ready-to-use classes. Use them to make the page visually engaging:
  - Containers & Grids: .hero-banner, .search-wrapper, .search-input, .search-icon, .section-header, .section-title, .restaurant-grid, .restaurant-card, .card-cover, .card-body, .card-title, .card-address, .card-cta, .card-cuisine-badge
  - Restaurant & Menu Details: .restaurant-header, .restaurant-info, .restaurant-meta, .cuisine-tag, .menu-grid, .menu-card, .menu-info, .menu-desc, .menu-footer, .menu-price
  - Cart & Ordering Controls: .qty-control, .btn-qty, .qty-number, .btn-add, .cart-floating-bar, .cart-summary, .cart-count-badge, .cart-total, .btn-checkout
  - Order History & Tracking: .order-card, .order-header, .order-id, .order-date, .status-badge (.pending, .confirmed, .delivered, .cancelled)
  - Auth, Alerts & Empty States: .auth-container, .auth-card, .auth-tabs, .auth-tab, .demo-credentials-box, .alert, .alert-success, .alert-error, .empty-state, .empty-state-icon, .btn-secondary

Page Implementation Patterns:
1. Listing / Catalog Pages (e.g. RestaurantListPage):
   - Render a hero banner at the top with a real-time search filter input (.search-input) that filters the list by name, cuisine, or address.
   - Render items in a responsive grid (.restaurant-grid) of attractive cards (.restaurant-card) with an emoji icon for the category/cuisine, location/details, and a CTA link ("View Menu & Order →") to its detail route.
2. Detail Pages (e.g. RestaurantDetailPage, route like /restaurants/:id):
   - Fetch the parent entity details via its GET endpoint (e.g. /restaurants/:id).
   - If related child items exist in api_contract (e.g. /menuitems), fetch them, filter for this parent's id (e.g. matching item.restaurant), and render them in a .menu-grid of .menu-card items.
   - Each item displays its name, description, price ($XX.XX), and an interactive quantity selector (- / count / +) or Add to Order button.
   - Maintain a cart state: when items are selected, display the floating bottom drawer (.cart-floating-bar) showing item count, total price, and "Confirm & Place Order →".
   - On checkout: check localStorage.getItem('token'). If not logged in, prompt to log in and redirect to /login. If logged in, create the order (POST /orders and POST /orderitems), show a success banner, and clear the cart.
3. Order History Pages (e.g. OrderPage):
   - If not logged in (!localStorage.getItem('token')), show a card with a message and a button linking to /login.
   - If logged in, fetch orders and render .order-card items with formatted timestamps, status badges (.status-badge), and a cancel button (DELETE /orders/:id).
4. Login / Register Pages (e.g. LoginPage):
   - Render .auth-container and .auth-card with tabs for Sign In vs Create Account.
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


def _build_index_css() -> str:
    """Deterministic modern design system stylesheet - NOT an LLM call.
    Rule #1 of project architecture: Anything a program can compute, compute
    in Python rather than asking an LLM. Guarantees that every generated
    frontend immediately looks attractive and responsive with zero token burn."""
    return """/* Modern, Attractive Food Delivery Design System */
:root {
  --primary: #ea580c;
  --primary-hover: #c2410c;
  --primary-light: #fff7ed;
  --primary-border: #fed7aa;
  --secondary: #0f172a;
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-muted: #f1f5f9;
  --text: #0f172a;
  --text-muted: #64748b;
  --text-light: #94a3b8;
  --border: #e2e8f0;
  --radius-sm: 6px;
  --radius: 12px;
  --radius-lg: 16px;
  --radius-full: 9999px;
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.07);
  --shadow-md: 0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08);
  --shadow-lg: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow-sm);
}

.nav-container {
  max-width: 1140px;
  margin: 0 auto;
  padding: 0.85rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-logo {
  font-size: 1.45rem;
  font-weight: 800;
  color: var(--primary);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  letter-spacing: -0.02em;
}

.brand-logo:hover {
  color: var(--primary-hover);
  text-decoration: none;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.nav-links a {
  color: var(--text-muted);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.95rem;
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius-sm);
  transition: all 0.15s ease;
}

.nav-links a:hover,
.nav-links a.active {
  color: var(--primary);
  background: var(--primary-light);
}

.btn-nav {
  background: var(--primary);
  color: #fff !important;
  padding: 0.5rem 1.25rem !important;
  border-radius: var(--radius-full) !important;
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  border: none;
  cursor: pointer;
  text-decoration: none;
  box-shadow: 0 2px 4px rgba(234, 88, 12, 0.2);
  transition: all 0.15s ease;
}

.btn-nav:hover {
  background: var(--primary-hover) !important;
  box-shadow: 0 4px 8px rgba(234, 88, 12, 0.3);
  transform: translateY(-1px);
}

.main-content {
  max-width: 1140px;
  width: 100%;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
  flex: 1;
}

.hero-banner {
  background: linear-gradient(135deg, #ea580c 0%, #f97316 60%, #fb923c 100%);
  color: white;
  padding: 3rem 2rem;
  border-radius: var(--radius-lg);
  margin-bottom: 2.5rem;
  text-align: center;
  box-shadow: var(--shadow-md);
  position: relative;
  overflow: hidden;
}

.hero-banner h1 {
  font-size: 2.5rem;
  font-weight: 800;
  margin: 0 0 0.75rem 0;
  color: white;
  border: none;
  padding: 0;
  letter-spacing: -0.02em;
}

.hero-banner p {
  font-size: 1.15rem;
  opacity: 0.95;
  max-width: 600px;
  margin: 0 auto 1.5rem;
}

.search-wrapper {
  max-width: 480px;
  margin: 0 auto;
  position: relative;
}

.search-input {
  width: 100%;
  padding: 0.85rem 1.25rem 0.85rem 2.85rem;
  font-size: 1rem;
  border-radius: var(--radius-full);
  border: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  outline: none;
}

.search-icon {
  position: absolute;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.1rem;
  color: var(--text-light);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.section-title {
  font-size: 1.65rem;
  font-weight: 700;
  color: var(--secondary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.restaurant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.75rem;
}

.restaurant-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
}

.restaurant-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--primary-border);
  text-decoration: none;
}

.card-cover {
  height: 140px;
  background: linear-gradient(135deg, #fef3c7, #fed7aa);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3.5rem;
  position: relative;
}

.card-cuisine-badge {
  position: absolute;
  bottom: 0.75rem;
  right: 0.75rem;
  background: rgba(255, 255, 255, 0.95);
  color: var(--primary);
  font-weight: 700;
  font-size: 0.75rem;
  padding: 0.25rem 0.65rem;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  box-shadow: var(--shadow-sm);
}

.card-body {
  padding: 1.25rem;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--secondary);
  margin: 0 0 0.5rem 0;
}

.card-address {
  color: var(--text-muted);
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1rem;
  flex: 1;
}

.card-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.85rem;
  border-top: 1px solid var(--border);
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--primary);
}

.restaurant-header {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2rem;
  margin-bottom: 2rem;
  box-shadow: var(--shadow);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1.5rem;
}

.restaurant-info h1 {
  font-size: 2rem;
  font-weight: 800;
  margin: 0 0 0.5rem 0;
  color: var(--secondary);
  border: none;
  padding: 0;
}

.restaurant-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: var(--text-muted);
  font-size: 0.95rem;
}

.cuisine-tag {
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 700;
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-full);
  text-transform: uppercase;
}

.menu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
  margin-bottom: 3rem;
}

.menu-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: all 0.2s ease;
}

.menu-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--primary-border);
}

.menu-info h3 {
  margin: 0 0 0.4rem 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--secondary);
}

.menu-desc {
  color: var(--text-muted);
  font-size: 0.875rem;
  margin: 0 0 1rem 0;
  min-height: 2.6rem;
}

.menu-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.menu-price {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--secondary);
}

.qty-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-qty {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--surface-muted);
  color: var(--secondary);
  border: 1px solid var(--border);
  font-size: 1.1rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: all 0.15s ease;
}

.btn-qty:hover {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.qty-number {
  font-weight: 700;
  font-size: 1rem;
  min-width: 24px;
  text-align: center;
}

.btn-add {
  background: var(--primary);
  color: white;
  font-weight: 600;
  font-size: 0.875rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-full);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.15s ease;
}

.btn-add:hover {
  background: var(--primary-hover);
  transform: scale(1.02);
}

.cart-floating-bar {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: var(--secondary);
  color: white;
  padding: 1rem 1.75rem;
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  z-index: 99;
  width: 90%;
  max-width: 600px;
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
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-full);
  font-size: 0.85rem;
}

.cart-total {
  font-size: 1.2rem;
  font-weight: 800;
}

.btn-checkout {
  background: var(--primary);
  color: white;
  font-weight: 700;
  font-size: 0.95rem;
  padding: 0.65rem 1.5rem;
  border-radius: var(--radius-full);
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-checkout:hover {
  background: #f97316;
  transform: scale(1.03);
}

.order-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: var(--shadow-sm);
}

.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.order-id {
  font-weight: 800;
  font-size: 1.1rem;
  color: var(--secondary);
}

.order-date {
  color: var(--text-muted);
  font-size: 0.875rem;
}

.status-badge {
  display: inline-block;
  padding: 0.3rem 0.75rem;
  border-radius: var(--radius-full);
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-badge.pending,
.status-badge.placed {
  background: #fef3c7;
  color: #b45309;
}

.status-badge.confirmed,
.status-badge.shipped,
.status-badge.preparing {
  background: #e0f2fe;
  color: #0369a1;
}

.status-badge.delivered,
.status-badge.completed {
  background: #dcfce7;
  color: #15803d;
}

.status-badge.cancelled {
  background: #fee2e2;
  color: #b91c1c;
}

.auth-container {
  max-width: 440px;
  margin: 2rem auto;
}

.auth-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2.25rem;
  box-shadow: var(--shadow-md);
}

.auth-tabs {
  display: flex;
  border-bottom: 2px solid var(--border);
  margin-bottom: 1.75rem;
}

.auth-tab {
  flex: 1;
  text-align: center;
  padding: 0.75rem 0;
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-muted);
  border: none;
  background: none;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  margin-bottom: -2px;
  transition: all 0.15s ease;
}

.auth-tab.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.demo-credentials-box {
  background: var(--primary-light);
  border: 1px dashed var(--primary-border);
  border-radius: var(--radius-sm);
  padding: 0.85rem 1rem;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
}

.demo-credentials-box button {
  background: var(--primary);
  color: white;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  margin-top: 0.5rem;
}

.alert {
  padding: 0.85rem 1.25rem;
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  font-weight: 500;
  margin-bottom: 1.25rem;
}

.alert-success {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.alert-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.empty-state {
  text-align: center;
  padding: 3rem 1.5rem;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
}

.empty-state-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.btn-secondary {
  background: var(--surface-muted);
  color: var(--secondary);
  border: 1px solid var(--border);
  font-weight: 600;
  padding: 0.55rem 1.15rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.15s ease;
}

.btn-secondary:hover {
  background: var(--border);
  text-decoration: none;
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
    # If the skeleton output generated src/index.css, enrich it with our full modern design system
    for f in skeleton["files"]:
        if f["path"] == "src/index.css":
            f["content"] = _build_index_css()
            break
    all_files.extend(skeleton["files"])

    return {
        "files": all_files,
        "setup_notes": skeleton["setup_notes"],
    }
