/** @odoo-module **/
/**
 * MYTHOS — TELEGRAM FLOATING WIDGET  (Step 6)
 * ============================================
 *
 * Global floating chat panel (WhatsApp-style).
 * Registered in the `main_components` registry so it mounts on every
 * backend screen without any extra menu or action.
 *
 * Features:
 *   • Fixed bottom-right FAB with Telegram icon
 *   • Click-to-expand panel showing last 10 mythos.telegram.message records
 *   • Auto-refresh every 5 s (only while panel is open)
 *   • Send messages via mythos.telegram.message.widget_send_message()
 *   • Enter-to-send keyboard shortcut
 *   • Respects Odoo access rights — silent fail if no read permission
 */

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Format an Odoo datetime string ("YYYY-MM-DD HH:MM:SS" UTC) as HH:MM local.
 */
function formatDate(dtStr) {
    if (!dtStr) return "";
    try {
        // Odoo returns naive UTC strings — append Z so Date parses as UTC
        const d = new Date(dtStr.replace(" ", "T") + "Z");
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (_) {
        return dtStr;
    }
}

// ── Component ─────────────────────────────────────────────────────────────────

class TelegramFloatingWidget extends Component {
    static template = "mythos_agents.TelegramFloatingWidget";
    static props = {};

    setup() {
        this.orm  = useService("orm");
        this.state = useState({
            isOpen:    false,
            messages:  [],
            inputText: "",
            sending:   false,
            hasAccess: true,
        });

        this.msgListRef = useRef("msgList");
        this._intervalId = null;

        // Expose helper to template scope
        this.formatDate = formatDate;

        onMounted(() => {
            // Auto-refresh every 5 s — fetch only when panel is open
            this._intervalId = setInterval(() => {
                if (this.state.isOpen) {
                    this._loadMessages();
                }
            }, 5000);
        });

        onWillUnmount(() => {
            if (this._intervalId) {
                clearInterval(this._intervalId);
                this._intervalId = null;
            }
        });
    }

    // ── Panel toggle ──────────────────────────────────────────────────────────

    togglePanel() {
        this.state.isOpen = !this.state.isOpen;
        if (this.state.isOpen) {
            this._loadMessages();
        }
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    async _loadMessages() {
        try {
            const msgs = await this.orm.searchRead(
                "mythos.telegram.message",
                [],
                ["message_text", "direction", "state", "message_date"],
                { limit: 10, order: "message_date asc" }
            );
            this.state.messages  = msgs;
            this.state.hasAccess = true;
            this._scrollToBottom();
        } catch (_err) {
            // User has no read access — show restricted notice, don't crash
            this.state.hasAccess = false;
        }
    }

    _scrollToBottom() {
        requestAnimationFrame(() => {
            const el = this.msgListRef.el;
            if (el) el.scrollTop = el.scrollHeight;
        });
    }

    // ── Send ──────────────────────────────────────────────────────────────────

    onKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    async sendMessage() {
        const text = (this.state.inputText || "").trim();
        if (!text || this.state.sending) return;

        this.state.sending = true;
        try {
            await this.orm.call(
                "mythos.telegram.message",
                "widget_send_message",
                [[], text]   // args[0]=IDs (empty for @api.model), args[1]=text
            );
            this.state.inputText = "";
            await this._loadMessages();
        } catch (_err) {
            // Silent — connection errors or access errors must not crash the UI
        } finally {
            this.state.sending = false;
        }
    }
}

// ── Register as a global main component ───────────────────────────────────────

registry.category("main_components").add("MythosTelegramFloatingWidget", {
    Component: TelegramFloatingWidget,
    props: {},
});
