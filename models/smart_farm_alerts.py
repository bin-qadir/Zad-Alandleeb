# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# smart.farm.alert.config  –  Configurable thresholds for financial alerts
# ─────────────────────────────────────────────────────────────────────────────
class SmartFarmAlertConfig(models.Model):
    _name = 'smart.farm.alert.config'
    _description = 'Smart Farm Financial Alert Configuration'
    _order = 'sequence, id'

    name = fields.Char(string='Alert Name', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, string='Active')

    alert_type = fields.Selection([
        ('over_budget',        'Cost Exceeds Budget'),
        ('low_profit_margin',  'Profit Margin Below Threshold'),
        ('material_threshold', 'Material Cost Exceeds Threshold'),
    ], string='Alert Type', required=True)

    # Threshold values
    profit_margin_threshold = fields.Float(
        string='Minimum Profit Margin (%)',
        default=10.0,
        help='Alert fires when profit margin falls below this percentage.',
    )
    material_cost_threshold = fields.Monetary(
        string='Material Cost Threshold',
        currency_field='currency_id',
        help='Alert fires when material cost on a single task exceeds this amount.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Severity
    severity = fields.Selection([
        ('info',    'Info'),
        ('warning', 'Warning'),
        ('danger',  'Critical'),
    ], string='Severity', default='warning', required=True)

    # Recipients
    notify_project_manager = fields.Boolean(
        string='Notify Project Manager',
        default=True,
    )
    notify_admins = fields.Boolean(
        string='Notify Farm Administrators',
        default=True,
    )
    extra_partner_ids = fields.Many2many(
        'res.partner',
        'sf_alert_config_partner_rel',
        'config_id',
        'partner_id',
        string='Additional Recipients',
    )

    # Internal note template
    note_template = fields.Text(
        string='Internal Note Template',
        help='Use {task}, {project}, {value}, {threshold} as placeholders.',
    )

    # State tracking
    last_run = fields.Datetime(string='Last Evaluated', readonly=True)
    alert_count = fields.Integer(
        string='Alerts Sent',
        compute='_compute_alert_count',
    )

    @api.depends()
    def _compute_alert_count(self):
        AlertLog = self.env['smart.farm.alert.log']
        for cfg in self:
            cfg.alert_count = AlertLog.search_count([('config_id', '=', cfg.id)])

    @api.constrains('profit_margin_threshold')
    def _check_margin(self):
        for r in self:
            if r.alert_type == 'low_profit_margin' and r.profit_margin_threshold < 0:
                raise ValidationError(_('Profit margin threshold cannot be negative.'))

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Alert Logs – %s') % self.name,
            'res_model': 'smart.farm.alert.log',
            'view_mode': 'list,form',
            'domain':    [('config_id', '=', self.id)],
        }


# ─────────────────────────────────────────────────────────────────────────────
# smart.farm.alert.log  –  Audit trail of every alert notification sent
# ─────────────────────────────────────────────────────────────────────────────
class SmartFarmAlertLog(models.Model):
    _name = 'smart.farm.alert.log'
    _description = 'Smart Farm Alert Log'
    _order = 'create_date desc'
    _rec_name = 'summary'

    config_id = fields.Many2one(
        'smart.farm.alert.config',
        string='Alert Config',
        ondelete='set null',
    )
    alert_type = fields.Char(string='Alert Type', readonly=True)
    severity   = fields.Selection([
        ('info', 'Info'), ('warning', 'Warning'), ('danger', 'Critical'),
    ], string='Severity', readonly=True)

    task_id    = fields.Many2one('project.task',    string='Task',    ondelete='cascade')
    project_id = fields.Many2one('project.project', string='Project', ondelete='cascade')

    summary    = fields.Char(string='Summary', readonly=True)
    body       = fields.Text(string='Full Message', readonly=True)

    # Snapshot of the values that triggered the alert
    triggered_value   = fields.Float(string='Triggered Value',   readonly=True)
    threshold_value   = fields.Float(string='Threshold Value',   readonly=True)

    # Delivery
    notified_user_ids = fields.Many2many(
        'res.users',
        'sf_alert_log_user_rel',
        'log_id', 'user_id',
        string='Notified Users',
        readonly=True,
    )
    message_id = fields.Many2one('mail.message', string='Chatter Message', readonly=True)


# ─────────────────────────────────────────────────────────────────────────────
# smart.farm.alert.engine  –  Core alert evaluation & dispatch logic
# ─────────────────────────────────────────────────────────────────────────────
class SmartFarmAlertEngine(models.AbstractModel):
    _name = 'smart.farm.alert.engine'
    _description = 'Smart Farm Alert Engine'

    # ── Public API ───────────────────────────────────────────────────────────

    @api.model
    def evaluate_task(self, task):
        """
        Evaluate all active alert configs against a single task.
        Called automatically from project.task write() hooks.
        """
        configs = self.env['smart.farm.alert.config'].search([('active', '=', True)])
        for cfg in configs:
            self._check_config(cfg, task)

    @api.model
    def evaluate_all(self):
        """
        Scheduled action entry-point: evaluate ALL tasks against ALL alert configs.
        Designed to run daily (or on-demand). Efficient: one read_group per config type.
        """
        configs = self.env['smart.farm.alert.config'].search([('active', '=', True)])
        Task    = self.env['project.task']

        # Pre-fetch all tasks with non-zero costs to reduce queries
        tasks = Task.search([
            '|', '|',
            ('total_cost', '>', 0),
            ('material_cost', '>', 0),
            ('selling_price', '>', 0),
        ])

        fired_count = 0
        for cfg in configs:
            for task in tasks:
                fired = self._check_config(cfg, task)
                if fired:
                    fired_count += 1

        configs.write({'last_run': fields.Datetime.now()})
        _logger.info('Smart Farm alerts: evaluated %d tasks × %d configs → %d alerts fired',
                     len(tasks), len(configs), fired_count)
        return fired_count

    # ── Per-config check ─────────────────────────────────────────────────────

    @api.model
    def _check_config(self, cfg, task):
        """
        Evaluate one config against one task.
        Returns True if an alert was fired, False otherwise.
        """
        if cfg.alert_type == 'over_budget':
            return self._check_over_budget(cfg, task)
        elif cfg.alert_type == 'low_profit_margin':
            return self._check_profit_margin(cfg, task)
        elif cfg.alert_type == 'material_threshold':
            return self._check_material_threshold(cfg, task)
        return False

    @api.model
    def _check_over_budget(self, cfg, task):
        if not task.budget_amount or task.budget_amount <= 0:
            return False
        if task.total_cost <= task.budget_amount:
            return False
        if self._already_alerted(cfg, task, task.total_cost):
            return False

        overage = task.total_cost - task.budget_amount
        pct     = (task.total_cost / task.budget_amount - 1) * 100

        summary = _(
            '⚠ Over Budget: %s (%.1f%% over — %s above budget)'
        ) % (task.name, pct, self._fmt_currency(overage, task))

        body = _(
            'Task "%s" in project "%s" has exceeded its budget.\n\n'
            '• Total Cost:   %s\n'
            '• Budget:       %s\n'
            '• Over by:      %s (%.1f%%)\n\n'
            'Immediate review is recommended.'
        ) % (
            task.name,
            task.project_id.name if task.project_id else '—',
            self._fmt_currency(task.total_cost, task),
            self._fmt_currency(task.budget_amount, task),
            self._fmt_currency(overage, task),
            pct,
        )

        self._fire_alert(cfg, task, summary, body,
                         triggered_value=task.total_cost,
                         threshold_value=task.budget_amount)
        return True

    @api.model
    def _check_profit_margin(self, cfg, task):
        if not task.selling_price or task.selling_price <= 0:
            return False
        margin_pct = ((task.selling_price - task.total_cost) / task.selling_price) * 100
        if margin_pct >= cfg.profit_margin_threshold:
            return False
        if self._already_alerted(cfg, task, margin_pct):
            return False

        summary = _(
            '📉 Low Margin: %s (%.1f%% — threshold: %.1f%%)'
        ) % (task.name, margin_pct, cfg.profit_margin_threshold)

        body = _(
            'Task "%s" in project "%s" has a profit margin below the alert threshold.\n\n'
            '• Selling Price:  %s\n'
            '• Total Cost:     %s\n'
            '• Profit Margin:  %.1f%%\n'
            '• Threshold:      %.1f%%\n\n'
            'Consider revising the pricing or reducing costs.'
        ) % (
            task.name,
            task.project_id.name if task.project_id else '—',
            self._fmt_currency(task.selling_price, task),
            self._fmt_currency(task.total_cost, task),
            margin_pct,
            cfg.profit_margin_threshold,
        )

        self._fire_alert(cfg, task, summary, body,
                         triggered_value=margin_pct,
                         threshold_value=cfg.profit_margin_threshold)
        return True

    @api.model
    def _check_material_threshold(self, cfg, task):
        if not cfg.material_cost_threshold or cfg.material_cost_threshold <= 0:
            return False
        if task.material_cost <= cfg.material_cost_threshold:
            return False
        if self._already_alerted(cfg, task, task.material_cost):
            return False

        overage = task.material_cost - cfg.material_cost_threshold

        summary = _(
            '🧱 High Material Cost: %s (%s over threshold)'
        ) % (task.name, self._fmt_currency(overage, task))

        body = _(
            'Task "%s" in project "%s" has exceeded the material cost threshold.\n\n'
            '• Material Cost:  %s\n'
            '• Threshold:      %s\n'
            '• Over by:        %s\n\n'
            'Review material lines and consider substitutions or supplier negotiation.'
        ) % (
            task.name,
            task.project_id.name if task.project_id else '—',
            self._fmt_currency(task.material_cost, task),
            self._fmt_currency(cfg.material_cost_threshold, task),
            self._fmt_currency(overage, task),
        )

        self._fire_alert(cfg, task, summary, body,
                         triggered_value=task.material_cost,
                         threshold_value=cfg.material_cost_threshold)
        return True

    # ── Alert dispatch ────────────────────────────────────────────────────────

    @api.model
    def _fire_alert(self, cfg, task, summary, body, triggered_value=0.0, threshold_value=0.0):
        """
        Dispatch an alert:
          1. Post an internal note (activity) on the task chatter.
          2. Send an Odoo inbox notification to each recipient.
          3. Write an audit log record.
        """
        recipients = self._resolve_recipients(cfg, task)
        if not recipients:
            _logger.warning('Alert "%s" fired for task %d but no recipients found.', cfg.name, task.id)
            return

        # ── 1. Internal chatter note ──────────────────────────────────────────
        severity_icons = {'info': 'ℹ', 'warning': '⚠', 'danger': '🔴'}
        icon = severity_icons.get(cfg.severity, '⚠')
        html_body = '<p><b>%s %s</b></p><pre style="background:#f8f8f8;padding:8px;border-radius:4px">%s</pre>' % (
            icon, summary, body.replace('\n', '<br/>')
        )

        partner_ids = recipients.mapped('partner_id').ids
        msg = task.message_post(
            body=html_body,
            subject=summary,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
            partner_ids=partner_ids,
        )

        # ── 2. Odoo inbox notification ────────────────────────────────────────
        self.env['mail.notification'].sudo().search([
            ('mail_message_id', '=', msg.id),
        ])
        # post already notifies via partner_ids; also notify via activity
        try:
            task.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                summary=summary[:250],
                note=html_body,
                user_id=recipients[0].id if recipients else self.env.user.id,
            )
        except Exception as e:
            _logger.warning('Could not schedule activity for alert: %s', e)

        # ── 3. Audit log ──────────────────────────────────────────────────────
        self.env['smart.farm.alert.log'].create({
            'config_id':        cfg.id,
            'alert_type':       cfg.alert_type,
            'severity':         cfg.severity,
            'task_id':          task.id,
            'project_id':       task.project_id.id if task.project_id else False,
            'summary':          summary,
            'body':             body,
            'triggered_value':  triggered_value,
            'threshold_value':  threshold_value,
            'notified_user_ids': [(6, 0, recipients.ids)],
            'message_id':       msg.id,
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    @api.model
    def _resolve_recipients(self, cfg, task):
        """Build the deduplicated list of res.users to notify."""
        users = self.env['res.users'].browse()

        if cfg.notify_project_manager and task.user_ids:
            users |= task.user_ids
        if cfg.notify_project_manager and task.project_id and task.project_id.user_id:
            users |= task.project_id.user_id

        if cfg.notify_admins:
            admin_group = self.env.ref(
                'smart_farm_alandleeb.group_farm_admin', raise_if_not_found=False
            )
            if admin_group:
                users |= admin_group.users

        # Extra partners → look up their res.users
        if cfg.extra_partner_ids:
            extra_users = self.env['res.users'].search([
                ('partner_id', 'in', cfg.extra_partner_ids.ids),
                ('active', '=', True),
            ])
            users |= extra_users

        # Exclude bot / inactive
        return users.filtered(lambda u: u.active and not u.share)

    @api.model
    def _already_alerted(self, cfg, task, current_value, window_hours=24):
        """
        Suppress duplicate alerts: return True if the same config + task
        combination already generated an alert within the last `window_hours`.
        """
        from datetime import datetime, timedelta
        cutoff = fields.Datetime.now() - timedelta(hours=window_hours)
        return bool(self.env['smart.farm.alert.log'].search_count([
            ('config_id', '=', cfg.id),
            ('task_id',   '=', task.id),
            ('create_date', '>=', fields.Datetime.to_string(cutoff)),
        ]))

    @api.model
    def _fmt_currency(self, amount, task):
        currency = task.cost_currency_id or self.env.company.currency_id
        return '%s %s' % (currency.symbol, '{:,.2f}'.format(amount))


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Hook write() to trigger alert evaluation on cost changes
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskAlertHook(models.Model):
    _inherit = 'project.task'

    def write(self, vals):
        result = super().write(vals)
        # Only re-evaluate when financially relevant fields change
        cost_fields = {
            'total_cost', 'material_cost', 'labor_cost', 'overhead_cost',
            'budget_amount', 'selling_price', 'margin_percent', 'margin_amount',
        }
        if cost_fields & set(vals.keys()):
            engine = self.env['smart.farm.alert.engine']
            for task in self:
                try:
                    engine.evaluate_task(task)
                except Exception as e:
                    # Never block a save because of an alert failure
                    _logger.error('Alert evaluation failed for task %d: %s', task.id, e)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Alert count smart button
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskAlertCount(models.Model):
    _inherit = 'project.task'

    task_alert_count = fields.Integer(
        string='Alert Count',
        compute='_compute_task_alert_count',
        store=False,
    )

    def _compute_task_alert_count(self):
        AlertLog = self.env['smart.farm.alert.log']
        for task in self:
            task.task_alert_count = AlertLog.search_count([
                ('task_id', '=', task.id)
            ])

    def action_view_task_alert_logs(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Alerts – %s') % self.name,
            'res_model': 'smart.farm.alert.log',
            'view_mode': 'list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'create': False},
        }
