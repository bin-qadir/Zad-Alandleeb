# -*- coding: utf-8 -*-
"""
Smart Farm — Intelligent Decision Engine
=========================================
Reads latest sensor readings, evaluates configurable condition rules,
and creates farm.decision records with prioritised action recommendations.

Architecture
────────────
  farm.decision.rule   — configurable IF-THEN rules (one per condition type)
  farm.decision        — a single decision/recommendation instance
  farm.decision.engine — AbstractModel with the evaluation loop (cron target)
  project.task         — inherited: shows linked decisions in smart button

Evaluation is done with a single read_group per sensor to get the latest
values without a Python loop over all readings.

Decision lifecycle
──────────────────
  pending → acknowledged → executed | dismissed
"""

import logging
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# ── Priority levels ──────────────────────────────────────────────────────────
PRIORITY_URGENT  = '2'
PRIORITY_HIGH    = '1'
PRIORITY_NORMAL  = '0'

PRIORITY_SEL = [
    (PRIORITY_NORMAL,  'Normal'),
    (PRIORITY_HIGH,    'High'),
    (PRIORITY_URGENT,  'Urgent'),
]

# ── Built-in action catalogue ────────────────────────────────────────────────
ACTION_CATALOGUE = {
    'cooling':       'Activate cooling / ventilation system',
    'heating':       'Activate heating system',
    'irrigation':    'Start irrigation / humidity control',
    'dehumidify':    'Activate dehumidification',
    'co2_inject':    'Increase CO₂ injection / open vents',
    'co2_reduce':    'Reduce CO₂ supply / increase ventilation',
    'manual_check':  'Manual inspection required',
    'alert_only':    'No automated action — send alert only',
}


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision.rule  –  Configurable condition → action rule
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionRule(models.Model):
    _name        = 'farm.decision.rule'
    _description = 'Farm Decision Rule'
    _order       = 'priority desc, sequence, id'

    name     = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(default=10)
    active   = fields.Boolean(default=True)

    # Condition
    metric = fields.Selection([
        ('temperature', 'Temperature (°C)'),
        ('humidity',    'Humidity (%)'),
        ('co2',         'CO₂ (ppm)'),
        ('offline',     'Sensor Offline'),
    ], string='Metric', required=True)

    operator = fields.Selection([
        ('gt',  'Greater than (>)'),
        ('gte', 'Greater than or equal (≥)'),
        ('lt',  'Less than (<)'),
        ('lte', 'Less than or equal (≤)'),
        ('eq',  'Equals (=)'),
        ('ne',  'Not equals (≠)'),
        ('offline', 'Is Offline'),
    ], string='Operator', required=True, default='gt')

    threshold = fields.Float(
        string='Threshold Value',
        help='The value to compare the metric against.',
    )
    offline_minutes = fields.Integer(
        string='Offline After (minutes)',
        default=30,
        help='Only used for metric=offline. Minutes since last reading.',
    )

    # Action
    action = fields.Selection(
        [(k, v) for k, v in ACTION_CATALOGUE.items()],
        string='Recommended Action',
        required=True,
        default='alert_only',
    )
    recommendation_template = fields.Text(
        string='Recommendation Text Template',
        help=(
            'Use placeholders: {sensor}, {farm}, {field}, {metric}, '
            '{value:.1f}, {threshold:.1f}, {action}'
        ),
    )
    priority = fields.Selection(PRIORITY_SEL, string='Priority', default=PRIORITY_NORMAL, required=True)
    auto_execute = fields.Boolean(
        string='Auto-Execute',
        default=False,
        help='If checked, the decision is automatically marked as executed '
             '(for integrations that can act on the action type).',
    )

    # Cooldown — avoid decision spam
    cooldown_minutes = fields.Integer(
        string='Cooldown (minutes)',
        default=60,
        help='Minimum time between two decisions of this rule for the same sensor.',
    )

    # Scope filter (optional — blank = apply to all)
    farm_ids = fields.Many2many(
        'farm.farm',
        'farm_decision_rule_farm_rel',
        'rule_id', 'farm_id',
        string='Limit to Farms',
        help='Leave empty to apply to all farms.',
    )

    decision_count = fields.Integer(
        string='Decisions',
        compute='_compute_decision_count',
    )

    def _compute_decision_count(self):
        Dec = self.env['farm.decision']
        for rule in self:
            rule.decision_count = Dec.search_count([('rule_id', '=', rule.id)])

    def action_view_decisions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Decisions — %s') % self.name,
            'res_model': 'farm.decision',
            'view_mode': 'kanban,list,form',
            'domain':    [('rule_id', '=', self.id)],
        }

    @api.constrains('threshold', 'metric', 'operator')
    def _check_offline_config(self):
        for r in self:
            if r.metric == 'offline' and r.operator not in ('offline', 'gt', 'gte'):
                raise ValidationError(
                    _('For metric "Offline", use operator "Is Offline" or "Greater than".')
                )


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision  –  A single intelligent recommendation record
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecision(models.Model):
    _name        = 'farm.decision'
    _description = 'Farm Intelligent Decision'
    _inherit     = ['mail.thread']
    _order       = 'priority desc, create_date desc'
    _rec_name    = 'summary'

    # ── Linkage ──────────────────────────────────────────────────────────────
    sensor_id = fields.Many2one(
        'farm.sensor', string='Sensor', ondelete='cascade', index=True,
    )
    farm_id  = fields.Many2one(
        related='sensor_id.farm_id', store=True, string='Farm', index=True,
    )
    field_id = fields.Many2one(
        related='sensor_id.field_id', store=True, string='Field',
    )
    task_id = fields.Many2one(
        related='sensor_id.task_id', store=True, string='Task',
    )
    rule_id = fields.Many2one(
        'farm.decision.rule', string='Rule', ondelete='set null',
    )
    alert_id = fields.Many2one(
        'farm.sensor.alert', string='Source Alert', ondelete='set null',
        help='If this decision was generated from a sensor alert.',
    )

    # ── Condition snapshot ────────────────────────────────────────────────────
    metric          = fields.Char(string='Metric', readonly=True)
    triggered_value = fields.Float(string='Triggered Value', digits=(8, 2), readonly=True)
    threshold_value = fields.Float(string='Threshold Value', digits=(8, 2), readonly=True)
    condition_text  = fields.Char(string='Condition', readonly=True)

    # ── Decision content ──────────────────────────────────────────────────────
    summary        = fields.Char(string='Summary', required=True, tracking=True)
    recommendation = fields.Text(string='Recommendation', tracking=True)
    action_type    = fields.Selection(
        [(k, v) for k, v in ACTION_CATALOGUE.items()],
        string='Action Type',
        required=True,
        default='alert_only',
        tracking=True,
    )
    priority = fields.Selection(PRIORITY_SEL, string='Priority',
                                default=PRIORITY_NORMAL, required=True, tracking=True)
    priority_int = fields.Integer(compute='_compute_priority_int', store=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status = fields.Selection([
        ('pending',      'Pending'),
        ('acknowledged', 'Acknowledged'),
        ('executed',     'Executed'),
        ('dismissed',    'Dismissed'),
    ], string='Status', default='pending', required=True, tracking=True)

    auto_executed   = fields.Boolean(string='Auto-Executed', default=False, readonly=True)
    acknowledged_by = fields.Many2one('res.users', string='Acknowledged By', readonly=True)
    acknowledged_at = fields.Datetime(string='Acknowledged At', readonly=True)
    executed_by     = fields.Many2one('res.users', string='Executed By',     readonly=True)
    executed_at     = fields.Datetime(string='Executed At',     readonly=True)
    execution_notes = fields.Text(string='Execution Notes')

    # ── Kanban color helper ───────────────────────────────────────────────────
    color = fields.Integer(string='Color Index', compute='_compute_color')

    @api.depends('priority', 'status')
    def _compute_priority_int(self):
        for d in self:
            d.priority_int = int(d.priority or 0)

    @api.depends('priority', 'status')
    def _compute_color(self):
        for d in self:
            if d.status in ('executed', 'dismissed'):
                d.color = 0   # grey
            elif d.priority == PRIORITY_URGENT:
                d.color = 1   # red
            elif d.priority == PRIORITY_HIGH:
                d.color = 3   # orange/yellow
            else:
                d.color = 10  # green

    # ────────────────────────────────────────────────────────────────────────
    # Lifecycle actions
    # ────────────────────────────────────────────────────────────────────────

    def action_acknowledge(self):
        for d in self:
            if d.status == 'pending':
                d.write({
                    'status':          'acknowledged',
                    'acknowledged_by': self.env.uid,
                    'acknowledged_at': fields.Datetime.now(),
                })

    def action_execute(self):
        for d in self:
            if d.status in ('pending', 'acknowledged'):
                d.write({
                    'status':      'executed',
                    'executed_by': self.env.uid,
                    'executed_at': fields.Datetime.now(),
                })

    def action_dismiss(self):
        for d in self:
            if d.status in ('pending', 'acknowledged'):
                d.write({'status': 'dismissed'})

    def action_reopen(self):
        for d in self:
            if d.status in ('dismissed', 'executed'):
                d.write({'status': 'pending'})

    # ────────────────────────────────────────────────────────────────────────
    # Smart button on sensor
    # ────────────────────────────────────────────────────────────────────────

    def action_view_sensor(self):
        self.ensure_one()
        if not self.sensor_id:
            return
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Sensor'),
            'res_model': 'farm.sensor',
            'res_id':    self.sensor_id.id,
            'view_mode': 'form',
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision.engine  –  Evaluation loop (cron target)
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionEngine(models.AbstractModel):
    _name        = 'farm.decision.engine'
    _description = 'Farm Intelligent Decision Engine'

    # ── Public API ────────────────────────────────────────────────────────────

    @api.model
    def run(self):
        """
        Main entry point — called by cron every 5 minutes.

        Steps:
          1. Fetch latest sensor reading per active sensor (one read_group).
          2. For each active rule, evaluate the condition against each sensor.
          3. Create farm.decision records for breached conditions.
          4. Auto-execute decisions where rule.auto_execute = True.
          5. Convert open sensor alerts to decisions (alert upgrade).

        Returns total number of decisions created.
        """
        _logger.info('Decision engine: starting evaluation run')

        # ── Step 1: latest readings per sensor (fast: one SQL aggregation) ────
        sensor_snapshot = self._fetch_sensor_snapshot()
        if not sensor_snapshot:
            _logger.debug('Decision engine: no active sensor readings found')
            return 0

        # ── Step 2 + 3: evaluate rules → create decisions ────────────────────
        rules = self.env['farm.decision.rule'].search([('active', '=', True)])
        total_created = 0

        for rule in rules:
            created = self._evaluate_rule(rule, sensor_snapshot)
            total_created += created

        # ── Step 4: auto-execute where rule says so ───────────────────────────
        auto_exec = self.env['farm.decision'].search([
            ('status',       '=', 'pending'),
            ('rule_id.auto_execute', '=', True),
        ])
        if auto_exec:
            auto_exec.write({
                'status':        'executed',
                'auto_executed': True,
                'executed_at':   fields.Datetime.now(),
                'executed_by':   self.env.ref('base.user_root').id,
            })
            _logger.info('Decision engine: auto-executed %d decisions', len(auto_exec))

        # ── Step 5: upgrade open sensor alerts → decisions ───────────────────
        alert_decisions = self._convert_alerts_to_decisions()
        total_created += alert_decisions

        _logger.info(
            'Decision engine: run complete — %d decisions created, %d from alerts',
            total_created, alert_decisions,
        )
        return total_created

    # ── Snapshot ──────────────────────────────────────────────────────────────

    @api.model
    def _fetch_sensor_snapshot(self):
        """
        Fetch the latest temperature/humidity/co2 and last_reading_at
        for every active sensor.

        Returns dict: {sensor_id (int) → {
            'temperature': float|None,
            'humidity':    float|None,
            'co2':         float|None,
            'last_at':     datetime|None,
            'sensor_obj':  farm.sensor record,
        }}

        Uses the cached last_* fields on farm.sensor (written by
        _evaluate_thresholds) — this is O(sensors) not O(readings).
        """
        sensors = self.env['farm.sensor'].search([('active', '=', True)])
        snapshot = {}
        for s in sensors:
            snapshot[s.id] = {
                'temperature': s.last_temperature or None,
                'humidity':    s.last_humidity    or None,
                'co2':         s.last_co2         or None,
                'last_at':     s.last_reading_at,
                'sensor_obj':  s,
            }
        return snapshot

    # ── Rule evaluation ───────────────────────────────────────────────────────

    @api.model
    def _evaluate_rule(self, rule, sensor_snapshot):
        """Evaluate one rule against all sensors in the snapshot."""
        created = 0

        for sensor_id, snap in sensor_snapshot.items():
            sensor = snap['sensor_obj']

            # Farm scope filter
            if rule.farm_ids and sensor.farm_id not in rule.farm_ids:
                continue

            # Evaluate condition
            triggered, value = self._check_condition(rule, snap)
            if not triggered:
                continue

            # Cooldown check — skip if a recent decision exists
            if self._is_in_cooldown(rule, sensor):
                continue

            # Build and create decision
            decision_vals = self._build_decision_vals(rule, sensor, value)
            self.env['farm.decision'].create(decision_vals)
            created += 1

        return created

    @staticmethod
    def _check_condition(rule, snap):
        """
        Evaluate rule.condition against the sensor snapshot.
        Returns (triggered: bool, value: float|None).
        """
        if rule.metric == 'offline':
            last_at = snap.get('last_at')
            if not last_at:
                return True, None
            age_min = (fields.Datetime.now() - last_at).total_seconds() / 60
            triggered = age_min >= (rule.offline_minutes or 30)
            return triggered, age_min

        value = snap.get(rule.metric)
        if value is None:
            return False, None

        ops = {
            'gt':  lambda v, t: v >  t,
            'gte': lambda v, t: v >= t,
            'lt':  lambda v, t: v <  t,
            'lte': lambda v, t: v <= t,
            'eq':  lambda v, t: abs(v - t) < 0.001,
            'ne':  lambda v, t: abs(v - t) >= 0.001,
        }
        fn = ops.get(rule.operator)
        if fn is None:
            return False, value
        return fn(value, rule.threshold), value

    @api.model
    def _is_in_cooldown(self, rule, sensor):
        """Return True if a decision for this rule+sensor was created recently."""
        if not rule.cooldown_minutes:
            return False
        cutoff = fields.Datetime.now() - timedelta(minutes=rule.cooldown_minutes)
        return bool(self.env['farm.decision'].search_count([
            ('rule_id',   '=', rule.id),
            ('sensor_id', '=', sensor.id),
            ('create_date', '>=', fields.Datetime.to_string(cutoff)),
            ('status', 'not in', ('dismissed',)),
        ]))

    @api.model
    def _build_decision_vals(self, rule, sensor, triggered_value):
        """Construct the vals dict for farm.decision.create()."""
        metric_labels = {
            'temperature': 'Temperature',
            'humidity':    'Humidity',
            'co2':         'CO₂',
            'offline':     'Offline',
        }
        unit_map = {
            'temperature': '°C',
            'humidity':    '%',
            'co2':         'ppm',
            'offline':     'min',
        }
        metric_label = metric_labels.get(rule.metric, rule.metric)
        unit         = unit_map.get(rule.metric, '')

        if rule.metric == 'offline':
            condition_text = _('Sensor offline for %.0f %s') % (triggered_value or 0, unit)
        else:
            op_labels = {
                'gt': '>', 'gte': '≥', 'lt': '<',
                'lte': '≤', 'eq': '=', 'ne': '≠',
            }
            op = op_labels.get(rule.operator, rule.operator)
            condition_text = _('%(metric)s %(op)s %(threshold)s%(unit)s (actual: %(value)s%(unit)s)') % {
                'metric':    metric_label,
                'op':        op,
                'threshold': rule.threshold,
                'value':     '%.1f' % triggered_value if triggered_value is not None else '?',
                'unit':      unit,
            }

        action_label = dict(ACTION_CATALOGUE).get(rule.action, rule.action)
        summary = _('[%(farm)s] %(rule)s → %(action)s') % {
            'farm':   sensor.farm_id.name if sensor.farm_id else '—',
            'rule':   rule.name,
            'action': action_label,
        }

        # Build recommendation from template or auto-generate
        if rule.recommendation_template:
            try:
                recommendation = rule.recommendation_template.format(
                    sensor=sensor.name,
                    farm=sensor.farm_id.name if sensor.farm_id else '—',
                    field=sensor.field_id.name if sensor.field_id else '—',
                    metric=metric_label,
                    value=triggered_value or 0,
                    threshold=rule.threshold,
                    action=action_label,
                )
            except (KeyError, ValueError):
                recommendation = summary
        else:
            recommendation = _(
                'Sensor "%(s)s" on %(farm)s reports %(condition)s.\n'
                'Recommended action: %(action)s.\n'
                'Please review and take appropriate steps.'
            ) % {
                's':         sensor.name,
                'farm':      sensor.farm_id.name if sensor.farm_id else '—',
                'condition': condition_text,
                'action':    action_label,
            }

        return {
            'sensor_id':       sensor.id,
            'rule_id':         rule.id,
            'task_id':         sensor.task_id.id if sensor.task_id else False,
            'metric':          rule.metric,
            'triggered_value': triggered_value or 0.0,
            'threshold_value': rule.threshold,
            'condition_text':  condition_text,
            'summary':         summary[:255],
            'recommendation':  recommendation,
            'action_type':     rule.action,
            'priority':        rule.priority,
            'status':          'pending',
        }

    # ── Alert → Decision conversion ───────────────────────────────────────────

    @api.model
    def _convert_alerts_to_decisions(self):
        """
        Upgrade open sensor alerts that have no linked decision yet.
        Creates one farm.decision per unlinked alert.
        """
        open_alerts = self.env['farm.sensor.alert'].search([
            ('resolved', '=', False),
        ])

        # Find alerts already converted (have a decision)
        linked_alert_ids = self.env['farm.decision'].search(
            [('alert_id', '!=', False)]
        ).mapped('alert_id').ids

        new_alerts = open_alerts.filtered(lambda a: a.id not in linked_alert_ids)
        if not new_alerts:
            return 0

        created = 0
        action_map = {
            'temperature': 'cooling',
            'humidity':    'irrigation',
            'co2':         'co2_inject',
        }
        priority_map = {
            'critical': PRIORITY_URGENT,
            'warning':  PRIORITY_HIGH,
        }
        metric_labels = {
            'temperature': 'Temperature',
            'humidity':    'Humidity',
            'co2':         'CO₂',
        }
        unit_map = {
            'temperature': '°C',
            'humidity':    '%',
            'co2':         'ppm',
        }

        for alert in new_alerts:
            sensor = alert.sensor_id
            if not sensor:
                continue

            metric_label = metric_labels.get(alert.metric, alert.metric)
            unit         = unit_map.get(alert.metric, '')
            action_type  = action_map.get(alert.metric, 'alert_only')
            priority     = priority_map.get(alert.severity, PRIORITY_NORMAL)
            action_label = dict(ACTION_CATALOGUE).get(action_type, action_type)

            summary = _('[%(farm)s] %(metric)s alert → %(action)s') % {
                'farm':   sensor.farm_id.name if sensor.farm_id else '—',
                'metric': metric_label,
                'action': action_label,
            }
            recommendation = _(
                'Sensor "%(s)s" triggered a %(sev)s alert:\n'
                '%(msg)s\n\n'
                'Recommended action: %(action)s\n'
                'Actual: %(val).1f%(unit)s | Threshold: %(thr).1f%(unit)s'
            ) % {
                's':      sensor.name,
                'sev':    alert.severity,
                'msg':    alert.message or '—',
                'action': action_label,
                'val':    alert.actual_value,
                'unit':   unit,
                'thr':    alert.threshold_value,
            }

            dec = self.env['farm.decision'].create({
                'sensor_id':       sensor.id,
                'alert_id':        alert.id,
                'task_id':         sensor.task_id.id if sensor.task_id else False,
                'metric':          alert.metric,
                'triggered_value': alert.actual_value,
                'threshold_value': alert.threshold_value,
                'condition_text':  alert.message or '',
                'summary':         summary[:255],
                'recommendation':  recommendation,
                'action_type':     action_type,
                'priority':        priority,
                'status':          'pending',
            })
            created += 1

        return created

    # ── Manual trigger ────────────────────────────────────────────────────────

    @api.model
    def run_now(self):
        """UI-callable method — runs the engine immediately and notifies."""
        count = self.run()
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Decision Engine'),
                'message': _('%d new decision(s) generated.') % count,
                'type':    'success' if count else 'info',
                'sticky':  False,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Decision count smart button
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskDecisions(models.Model):
    _inherit = 'project.task'

    task_decision_count = fields.Integer(
        string='Decisions',
        compute='_compute_task_decision_count',
    )

    def _compute_task_decision_count(self):
        Dec = self.env['farm.decision']
        for task in self:
            task.task_decision_count = Dec.search_count([
                ('task_id', '=', task.id),
                ('status',  '=', 'pending'),
            ])

    def action_view_task_decisions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Decisions – %s') % self.name,
            'res_model': 'farm.decision',
            'view_mode': 'kanban,list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'default_task_id': self.id},
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.sensor  –  Decision count smart button
# ─────────────────────────────────────────────────────────────────────────────
class FarmSensorDecisions(models.Model):
    _inherit = 'farm.sensor'

    pending_decision_count = fields.Integer(
        string='Pending Decisions',
        compute='_compute_pending_decision_count',
    )

    def _compute_pending_decision_count(self):
        Dec = self.env['farm.decision']
        for sensor in self:
            sensor.pending_decision_count = Dec.search_count([
                ('sensor_id', '=', sensor.id),
                ('status',    '=', 'pending'),
            ])

    def action_view_decisions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Decisions – %s') % self.name,
            'res_model': 'farm.decision',
            'view_mode': 'kanban,list,form',
            'domain':    [('sensor_id', '=', self.id)],
        }
