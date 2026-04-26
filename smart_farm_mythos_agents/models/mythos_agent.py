"""
mythos.agent — Construction Mythos Agent Registry
==================================================
Each record represents one AI agent classified by:
  • business_activity (currently: construction only)
  • agent_layer       (8 operational layers)
  • agent_function    (one of 14 specific functions)

This module only defines the registry and logging skeleton.
Heavy analysis logic is intentionally deferred to later phases.
"""
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── Selection constants ────────────────────────────────────────────────────────

AGENT_LAYER_SELECTION = [
    ('pre_contract',       'Pre-Contract'),
    ('contract',           'Contract'),
    ('execution',          'Execution'),
    ('procurement',        'Procurement'),
    ('quality_handover',   'Quality & Handover'),
    ('financial_claims',   'Financial Claims'),
    ('risk_control',       'Risk & Control'),
    ('executive_dashboard','Executive Dashboard'),
]

AGENT_FUNCTION_SELECTION = [
    ('boq_analysis',        'BOQ Analysis'),
    ('costing_analysis',    'Costing Analysis'),
    ('quotation_review',    'Quotation Review'),
    ('contract_control',    'Contract Control'),
    ('job_order_monitor',   'Job Order Monitor'),
    ('resources_monitor',   'Resources Monitor'),
    ('procurement_monitor', 'Procurement Monitor'),
    ('quality_inspection',  'Quality Inspection'),
    ('handover_control',    'Handover Control'),
    ('claims_control',      'Claims Control'),
    ('invoicing_control',   'Invoicing Control'),
    ('risk_monitor',        'Risk Monitor'),
    ('compliance_monitor',  'Compliance Monitor'),
    ('executive_summary',   'Executive Summary'),
]

LAST_STATUS_SELECTION = [
    ('never_run', 'Never Run'),
    ('success',   'Success'),
    ('warning',   'Warning'),
    ('failed',    'Failed'),
]


class MythosAgent(models.Model):
    """Mythos Agent — one entry per AI agent in the Construction pipeline."""

    _name        = 'mythos.agent'
    _description = 'Mythos AI Agent'
    _order       = 'sequence, agent_layer, name'
    _rec_name    = 'name'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Agent Name',
        required=True,
        tracking=True,
        help='Editable agent name. Never overwritten by system upgrades.',
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique machine-readable identifier (e.g. MYTHOS-BOQ).',
    )
    business_activity = fields.Selection(
        selection=[
            ('construction', 'Construction'),
        ],
        string='Business Activity',
        default='construction',
        required=True,
        index=True,
        tracking=True,
    )

    # ── Classification ────────────────────────────────────────────────────────

    agent_layer = fields.Selection(
        selection=AGENT_LAYER_SELECTION,
        string='Agent Layer',
        required=True,
        index=True,
        tracking=True,
        help='The operational layer this agent belongs to.',
    )
    agent_function = fields.Selection(
        selection=AGENT_FUNCTION_SELECTION,
        string='Agent Function',
        required=True,
        index=True,
        tracking=True,
        help='Specific analytical function this agent performs.',
    )
    description = fields.Text(
        string='Description',
        help='What this agent does, what it monitors, and what actions it can take.',
    )

    # ── Visibility / ordering ─────────────────────────────────────────────────

    active   = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Lower sequence = displayed first within the same layer.',
    )

    # ── Lifecycle state (Step 1 — basic monitor integration) ──────────────────

    state = fields.Selection(
        selection=[
            ('draft',  'Draft'),
            ('active', 'Active'),
            ('paused', 'Paused'),
        ],
        string='State',
        default='active',
        required=True,
        tracking=True,
        help=(
            'Draft: agent defined but not yet enabled.\n'
            'Active: agent is enabled and will run on the cron schedule.\n'
            'Paused: agent is temporarily disabled.'
        ),
    )
    priority = fields.Integer(
        string='Priority',
        default=5,
        help='Lower number = higher priority (1 = highest, 10 = lowest).',
    )

    # ── Run metadata ──────────────────────────────────────────────────────────

    last_run_datetime = fields.Datetime(
        string='Last Run',
        readonly=True,
        copy=False,
        tracking=True,
    )
    last_status = fields.Selection(
        selection=LAST_STATUS_SELECTION,
        string='Last Status',
        default='never_run',
        readonly=True,
        copy=False,
        tracking=True,
    )
    run_count = fields.Integer(
        string='Run Count',
        readonly=True,
        copy=False,
        default=0,
    )

    # ── KPI counters (set by the analysis logic in future phases) ─────────────

    insight_count = fields.Integer(
        string='Insights',
        readonly=True,
        copy=False,
        default=0,
        help='Total insights generated by this agent across all runs.',
    )
    action_count = fields.Integer(
        string='Actions',
        readonly=True,
        copy=False,
        default=0,
        help='Total recommended actions raised by this agent across all runs.',
    )

    # ── Logs ──────────────────────────────────────────────────────────────────

    log_ids = fields.One2many(
        'mythos.agent.log',
        'agent_id',
        string='Logs',
    )
    log_count = fields.Integer(
        string='Log Entries',
        compute='_compute_log_count',
    )

    # ── Alerts (from mythos.alert via agent_id) ───────────────────────────────

    alert_ids = fields.One2many(
        'mythos.alert',
        'agent_id',
        string='Alerts',
    )
    alert_count = fields.Integer(
        string='Open Alerts',
        compute='_compute_alert_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    @api.depends('alert_ids.state')
    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = len(rec.alert_ids.filtered(
                lambda a: a.state != 'resolved'
            ))

    # ────────────────────────────────────────────────────────────────────────
    # Constraints
    # ────────────────────────────────────────────────────────────────────────

    _sql_constraints = [
        (
            'code_unique',
            'UNIQUE(code)',
            'Agent code must be unique across all Mythos agents.',
        ),
    ]

    # ────────────────────────────────────────────────────────────────────────
    # Placeholder run action
    # ────────────────────────────────────────────────────────────────────────

    def action_run_agent(self):
        """Placeholder: run this agent.

        In Phase 1 this simply records a success log entry and updates the
        run metadata.  Heavy analysis logic will be added in later phases.
        """
        self.ensure_one()
        _logger.info('MythosAgent [%s / %s]: run triggered (placeholder)', self.code, self.name)

        log = self.env['mythos.agent.log'].create({
            'agent_id':       self.id,
            'agent_layer':    self.agent_layer,
            'agent_function': self.agent_function,
            'title':          _('Agent run triggered — %s') % self.name,
            'details':        _(
                'Placeholder run. Analysis logic will be implemented in future phases.\n'
                'Agent: %(name)s\nLayer: %(layer)s\nFunction: %(fn)s',
                name=self.name,
                layer=dict(AGENT_LAYER_SELECTION).get(self.agent_layer, self.agent_layer),
                fn=dict(AGENT_FUNCTION_SELECTION).get(self.agent_function, self.agent_function),
            ),
            'result':         'success',
            'user_id':        self.env.uid,
        })

        self.write({
            'last_run_datetime': fields.Datetime.now(),
            'last_status':       'success',
            'run_count':         self.run_count + 1,
        })

        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Agent Run — %s') % self.name,
                'message': _('Run logged successfully. Log entry: %s', log.title),
                'type':    'success',
                'sticky':  False,
            },
        }

    def action_view_logs(self):
        """Open all log entries for this agent."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Logs — %s') % self.name,
            'res_model': 'mythos.agent.log',
            'view_mode': 'list,form',
            'domain':    [('agent_id', '=', self.id)],
            'context':   {'default_agent_id': self.id},
        }

    def action_view_alerts(self):
        """Open open alerts for this agent."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Alerts — %s') % self.name,
            'res_model': 'mythos.alert',
            'view_mode': 'list,form',
            'domain':    [('agent_id', '=', self.id)],
            'context':   {'default_agent_id': self.id},
        }

    # ────────────────────────────────────────────────────────────────────────
    # Mythos Basic Monitor — cron entry point (Step 1)
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _run_basic_monitor(self):
        """Cron: Mythos Basic Monitor (runs every 60 minutes).

        Three lightweight checks using the three basic monitor agents
        (codes: boq_agent, execution_agent, financial_agent).

        SAFETY:
          - Never sends emails or external messages
          - Never calls external APIs
          - Never modifies existing farm.project / farm.boq data
          - Only creates mythos.alert records
          - Duplicate-safe: skips if an open alert already exists for the
            same agent + related record combination
        """
        Alert = self.env['mythos.alert']

        def _get_agent(code):
            return self.search([('code', '=', code), ('state', '=', 'active')], limit=1)

        def _alert_exists(agent, related_model, related_id):
            return bool(Alert.search([
                ('agent_id',      '=', agent.id),
                ('related_model', '=', related_model),
                ('related_id',    '=', related_id),
                ('state',         '!=', 'resolved'),
            ], limit=1))

        # ── 1. BOQ Agent — actual cost > 110% of estimated cost ───────────────
        boq_agent = _get_agent('boq_agent')
        if boq_agent:
            for boq in self.env['farm.boq'].search([]):
                proj = boq.project_id
                if not proj:
                    continue
                estimated = proj.estimated_cost or 0.0
                actual    = proj.actual_total_cost or 0.0
                if estimated and actual and actual > estimated * 1.1:
                    if not _alert_exists(boq_agent, 'farm.boq', boq.id):
                        Alert.create({
                            'name':          _('BOQ Cost Overrun — %s') % boq.name,
                            'agent_id':      boq_agent.id,
                            'severity':      'high',
                            'message':       _(
                                'Actual cost (%(actual).2f) exceeds estimated cost '
                                '(%(estimated).2f) by more than 10%% on BOQ %(boq)s '
                                '(Project: %(project)s).',
                                actual=actual,
                                estimated=estimated,
                                boq=boq.name,
                                project=proj.name,
                            ),
                            'related_model': 'farm.boq',
                            'related_id':    boq.id,
                        })
            _logger.info('MythosBasicMonitor: BOQ Agent check complete.')

        # ── 2. Execution Agent — progress < 50% in execution phase ────────────
        exec_agent = _get_agent('execution_agent')
        if exec_agent:
            for proj in self.env['farm.project'].search([
                ('project_phase', '=', 'execution'),
            ]):
                if (proj.execution_progress_pct or 0.0) < 50.0:
                    if not _alert_exists(exec_agent, 'farm.project', proj.id):
                        Alert.create({
                            'name':          _('Execution Delay — %s') % proj.name,
                            'agent_id':      exec_agent.id,
                            'severity':      'medium',
                            'message':       _(
                                'Project %(project)s is in Execution phase but only '
                                '%(pct).1f%% complete — below the 50%% threshold.',
                                project=proj.name,
                                pct=proj.execution_progress_pct or 0.0,
                            ),
                            'related_model': 'farm.project',
                            'related_id':    proj.id,
                        })
            _logger.info('MythosBasicMonitor: Execution Agent check complete.')

        # ── 3. Financial Agent — actual total cost > contract value ───────────
        fin_agent = _get_agent('financial_agent')
        if fin_agent:
            for proj in self.env['farm.project'].search([]):
                contract_val = proj.contract_value or 0.0
                actual_cost  = proj.actual_total_cost or 0.0
                if contract_val and actual_cost > contract_val:
                    if not _alert_exists(fin_agent, 'farm.project', proj.id):
                        Alert.create({
                            'name':          _('Cost Exceeds Contract — %s') % proj.name,
                            'agent_id':      fin_agent.id,
                            'severity':      'critical',
                            'message':       _(
                                'Actual total cost (%(actual).2f) has exceeded the '
                                'contract value (%(contract).2f) on project %(project)s.',
                                actual=actual_cost,
                                contract=contract_val,
                                project=proj.name,
                            ),
                            'related_model': 'farm.project',
                            'related_id':    proj.id,
                        })
            _logger.info('MythosBasicMonitor: Financial Agent check complete.')

        _logger.info('MythosBasicMonitor: full run complete.')
