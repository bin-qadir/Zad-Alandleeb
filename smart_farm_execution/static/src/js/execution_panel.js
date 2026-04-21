/** @odoo-module **/
/**
 * Execution Control Panel — Tab Navigation
 *
 * Intercepts clicks (and keyboard activation) on .ecp-card elements
 * inside the farm.job.order form view and switches the notebook to
 * the corresponding tab page.
 *
 * Odoo 18 OWL notebook renders tab buttons as:
 *   <a class="nav-link" data-page-name="<page_name>">…</a>
 * inside .o_notebook_headers.
 */

// ─── Click handler ───────────────────────────────────────────────────────────
document.addEventListener("click", (evt) => {
    // Action buttons inside .ecp-actions handle their own Odoo RPC — skip tab switch
    if (evt.target.closest(".ecp-actions")) return;
    const card = evt.target.closest(".ecp-card[data-tab]");
    if (!card) return;
    activateTab(card, card.dataset.tab);
}, false);

// ─── Keyboard handler (Enter / Space) ────────────────────────────────────────
document.addEventListener("keydown", (evt) => {
    if (evt.key !== "Enter" && evt.key !== " ") return;
    if (evt.target.closest(".ecp-actions")) return;
    const card = evt.target.closest(".ecp-card[data-tab]");
    if (!card) return;
    evt.preventDefault();
    activateTab(card, card.dataset.tab);
}, false);

// ─── Core: find + click the matching notebook tab button ─────────────────────
function activateTab(card, tabName) {
    // Walk up to the enclosing Odoo form view
    const formView = card.closest(".o_form_view");
    if (!formView) return;

    const notebook = formView.querySelector(".o_notebook");
    if (!notebook) return;

    // Odoo 18 selectors (try most-specific first)
    const btn =
        notebook.querySelector(`.o_notebook_headers .nav-link[data-page-name="${tabName}"]`) ||
        notebook.querySelector(`.o_notebook_headers a[data-page-name="${tabName}"]`)         ||
        notebook.querySelector(`.nav-link[data-page-name="${tabName}"]`)                      ||
        notebook.querySelector(`[data-page-name="${tabName}"]`);

    if (btn) {
        btn.click();

        // Highlight the active card in the panel
        formView.querySelectorAll(".ecp-card.ecp-active").forEach((c) => c.classList.remove("ecp-active"));
        card.classList.add("ecp-active");

        // Smooth-scroll the notebook into view after OWL re-render
        setTimeout(() => {
            notebook.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 70);
    }
}

// ─── Sync active-card highlight when notebook tab changes externally ──────────
// (e.g., user clicks the tab directly — removes the ecp-active class)
document.addEventListener("click", (evt) => {
    const tabBtn = evt.target.closest(".o_notebook_headers .nav-link");
    if (!tabBtn) return;

    const formView = tabBtn.closest(".o_form_view");
    if (!formView) return;

    const pageName = tabBtn.dataset.pageName;
    if (!pageName) return;

    // Sync: mark the matching ecp-card active, clear the rest
    formView.querySelectorAll(".ecp-card").forEach((c) => {
        const matches = c.dataset.tab === pageName;
        c.classList.toggle("ecp-active", matches);
    });
}, false);
