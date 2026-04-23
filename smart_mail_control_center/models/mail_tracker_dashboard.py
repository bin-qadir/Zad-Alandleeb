"""
SMART MAIL CONTROL CENTER — Per-User Dashboard
===============================================

mail.tracker.dashboard is a TransientModel (no database table).
A fresh record is created each time the user opens the dashboard.
Computed KPI fields are calculated on-the-fly for the current user.

Each KPI integer field has a corresponding action_open_* method that opens
a filtered mail.tracker.record list/kanban view.

The dashboard menu action calls action_open_my_dashboard() which creates
a new transient record and redirects to it.
"""
from odoo import api, fields, models, _


class MailTrackerDashboard(models.TransientModel):
    """Per-user email workload dashboard."""

    _name = 'mail.tracker.dashboard'
    _description = 'Mail Tracker User Dashboard'

    # ── KPI counts ────────────────────────────────────────────────────────────

    important_inbox_count = fields.Integer(
        string='Important Inbox',
        compute='_compute_kpis',
    )
    other_inbox_count = fields.Integer(
        string='Other Inbox',
        compute='_compute_kpis',
    )
    sent_count = fields.Integer(
        string='Sent Emails',
        compute='_compute_kpis',
    )
    drafts_count = fields.Integer(
        string='Drafts',
        compute='_compute_kpis',
    )
    assigned_to_me_count = fields.Integer(
        string='Assigned To Me',
        compute='_compute_kpis',
    )
    waiting_reply_count = fields.Integer(
        string='Waiting Reply',
        compute='_compute_kpis',
    )
    escalated_count = fields.Integer(
        string='Escalated',
        compute='_compute_kpis',
    )
    overdue_count = fields.Integer(
        string='Overdue Follow-up',
        compute='_compute_kpis',
    )
    converted_to_task_count = fields.Integer(
        string='Converted to Tasks',
        compute='_compute_kpis',
    )
    total_open_count = fields.Integer(
        string='Total Open',
        compute='_compute_kpis',
    )

    # ── Intelligence KPIs (Part 6) ────────────────────────────────────────────

    linked_to_project_count = fields.Integer(
        string='Linked to Project',
        compute='_compute_intelligence_kpis',
    )
    unlinked_count = fields.Integer(
        string='Unlinked Emails',
        compute='_compute_intelligence_kpis',
    )
    requires_action_count = fields.Integer(
        string='Requires Action',
        compute='_compute_intelligence_kpis',
    )
    auto_tasks_count = fields.Integer(
        string='Auto-Tasks Created',
        compute='_compute_intelligence_kpis',
    )

    # ── Operational Link KPIs (Part 9) ───────────────────────────────────────

    linked_claims_count = fields.Integer(
        string='Linked Claims',
        compute='_compute_operational_kpis',
    )
    linked_contracts_count = fields.Integer(
        string='Linked Contracts',
        compute='_compute_operational_kpis',
    )
    linked_invoices_count = fields.Integer(
        string='Linked Invoices',
        compute='_compute_operational_kpis',
    )
    linked_boq_emails_count = fields.Integer(
        string='Linked BOQ Emails',
        compute='_compute_operational_kpis',
    )
    linked_rfq_emails_count = fields.Integer(
        string='Linked RFQ Emails',
        compute='_compute_operational_kpis',
    )

    # ── Decision Engine KPIs (Part 8) ─────────────────────────────────────────

    high_priority_count = fields.Integer(
        string='High Priority',
        compute='_compute_decision_kpis',
    )
    decision_required_count = fields.Integer(
        string='Decision Required',
        compute='_compute_decision_kpis',
    )
    escalated_now_count = fields.Integer(
        string='Escalated Now',
        compute='_compute_decision_kpis',
    )
    deadline_critical_count = fields.Integer(
        string='Deadline Critical',
        compute='_compute_decision_kpis',
    )
    low_confidence_count = fields.Integer(
        string='Low Confidence',
        compute='_compute_decision_kpis',
    )

    # ── Alert KPIs (Part 7 — Intelligence Engine) ─────────────────────────────

    not_assigned_count = fields.Integer(
        string='Not Assigned',
        compute='_compute_intelligence_kpis',
    )
    needs_action_count = fields.Integer(
        string='Needs Action',
        compute='_compute_intelligence_kpis',
    )
    delay_count = fields.Integer(
        string='Delay / EOT',
        compute='_compute_intelligence_kpis',
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends()
    def _compute_kpis(self):
        """Compute all KPI counts for the current user."""
        for rec in self:
            user_id = self.env.uid
            Tracker = self.env['mail.tracker.record']

            def count(domain):
                return Tracker.search_count(domain)

            base_mine = [('assigned_user_id', '=', user_id)]
            open_states = [('state', 'not in', ['done', 'archived'])]

            rec.important_inbox_count = count([
                ('mailbox_type', '=', 'inbox_important'),
            ] + open_states)

            rec.other_inbox_count = count([
                ('mailbox_type', '=', 'inbox_other'),
            ] + open_states)

            rec.sent_count = count([
                ('mailbox_type', '=', 'sent'),
            ] + open_states)

            rec.drafts_count = count([
                ('mailbox_type', '=', 'drafts'),
            ] + open_states)

            rec.assigned_to_me_count = count(
                base_mine + [('state', 'not in', ['done', 'archived'])]
            )

            rec.waiting_reply_count = count([
                ('state', '=', 'waiting'),
            ])

            rec.escalated_count = count([
                ('state', '=', 'escalated'),
            ])

            # Overdue: in open state and older than threshold
            from datetime import timedelta
            from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
            cutoff = fields.Datetime.now() - timedelta(days=3)
            rec.overdue_count = count([
                ('state', 'in', ['new', 'assigned', 'in_progress', 'waiting']),
                ('received_date', '<=', cutoff),
            ])

            rec.converted_to_task_count = count([
                ('converted_to_task', '=', True),
            ])

            rec.total_open_count = count(open_states)

    @api.depends()
    def _compute_intelligence_kpis(self):
        """Compute auto-link intelligence KPIs."""
        for rec in self:
            Tracker = self.env['mail.tracker.record']
            open_filter = [('state', 'not in', ['done', 'archived'])]

            rec.linked_to_project_count = Tracker.search_count(
                [('project_id', '!=', False)] + open_filter
            )
            rec.unlinked_count = Tracker.search_count(
                [('project_id', '=', False)] + open_filter
            )
            rec.requires_action_count = Tracker.search_count(
                [('requires_action', '=', True)] + open_filter
            )
            rec.auto_tasks_count = Tracker.search_count(
                [('auto_task_created', '=', True)]
            )
            rec.not_assigned_count = Tracker.search_count(
                [('not_assigned', '=', True)] + open_filter
            )
            rec.needs_action_count = Tracker.search_count(
                [('needs_action', '=', True)] + open_filter
            )
            rec.delay_count = Tracker.search_count(
                [('mail_type', '=', 'delay')] + open_filter
            )

    # ── Dashboard entry ───────────────────────────────────────────────────────

    @api.model
    def action_open_my_dashboard(self):
        """Create a fresh dashboard record for the current user and open it."""
        record = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _('My Email Dashboard'),
            'res_model': 'mail.tracker.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'main',
            'flags': {'mode': 'readonly'},
        }

    # ── KPI drill-down actions ────────────────────────────────────────────────

    def _open_tracker_list(self, domain, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'mail.tracker.record',
            'view_mode': 'list,form,kanban',
            'domain': domain,
            'context': {'search_default_my_emails': 0},
        }

    def action_open_important_inbox(self):
        return self._open_tracker_list(
            [('mailbox_type', '=', 'inbox_important'),
             ('state', 'not in', ['done', 'archived'])],
            _('Important Inbox'),
        )

    def action_open_other_inbox(self):
        return self._open_tracker_list(
            [('mailbox_type', '=', 'inbox_other'),
             ('state', 'not in', ['done', 'archived'])],
            _('Other Inbox'),
        )

    def action_open_sent(self):
        return self._open_tracker_list(
            [('mailbox_type', '=', 'sent'),
             ('state', 'not in', ['done', 'archived'])],
            _('Sent Emails'),
        )

    def action_open_drafts(self):
        return self._open_tracker_list(
            [('mailbox_type', '=', 'drafts')],
            _('Drafts'),
        )

    def action_open_assigned_to_me(self):
        return self._open_tracker_list(
            [('assigned_user_id', '=', self.env.uid),
             ('state', 'not in', ['done', 'archived'])],
            _('Assigned To Me'),
        )

    def action_open_waiting_reply(self):
        return self._open_tracker_list(
            [('state', '=', 'waiting')],
            _('Waiting Reply'),
        )

    def action_open_escalated(self):
        return self._open_tracker_list(
            [('state', '=', 'escalated')],
            _('Escalated'),
        )

    def action_open_overdue(self):
        from datetime import timedelta
        cutoff = fields.Datetime.now() - timedelta(days=3)
        return self._open_tracker_list(
            [('state', 'in', ['new', 'assigned', 'in_progress', 'waiting']),
             ('received_date', '<=', cutoff)],
            _('Overdue Follow-up'),
        )

    def action_open_converted_tasks(self):
        return self._open_tracker_list(
            [('converted_to_task', '=', True)],
            _('Converted to Tasks'),
        )

    def action_open_all(self):
        return self._open_tracker_list(
            [('state', 'not in', ['done', 'archived'])],
            _('All Open Emails'),
        )

    def action_manual_sync(self):
        """Trigger an immediate email sync from the dashboard."""
        return self.env['mail.tracker.record'].action_manual_scan()

    # ── Intelligence KPI drill-downs ──────────────────────────────────────────

    def action_open_linked_to_project(self):
        return self._open_tracker_list(
            [('project_id', '!=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Linked to Project'),
        )

    def action_open_unlinked(self):
        return self._open_tracker_list(
            [('project_id', '=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Unlinked Emails'),
        )

    def action_open_requires_action(self):
        return self._open_tracker_list(
            [('requires_action', '=', True),
             ('state', 'not in', ['done', 'archived'])],
            _('Requires Action'),
        )

    def action_open_auto_tasks(self):
        return self._open_tracker_list(
            [('auto_task_created', '=', True)],
            _('Auto-Tasks Created'),
        )

    @api.depends()
    def _compute_operational_kpis(self):
        """Compute operational document link KPIs."""
        for rec in self:
            Tracker = self.env['mail.tracker.record']
            open_filter = [('state', 'not in', ['done', 'archived'])]

            rec.linked_claims_count = Tracker.search_count(
                [('op_claim_id', '!=', False)] + open_filter
            )
            rec.linked_contracts_count = Tracker.search_count(
                [('op_contract_id', '!=', False)] + open_filter
            )
            rec.linked_invoices_count = Tracker.search_count(
                [('op_invoice_id', '!=', False)] + open_filter
            )
            rec.linked_boq_emails_count = Tracker.search_count(
                [('op_boq_id', '!=', False)] + open_filter
            )
            # RFQ covers both Material Request (primary) and Purchase Order (fallback)
            rec.linked_rfq_emails_count = Tracker.search_count(
                ['&', '|',
                 ('op_rfq_mr_id', '!=', False),
                 ('op_rfq_po_id', '!=', False),
                 ('state', 'not in', ['done', 'archived'])]
            )

    # ── Operational KPI drill-downs ────────────────────────────────────────────

    def action_open_linked_claims(self):
        return self._open_tracker_list(
            [('op_claim_id', '!=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Emails Linked to Claims'),
        )

    def action_open_linked_contracts(self):
        return self._open_tracker_list(
            [('op_contract_id', '!=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Emails Linked to Contracts'),
        )

    def action_open_linked_invoices(self):
        return self._open_tracker_list(
            [('op_invoice_id', '!=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Emails Linked to Invoices'),
        )

    def action_open_linked_boq(self):
        return self._open_tracker_list(
            [('op_boq_id', '!=', False),
             ('state', 'not in', ['done', 'archived'])],
            _('Emails Linked to BOQ'),
        )

    def action_open_linked_rfq(self):
        """Open emails linked to RFQ (Material Request or Purchase Order)."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Emails Linked to RFQ / Procurement'),
            'res_model': 'mail.tracker.record',
            'view_mode': 'list,form,kanban',
            'domain': ['&', '|',
                       ('op_rfq_mr_id', '!=', False),
                       ('op_rfq_po_id', '!=', False),
                       ('state', 'not in', ['done', 'archived'])],
            'context': {'search_default_my_emails': 0},
        }

    @api.depends()
    def _compute_decision_kpis(self):
        """Compute Decision Engine KPIs."""
        from datetime import timedelta
        today = fields.Date.today()
        cutoff = today + timedelta(days=3)

        for rec in self:
            Tracker = self.env['mail.tracker.record']
            open_filter = [('state', 'not in', ['done', 'archived'])]

            rec.high_priority_count = Tracker.search_count(
                [('priority_score', '>=', 70)] + open_filter
            )
            rec.decision_required_count = Tracker.search_count([
                ('recommended_action', 'not in', ['general', False]),
                ('recommended_action', '!=', 'archive'),
                ('state', 'in', ['new', 'assigned']),
            ])
            rec.escalated_now_count = Tracker.search_count([
                ('state', '=', 'escalated'),
            ])
            rec.deadline_critical_count = Tracker.search_count(
                [('parsed_deadline', '!=', False),
                 ('parsed_deadline', '<=', cutoff)] + open_filter
            )
            rec.low_confidence_count = Tracker.search_count(
                [('route_confidence', '>', 0),
                 ('route_confidence', '<', 50),
                 ('mail_type', '!=', 'general')] + open_filter
            )

    # ── Decision Engine KPI drill-downs ───────────────────────────────────────

    def action_open_high_priority(self):
        return self._open_tracker_list(
            [('priority_score', '>=', 70),
             ('state', 'not in', ['done', 'archived'])],
            _('High Priority Emails'),
        )

    def action_open_decision_required(self):
        return self._open_tracker_list(
            [('recommended_action', 'not in', ['general', False, 'archive']),
             ('state', 'in', ['new', 'assigned'])],
            _('Decision Required'),
        )

    def action_open_escalated_now(self):
        return self._open_tracker_list(
            [('state', '=', 'escalated')],
            _('Escalated Emails'),
        )

    def action_open_deadline_critical(self):
        from datetime import timedelta
        today = fields.Date.today()
        cutoff = today + timedelta(days=3)
        return self._open_tracker_list(
            [('parsed_deadline', '!=', False),
             ('parsed_deadline', '<=', cutoff),
             ('state', 'not in', ['done', 'archived'])],
            _('Deadline Critical'),
        )

    def action_open_low_confidence(self):
        return self._open_tracker_list(
            [('route_confidence', '>', 0),
             ('route_confidence', '<', 50),
             ('mail_type', '!=', 'general'),
             ('state', 'not in', ['done', 'archived'])],
            _('Low Confidence Classifications'),
        )

    def action_open_not_assigned(self):
        return self._open_tracker_list(
            [('not_assigned', '=', True),
             ('state', 'not in', ['done', 'archived'])],
            _('Not Assigned'),
        )

    def action_open_needs_action(self):
        return self._open_tracker_list(
            [('needs_action', '=', True),
             ('state', 'not in', ['done', 'archived'])],
            _('Needs Action'),
        )

    def action_open_delay(self):
        return self._open_tracker_list(
            [('mail_type', '=', 'delay'),
             ('state', 'not in', ['done', 'archived'])],
            _('Delay / EOT Notices'),
        )

    def action_run_auto_processing(self):
        """Re-run the full auto-link pipeline on all open unprocessed emails."""
        records = self.env['mail.tracker.record'].search([
            ('state', 'not in', ['done', 'archived']),
            ('mail_type', '=', 'general'),
        ], limit=200)
        if records:
            records.run_full_auto_processing()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto-Processing Complete'),
                'message': _(
                    'Processed %(n)d emails — type classification, project linking, '
                    'document routing, and auto-tasks applied.',
                    n=len(records),
                ),
                'type': 'success',
                'sticky': False,
            },
        }
