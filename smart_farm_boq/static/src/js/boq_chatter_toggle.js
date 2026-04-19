/** @odoo-module **/
/**
 * BOQ Chatter Toggle Widget
 *
 * Renders a small "Show / Hide Discussion" button inside the BOQ form.
 * Default state: chatter HIDDEN (maximises the BOQ table area).
 * State persisted to localStorage so it survives navigation.
 *
 * CSS contract
 * ─────────────────────────────────────────────────────────────────────
 *  .o_boq_form                      → chatter hidden  (default)
 *  .o_boq_form.boq-chatter-open     → chatter visible
 *
 * The CSS file (boq_chatter.css) applies display:none / display:flex
 * based on this class pair.
 */

import { Component, useState, onMounted } from "@odoo/owl";
import { xml } from "@odoo/owl";
import { registry } from "@web/core/registry";

const STORAGE_KEY = "boq_chatter_open";

class BoqChatterToggle extends Component {

    static template = xml`
<span class="o_boq_chatter_toggle_wrap d-inline-flex align-items-center">
    <button
        class="btn btn-sm o_boq_toggle_btn"
        t-att-class="state.open ? 'btn-secondary' : 'btn-outline-secondary'"
        t-on-click="toggle"
        t-att-title="state.open ? 'Hide Discussion Panel' : 'Show Discussion Panel'">
        <i t-att-class="'fa ' + (state.open ? 'fa-compress' : 'fa-comments-o')"/>
        <span class="ms-1" t-esc="state.open ? 'Hide Discussion' : 'Show Discussion'"/>
    </button>
</span>`;

    /* Accept any props the view framework passes (record, readonly, node …) */
    static props = { "*": true };

    setup() {
        /* Read saved preference; default to CLOSED (chatter hidden) */
        const saved = localStorage.getItem(STORAGE_KEY);
        this.state = useState({
            open: saved === "true",   /* "true" string → open; anything else → closed */
        });
        /* Apply initial state once the button is mounted in the DOM */
        onMounted(() => this._applyClass());
    }

    /* ── toggle ────────────────────────────────────────────────────── */
    toggle() {
        this.state.open = !this.state.open;
        localStorage.setItem(STORAGE_KEY, this.state.open ? "true" : "false");
        this._applyClass();
    }

    /* ── private helpers ───────────────────────────────────────────── */
    _applyClass() {
        const form = document.querySelector(".o_boq_form");
        if (form) {
            form.classList.toggle("boq-chatter-open", this.state.open);
        }
    }
}

/* Register as a named view widget so <widget name="boq_chatter_toggle"/>
   in the form XML renders this component. */
registry.category("view_widgets").add("boq_chatter_toggle", {
    component: BoqChatterToggle,
    extractProps: () => ({}),
});
