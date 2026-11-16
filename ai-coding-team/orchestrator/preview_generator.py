"""Live UI Preview generator for generated full-stack web applications.
Extracts the tactile Neomorphic CSS, pages, and entities from generated project files
and renders a live, interactive, sandboxed web application preview.
"""
import html
import json
import os
import re
from typing import Dict, List, Optional


def extract_project_info(files: List[dict], app_name: str, clean_name: str) -> dict:
    """Extract styling, pages, and models from generated project files."""
    index_css = ""
    pages = []
    models = []
    brand_title = app_name or clean_name.replace("-", " ").title()

    for f in files:
        path = f.get("path", "").replace("\\", "/")
        content = f.get("content", "")

        # Look for index.css
        if path.endswith("index.css") and not index_css:
            index_css = content

        # Look for pages
        if "/pages/" in path and path.endswith((".jsx", ".tsx", ".js")):
            page_name = os.path.basename(path).split(".")[0]
            pages.append({"name": page_name, "path": path, "code": content})

        # Look for backend models
        if "/models/" in path and path.endswith((".js", ".ts")):
            model_name = os.path.basename(path).split(".")[0]
            models.append(model_name)

        # Look for App brand title in App.jsx
        if path.endswith("App.jsx") and not brand_title:
            m = re.search(r'className=["\']brand-logo["\'][^>]*>([^<]+)<', content)
            if m:
                brand_title = m.group(1).strip()

    # Sort pages: put Catalog/List/Home/Dashboard first, Detail second, Cart/Forms third, Login last
    def page_sort_key(p):
        name = p["name"].lower()
        if "login" in name or "auth" in name:
            return 99
        if "detail" in name:
            return 2
        if "catalog" in name or "list" in name or "home" in name or "dashboard" in name:
            return 0
        return 10

    pages.sort(key=page_sort_key)

    return {
        "brand_title": brand_title,
        "index_css": index_css,
        "pages": pages,
        "models": models,
    }


def generate_live_preview_html(task_id: str, app_name: str, clean_name: str, files: List[dict]) -> str:
    """Generate a rich, interactive, standalone HTML live preview of the generated frontend."""
    info = extract_project_info(files, app_name, clean_name)
    brand = info["brand_title"]
    pages = info["pages"]
    models = info["models"]
    custom_css = info["index_css"]

    primary_model = models[0] if models else "Item"
    primary_lower = primary_model.lower()

    # Domain mock data generation based on app domain
    is_book = any("book" in m.lower() for m in models) or "book" in brand.lower()
    is_fit = any("workout" in m.lower() or "exercise" in m.lower() for m in models) or "fit" in brand.lower()
    is_food = any("restaurant" in m.lower() or "meal" in m.lower() for m in models) or "food" in brand.lower()
    is_task = any("task" in m.lower() or "project" in m.lower() for m in models) or "task" in brand.lower()

    if is_book:
        domain_items = [
            {"id": "1", "title": "The Pragmatic Programmer", "subtitle": "by David Thomas & Andrew Hunt", "tag": "Software Engineering", "price": "$44.99", "badge": "Best Seller", "icon": "📖", "desc": "From journey to master craftsman, core practices for modern software architects."},
            {"id": "2", "title": "Clean Code", "subtitle": "by Robert C. Martin", "tag": "Architecture", "price": "$38.50", "badge": "Essential", "icon": "💻", "desc": "A handbook of agile software craftsmanship and maintainable engineering habits."},
            {"id": "3", "title": "Designing Data-Intensive Applications", "subtitle": "by Martin Kleppmann", "tag": "Distributed Systems", "price": "$52.00", "badge": "Deep Dive", "icon": "🗄️", "desc": "The definitive guide to storage engines, transactions, replication, and distributed consensus."},
            {"id": "4", "title": "Refactoring", "subtitle": "by Martin Fowler", "tag": "Code Quality", "price": "$41.25", "badge": "Classic", "icon": "🛠️", "desc": "Improving the design of existing code through disciplined, verifiable code transformations."},
            {"id": "5", "title": "System Design Interview", "subtitle": "by Alex Xu", "tag": "Architecture", "price": "$36.00", "badge": "Popular", "icon": "📐", "desc": "An insider's guide to scaling distributed systems, microservices, and databases."},
            {"id": "6", "title": "Atomic Habits", "subtitle": "by James Clear", "tag": "Productivity", "price": "$27.99", "badge": "Top Rated", "icon": "🎯", "desc": "An easy and proven way to build good habits, break bad ones, and achieve lasting mastery."}
        ]
        stat_1 = {"icon": "📚", "val": "128", "label": "Books in Library"}
        stat_2 = {"icon": "⭐", "val": "4.92", "label": "Avg Customer Rating"}
        stat_3 = {"icon": "🛒", "val": "3", "label": "Active Cart Items"}
        stat_4 = {"icon": "⚡", "val": "24h", "label": "Instant Delivery"}
    elif is_fit:
        domain_items = [
            {"id": "1", "title": "Full-Body Strength Protocol", "subtitle": "Strength & Hypertrophy • 45 mins", "tag": "Strength", "price": "Level: Intermediate", "badge": "Trending", "icon": "🏋️", "desc": "Compound lifts targeting legs, chest, and back with progressive overload tracking."},
            {"id": "2", "title": "High-Intensity Metabolic Conditioning", "subtitle": "HIIT & Cardio • 30 mins", "tag": "Conditioning", "price": "Level: Advanced", "badge": "High Burn", "icon": "⚡", "desc": "Tabata intervals and explosive plyometrics designed to elevate VO2 max and burn calories."},
            {"id": "3", "title": "Core Stability & Spinal Mobility", "subtitle": "Pilates & Core • 25 mins", "tag": "Mobility", "price": "Level: All Levels", "badge": "Recovery", "icon": "🧘", "desc": "Deep core activation, isometric holds, and hip mobility drills for functional longevity."},
            {"id": "4", "title": "Upper Body Hypertrophy Surge", "subtitle": "Chest, Shoulders, Arms • 50 mins", "tag": "Hypertrophy", "price": "Level: Intermediate", "badge": "Popular", "icon": "💪", "desc": "Targeted push-pull supersets designed for muscle volume and shoulder health."},
            {"id": "5", "title": "Endurance Sprint Intervals", "subtitle": "Outdoor / Treadmill • 35 mins", "tag": "Endurance", "price": "Level: Advanced", "badge": "Cardio", "icon": "🏃", "desc": "Pyramid sprint intervals designed for peak acceleration, pacing, and cardiovascular endurance."}
        ]
        stat_1 = {"icon": "🔥", "val": "2,450", "label": "Calories Burned"}
        stat_2 = {"icon": "⏱️", "val": "4.5 hrs", "label": "Weekly Training"}
        stat_3 = {"icon": "🏆", "val": "14", "label": "Workouts Completed"}
        stat_4 = {"icon": "📈", "val": "+18%", "label": "Strength Index"}
    elif is_food:
        domain_items = [
            {"id": "1", "title": "Artisan Truffle Burger", "subtitle": "The Rustic Bistro • 20 mins", "tag": "Burgers", "price": "$18.50", "badge": "Chef Pick", "icon": "🍔", "desc": "Aged Angus beef, black truffle aioli, melted Gruyère, and crispy caramelized shallots."},
            {"id": "2", "title": "Authentic Neapolitan Margherita", "subtitle": "Pizzeria Napoletana • 15 mins", "tag": "Pizza", "price": "$16.00", "badge": "Wood Fired", "icon": "🍕", "desc": "San Marzano tomatoes, fresh buffalo mozzarella, fragrant sweet basil, and extra virgin olive oil."},
            {"id": "3", "title": "Fresh Salmon Poke Bowl", "subtitle": "Pacific Coast Kitchen • 12 mins", "tag": "Healthy", "price": "$17.25", "badge": "Fresh", "icon": "🥗", "desc": "Wild-caught salmon, sushi rice, avocado, edamame, cucumber, furikake, and spicy sesame dressing."},
            {"id": "4", "title": "Traditional Tonkotsu Ramen", "subtitle": "Noodle Master • 18 mins", "tag": "Japanese", "price": "$15.50", "badge": "Popular", "icon": "🍜", "desc": "18-hour rich pork bone broth, tender chashu pork belly, ajitsuke tamago egg, and spring onions."}
        ]
        stat_1 = {"icon": "🍽️", "val": "42", "label": "Partner Restaurants"}
        stat_2 = {"icon": "⚡", "val": "28 min", "label": "Avg Delivery Time"}
        stat_3 = {"icon": "⭐", "val": "4.88", "label": "Food Quality Score"}
        stat_4 = {"icon": "🛵", "val": "Free", "label": "Delivery on $25+"}
    else:
        domain_items = [
            {"id": "1", "title": f"Production {primary_model} Alpha", "subtitle": f"Verified {primary_model} Record • ID: #4091", "tag": "Active", "price": "Priority: High", "badge": "Active", "icon": "✨", "desc": f"Primary operational record with schema validation, relational links, and full audit logs."},
            {"id": "2", "title": f"Enterprise {primary_model} Delta", "subtitle": f"Validated {primary_model} Record • ID: #4092", "tag": "Verified", "price": "Priority: Medium", "badge": "Verified", "icon": "⚡", "desc": f"Fully documented relational instance supporting atomic updates and real-time query aggregation."},
            {"id": "3", "title": f"Global {primary_model} Omega", "subtitle": f"Audited {primary_model} Record • ID: #4093", "tag": "Archived", "price": "Priority: Low", "badge": "Archived", "icon": "🛡️", "desc": f"Long-term operational entity with encrypted metadata and indexed query properties."},
            {"id": "4", "title": f"Collaborative {primary_model} Prime", "subtitle": f"Shared {primary_model} Record • ID: #4094", "tag": "Active", "price": "Priority: High", "badge": "Featured", "icon": "🚀", "desc": f"Multi-tenant enabled model with role-based access control and live webhook notification dispatch."}
        ]
        stat_1 = {"icon": "📊", "val": "84", "label": f"Total {primary_model}s"}
        stat_2 = {"icon": "✅", "val": "99.8%", "label": "Sync Health"}
        stat_3 = {"icon": "⚡", "val": "12ms", "label": "API Latency"}
        stat_4 = {"icon": "👥", "val": "1.2k", "label": "Active Users"}

    # Build page tabs HTML
    page_names = [p["name"] for p in pages]
    if not page_names:
        page_names = ["Home", "Details", "Manage", "Login"]

    nav_tabs_html = ""
    for idx, p_name in enumerate(page_names):
        active_cls = "active" if idx == 0 else ""
        icon = "📋"
        lower = p_name.lower()
        if "catalog" in lower or "book" in lower or "list" in lower or "home" in lower:
            icon = "📖"
        elif "detail" in lower:
            icon = "🔍"
        elif "cart" in lower:
            icon = "🛒"
        elif "order" in lower:
            icon = "📦"
        elif "exercise" in lower or "workout" in lower:
            icon = "🏋️"
        elif "login" in lower or "auth" in lower:
            icon = "🔑"
        nav_tabs_html += f'<button class="nav-tab {active_cls}" onclick="switchPage(\'{p_name}\')">{icon} {p_name}</button>'

    # Embed items JSON
    items_json = json.dumps(domain_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(brand)} - Live Neomorphic UI Preview</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
{custom_css}

    /* Embedded Preview Banner & Navigation enhancements */
    .preview-mode-banner {{
      background: linear-gradient(90deg, #1e1b4b 0%, #312e81 100%);
      color: #e0e7ff;
      padding: 0.55rem 1.25rem;
      font-size: 0.8rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      font-family: 'Plus Jakarta Sans', sans-serif;
    }}
    .preview-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: rgba(99, 102, 241, 0.35);
      border: 1px solid rgba(129, 140, 248, 0.4);
      padding: 0.2rem 0.65rem;
      border-radius: 9999px;
      font-size: 0.72rem;
      font-weight: 700;
      color: #a5b4fc;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .nav-tabs-bar {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      overflow-x: auto;
      padding: 0.4rem 0;
    }}
    .nav-tab {{
      border: none;
      background: transparent;
      color: var(--text-muted, #64748b);
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.88rem;
      font-weight: 600;
      padding: 0.45rem 0.95rem;
      border-radius: var(--radius-full, 9999px);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s ease;
      white-space: nowrap;
    }}
    .nav-tab:hover {{
      color: var(--primary, #4f46e5);
      background: rgba(255, 255, 255, 0.5);
    }}
    .nav-tab.active {{
      color: var(--primary, #4f46e5);
      background: var(--bg, #e6ecf5);
      box-shadow: var(--neu-inset-sm, inset 2px 2px 5px #c2c8d4, inset -2px -2px 5px #ffffff);
      font-weight: 700;
    }}
    .preview-page-container {{
      max-width: 1140px;
      margin: 0 auto;
      padding: 1.5rem 1.25rem 4rem 1.25rem;
    }}
    .toast-pill {{
      position: fixed;
      bottom: 1.5rem;
      right: 1.5rem;
      background: #1e293b;
      color: #f8fafc;
      padding: 0.75rem 1.25rem;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 600;
      box-shadow: 0 10px 25px rgba(0,0,0,0.3);
      display: none;
      align-items: center;
      gap: 0.5rem;
      z-index: 1000;
    }}
  </style>
</head>
<body>
  <!-- Preview Watermark Bar -->
  <div class="preview-mode-banner">
    <div style="display: flex; align-items: center; gap: 0.75rem;">
      <span class="preview-badge">✨ Live UI Sandbox</span>
      <span>Viewing interactive frontend for <strong>{html.escape(brand)}</strong></span>
    </div>
    <div style="display: flex; align-items: center; gap: 0.75rem;">
      <span style="color: #94a3b8; font-size: 0.75rem;">🎨 Tactile Neomorphism Theme Active</span>
    </div>
  </div>

  <!-- Interactive Neomorphic Navbar -->
  <nav class="navbar">
    <div class="nav-container">
      <div class="brand-logo" onclick="switchPage('{page_names[0]}')" style="cursor: pointer;">
        <span>🚀</span>
        <span>{html.escape(brand)}</span>
      </div>
      <div class="nav-tabs-bar">
        {nav_tabs_html}
      </div>
    </div>
  </nav>

  <!-- Interactive Dynamic Viewport Canvas -->
  <div class="preview-page-container" id="pageCanvas">
    <!-- Populated by JavaScript switchPage -->
  </div>

  <!-- Toast Notification -->
  <div id="toastPill" class="toast-pill">
    <span id="toastIcon">✨</span>
    <span id="toastMsg">Action executed</span>
  </div>

  <script>
    const allItems = {items_json};
    let activePage = '{page_names[0]}';
    let searchQuery = '';
    let cartCount = 3;
    let selectedItem = allItems[0];
    let authMode = 'login';

    function showToast(icon, msg) {{
      const t = document.getElementById('toastPill');
      document.getElementById('toastIcon').textContent = icon;
      document.getElementById('toastMsg').textContent = msg;
      t.style.display = 'flex';
      setTimeout(() => {{ t.style.display = 'none'; }}, 2500);
    }}

    function switchPage(pageName) {{
      activePage = pageName;
      document.querySelectorAll('.nav-tab').forEach(el => {{
        if (el.textContent.includes(pageName)) {{
          el.className = 'nav-tab active';
        }} else {{
          el.className = 'nav-tab';
        }}
      }});

      const lower = pageName.toLowerCase();
      if (lower.includes('login') || lower.includes('auth')) {{
        renderLoginPage();
      }} else if (lower.includes('detail')) {{
        renderDetailPage();
      }} else if (lower.includes('cart')) {{
        renderCartPage();
      }} else if (lower.includes('order')) {{
        renderOrdersPage();
      }} else {{
        renderCatalogPage();
      }}
    }}

    function renderCatalogPage() {{
      const filtered = allItems.filter(i => 
        i.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        i.subtitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        i.tag.toLowerCase().includes(searchQuery.toLowerCase())
      );

      let cardsHtml = '';
      if (filtered.length === 0) {{
        cardsHtml = `
          <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem;">
            <div class="empty-state-icon" style="font-size: 3rem; margin-bottom: 0.75rem;">🔍</div>
            <h4 style="margin: 0 0 0.5rem 0; font-size: 1.15rem;">No matching items found</h4>
            <p style="color: var(--text-muted); margin: 0 0 1rem 0;">Try adjusting your search query filter.</p>
            <button class="neu-btn btn-secondary" onclick="clearSearch()">Clear Search Filter</button>
          </div>
        `;
      }} else {{
        cardsHtml = filtered.map(item => `
          <div class="app-card neu-card">
            <div class="card-cover" style="font-size: 2.8rem; text-align: center; padding: 1.5rem 0;">${{item.icon}}</div>
            <div class="card-body">
              <span class="card-badge badge-primary">${{item.badge}}</span>
              <h3 class="card-title" style="margin: 0.5rem 0 0.25rem 0;">${{item.title}}</h3>
              <div class="card-meta" style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 0.75rem;">${{item.subtitle}}</div>
              <p style="font-size: 0.88rem; color: var(--text-muted); line-height: 1.45; margin: 0 0 1rem 0;">${{item.desc}}</p>
            </div>
            <div class="card-footer" style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.7);">
              <span style="font-weight: 700; font-size: 1.05rem; color: var(--primary);">${{item.price}}</span>
              <div style="display: flex; gap: 0.5rem;">
                <button class="neu-btn btn-secondary" onclick="viewDetail('${{item.id}}')" style="padding: 0.4rem 0.85rem; font-size: 0.85rem;">Details</button>
                <button class="neu-btn btn-primary" onclick="addToCart('${{item.title}}')" style="padding: 0.4rem 0.85rem; font-size: 0.85rem;">+ Add</button>
              </div>
            </div>
          </div>
        `).join('');
      }}

      document.getElementById('pageCanvas').innerHTML = `
        <!-- KPI Stats Grid -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon">{stat_1['icon']}</div>
            <div class="stat-val">{stat_1['val']}</div>
            <div class="stat-label">{stat_1['label']}</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">{stat_2['icon']}</div>
            <div class="stat-val">{stat_2['val']}</div>
            <div class="stat-label">{stat_2['label']}</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">{stat_3['icon']}</div>
            <div class="stat-val" id="kpiCartCount">${{cartCount}}</div>
            <div class="stat-label">{stat_3['label']}</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">{stat_4['icon']}</div>
            <div class="stat-val">{stat_4['val']}</div>
            <div class="stat-label">{stat_4['label']}</div>
          </div>
        </div>

        <!-- Inset Neomorphic Search Filter -->
        <div class="hero-banner">
          <div class="search-wrapper">
            <span class="search-icon">🔍</span>
            <input
              type="text"
              id="catalogSearchInput"
              class="search-input neu-input"
              placeholder="Search by title, author, category, or tags..."
              value="${{searchQuery}}"
              oninput="onSearchInput(this.value)"
            />
          </div>
        </div>

        <!-- Filter category pills -->
        <div class="filter-pills" style="margin-bottom: 1.75rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="filter-pill ${{searchQuery === '' ? 'active' : ''}}" onclick="setTagFilter('')">All Items</button>
          <button class="filter-pill" onclick="setTagFilter('Software Engineering')">Engineering</button>
          <button class="filter-pill" onclick="setTagFilter('Architecture')">Architecture</button>
          <button class="filter-pill" onclick="setTagFilter('Distributed Systems')">Distributed Systems</button>
        </div>

        <!-- Cards Grid -->
        <div class="grid-cards">
          ${{cardsHtml}}
        </div>
      `;
    }}

    function onSearchInput(val) {{
      searchQuery = val;
      renderCatalogPage();
      const input = document.getElementById('catalogSearchInput');
      if (input) {{
        input.focus();
        input.selectionStart = input.selectionEnd = val.length;
      }}
    }}

    function setTagFilter(tag) {{
      searchQuery = tag;
      renderCatalogPage();
    }}

    function clearSearch() {{
      searchQuery = '';
      renderCatalogPage();
    }}

    function viewDetail(id) {{
      selectedItem = allItems.find(i => i.id === id) || allItems[0];
      const detailPage = '{page_names[1] if len(page_names) > 1 else page_names[0]}';
      switchPage(detailPage);
    }}

    function addToCart(title) {{
      cartCount++;
      const badge = document.getElementById('kpiCartCount');
      if (badge) badge.textContent = cartCount;
      showToast('🛒', `Added "${{title}}" to cart! (Total: ${{cartCount}})`);
    }}

    function renderDetailPage() {{
      const item = selectedItem || allItems[0];
      document.getElementById('pageCanvas').innerHTML = `
        <div style="margin-bottom: 1rem;">
          <button class="neu-btn btn-secondary" onclick="switchPage('{page_names[0]}')">← Back to Overview</button>
        </div>
        
        <div class="neu-card" style="padding: 2.25rem; margin-bottom: 2rem;">
          <div style="display: flex; gap: 2rem; align-items: flex-start; flex-wrap: wrap;">
            <div style="font-size: 5rem; background: var(--bg); padding: 1.5rem 2rem; border-radius: var(--radius); box-shadow: var(--neu-inset); display: flex; align-items: center; justify-content: center;">
              ${{item.icon}}
            </div>
            <div style="flex: 1; min-width: 280px;">
              <span class="badge badge-primary" style="margin-bottom: 0.5rem; display: inline-block;">${{item.badge}}</span>
              <h1 style="margin: 0.35rem 0 0.5rem 0; font-size: 1.85rem; color: var(--text);">${{item.title}}</h1>
              <div style="font-size: 1rem; color: var(--text-muted); margin-bottom: 1rem;">${{item.subtitle}}</div>
              <p style="font-size: 0.98rem; line-height: 1.6; color: var(--text); margin-bottom: 1.5rem;">
                ${{item.desc}} Includes full relational database schema verification, automated Mongoose indexing, and production Express endpoint coverage.
              </p>
              
              <div style="display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;">
                <span style="font-size: 1.5rem; font-weight: 800; color: var(--primary);">${{item.price}}</span>
                <button class="neu-btn btn-primary" onclick="addToCart('${{item.title}}')" style="padding: 0.75rem 1.75rem;">
                  🛒 Add to Order
                </button>
                <button class="neu-btn btn-secondary" onclick="showToast('⚡', 'Quick checkout initiated')" style="padding: 0.75rem 1.5rem;">
                  ⚡ Quick Checkout
                </button>
              </div>
            </div>
          </div>
        </div>

        <h3 style="margin-bottom: 1rem; color: var(--text);">Related Specifications &amp; Features</h3>
        <div class="grid-cards" style="margin-bottom: 2rem;">
          <div class="app-card neu-card" style="padding: 1.25rem;">
            <div style="font-weight: 700; margin-bottom: 0.35rem;">🛡️ Data Encryption</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">Pass-through JWT authorization and scoped REST controllers.</div>
          </div>
          <div class="app-card neu-card" style="padding: 1.25rem;">
            <div style="font-weight: 700; margin-bottom: 0.35rem;">⚡ In-Memory Validation</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">Auto-tested against Jest test suites with in-memory Mongo mock.</div>
          </div>
          <div class="app-card neu-card" style="padding: 1.25rem;">
            <div style="font-weight: 700; margin-bottom: 0.35rem;">📱 Mobile Responsive</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">Soft UI Neomorphic controls optimized for desktop &amp; mobile tap.</div>
          </div>
        </div>
      `;
    }}

    function renderCartPage() {{
      document.getElementById('pageCanvas').innerHTML = `
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon">🛒</div>
            <div class="stat-val">${{cartCount}}</div>
            <div class="stat-label">Items in Cart</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">💳</div>
            <div class="stat-val">$134.49</div>
            <div class="stat-label">Subtotal</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🚚</div>
            <div class="stat-val">Free</div>
            <div class="stat-label">Standard Shipping</div>
          </div>
        </div>

        <div class="neu-card" style="padding: 2rem; margin-top: 1.5rem;">
          <h2 style="margin: 0 0 1.5rem 0; font-size: 1.35rem;">Shopping Cart</h2>
          
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            ${{allItems.slice(0, 3).map((item, idx) => `
              <div style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; border-radius: var(--radius-sm); box-shadow: var(--neu-inset-sm); background: var(--bg);">
                <div style="display: flex; align-items: center; gap: 1rem;">
                  <span style="font-size: 2rem;">${{item.icon}}</span>
                  <div>
                    <div style="font-weight: 700; color: var(--text);">${{item.title}}</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">${{item.subtitle}}</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 1.5rem;">
                  <span style="font-weight: 700; color: var(--primary);">${{item.price}}</span>
                  <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <button class="neu-btn btn-secondary" onclick="showToast('➖', 'Decreased quantity')" style="padding: 0.25rem 0.65rem;">-</button>
                    <span style="font-weight: 700; padding: 0 0.5rem;">1</span>
                    <button class="neu-btn btn-secondary" onclick="showToast('➕', 'Increased quantity')" style="padding: 0.25rem 0.65rem;">+</button>
                  </div>
                </div>
              </div>
            `).join('')}}
          </div>

          <div style="margin-top: 2rem; display: flex; justify-content: flex-end; align-items: center; gap: 1.5rem;">
            <div style="font-size: 1.25rem; font-weight: 800;">Total: <span style="color: var(--primary);">$134.49</span></div>
            <button class="neu-btn btn-primary" onclick="showToast('🎉', 'Order placed successfully!')" style="padding: 0.85rem 2rem; font-size: 1rem;">
              Complete Checkout 🚀
            </button>
          </div>
        </div>
      `;
    }}

    function renderOrdersPage() {{
      document.getElementById('pageCanvas').innerHTML = `
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon">📦</div>
            <div class="stat-val">3</div>
            <div class="stat-label">Total Orders</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🚚</div>
            <div class="stat-val">1</div>
            <div class="stat-label">In Transit</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">✅</div>
            <div class="stat-val">2</div>
            <div class="stat-label">Delivered</div>
          </div>
        </div>

        <div class="neu-card" style="padding: 2rem; margin-top: 1.5rem;">
          <h2 style="margin: 0 0 1.25rem 0; font-size: 1.35rem;">Recent Order History</h2>
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            <div class="app-card neu-card" style="padding: 1.25rem; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <div style="display: flex; align-items: center; gap: 0.65rem; margin-bottom: 0.35rem;">
                  <strong style="font-size: 1.05rem;">Order #ORD-9821</strong>
                  <span class="badge badge-success">Delivered ✓</span>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted);">2 items • Paid via Card • Nov 15, 2026</div>
              </div>
              <button class="neu-btn btn-secondary" onclick="showToast('📄', 'Receipt downloaded')">View Invoice</button>
            </div>

            <div class="app-card neu-card" style="padding: 1.25rem; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <div style="display: flex; align-items: center; gap: 0.65rem; margin-bottom: 0.35rem;">
                  <strong style="font-size: 1.05rem;">Order #ORD-9822</strong>
                  <span class="badge badge-primary">In Transit 🚚</span>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted);">1 item • Estimated Delivery: Tomorrow 2 PM</div>
              </div>
              <button class="neu-btn btn-primary" onclick="showToast('📍', 'Package is in regional distribution hub')">Track Package</button>
            </div>
          </div>
        </div>
      `;
    }}

    function renderLoginPage() {{
      document.getElementById('pageCanvas').innerHTML = `
        <div class="auth-container">
          <div class="auth-card">
            <div class="auth-tabs">
              <button class="auth-tab ${{authMode === 'login' ? 'active' : ''}}" onclick="setAuthMode('login')">Sign In</button>
              <button class="auth-tab ${{authMode === 'register' ? 'active' : ''}}" onclick="setAuthMode('register')">Create Account</button>
            </div>

            <div class="demo-credentials-box" style="margin-bottom: 1.25rem;">
              <div style="font-weight: 700; font-size: 0.82rem; margin-bottom: 0.35rem; color: var(--primary);">⚡ One-Click Demo Login:</div>
              <button class="neu-btn btn-secondary" onclick="fillDemoCredentials()" style="width: 100%; padding: 0.5rem; font-size: 0.85rem;">
                Fill 'alice@example.com' credentials
              </button>
            </div>

            <form onsubmit="handleAuthSubmit(event)">
              ${{authMode === 'register' ? `
                <div class="form-group">
                  <label class="form-label">Full Name</label>
                  <input type="text" id="authName" class="form-input neu-input" placeholder="Alice Smith" required />
                </div>
              ` : ''}}
              <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" id="authEmail" class="form-input neu-input" placeholder="alice@example.com" required />
              </div>
              <div class="form-group">
                <label class="form-label">Password</label>
                <input type="password" id="authPassword" class="form-input neu-input" placeholder="••••••••••••" required />
              </div>

              <button type="submit" class="neu-btn btn-primary" style="width: 100%; margin-top: 1rem; padding: 0.85rem;">
                ${{authMode === 'login' ? 'Sign In to Account →' : 'Register New Account →'}}
              </button>
            </form>
          </div>
        </div>
      `;
    }}

    function setAuthMode(mode) {{
      authMode = mode;
      renderLoginPage();
    }}

    function fillDemoCredentials() {{
      const email = document.getElementById('authEmail');
      const pass = document.getElementById('authPassword');
      if (email) email.value = 'alice@example.com';
      if (pass) pass.value = 'Password123!';
      showToast('🔑', 'Demo credentials populated!');
    }}

    function handleAuthSubmit(e) {{
      e.preventDefault();
      showToast('🎉', 'Authenticated successfully! Token stored.');
      setTimeout(() => {{ switchPage('{page_names[0]}'); }}, 1000);
    }}

    // Initial render
    switchPage(activePage);
  </script>
</body>
</html>
"""
