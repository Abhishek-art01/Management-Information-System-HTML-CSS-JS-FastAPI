/**
 * Localitycorner.js — fast, debounced locality manager UI
 */
(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────
  let currentPage  = 1;
  let totalPages   = 1;
  let localities   = [];
  let selectedIds  = new Set();
  let searchTimer  = null;

  // ── DOM ────────────────────────────────────────────────────────────────
  const tbody          = document.getElementById("table-body");
  const pagination     = document.getElementById("pagination");
  const searchInput    = document.getElementById("search-input");
  const localityFilter = document.getElementById("locality-filter");
  const bulkMapBtn     = document.getElementById("bulk-map-btn");
  const selectAll      = document.getElementById("select-all");
  const modalBackdrop  = document.getElementById("modal-backdrop");
  const modalClose     = document.getElementById("modal-close");
  const modalCancel    = document.getElementById("modal-cancel");
  const modalConfirm   = document.getElementById("modal-confirm");
  const modalSelect    = document.getElementById("modal-locality-select");
  const mapCount       = document.getElementById("map-count");

  // ── Fetch localities for dropdowns ─────────────────────────────────────
  async function loadLocalities() {
    try {
      const data = await apiFetch("/api/dropdown-localities/");
      localities = data;
      const frag = document.createDocumentFragment();
      data.forEach(loc => {
        const opt = document.createElement("option");
        opt.value = loc.locality;
        opt.textContent = `${loc.locality} — ${loc.zone ?? "?"} (${loc.billing_km ?? "-"} km)`;
        frag.appendChild(opt.cloneNode(true));
      });
      localityFilter.appendChild(frag.cloneNode(true));
      modalSelect.appendChild(frag);
    } catch (e) {
      console.warn("Could not load localities:", e);
    }
  }

  // ── Fetch address table ─────────────────────────────────────────────────
  async function loadTable(page = 1, search = "") {
    tbody.innerHTML = `
      <tr><td colspan="7" style="text-align:center; padding:40px; color:var(--text-muted);">
        <span class="spinner"></span>
      </td></tr>`;
    selectedIds.clear();
    updateBulkBtn();

    const params = new URLSearchParams({ page, search });
    const locality = localityFilter.value;
    if (locality) params.set("locality", locality);

    try {
      const data = await apiFetch(`/api/localities/?${params}`);
      currentPage = data.page ?? page;
      totalPages  = data.total_pages ?? 1;
      renderTable(data.addresses ?? data.results ?? []);
      renderPagination();
    } catch (e) {
      tbody.innerHTML = `
        <tr><td colspan="7">
          <div class="empty-state">
            <span class="empty-icon">⚠</span>
            <p>Failed to load data: ${escHtml(e.message)}</p>
          </div>
        </td></tr>`;
    }
  }

  // ── Render table rows ───────────────────────────────────────────────────
  function renderTable(rows) {
    if (rows.length === 0) {
      tbody.innerHTML = `
        <tr><td colspan="7">
          <div class="empty-state">
            <span class="empty-icon">◉</span>
            <p>No addresses found</p>
          </div>
        </td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td><input type="checkbox" class="chk row-chk" data-id="${r.id}" ${selectedIds.has(r.id) ? "checked" : ""}></td>
        <td style="font-family:var(--font-mono); font-size:.78rem; color:var(--text-muted);">${r.id}</td>
        <td style="max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escHtml(r.address)}">${escHtml(r.address)}</td>
        <td>${r.locality ? `<span class="badge badge-cyan">${escHtml(r.locality)}</span>` : `<span class="badge badge-gray">—</span>`}</td>
        <td>${r.zone  ? escHtml(r.zone)  : '<span style="color:var(--text-muted)">—</span>'}</td>
        <td style="font-family:var(--font-mono);">${r.km ?? '—'}</td>
        <td>
          <button class="row-action map-single" data-id="${r.id}" data-address="${escHtml(r.address)}">Map</button>
        </td>
      </tr>`).join("");

    // Row checkboxes
    tbody.querySelectorAll(".row-chk").forEach(chk => {
      chk.addEventListener("change", () => {
        const id = parseInt(chk.dataset.id);
        chk.checked ? selectedIds.add(id) : selectedIds.delete(id);
        updateBulkBtn();
        selectAll.indeterminate = selectedIds.size > 0 && selectedIds.size < rows.length;
        selectAll.checked = selectedIds.size === rows.length;
      });
    });

    // Single-row map buttons
    tbody.querySelectorAll(".map-single").forEach(btn => {
      btn.addEventListener("click", () => {
        selectedIds.clear();
        selectedIds.add(parseInt(btn.dataset.id));
        openModal();
      });
    });
  }

  // ── Pagination ──────────────────────────────────────────────────────────
  function renderPagination() {
    pagination.innerHTML = "";
    if (totalPages <= 1) return;

    const addBtn = (label, page, active = false, disabled = false) => {
      const btn = document.createElement("button");
      btn.className = "page-btn" + (active ? " active" : "");
      btn.textContent = label;
      btn.disabled = disabled;
      if (!disabled) btn.addEventListener("click", () => loadTable(page, searchInput.value.trim()));
      pagination.appendChild(btn);
    };

    addBtn("‹", currentPage - 1, false, currentPage === 1);
    const start = Math.max(1, currentPage - 2);
    const end   = Math.min(totalPages, start + 4);
    for (let p = start; p <= end; p++) addBtn(p, p, p === currentPage);
    addBtn("›", currentPage + 1, false, currentPage === totalPages);
  }

  // ── Bulk select ─────────────────────────────────────────────────────────
  selectAll.addEventListener("change", () => {
    const all = tbody.querySelectorAll(".row-chk");
    all.forEach(chk => {
      chk.checked = selectAll.checked;
      const id = parseInt(chk.dataset.id);
      selectAll.checked ? selectedIds.add(id) : selectedIds.delete(id);
    });
    updateBulkBtn();
  });

  function updateBulkBtn() {
    bulkMapBtn.disabled = selectedIds.size === 0;
    if (selectedIds.size > 0) {
      bulkMapBtn.textContent = `Map ${selectedIds.size} Selected`;
    } else {
      bulkMapBtn.textContent = "Map Selected";
    }
  }

  bulkMapBtn.addEventListener("click", openModal);

  // ── Modal ───────────────────────────────────────────────────────────────
  function openModal() {
    mapCount.textContent = selectedIds.size;
    modalSelect.value = "";
    modalBackdrop.style.display = "grid";
  }
  function closeModal() { modalBackdrop.style.display = "none"; }

  modalClose.addEventListener("click",   closeModal);
  modalCancel.addEventListener("click",  closeModal);
  modalBackdrop.addEventListener("click", e => { if (e.target === modalBackdrop) closeModal(); });

  modalConfirm.addEventListener("click", async () => {
    const locality = modalSelect.value;
    if (!locality) { alert("Please select a locality."); return; }

    modalConfirm.disabled = true;
    modalConfirm.textContent = "Mapping…";

    try {
      const body = {
        address_ids: [...selectedIds],
        locality_name: locality,
      };
      await apiFetch("/api/bulk-map/", { method: "POST", body: JSON.stringify(body) });
      closeModal();
      selectedIds.clear();
      updateBulkBtn();
      loadTable(currentPage, searchInput.value.trim());
    } catch (e) {
      alert("Mapping failed: " + e.message);
    } finally {
      modalConfirm.disabled = false;
      modalConfirm.textContent = "Confirm Mapping";
    }
  });

  // ── Search with debounce ────────────────────────────────────────────────
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadTable(1, searchInput.value.trim()), 320);
  });

  localityFilter.addEventListener("change", () => loadTable(1, searchInput.value.trim()));

  // ── API helper ──────────────────────────────────────────────────────────
  async function apiFetch(url, opts = {}) {
    const defaults = { headers: { "Content-Type": "application/json" } };
    const res = await fetch(url, { ...defaults, ...opts });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }
    return res.json();
  }

  function escHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  // ── Init ────────────────────────────────────────────────────────────────
  loadLocalities();
  loadTable();

})();
