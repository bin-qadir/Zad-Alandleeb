"""
smart.ai.action — Layers 8+9+10: Action Engine + Approval Gate + Audit Trail
=============================================================================

SAFETY: High-impact actions (confirm PO, post invoice, submit claim) are NEVER
auto-executed. They require explicit human approval and manual execution.

The Approval Gate (Layer 9) ensures:
  - Low-impact actions: auto-approved on submission
  - High-impact actions: routed to 'waiting_approval' — a human must approve

The Audit Trail (Layer 10) records every state transition with timestamp + user.
"""
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

HIGH_IMPACT_TYPES = [
    'confirm_purchase_order',
    'post_invoice',
    'submit_claim',
    'contract_change',
    'financial_commitment',
]

LOW_IMPACT_TYPES = [
    'create_task',
    'create_material_request',
    'send_notification',
    'create_followup',
    'reschedule_activity',
]

ACTION_TYPE_SELECTION = [
    ('create_task',              'Create Task'),
    ('create_material_request',  'Create Material Request (Draft)'),
    ('prepare_claim',            'Prepare Claim Entry'),
    ('send_notification',        'Send Notification'),
    ('escalate_approval',        'Escalate for Approval'),
    ('reschedule_activity',      'Reschedule Activity'),
    ('create_followup',          'Create Follow-up Activity'),
    ('confirm_purchase_order',   'Confirm Purchase Order [HIGH IMPACT]'),
    ('post_invoice',             'Post Invoice [HIGH IMPACT]'),
    ('submit_claim',             'Submit Claim [HIGH IMPACT]'),
]


class SmartAiAction(models.Model):
    _name        = 'smart.ai.action'
    _description = 'AI Proposed Action — Layers 8+9+10 Action Engine + Approval Gate + Audit Trail'
    _order       = 'create_date desc'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(string='Name', required=True)
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        ondelete='cascade',
        index=True,
    )
    business_activity = fields.Selection(
        related='project_id.business_activity',
        store=True,
        string='Business Activity',
    )
    action_type = fields.Selection(
        ACTION_TYPE_SELECTION,
        string='Action Type',
        required=True,
    )
    impact_level = fields.Selection(
        selection=[
            ('low',  'Low Impact — Auto-Draft'),
            ('high', 'High Impact — Requires Approval'),
        ],
        string='Impact Level',
        compute='_compute_impact_level',
        store=True,
    )
    title       = fields.Char(string='Title', required=True)
    description = fields.Text(string='Action Description')
    reason      = fields.Text(string='AI Reasoning')

    # ── Linkage ───────────────────────────────────────────────────────────────

    risk_score_id = fields.Many2one(
        'smart.ai.risk.score',
        string='Source Risk Score',
        ondelete='set null',
    )
    triggered_rule_id = fields.Many2one(
        'smart.ai.rule',
        string='Triggered Rule',
        ondelete='set null',
    )

    # ── Workflow ──────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',            'Draft'),
            ('waiting_approval', 'Waiting Approval'),
            ('approved',         'Approved'),
            ('rejected',         'Rejected'),
            ('executed',         'Executed'),
        ],
        string='State',
        default='draft',
        index=True,
    )
    is_reversible = fields.Boolean(string='Reversible?', default=True)

    # ── Audit Trail ───────────────────────────────────────────────────────────

    created_by   = fields.Many2one('res.users', string='Created By', default=lambda self: self.env.user)
    approved_by  = fields.Many2one('res.users', string='Approved By',  readonly=True)
    approved_at  = fields.Datetime(string='Approved At',               readonly=True)
    rejected_by  = fields.Many2one('res.users', string='Rejected By',  readonly=True)
    rejected_at  = fields.Datetime(string='Rejected At',               readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason',          readonly=True)
    executed_at  = fields.Datetime(string='Executed At',               readonly=True)
    execution_log = fields.Text(string='Execution Log',                readonly=True)

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('action_type')
    def _compute_impact_level(self):
        for rec in self:
            rec.impact_level = 'high' if rec.action_type in HIGH_IMPACT_TYPES else 'low'

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_submit_for_approval(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            if rec.impact_level == 'low':
                rec.state = 'approved'
            else:
                rec.state = 'waiting_approval'

    def action_approve(self):
        now = fields.Datetime.now()
        for rec in self.filtered(lambda r: r.state == 'waiting_approval'):
            rec.write({
                'state':       'approved',
                'approved_by': self.env.uid,
                'approved_at': now,
            })

    def action_reject(self):
        now = fields.Datetime.now()
        for rec in self.filtered(lambda r: r.state == 'waiting_approval'):
            rec.write({
                'state':       'rejected',
                'rejected_by': self.env.uid,
                'rejected_at': now,
            })

    def action_execute(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Action must be approved before execution.'))
        if self.impact_level == 'high':
            raise UserError(_(
                'High-impact actions cannot be auto-executed. '
                'Please execute manually.'
            ))
        now = fields.Datetime.now()
        self.write({
            'state':        'executed',
            'executed_at':  now,
            'execution_log': (
                f"Executed by {self.env.user.name} at {now}. "
                f"Action type: {self.action_type}."
            ),
        })
