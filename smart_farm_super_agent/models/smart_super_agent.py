"""
smart.super.agent — Mythos-style Super AI Agent Command Center
==============================================================
Singleton-per-activity.  Currently active only for Construction.
"""
import time
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SmartSuperAgent(models.Model):
    _name        = 'smart.super.agent'
    _description = 'Smart Super AI Agent — Command Center'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(string='Name', required=True)
    business_activity = fields.Selection(
        selection=[
            ('construction', 'Construction'),
            ('agriculture',  'Agriculture'),
            ('manufacturing','Manufacturing'),
            ('livestock',    'Livestock'),
        ],
        string='Business Activity',
        required=True,
        index=True,
    )
    active = fields.Boolean(default=True)

    # ── Run metadata ──────────────────────────────────────────────────────────

    last_run = fields.Datetime(
        string='Last Full Analysis',
        readonly=True,
    )
    last_run_projects = fields.Integer(
        string='Projects Analyzed',
        readonly=True,
    )
    last_run_duration = fields.Float(
        string='Duration (s)',
        digits=(16, 2),
        readonly=True,
    )

    # ── KPI fields (computed, not stored) ────────────────────────────────────

    total_projects = fields.Integer(
        string='Total Projects',
        compute='_compute_kpis',
        store=False,
    )
    critical_count = fields.Integer(
        string='Critical Projects',
        compute='_compute_kpis',
        store=False,
    )
    warning_count = fields.Integer(
        string='Warning Projects',
        compute='_compute_kpis',
        store=False,
    )
    healthy_count = fields.Integer(
        string='Healthy Projects',
        compute='_compute_kpis',
        store=False,
    )
    pending_actions_count = fields.Integer(
        string='Pending AI Actions',
        compute='_compute_kpis',
        store=False,
    )
    triggered_rule_count = fields.Integer(
        string='Rules Triggered Today',
        compute='_compute_kpis',
        store=False,
    )
    pending_suggestions_count = fields.Integer(
        string='Open Suggestions',
        compute='_compute_kpis',
        store=False,
    )

    # ── Compute KPIs ─────────────────────────────────────────────────────────

    @api.depends('business_activity')
    def _compute_kpis(self):
        for rec in self:
            if rec.business_activity != 'construction':
                rec.total_projects          = 0
                rec.critical_count          = 0
                rec.warning_count           = 0
                rec.healthy_count           = 0
                rec.pending_actions_count   = 0
                rec.triggered_rule_count    = 0
                rec.pending_suggestions_count = 0
                continue

            projects    = self.env['farm.project'].search([('business_activity', '=', 'construction')])
            project_ids = projects.ids

            scores = self.env['smart.ai.risk.score'].search([('project_id', 'in', project_ids)])

            rec.total_projects   = len(projects)
            rec.critical_count   = sum(1 for s in scores if s.status == 'critical')
            rec.warning_count    = sum(1 for s in scores if s.status == 'warning')
            rec.healthy_count    = sum(1 for s in scores if s.status == 'healthy')

            rec.pending_actions_count = self.env['smart.ai.action'].search_count([
                ('project_id', 'in', project_ids),
                ('state', 'in', ['draft', 'waiting_approval']),
            ])

            rec.triggered_rule_count = sum(s.triggered_rule_count for s in scores)

            rec.pending_suggestions_count = self.env['smart.ai.optimization.suggestion'].search_count([
                ('project_id', 'in', project_ids),
                ('state', '=', 'pending'),
            ])

    # ── Full Analysis ─────────────────────────────────────────────────────────

    def action_run_full_analysis(self):
        self.ensure_one()
        if self.business_activity != 'construction':
            raise UserError(_('Super Agent is currently active for Construction only.'))

        t0       = time.time()
        projects = self.env['farm.project'].search([('business_activity', '=', 'construction')])
        count    = 0

        for proj in projects:
            try:
                self.env['smart.ai.context.snapshot'].capture_for_project(proj)
                self.env['smart.ai.risk.score'].generate_for_project(proj)
                self.env['smart.ai.prediction'].generate_for_project(proj)
                self.env['smart.ai.optimization.suggestion'].generate_for_project(proj)
                count += 1
            except Exception as exc:
                _logger.warning('Super Agent failed for project %s (%s): %s', proj.name, proj.id, exc)

        duration = round(time.time() - t0, 2)
        self.write({
            'last_run':          fields.Datetime.now(),
            'last_run_projects': count,
            'last_run_duration': duration,
        })

        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Super Agent Analysis Complete'),
                'message': _(
                    'Analyzed %(count)d construction project(s) in %(duration).1fs.',
                    count=count, duration=duration,
                ),
                'type':   'success',
                'sticky': False,
            },
        }

    # ── Singleton opener (used by menu server action) ─────────────────────────

    @api.model
    def action_open_command_center(self):
        """Return an act_window pointing to the existing Construction singleton.

        This guarantees the menu always opens the SAME record instead of an
        empty new-record form.  The record is created with default values only
        when it does not exist yet (e.g. fresh install before demo data loads).
        """
        agent = self.search(
            [('business_activity', '=', 'construction')], limit=1
        )
        if not agent:
            agent = self.create({
                'name': 'Construction AI Brain',
                'business_activity': 'construction',
            })
        return {
            'type':      'ir.actions.act_window',
            'name':      _('AI Command Center'),
            'res_model': 'smart.super.agent',
            'res_id':    agent.id,
            'view_mode': 'form',
            'target':    'current',
        }

    # ── Cron entrypoint ───────────────────────────────────────────────────────

    @api.model
    def run_daily_super_agent(self):
        agent = self.search([
            ('active', '=', True),
            ('business_activity', '=', 'construction'),
        ], limit=1)
        if agent:
            agent.action_run_full_analysis()
        else:
            _logger.warning('Super Agent: no active construction agent record found for daily run.')

    # ── Drill-down actions ────────────────────────────────────────────────────

    def action_view_critical_projects(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Critical Projects — Risk Scores'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('status', '=', 'critical')],
            'context':   {},
        }

    def action_view_warning_projects(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Warning Projects — Risk Scores'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('status', '=', 'warning')],
            'context':   {},
        }

    def action_view_pending_actions(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Pending AI Actions'),
            'res_model': 'smart.ai.action',
            'view_mode': 'list,form',
            'domain':    [('state', 'in', ['draft', 'waiting_approval'])],
            'context':   {},
        }

    def action_view_all_risks(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('All Risk Scores'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [],
            'context':   {},
        }

    def action_view_predictions(self):
        projects = self.env['farm.project'].search([('business_activity', '=', 'construction')])
        return {
            'type':      'ir.actions.act_window',
            'name':      _('AI Predictions'),
            'res_model': 'smart.ai.prediction',
            'view_mode': 'list,form',
            'domain':    [('project_id', 'in', projects.ids)],
            'context':   {},
        }

    def action_view_suggestions(self):
        projects = self.env['farm.project'].search([('business_activity', '=', 'construction')])
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Optimization Suggestions'),
            'res_model': 'smart.ai.optimization.suggestion',
            'view_mode': 'list,form',
            'domain':    [('project_id', 'in', projects.ids), ('state', '=', 'pending')],
            'context':   {},
        }

    def action_view_rules(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('AI Rules (Construction)'),
            'res_model': 'smart.ai.rule',
            'view_mode': 'list,form',
            'domain':    [('business_activity', '=', 'construction'), ('active', '=', True)],
            'context':   {},
        }
