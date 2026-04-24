"""
mythos.agent.log — Per-run audit log for Mythos AI Agents
==========================================================
Each record captures one run event: what ran, when, result, and optional
link to the record that triggered or was affected by the run.
"""
from odoo import api, fields, models, _
from .mythos_agent import AGENT_LAYER_SELECTION, AGENT_FUNCTION_SELECTION


class MythosAgentLog(models.Model):
    """Mythos Agent Log — audit trail for every agent run."""

    _name        = 'mythos.agent.log'
    _description = 'Mythos Agent Log'
    _order       = 'datetime desc, id desc'
    _rec_name    = 'title'

    # ── Agent link ────────────────────────────────────────────────────────────

    agent_id = fields.Many2one(
        'mythos.agent',
        string='Agent',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # ── When ──────────────────────────────────────────────────────────────────

    datetime = fields.Datetime(
        string='Date / Time',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    # ── Classification (mirrored from agent for direct filtering) ─────────────

    agent_layer = fields.Selection(
        selection=AGENT_LAYER_SELECTION,
        string='Agent Layer',
        index=True,
    )
    agent_function = fields.Selection(
        selection=AGENT_FUNCTION_SELECTION,
        string='Agent Function',
        index=True,
    )

    # ── Content ───────────────────────────────────────────────────────────────

    title = fields.Char(
        string='Title',
        required=True,
        help='Short summary of the log entry.',
    )
    details = fields.Text(
        string='Details',
        help='Full narrative: what the agent did, what it found, and what it recommends.',
    )

    # ── Outcome ───────────────────────────────────────────────────────────────

    result = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('warning', 'Warning'),
            ('failed',  'Failed'),
        ],
        string='Result',
        required=True,
        default='success',
        index=True,
    )

    # ── Affected record ───────────────────────────────────────────────────────

    related_model = fields.Char(
        string='Related Model',
        help='Technical model name of the record affected by this run (e.g. farm.job.order).',
    )
    related_record_id = fields.Integer(
        string='Related Record ID',
        help='Database ID of the affected record.',
    )

    # ── User ──────────────────────────────────────────────────────────────────

    user_id = fields.Many2one(
        'res.users',
        string='Triggered By',
        default=lambda self: self.env.uid,
        ondelete='set null',
        index=True,
    )
