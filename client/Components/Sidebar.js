/**
 * Sidebar.js
 * - Injects sidebar HTML into every page
 * - Desktop: hidable via toggle button in topbar (state persisted in localStorage)
 * - Mobile: overlay drawer via hamburger button
 */
(function () {
  "use strict";

  const STORAGE_KEY = "mis_sidebar_hidden";
  const MOBILE_BP   = 768;

  // ── Nav definition ──────────────────────────────────────────
  const NAV = [
    {
      section: "Main",
      items: [
        { href: "/",                  icon: "⬡",  label: "Dashboard" },
        { href: "/cleaner",           icon: "⚡",  label: "Data Cleaner" },
      ],
    },
    {
      section: "Audit Corner",
      items: [
        {
          label: "Audit Corner", icon: "◈", dropdown: true, id: "audit",
          children: [
            { href: "/audit/mcd",         label: "MCD Audit" },
            { href: "/audit/alt-vehicle", label: "Alt Vehicle" },
            { href: "/audit/toll",        label: "Toll Trips" },
            { href: "/b2b-maker",         label: "B2B Maker" },
            { href: "/audit/gps",         label: "GPS Audit" },
            { href: "/audit/incomplete",  label: "Incomplete Trips" },
          ],
        },
      ],
    },
    {
      section: "Tools",
      items: [
        { href: "/locality-manager",  icon: "◉",  label: "Locality Manager" },
        { href: "/operation-manager", icon: "↓",   label: "Downloads" },
        { href: "/admin",             icon: "⚙",   label: "Admin Panel" },
      ],
    },
  ];

  // ── Build sidebar HTML ───────────────────────────────────────
  function buildNavHTML() {
    return NAV.map(group => {
      const items = group.items.map(item => {
        if (item.dropdown) {
          const children = item.children.map(c =>
            `<a href="${c.href}" class="sub-nav-item">${c.label}</a>`
          ).join("");
          return `
            <div class="nav-dropdown">
              <button class="nav-item dropdown-btn" id="dd-btn-${item.id}">
                <span class="nav-icon">${item.icon}</span>
                <span class="nav-label">${item.label}</span>
                <span class="dropdown-arrow">▾</span>
              </button>
              <div class="dropdown-container" id="dd-${item.id}">${children}</div>
            </div>`;
        }
        return `
          <a href="${item.href}" class="nav-item">
            <span class="nav-icon">${item.icon}</span>
            <span class="nav-label">${item.label}</span>
          </a>`;
      }).join("");

      return `
        <div class="nav-section-label">${group.section}</div>
        ${items}`;
    }).join("");
  }

  function inject() {
    const sidebarHTML = `
      <div id="sidebar-overlay" class="sidebar-overlay"></div>
      <div id="sidebar-container" class="sidebar-container" role="navigation" aria-label="Main navigation">

        <div class="sidebar-header">
          <div class="brand">
            <div class="brand-logo">M</div>
            <div class="brand-text">
              <div class="brand-name">MIS</div>
              <div class="brand-tagline">Management System</div>
            </div>
          </div>
          <button id="sidebar-close-btn" class="close-btn" aria-label="Close sidebar">✕</button>
        </div>

        <nav class="sidebar-nav">${buildNavHTML()}</nav>

        <div class="sidebar-footer">
          <a href="/logout" class="nav-item logout-item">
            <span class="nav-icon">⎋</span>
            <span class="nav-label">Logout</span>
          </a>
        </div>
      </div>`;

    document.body.insertAdjacentHTML("afterbegin", sidebarHTML);

    // Inject toggle button into topbar (prepended before topbar-title)
    const topbar = document.querySelector(".topbar");
    if (topbar) {
      const btn = document.createElement("button");
      btn.id = "sidebar-toggle-btn";
      btn.className = "sidebar-toggle-btn";
      btn.setAttribute("aria-label", "Toggle sidebar");
      btn.setAttribute("title", "Toggle sidebar");
      btn.textContent = "☰";
      topbar.insertBefore(btn, topbar.firstChild);
    }
  }

  // ── State helpers ────────────────────────────────────────────
  function isMobile() { return window.innerWidth <= MOBILE_BP; }

  function isHidden() {
    return localStorage.getItem(STORAGE_KEY) === "1";
  }

  function applyState(hidden) {
    if (isMobile()) {
      // Mobile: body class drives overlay, ignore localStorage
      return;
    }
    if (hidden) {
      document.body.classList.add("sidebar-hidden");
    } else {
      document.body.classList.remove("sidebar-hidden");
    }
    updateToggleIcon(hidden);
  }

  function updateToggleIcon(hidden) {
    const btn = document.getElementById("sidebar-toggle-btn");
    if (btn) btn.textContent = hidden ? "☰" : "✕";
  }

  // ── Init ─────────────────────────────────────────────────────
  function init() {
    const sidebar  = document.getElementById("sidebar-container");
    const overlay  = document.getElementById("sidebar-overlay");
    const closeBtn = document.getElementById("sidebar-close-btn");
    const toggleBtn = document.getElementById("sidebar-toggle-btn");

    // ── Desktop toggle ─────────────────────────────────────────
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        if (isMobile()) {
          // On mobile, act as hamburger
          openMobile();
        } else {
          const nowHidden = !document.body.classList.contains("sidebar-hidden");
          localStorage.setItem(STORAGE_KEY, nowHidden ? "1" : "0");
          applyState(nowHidden);
        }
      });
    }

    // ── Mobile open/close ──────────────────────────────────────
    function openMobile() {
      sidebar.classList.add("mobile-open");
      document.body.classList.add("mobile-sidebar-open");
      overlay.classList.add("active");
    }
    function closeMobile() {
      sidebar.classList.remove("mobile-open");
      document.body.classList.remove("mobile-sidebar-open");
      overlay.classList.remove("active");
    }

    closeBtn?.addEventListener("click", closeMobile);
    overlay?.addEventListener("click", closeMobile);
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeMobile(); });

    // ── Dropdowns ──────────────────────────────────────────────
    document.querySelectorAll(".dropdown-btn").forEach(btn => {
      const id      = btn.id.replace("dd-btn-", "");
      const content = document.getElementById(`dd-${id}`);
      btn.addEventListener("click", () => {
        content?.classList.toggle("show");
        btn.classList.toggle("dropdown-active");
      });
    });

    // ── Active link highlight ──────────────────────────────────
    const path = window.location.pathname;
    document.querySelectorAll(".nav-item[href], .sub-nav-item[href]").forEach(link => {
      if (link.getAttribute("href") === path) {
        link.classList.add("active");
        const parent = link.closest(".dropdown-container");
        if (parent) {
          parent.classList.add("show");
          const btnId = parent.id.replace("dd-", "dd-btn-");
          document.getElementById(btnId)?.classList.add("dropdown-active");
        }
      }
    });

    // ── Responsive: re-apply on resize ────────────────────────
    window.addEventListener("resize", () => {
      if (!isMobile()) {
        // Restore desktop state from storage
        closeMobile();
        applyState(isHidden());
        updateToggleIcon(isHidden());
      } else {
        // On mobile always remove desktop hidden class
        document.body.classList.remove("sidebar-hidden");
      }
    });

    // ── Apply initial desktop state ────────────────────────────
    if (!isMobile()) {
      applyState(isHidden());
    }
  }

  // ── Boot ─────────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { inject(); init(); });
  } else {
    inject(); init();
  }
})();
