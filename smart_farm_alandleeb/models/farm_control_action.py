# -*- coding: utf-8 -*-
"""
Smart Farm — Control Action Execution Layer
============================================
Turns farm.decision recommendations into actual operational commands
that can be sent to actuators via MQTT or logged for manual execution.

Models
──────
  farm.actuator          — registered actuator devices (fans, pumps, valves…)
  farm.actuator.mapping  — action_type → actuator mapping per farm/field
  farm.control.action    — one execution attempt for one decision
  farm.control.log       — immutable per-attempt audit log row

Execution modes
────────────────
  manual     — operator presses "Execute" — command sent immediately
  semi_auto  — command is queued; operator must confirm before send
  auto       — command created and sent without human intervention

State machine
─────────────
  draft → queued → sent → success | failed
                  ↓
               cancelled

MQTT command topic pattern
──────────────────────────
  farm/actuators/<device_id>/set
  Payload: {"action": "cooling_on", "value": 1, "source": "odoo", "ts": "..."}
"""

import json
import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Canonical action → MQTT command payload mapping
ACTION_COMMANDS = {
    'cooling':      {'action': 'cooling_on',     'value': 1},
    'heating':      {'action': 'heating_on',      'value': 1},
    'irrigation':   {'action': 'irrigation_on',   'value': 1},
    'dehumidify':   {'action': 'dehumidify_on',   'value': 1},
    'co2_inject':   {'action': 'co2_inject_on',   'value': 1},
    'co2_reduce':   {'action': 'co2_vent_on',     'value': 1},
    'manual_check': {'action': 'alert_operator',  'value': 0},
    'alert_only':   {'action': 'alert_only',      'value': 0},
}

ACTUATOR_TOPIC_PATTERN = 'farm/actuators/{device_id}/set'


# ─────────────────────────────────────────────────────────────────────────────
# farm.actuator  –  Physical actuator device registry
# ─────────────────────────────────────────────────────────────────────────────
class FarmActuator(models.Model):
    _name        = 'farm.actuator'
    _description = 'Farm Actuator Device'
    _order       = 'farm_id, name'

    name      = fields.Char(string='Actuator Name', required=True)
    device_id = fields.Char(
        string='Device ID',
        required=True,
        copy=False,
        index=True,
        help='Unique identifier used in the MQTT topic: farm/actuators/<device_id>/set',
    )
    active = fields.Boolean(default=True)

    actuator_type = fields.Selection([
        ('cooling',    'Cooling / Fan'),
        ('heating',    'Heating'),
        ('irrigation', 'Irrigation / Pump'),
        ('dehumidify', 'Dehumidifier'),
        ('co2',        'CO₂ Controller'),
        ('valve',      'Valve'),
        ('light',      'Lighting'),
        ('generic',    'Generic'),
    ], string='Actuator Type', required=True, default='generic')

    farm_id  = fields.Many2one('farm.farm',  string='Farm', required=True)
    field_id = fields.Many2one('farm.field', string='Field',
                               domain="[('farm_id','=',farm_id)]")

    broker_id = fields.Many2one('farm.mqtt.broker', string='MQTT Broker', ondelete='set null')
    mqtt_topic = fields.Char(
        string='Command Topic',
        compute='_compute_mqtt_topic',
        store=True,
        readonly=False,
        help='Topic to publish commands to.',
    )

    # Last known state
    last_command    = fields.Char(string='Last Command',  readonly=True)
    last_command_at = fields.Datetime(string='Last Sent', readonly=True)
    last_result     = fields.Selection([
        ('success', 'Success'), ('failed', 'Failed'),
    ], string='Last Result', readonly=True)

    control_action_count = fields.Integer(
        string='Control Actions',
        compute='_compute_control_action_count',
    )

    _sql_constraints = [
        ('device_id_uniq', 'unique(device_id)',
         'Actuator Device ID must be unique.'),
    ]

    @api.depends('device_id')
    def _compute_mqtt_topic(self):
        for rec in self:
            if rec.device_id:
                rec.mqtt_topic = ACTUATOR_TOPIC_PATTERN.format(device_id=rec.device_id)
            else:
                rec.mqtt_topic = ''

    def _compute_control_action_count(self):
        CA = self.env['farm.control.action']
        for rec in self:
            rec.control_action_count = CA.search_count([('actuator_id', '=', rec.id)])

    def action_view_control_actions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Control Actions — %s') % self.name,
            'res_model': 'farm.control.action',
            'view_mode': 'list,form',
            'domain':    [('actuator_id', '=', self.id)],
        }

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, '%s [%s]' % (rec.name, rec.device_id)))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# farm.actuator.mapping  –  action_type → actuator routing table
# ─────────────────────────────────────────────────────────────────────────────
class FarmActuatorMapping(models.Model):
    _name        = 'farm.actuator.mapping'
    _description = 'Action-to-Actuator Mapping'
    _order       = 'farm_id, action_type'

    farm_id = fields.Many2one(
        'farm.farm', string='Farm', required=True, ondelete='cascade', index=True,
    )
    field_id = fields.Many2one(
        'farm.field', string='Field (optional)',
        domain="[('farm_id','=',farm_id)]",
        help='Leave empty to apply to the whole farm.',
    )
    action_type = fields.Selection(
        [(k, k.replace('_', ' ').title()) for k in ACTION_COMMANDS],
        string='Action Type',
        required=True,
    )
    actuator_id = fields.Many2one(
        'farm.actuator', string='Actuator', required=True, ondelete='restrict',
    )
    execution_mode = fields.Selection([
        ('manual',    'Manual — human presses Execute'),
        ('semi_auto', 'Semi-Auto — queued, needs confirmation'),
        ('auto',      'Auto — execute immediately'),
    ], string='Execution Mode', default='manual', required=True)

    custom_payload = fields.Text(
        string='Custom Payload (JSON)',
        help='Override the default command payload. Leave empty for default.',
    )

    active = fields.Boolean(default=True)

    @api.constrains('custom_payload')
    def _check_custom_payload(self):
        for rec in self:
            if rec.custom_payload:
                try:
                    json.loads(rec.custom_payload)
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValidationError(
                        _('Custom payload is not valid JSON: %s') % e
                    )

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, '%s → %s → %s' % (
                rec.farm_id.name, rec.action_type, rec.actuator_id.name,
            )))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# farm.control.action  –  One execution record per decision + actuator
# ─────────────────────────────────────────────────────────────────────────────
class FarmControlAction(models.Model):
    _name        = 'farm.control.action'
    _description = 'Farm Control Action'
    _inherit     = ['mail.thread']
    _order       = 'create_date desc'
    _rec_name    = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )

    # ── Source linkage ────────────────────────────────────────────────────────
    decision_id = fields.Many2one(
        'farm.decision', string='Decision',
        ondelete='cascade', index=True, tracking=True,
    )
    sensor_id = fields.Many2one(
        related='decision_id.sensor_id', store=True, string='Sensor', readonly=True,
    )
    farm_id = fields.Many2one(
        related='decision_id.farm_id', store=True, string='Farm', readonly=True, index=True,
    )
    field_id = fields.Many2one(
        related='decision_id.field_id', store=True, string='Field', readonly=True,
    )
    task_id = fields.Many2one(
        related='decision_id.task_id', store=True, string='Task', readonly=True,
    )

    # ── Actuator target ───────────────────────────────────────────────────────
    actuator_id = fields.Many2one(
        'farm.actuator', string='Actuator', ondelete='set null', tracking=True,
    )
    broker_id = fields.Many2one(
        'farm.mqtt.broker', string='MQTT Broker',
        compute='_compute_broker', store=True, readonly=False,
    )
    topic = fields.Char(
        string='Command Topic',
        compute='_compute_topic', store=True, readonly=False,
    )
    device_target = fields.Char(
        string='Target Device ID', readonly=True,
    )

    # ── Command ───────────────────────────────────────────────────────────────
    action_type = fields.Selection(
        [(k, k.replace('_', ' ').title()) for k in ACTION_COMMANDS],
        string='Action Type', required=True, tracking=True,
    )
    command_payload = fields.Text(
        string='Command Payload (JSON)',
        help='JSON payload to publish. Auto-generated from action_type if empty.',
    )
    execution_mode = fields.Selection([
        ('manual',    'Manual'),
        ('semi_auto', 'Semi-Auto'),
        ('auto',      'Auto'),
    ], string='Execution Mode', default='manual', required=True, tracking=True)

    # ── State machine ─────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',      'Draft'),
        ('queued',     'Queued'),
        ('sent',       'Sent'),
        ('success',    'Success'),
        ('failed',     'Failed'),
        ('cancelled',  'Cancelled'),
    ], string='State', default='draft', required=True, tracking=True)

    executed_at     = fields.Datetime(string='Executed At',  readonly=True)
    executed_by     = fields.Many2one('res.users', string='Executed By', readonly=True)
    result_message  = fields.Text(string='Result / Error Message', readonly=True)
    retry_count = fields.Integer(
        string='Retry Count',
        default=0,
        readonly=True,
        help='Number of times this action has been retried after a failure.',
    )
    forced          = fields.Boolean(
        string='Forced Re-execution',
        default=False,
        help='True when executed despite an existing completed action.',
    )

    # ── Execution log ─────────────────────────────────────────────────────────
    log_ids = fields.One2many('farm.control.log', 'control_action_id', string='Execution Log')
    log_count = fields.Integer(compute='_compute_log_count', string='Log Entries')

    mqtt_publish_log_count = fields.Integer(
        string='MQTT Logs',
        compute='_compute_mqtt_publish_log_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.control.action') \
                               or _('New')
        return super().create(vals_list)

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('actuator_id')
    def _compute_broker(self):
        for rec in self:
            rec.broker_id = rec.actuator_id.broker_id if rec.actuator_id else False

    @api.depends('actuator_id')
    def _compute_topic(self):
        for rec in self:
            rec.topic = rec.actuator_id.mqtt_topic if rec.actuator_id else ''

    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    def _compute_mqtt_publish_log_count(self):
        MqttLog = self.env['farm.mqtt.publish.log']
        for rec in self:
            rec.mqtt_publish_log_count = MqttLog.search_count([
                ('source_model', '=', 'farm.control.action'),
                ('source_id',    '=', rec.id),
            ])

    def action_view_mqtt_publish_logs(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('MQTT Publish Log — %s') % self.name,
            'res_model': 'farm.mqtt.publish.log',
            'view_mode': 'list,form',
            'domain':    [
                ('source_model', '=', 'farm.control.action'),
                ('source_id',    '=', self.id),
            ],
        }

    # ────────────────────────────────────────────────────────────────────────
    # Payload builder
    # ────────────────────────────────────────────────────────────────────────

    def _build_payload(self):
        """
        Return the JSON string to publish as the MQTT command.
        Precedence:
          1. Custom payload on the actuator mapping
          2. Custom payload on this control action record
          3. Default from ACTION_COMMANDS catalogue
        """
        self.ensure_one()
        # Check actuator mapping for custom payload
        mapping = False
        if self.decision_id and self.actuator_id:
            mapping = self.env['farm.actuator.mapping'].search([
                ('farm_id',     '=', self.farm_id.id),
                ('action_type', '=', self.action_type),
                ('actuator_id', '=', self.actuator_id.id),
                ('active',      '=', True),
            ], limit=1)

        if mapping and mapping.custom_payload:
            try:
                payload = json.loads(mapping.custom_payload)
            except (json.JSONDecodeError, ValueError):
                payload = {}
        elif self.command_payload:
            try:
                payload = json.loads(self.command_payload)
            except (json.JSONDecodeError, ValueError):
                payload = {}
        else:
            payload = dict(ACTION_COMMANDS.get(self.action_type, {'action': self.action_type, 'value': 1}))

        # Always inject metadata
        payload.update({
            'source':    'odoo_smart_farm',
            'ts':        datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'decision':  self.decision_id.id if self.decision_id else None,
        })
        return json.dumps(payload, ensure_ascii=False)

    # ────────────────────────────────────────────────────────────────────────
    # MQTT publish
    # ────────────────────────────────────────────────────────────────────────

    def _publish_mqtt(self, payload_str):
        """
        Publish `payload_str` to `self.topic` via the farm.mqtt.publisher service.

        Delegates to FarmMqttPublisher.publish() which:
          - Reuses any active listener connection for this broker (zero TCP overhead)
          - Falls back to a one-shot connect-publish-disconnect
          - Waits for QoS-1 broker acknowledgement via wait_for_publish()
          - Writes an audit record to farm.mqtt.publish.log

        Returns (success: bool, message: str).
        """
        self.ensure_one()

        if not self.topic:
            return False, _('No MQTT topic configured.')
        if not self.broker_id:
            return False, _('No MQTT broker linked to actuator "%s".') % (
                self.actuator_id.name if self.actuator_id else '?'
            )

        result = self.env['farm.mqtt.publisher'].publish(
            broker=self.broker_id,
            topic=self.topic,
            payload=payload_str,
            qos=1,
            retain=False,
            source_model=self._name,
            source_id=self.id,
        )
        return result.success, result.message

    # ────────────────────────────────────────────────────────────────────────
    # Core execute method
    # ────────────────────────────────────────────────────────────────────────

    def execute(self, force=False):
        """
        Execute this control action:
          1. Check for duplicate (unless force=True).
          2. Build payload.
          3. If actuator present → publish MQTT; else log as manual.
          4. Write state + result + audit log.
          5. If success → mark linked decision as executed.

        Returns dict {success, message, payload} for UI notification.
        """
        self.ensure_one()

        # Duplicate guard
        if not force and self.state in ('sent', 'success'):
            existing = _('Already executed at %s. Use Force Re-execute to override.') % self.executed_at
            return {'success': False, 'message': existing, 'payload': ''}

        payload_str = self._build_payload()

        # Persist payload snapshot
        self.command_payload = payload_str

        # Action types that are manual-only (no actuator needed)
        manual_only = {'manual_check', 'alert_only'}
        is_manual   = self.action_type in manual_only or not self.actuator_id

        if is_manual:
            success = True
            message = _('Manual action logged. No MQTT command sent.')
            self._log_attempt('manual', payload_str, True, message)
        else:
            self.write({'state': 'sent'})
            success, message = self._publish_mqtt(payload_str)
            self._log_attempt('mqtt', payload_str, success, message)

        # Update state + actuator last_command
        now = fields.Datetime.now()
        new_state = 'success' if success else 'failed'
        self.write({
            'state':          new_state,
            'executed_at':    now,
            'executed_by':    self.env.uid,
            'result_message': message,
            'forced':         force,
        })

        if success and self.actuator_id:
            self.actuator_id.write({
                'last_command':    payload_str,
                'last_command_at': now,
                'last_result':     'success',
            })
        elif not success and self.actuator_id:
            self.actuator_id.last_result = 'failed'

        # Mark linked decision executed on success
        if success and self.decision_id and self.decision_id.status in ('pending', 'acknowledged'):
            self.decision_id.write({
                'status':      'executed',
                'executed_by': self.env.uid,
                'executed_at': now,
                'execution_notes': _('Executed via control action %s') % self.name,
            })

        return {'success': success, 'message': message, 'payload': payload_str}

    def _log_attempt(self, method, payload, success, message):
        """Append an immutable row to farm.control.log."""
        self.env['farm.control.log'].create({
            'control_action_id': self.id,
            'method':    method,
            'payload':   payload[:4096] if payload else '',
            'success':   success,
            'message':   message[:512] if message else '',
            'user_id':   self.env.uid,
        })

    # ────────────────────────────────────────────────────────────────────────
    # UI-facing button actions
    # ────────────────────────────────────────────────────────────────────────

    def action_execute_now(self):
        """Called from the 'Execute' button on the form view."""
        self.ensure_one()
        result = self.execute(force=False)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Control Action'),
                'message': result['message'],
                'type':    'success' if result['success'] else 'danger',
                'sticky':  not result['success'],
            },
        }

    def action_force_execute(self):
        """Force re-execution even if already succeeded."""
        self.ensure_one()
        result = self.execute(force=True)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Force Re-execute'),
                'message': result['message'],
                'type':    'success' if result['success'] else 'danger',
                'sticky':  not result['success'],
            },
        }

    def action_cancel(self):
        for rec in self:
            if rec.state in ('draft', 'queued'):
                rec.write({'state': 'cancelled', 'result_message': _('Cancelled by user.')})

    def action_reset_draft(self):
        for rec in self:
            if rec.state in ('failed', 'cancelled'):
                rec.write({
                    'state': 'draft',
                    'result_message': False,
                    'executed_at': False,
                    'executed_by': False,
                })

    def action_retry(self):
        """
        Retry a failed control action.
        Increments retry_count, resets to draft, then immediately executes.
        Returns a notification with success/fail result.
        """
        self.ensure_one()
        if self.state not in ('failed', 'cancelled'):
            return {
                'type': 'ir.actions.client',
                'tag':  'display_notification',
                'params': {
                    'title':   _('Retry'),
                    'message': _('Can only retry failed or cancelled actions.'),
                    'type':    'warning',
                    'sticky':  False,
                },
            }
        self.write({
            'state':          'draft',
            'retry_count':    self.retry_count + 1,
            'result_message': _('Retrying (attempt %d)...') % (self.retry_count + 1),
            'executed_at':    False,
            'executed_by':    False,
        })
        _logger.info(
            'Control action %s: retry attempt %d', self.name, self.retry_count
        )
        result = self.execute(force=True)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Retry — Attempt %d') % self.retry_count,
                'message': result['message'],
                'type':    'success' if result['success'] else 'danger',
                'sticky':  not result['success'],
            },
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Execution Log — %s') % self.name,
            'res_model': 'farm.control.log',
            'view_mode': 'list',
            'domain':    [('control_action_id', '=', self.id)],
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.control.log  –  Immutable audit trail per execution attempt
# ─────────────────────────────────────────────────────────────────────────────
class FarmControlLog(models.Model):
    _name        = 'farm.control.log'
    _description = 'Control Action Execution Log'
    _order       = 'create_date desc'

    control_action_id = fields.Many2one(
        'farm.control.action', string='Control Action',
        required=True, ondelete='cascade', index=True,
    )
    method  = fields.Selection([
        ('mqtt',   'MQTT Publish'),
        ('manual', 'Manual / No-Op'),
        ('api',    'REST API'),
    ], string='Method', required=True, default='mqtt')

    payload = fields.Text(string='Payload Sent', readonly=True)
    success = fields.Boolean(string='Success', readonly=True)
    message = fields.Text(string='Result Message', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True,
                              default=lambda self: self.env.uid)


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision  –  Extend with control action creation + smart button
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionControlActions(models.Model):
    _inherit = 'farm.decision'

    control_action_ids = fields.One2many(
        'farm.control.action', 'decision_id',
        string='Control Actions',
    )
    control_action_count = fields.Integer(
        string='Actions Count',
        compute='_compute_control_action_count',
    )
    has_active_action = fields.Boolean(
        string='Has Active Action',
        compute='_compute_control_action_count',
        help='True if a non-cancelled/failed control action exists.',
    )

    def _compute_control_action_count(self):
        for dec in self:
            actions = dec.control_action_ids
            dec.control_action_count = len(actions)
            dec.has_active_action = any(
                a.state in ('draft', 'queued', 'sent', 'success') for a in actions
            )

    def action_view_control_actions(self):
        self.ensure_one()
        ctx = {'default_decision_id': self.id,
               'default_action_type': self.action_type,
               'default_execution_mode': 'manual'}
        if len(self.control_action_ids) == 1:
            return {
                'type':      'ir.actions.act_window',
                'name':      _('Control Action'),
                'res_model': 'farm.control.action',
                'res_id':    self.control_action_ids.id,
                'view_mode': 'form',
                'context':   ctx,
            }
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Control Actions — %s') % self.summary,
            'res_model': 'farm.control.action',
            'view_mode': 'list,form',
            'domain':    [('decision_id', '=', self.id)],
            'context':   ctx,
        }

    def action_create_and_execute(self):
        """
        One-click button on the decision form:
          1. Find (or create) the best actuator mapping for this decision.
          2. Create a farm.control.action record.
          3. Execute it immediately.
          4. Open the control action form to show the result.
        """
        self.ensure_one()

        if self.status in ('executed', 'dismissed'):
            raise UserError(
                _('Decision is already %s. Re-open it first.') % self.status
            )

        # Duplicate guard — block if an active success already exists
        existing_success = self.control_action_ids.filtered(
            lambda a: a.state == 'success'
        )
        if existing_success:
            raise UserError(
                _('A successful control action already exists for this decision: %s.\n'
                  'Use "Force Re-execute" on that action record if needed.') % existing_success[0].name
            )

        # Resolve actuator via mapping
        actuator, mapping, execution_mode = self._resolve_actuator()

        control_action = self.env['farm.control.action'].create({
            'decision_id':    self.id,
            'action_type':    self.action_type,
            'actuator_id':    actuator.id if actuator else False,
            'execution_mode': execution_mode,
            'state':          'queued' if execution_mode == 'semi_auto' else 'draft',
        })

        # Execute immediately unless semi_auto (semi_auto waits for confirmation)
        if execution_mode != 'semi_auto':
            result = control_action.execute(force=False)
            msg = result['message']
            ntype = 'success' if result['success'] else 'danger'
        else:
            msg = _('Action queued — open the control action and confirm to send.')
            ntype = 'info'

        # Show result notification then open the control action form
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Control Action'),
            'res_model': 'farm.control.action',
            'res_id':    control_action.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def _resolve_actuator(self):
        """
        Find the best actuator mapping for this decision's farm + action_type.
        Returns (actuator | False, mapping | False, execution_mode).

        Lookup order:
          1. Mapping that matches farm + field + action_type (most specific)
          2. Mapping that matches farm + action_type (farm-wide)
          3. No mapping → return (False, False, 'manual')
        """
        self.ensure_one()
        domain_base = [
            ('action_type', '=', self.action_type),
            ('farm_id',     '=', self.farm_id.id),
            ('active',      '=', True),
        ]
        # Try field-specific first
        mapping = False
        if self.field_id:
            mapping = self.env['farm.actuator.mapping'].search(
                domain_base + [('field_id', '=', self.field_id.id)], limit=1,
            )
        # Fall back to farm-wide
        if not mapping:
            mapping = self.env['farm.actuator.mapping'].search(
                domain_base + [('field_id', '=', False)], limit=1,
            )

        if not mapping:
            _logger.warning(
                'Decision %d: no actuator mapping for farm=%s action=%s',
                self.id, self.farm_id.name if self.farm_id else '?', self.action_type,
            )
            return False, False, 'manual'

        return mapping.actuator_id, mapping, mapping.execution_mode


# ─────────────────────────────────────────────────────────────────────────────
# farm.sensor  –  Control action smart button
# ─────────────────────────────────────────────────────────────────────────────
class FarmSensorControlActions(models.Model):
    _inherit = 'farm.sensor'

    sensor_control_action_count = fields.Integer(
        string='Control Actions',
        compute='_compute_sensor_control_action_count',
    )

    def _compute_sensor_control_action_count(self):
        CA = self.env['farm.control.action']
        for sensor in self:
            sensor.sensor_control_action_count = CA.search_count(
                [('sensor_id', '=', sensor.id)]
            )

    def action_view_sensor_control_actions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Control Actions — %s') % self.name,
            'res_model': 'farm.control.action',
            'view_mode': 'list,form',
            'domain':    [('sensor_id', '=', self.id)],
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision.engine  –  Auto-create control actions for auto_execute rules
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionEngineControlHook(models.AbstractModel):
    _inherit = 'farm.decision.engine'

    @api.model
    def run(self):
        """
        Override run() to additionally auto-create + execute control actions
        for decisions whose rule has auto_execute = True.
        """
        total = super().run()
        self._auto_execute_control_actions()
        return total

    @api.model
    def _auto_execute_control_actions(self):
        """
        Find pending decisions linked to auto_execute rules that have
        no existing control action, and create + execute them.
        """
        pending = self.env['farm.decision'].search([
            ('status',               '=', 'pending'),
            ('rule_id.auto_execute', '=', True),
        ])

        executed = 0
        for dec in pending:
            # Skip if already has a successful control action
            if dec.control_action_ids.filtered(lambda a: a.state == 'success'):
                continue
            try:
                actuator, mapping, execution_mode = dec._resolve_actuator()
                ca = self.env['farm.control.action'].create({
                    'decision_id':    dec.id,
                    'action_type':    dec.action_type,
                    'actuator_id':    actuator.id if actuator else False,
                    'execution_mode': 'auto',
                    'state':          'draft',
                })
                result = ca.execute(force=False)
                if result['success']:
                    executed += 1
                else:
                    _logger.warning(
                        'Auto-execute failed for decision %d: %s', dec.id, result['message']
                    )
            except Exception as e:
                _logger.error('Auto-execute error for decision %d: %s', dec.id, e)

        if executed:
            _logger.info('Decision engine auto-executed %d control actions', executed)


# ─────────────────────────────────────────────────────────────────────────────
# farm.control.action  –  Integration with farm.actuator.device
# ─────────────────────────────────────────────────────────────────────────────
class FarmControlActionActuatorDevice(models.Model):
    """
    Extends farm.control.action with farm.actuator.device integration:

    • actuator_device_id     — explicit link to a farm.actuator.device record
    • _compute_actuator_device — auto-resolves the best matching device on create
    • no_actuator_warning    — shown in the form when no device can be resolved
    • send_command_payload   — pre-computed JSON for the "Send Command" button
    • action_send_command()  — primary button: auto-resolves device, builds
                               payload, publishes MQTT, logs result, updates state
    """
    _inherit = 'farm.control.action'

    # ── New field: link to farm.actuator.device ───────────────────────────────
    actuator_device_id = fields.Many2one(
        'farm.actuator.device',
        string='Actuator Device',
        ondelete='set null',
        tracking=True,
        help='The farm.actuator.device that will receive the MQTT command. '
             'Auto-resolved on creation; can be overridden manually.',
    )

    # ── Warning flag (visible in form when no device found) ──────────────────
    no_actuator_warning = fields.Char(
        string='Actuator Warning',
        compute='_compute_no_actuator_warning',
        help='Non-empty string means no suitable actuator.device was found.',
    )

    # ── Pre-built payload preview ─────────────────────────────────────────────
    send_command_payload = fields.Text(
        string='Command Payload Preview',
        compute='_compute_send_command_payload',
        help='Auto-built JSON payload that will be sent on "Send Command".',
    )

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            # Auto-resolve actuator.device if not explicitly set
            if not rec.actuator_device_id:
                rec._auto_resolve_actuator_device()
        return records

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('actuator_device_id', 'action_type', 'farm_id', 'state')
    def _compute_no_actuator_warning(self):
        """
        Show a warning when:
          - state is still 'draft'
          - action_type requires a real device (not manual_check / alert_only)
          - no actuator_device_id is set
        """
        manual_actions = {'manual_check', 'alert_only'}
        for rec in self:
            if rec.state not in ('draft', 'queued'):
                rec.no_actuator_warning = ''
                continue
            if rec.action_type in manual_actions:
                rec.no_actuator_warning = ''
                continue
            if rec.actuator_device_id:
                rec.no_actuator_warning = ''
            else:
                rec.no_actuator_warning = _(
                    'No actuator device found for action "%s" on farm "%s". '
                    'Assign a device manually or register a compatible actuator.'
                ) % (rec.action_type or '?', rec.farm_id.name if rec.farm_id else '?')

    @api.depends('action_type', 'actuator_device_id', 'decision_id')
    def _compute_send_command_payload(self):
        """Build a preview of the JSON payload that will be sent."""
        for rec in self:
            if rec.actuator_device_id:
                rec.send_command_payload = rec.actuator_device_id.get_command_payload(
                    rec.action_type or 'alert_only',
                    extra={'control_action_id': rec.id,
                           'decision_id': rec.decision_id.id if rec.decision_id else None}
                )
            elif rec.action_type:
                # Fall back to the catalogue without device metadata
                base = dict(ACTION_COMMANDS.get(rec.action_type, {'action': rec.action_type}))
                base.update({
                    'source': 'odoo_smart_farm',
                    'control_action_id': rec.id,
                })
                rec.send_command_payload = json.dumps(base, separators=(',', ':'))
            else:
                rec.send_command_payload = ''

    # ────────────────────────────────────────────────────────────────────────
    # Resolution helpers
    # ────────────────────────────────────────────────────────────────────────

    def _auto_resolve_actuator_device(self):
        """
        Find the best farm.actuator.device for this control action using the
        following priority chain:

          1. Same farm + same field + supports action_type
          2. Same farm              + supports action_type
          3. sensor_id.actuator_device_ids matching action_type
          4. Any active device      + supports action_type (global fallback)

        Sets self.actuator_device_id or leaves it False if nothing found.
        """
        self.ensure_one()
        if not self.action_type or self.action_type in ('manual_check', 'alert_only'):
            return

        ActDev = self.env['farm.actuator.device']
        domain_base = [
            ('active', '=', True),
            ('status', 'not in', ('offline', 'maintenance')),
            ('supported_action_keys', 'like', self.action_type),
        ]

        # Priority 1: field-scoped
        if self.field_id:
            dev = ActDev.search(
                domain_base + [('field_id', '=', self.field_id.id)], limit=1
            )
            if dev:
                self.actuator_device_id = dev
                return

        # Priority 2: farm-scoped
        if self.farm_id:
            dev = ActDev.search(
                domain_base + [('farm_id', '=', self.farm_id.id)], limit=1
            )
            if dev:
                self.actuator_device_id = dev
                return

        # Priority 3: via sensor linkage
        if self.sensor_id:
            sensor_devs = ActDev.search(
                domain_base + [('sensor_id', '=', self.sensor_id.id)], limit=1
            )
            if sensor_devs:
                self.actuator_device_id = sensor_devs
                return

        # Priority 4: any matching device (global fallback)
        dev = ActDev.search(domain_base, limit=1)
        if dev:
            self.actuator_device_id = dev

        # Nothing found → actuator_device_id remains False; warning computed field fires

    def action_resolve_actuator_device(self):
        """
        UI button: re-run auto-resolution on demand.
        Useful when a new actuator.device is registered after the action was created.
        """
        self.ensure_one()
        self.actuator_device_id = False
        self._auto_resolve_actuator_device()

        if self.actuator_device_id:
            msg   = _('Actuator resolved: %s') % self.actuator_device_id.name
            ntype = 'success'
        else:
            msg   = _('No matching actuator device found for action "%s".') % self.action_type
            ntype = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {'title': _('Actuator Resolution'), 'message': msg,
                       'type': ntype, 'sticky': ntype == 'warning'},
        }

    # ────────────────────────────────────────────────────────────────────────
    # "Send Command" button — the primary integration point
    # ────────────────────────────────────────────────────────────────────────

    def action_send_command(self):
        """
        Primary "Send Command" button handler.

        Steps:
          1. If no actuator_device_id: try auto-resolve. If still none → UserError.
          2. Validate the device is active and online-capable.
          3. Build payload via actuator_device_id.get_command_payload().
          4. Publish MQTT via actuator_device_id._publish_mqtt().
          5. Write result: state, result_message, executed_at/by.
          6. Append audit log entry.
          7. Update actuator_device_id status + last_command fields.
          8. If success → mark linked decision as 'executed'.
          9. Return UI notification.
        """
        self.ensure_one()

        # ── Step 1: resolve device if missing ────────────────────────────────
        if not self.actuator_device_id:
            self._auto_resolve_actuator_device()

        if not self.actuator_device_id:
            if self.action_type in ('manual_check', 'alert_only'):
                # No device needed — just log it
                self._log_manual_action()
                return self._notify_result(True, _('Manual action logged. No MQTT command sent.'))

            raise UserError(_(
                'No actuator device found for action "%s" on farm "%s".\n\n'
                'Options:\n'
                '  • Register a farm.actuator.device that supports "%s"\n'
                '  • Assign a device manually in the "Target" field\n'
                '  • Change the action type to "Manual Check" or "Alert Only"'
            ) % (self.action_type, self.farm_id.name if self.farm_id else '—', self.action_type))

        device = self.actuator_device_id

        # ── Step 2: device health check ──────────────────────────────────────
        if not device.active:
            raise UserError(_('Actuator device "%s" is inactive.') % device.name)
        if device.status == 'maintenance':
            raise UserError(_(
                'Actuator device "%s" is in maintenance mode.\n'
                'Change its status to send commands.'
            ) % device.name)

        # ── Step 3: build payload ─────────────────────────────────────────────
        payload_str = device.get_command_payload(
            self.action_type,
            extra={
                'control_action_id': self.id,
                'decision_id':       self.decision_id.id if self.decision_id else None,
                'source':            'odoo_smart_farm',
            },
        )
        # Persist payload snapshot on the record
        self.write({
            'command_payload': payload_str,
            'state':           'sent',
        })

        # ── Step 4: publish MQTT ──────────────────────────────────────────────
        # Override broker and topic from the device record
        original_broker = self.broker_id
        original_topic  = self.topic
        self.write({
            'broker_id':    device.broker_id.id if device.broker_id else self.broker_id.id,
            'topic':        device.command_topic or self.topic,
            'device_target': device.actuator_id,
        })

        success, message = self._publish_mqtt(payload_str)

        # ── Step 5: write result state ────────────────────────────────────────
        now       = fields.Datetime.now()
        new_state = 'success' if success else 'failed'
        self.write({
            'state':          new_state,
            'result_message': message,
            'executed_at':    now,
            'executed_by':    self.env.uid,
        })

        # ── Step 6: audit log ─────────────────────────────────────────────────
        self._log_attempt('mqtt', payload_str, success, message)

        # ── Step 7: update actuator_device status ─────────────────────────────
        device_update = {
            'last_command':    self.action_type,
            'last_command_at': now,
            'last_result':     'success' if success else 'failed',
        }
        if success:
            device_update['status'] = 'online'
        else:
            device_update['status'] = 'error'
        device.write(device_update)

        # Also update legacy farm.actuator if still linked
        if self.actuator_id:
            self.actuator_id.write({
                'last_command':    payload_str[:200],
                'last_command_at': now,
                'last_result':     'success' if success else 'failed',
            })

        # ── Step 8: mark decision executed on success ─────────────────────────
        if success and self.decision_id and self.decision_id.status in ('pending', 'acknowledged'):
            self.decision_id.write({
                'status':          'executed',
                'executed_by':     self.env.uid,
                'executed_at':     now,
                'execution_notes': _(
                    'Executed via control action %s → actuator device "%s"'
                ) % (self.name, device.name),
            })

        # ── Step 9: return UI notification ────────────────────────────────────
        return self._notify_result(success, message)

    # ────────────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────────────

    def _log_manual_action(self):
        """Log a manual (no-MQTT) execution attempt."""
        now = fields.Datetime.now()
        msg = _('Manual action logged. No actuator device assigned or needed.')
        self.write({
            'state':          'success',
            'result_message': msg,
            'executed_at':    now,
            'executed_by':    self.env.uid,
        })
        self._log_attempt('manual', '', True, msg)
        if self.decision_id and self.decision_id.status in ('pending', 'acknowledged'):
            self.decision_id.write({
                'status':          'executed',
                'executed_by':     self.env.uid,
                'executed_at':     now,
                'execution_notes': _('Executed manually via control action %s') % self.name,
            })

    @staticmethod
    def _notify_result(success, message):
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Command Sent') if success else _('Command Failed'),
                'message': message,
                'type':    'success' if success else 'danger',
                'sticky':  not success,
            },
        }
