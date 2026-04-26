"""
mythos.alert — Mythos AI Alert
================================
Lightweight alert records created by the Mythos Basic Monitor cron and,
in future phases, by individual agents.

Safety rules (enforced by design):
  - No emails, no external messages, no API calls
  - Only creates records — never modifies existing operational data
  - Duplicate-safe: cron checks for open alerts before creating a new one
"""
import logging
from odoo import fields, models, _

_logger = logging.getLogger(__name__)


class MythosAlert(models.Model):
    """One alert record per triggered condition."""

    _name        = 'mythos.alert'
    _description = 'Mythos AI Alert'
    _order       = 'date desc, severity desc, id desc'
    _rec_name    = 'name'

    # ── Core identity ─────────────────────────────────────────────────────────

    name = fields.Char(
        string='Alert',
        required=True,
    )
    agent_id = fields.Many2one(
        comodel_name='mythos.agent',
        string='Agent',
        ondelete='set null',
        index=True,
    )

    # ── Classification ────────────────────────────────────────────────────────

    severity = fields.Selection(
        selection=[
            ('low',      'Low'),
            ('medium',   'Medium'),
            ('high',     'High'),
            ('critical', 'Critical'),
        ],
        string='Severity',
        required=True,
        default='medium',
        index=True,
    )
    state = fields.Selection(
        selection=[
            ('new',          'New'),
            ('acknowledged', 'Acknowledged'),
            ('resolved',     'Resolved'),
        ],
        string='State',
        required=True,
        default='new',
        index=True,
    )

    # ── Content ───────────────────────────────────────────────────────────────

    message = fields.Text(string='Message')
    date    = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        index=True,
    )

    # ── Source record reference (generic pointer, no FK) ──────────────────────

    related_model = fields.Char(
        string='Related Model',
        help='Technical model name (e.g. farm.project, farm.boq).',
    )
    related_id = fields.Integer(
        string='Related Record ID',
        help='ID of the record that triggered this alert.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Actions (safe: only write to this model)
    # ────────────────────────────────────────────────────────────────────────

    def action_acknowledge(self):
        """Mark selected alerts as Acknowledged."""
        self.write({'state': 'acknowledged'})

    def action_resolve(self):
        """Mark selected alerts as Resolved."""
        self.write({'state': 'resolved'})
