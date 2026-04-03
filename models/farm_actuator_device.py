# -*- coding: utf-8 -*-
"""
Smart Farm — Actuator Mapping Layer
=====================================
Model: farm.actuator.device

Maps farm.decision action types to physical actuator hardware.
Commands are published via MQTT.

Decision → actuator action mapping
─────────────────────────────────────
  cooling      → {"action":"cooling_on"}
  heating      → {"action":"heating_on"}
  irrigation   → {"action":"irrigation_on"}
  dehumidify   → {"action":"dehumidify_on"}
  co2_inject   → {"action":"co2_inject_on"}
  co2_reduce   → {"action":"co2_vent_on"}
  manual_check → {"action":"operator_alert"}
  alert_only   → {"action":"alert_only"}

Topic pattern: farm/actuators/<actuator_id>/set
"""
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ── Supported actions per actuator_type ─────────────────────────────────────
_TYPE_ACTIONS = {
    'cooling':    ['cooling', 'co2_reduce'],
    'heating':    ['heating'],
    'irrigation': ['irrigation'],
    'dehumidify': ['dehumidify'],
    'co2':        ['co2_inject', 'co2_reduce'],
    'valve':      ['irrigation'],
    'multi':      ['cooling', 'heating', 'irrigation', 'dehumidify',
                   'co2_inject', 'co2_reduce', 'manual_check', 'alert_only'],
    'generic':    ['cooling', 'heating', 'irrigation', 'dehumidify',
                   'co2_inject', 'co2_reduce', 'manual_check', 'alert_only'],
}

# ── Command payload catalogue ────────────────────────────────────────────────
_COMMAND_PAYLOADS = {
    'cooling':      {'action': 'cooling_on'},
    'heating':      {'action': 'heating_on'},
    'irrigation':   {'action': 'irrigation_on'},
    'dehumidify':   {'action': 'dehumidify_on'},
    'co2_inject':   {'action': 'co2_inject_on'},
    'co2_reduce':   {'action': 'co2_vent_on'},
    'manual_check': {'action': 'operator_alert'},
    'alert_only':   {'action': 'alert_only'},
}

_SUPPORTED_ACTIONS_SEL = [
    ('cooling',      'Cooling / Ventilation'),
    ('heating',      'Heating'),
    ('irrigation',   'Irrigation / Pump'),
    ('dehumidify',   'Dehumidification'),
    ('co2_inject',   'CO₂ Injection'),
    ('co2_reduce',   'CO₂ Reduction / Venting'),
    ('manual_check', 'Manual Inspection'),
    ('alert_only',   'Alert Only'),
]


class FarmActuatorDevice(models.Model):
    _name        = 'farm.actuator.device'
    _description = 'Farm Actuator Device'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'farm_id, name'

    # ── General Info ─────────────────────────────────────────────────────────
    name = fields.Char(
        string='Name', required=True, tracking=True,
    )
    actuator_id = fields.Char(
        string='Actuator ID',
        required=True,
        copy=False,
        index=True,
        help='Unique identifier. Used in MQTT topic: farm/actuators/<id>/set',
    )
    active = fields.Boolean(default=True)

    actuator_type = fields.Selection([
        ('cooling',    'Cooling / Fan'),
        ('heating',    'Heating System'),
        ('irrigation', 'Irrigation / Pump'),
        ('dehumidify', 'Dehumidifier'),
        ('co2',        'CO₂ Controller'),
        ('valve',      'Solenoid Valve'),
        ('multi',      'Multi-Function'),
        ('generic',    'Generic'),
    ], string='Type', required=True, default='generic', tracking=True)

    # ── Mapping / Location ───────────────────────────────────────────────────
    sensor_id = fields.Many2one(
        'farm.sensor',
        string='Linked Sensor',
        ondelete='set null',
        help='Sensor whose readings/decisions drive this actuator.',
        tracking=True,
    )

    # farm_id: primarily from sensor, but can be set directly
    farm_id = fields.Many2one(
        'farm.farm',
        string='Farm',
        compute='_compute_location_from_sensor',
        store=True,
        readonly=False,
        tracking=True,
    )
    field_id = fields.Many2one(
        'farm.field',
        string='Field',
        compute='_compute_location_from_sensor',
        store=True,
        readonly=False,
        domain="[('farm_id', '=', farm_id)]",
        tracking=True,
    )

    # Supported actions — tag-style Many2many for flexibility
    supported_actions = fields.Many2many(
        'farm.actuator.action.type',
        'farm_actuator_device_action_rel',
        'device_id', 'action_type_id',
        string='Supported Actions',
    )
    # Computed comma-key string for fast domain filtering
    supported_action_keys = fields.Char(
        string='Supported Action Keys',
        compute='_compute_supported_action_keys',
        store=True,
        help='Comma-separated action type keys — used for fast filtering.',
    )

    # ── MQTT Configuration ───────────────────────────────────────────────────
    broker_id = fields.Many2one(
        'farm.mqtt.broker',
        string='MQTT Broker',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    command_topic = fields.Char(
        string='Command Topic',
        required=True,
        compute='_compute_command_topic',
        store=True,
        readonly=False,
        help='Topic to publish commands. Default: farm/actuators/<actuator_id>/set',
    )
    command_qos = fields.Selection([
        ('0', 'QoS 0 — At most once'),
        ('1', 'QoS 1 — At least once'),
        ('2', 'QoS 2 — Exactly once'),
    ], string='QoS', default='1')
    command_retain = fields.Boolean(
        string='Retain',
        default=False,
        help='Broker retains the last command payload.',
    )

    # ── Status / Notes ───────────────────────────────────────────────────────
    status = fields.Selection([
        ('unknown',      'Unknown'),
        ('online',       'Online'),
        ('offline',      'Offline'),
        ('maintenance',  'Maintenance'),
        ('error',        'Error'),
    ], string='Status', default='unknown', tracking=True, readonly=True)

    last_seen       = fields.Datetime(string='Last Seen',        readonly=True)
    last_command    = fields.Char(    string='Last Command',     readonly=True)
    last_command_at = fields.Datetime(string='Last Sent',        readonly=True)
    last_result     = fields.Selection([
        ('success', 'Success'), ('failed', 'Failed'),
    ], string='Last Result', readonly=True)

    notes = fields.Text(string='Notes')

    # ── Counters ──────────────────────────────────────────────────────────────
    command_count = fields.Integer(
        string='Commands Sent',
        compute='_compute_command_count',
    )

    # ── SQL constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        ('actuator_id_uniq', 'UNIQUE(actuator_id)',
         'Actuator ID must be unique across all devices.'),
    ]

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('sensor_id', 'sensor_id.farm_id', 'sensor_id.field_id')
    def _compute_location_from_sensor(self):
        """Auto-fill farm_id and field_id from the linked sensor when possible."""
        for rec in self:
            if rec.sensor_id:
                if not rec.farm_id:
                    rec.farm_id  = rec.sensor_id.farm_id
                if not rec.field_id and rec.sensor_id.field_id:
                    rec.field_id = rec.sensor_id.field_id
            # If sensor cleared and farm/field still empty — leave as is
            # so manual overrides are preserved.

    @api.depends('actuator_id')
    def _compute_command_topic(self):
        for rec in self:
            if rec.actuator_id and not rec.command_topic:
                rec.command_topic = 'farm/actuators/%s/set' % rec.actuator_id

    @api.depends('supported_actions', 'supported_actions.key')
    def _compute_supported_action_keys(self):
        for rec in self:
            rec.supported_action_keys = ','.join(
                rec.supported_actions.mapped('key')
            ) if rec.supported_actions else ''

    def _compute_command_count(self):
        Log = self.env['farm.actuator.command.log']
        for rec in self:
            rec.command_count = Log.search_count([('actuator_device_id', '=', rec.id)])

    # ────────────────────────────────────────────────────────────────────────
    # ORM hooks
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.command_topic and rec.actuator_id:
                rec.command_topic = 'farm/actuators/%s/set' % rec.actuator_id
            if not rec.supported_actions:
                rec._auto_assign_supported_actions()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'actuator_type' in vals:
            for rec in self:
                if not rec.supported_actions:
                    rec._auto_assign_supported_actions()
        return res

    def _auto_assign_supported_actions(self):
        """Populate supported_actions from actuator_type defaults."""
        keys = _TYPE_ACTIONS.get(self.actuator_type, [])
        if keys:
            types = self.env['farm.actuator.action.type'].search([('key', 'in', keys)])
            if types:
                self.supported_actions = [(6, 0, types.ids)]

    # ────────────────────────────────────────────────────────────────────────
    # Constraints
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('command_topic')
    def _check_command_topic(self):
        for rec in self:
            if not rec.command_topic or not rec.command_topic.strip():
                raise ValidationError(
                    _('Command topic cannot be empty for actuator "%s".') % rec.name
                )

    @api.constrains('actuator_id')
    def _check_actuator_id_format(self):
        for rec in self:
            if not rec.actuator_id or not rec.actuator_id.strip():
                raise ValidationError(_('Actuator ID cannot be empty.'))
            if ' ' in rec.actuator_id:
                raise ValidationError(
                    _('Actuator ID "%s" must not contain spaces.') % rec.actuator_id
                )

    # ────────────────────────────────────────────────────────────────────────
    # Public logic methods
    # ────────────────────────────────────────────────────────────────────────

    def get_command_payload(self, action_type, extra=None):
        """
        Build the JSON command payload for a given action_type.

        Args:
            action_type (str): key from _COMMAND_PAYLOADS, e.g. 'cooling'
            extra (dict):      optional extra fields merged into payload

        Returns:
            str  — JSON string ready to publish

        Examples:
            get_command_payload('cooling')
              → '{"action":"cooling_on","device_id":"fan01","source":"odoo"}'

            get_command_payload('irrigation', {'zone': 3})
              → '{"action":"irrigation_on","device_id":"pump01","zone":3,...}'
        """
        self.ensure_one()
        base = dict(_COMMAND_PAYLOADS.get(action_type, {'action': action_type}))
        base.update({
            'device_id': self.actuator_id,
            'source':    'odoo_smartfarm',
            'ts':        fields.Datetime.now().isoformat(),
        })
        if extra and isinstance(extra, dict):
            base.update(extra)
        return json.dumps(base, separators=(',', ':'))

    @api.model
    def resolve_for_action(self, action_type, farm_id=None, field_id=None):
        """
        Find the best actuator device that can handle `action_type`.

        Resolution order:
          1. field-scoped match (field_id + action_type)
          2. farm-scoped match  (farm_id  + action_type)
          3. any active device  (action_type only)

        Returns:
            farm.actuator.device record or empty recordset.
        """
        domain_base = [
            ('active', '=', True),
            ('status', 'not in', ('offline', 'maintenance')),
            ('supported_action_keys', 'like', action_type),
        ]

        if field_id:
            result = self.search(domain_base + [('field_id', '=', field_id)], limit=1)
            if result:
                return result

        if farm_id:
            result = self.search(domain_base + [('farm_id', '=', farm_id)], limit=1)
            if result:
                return result

        return self.search(domain_base, limit=1)

    def can_handle_action(self, action_type):
        """Return True if this actuator supports the given action_type."""
        self.ensure_one()
        keys = self.supported_action_keys or ''
        return action_type in [k.strip() for k in keys.split(',') if k.strip()]

    # ────────────────────────────────────────────────────────────────────────
    # Command dispatch
    # ────────────────────────────────────────────────────────────────────────

    def send_command(self, action_type, decision=None, extra_payload=None):
        """
        Publish an MQTT command and log the attempt.

        Args:
            action_type   (str): e.g. 'cooling', 'irrigation'
            decision      (farm.decision record): optional source decision
            extra_payload (dict): merged into JSON payload

        Returns:
            farm.actuator.command.log record
        """
        self.ensure_one()

        if not self.active:
            raise UserError(_('Actuator "%s" is inactive.') % self.name)
        if not self.command_topic:
            raise UserError(_('No command topic configured for "%s".') % self.name)
        if not self.can_handle_action(action_type):
            raise UserError(
                _('Actuator "%s" does not support action "%s".\nSupported: %s')
                % (self.name, action_type, self.supported_action_keys)
            )

        payload_str = self.get_command_payload(action_type, extra_payload)
        ok, error   = self._publish_mqtt(payload_str)

        log = self.env['farm.actuator.command.log'].create({
            'actuator_device_id': self.id,
            'decision_id':        decision.id if decision else False,
            'farm_id':            self.farm_id.id if self.farm_id else False,
            'field_id':           self.field_id.id if self.field_id else False,
            'action_type':        action_type,
            'command_topic':      self.command_topic,
            'payload':            payload_str,
            'status':             'sent' if ok else 'failed',
            'error_message':      error or False,
        })

        self.write({
            'last_command':    action_type,
            'last_command_at': fields.Datetime.now(),
            'last_result':     'success' if ok else 'failed',
            'status':          'online' if ok else 'error',
        })

        if not ok:
            _logger.error('Actuator "%s" command failed: %s', self.name, error)

        return log

    def _publish_mqtt(self, payload_str):
        """
        Publish payload to self.command_topic via farm.mqtt.publisher.

        Uses the publisher service which:
          - Reuses active listener connections (zero extra TCP)
          - Falls back to one-shot connect-publish-disconnect
          - Waits for QoS-1 ACK via wait_for_publish()
          - Logs every attempt to farm.mqtt.publish.log

        Returns (success: bool, error: str|None).
        """
        if not self.broker_id:
            return False, 'No MQTT broker assigned to actuator "%s"' % self.name
        if not self.command_topic:
            return False, 'No command topic on actuator "%s"' % self.name

        result = self.env['farm.mqtt.publisher'].publish(
            broker=self.broker_id,
            topic=self.command_topic,
            payload=payload_str,
            qos=int(self.command_qos or 1),
            retain=self.command_retain,
            source_model=self._name,
            source_id=self.id,
        )
        return result.success, None if result.success else result.message

    # ────────────────────────────────────────────────────────────────────────
    # UI actions
    # ────────────────────────────────────────────────────────────────────────

    def action_test_command(self):
        """Send a test ping payload to the actuator."""
        self.ensure_one()
        payload = json.dumps({
            'action': 'ping', 'device_id': self.actuator_id,
            'source': 'odoo_test', 'ts': fields.Datetime.now().isoformat(),
        }, separators=(',', ':'))
        ok, error = self._publish_mqtt(payload)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title':   _('Actuator Test'),
                'message': (_('Ping sent to %s') % self.name) if ok else
                           (_('Ping failed: %s') % error),
                'type':    'success' if ok else 'danger',
                'sticky':  not ok,
            },
        }

    def action_mark_online(self):
        self.write({'status': 'online', 'last_seen': fields.Datetime.now()})

    def action_mark_offline(self):
        self.write({'status': 'offline'})

    def action_mark_maintenance(self):
        self.write({'status': 'maintenance'})

    def action_view_command_log(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Commands — %s') % self.name,
            'res_model': 'farm.actuator.command.log',
            'view_mode': 'list,form',
            'domain':    [('actuator_device_id', '=', self.id)],
        }

    def name_get(self):
        return [(r.id, '%s [%s]' % (r.name, r.actuator_id)) for r in self]


# ─────────────────────────────────────────────────────────────────────────────
# farm.actuator.action.type  –  Action type tag registry
# ─────────────────────────────────────────────────────────────────────────────
class FarmActuatorActionType(models.Model):
    _name        = 'farm.actuator.action.type'
    _description = 'Actuator Action Type'
    _order       = 'sequence, key'

    key      = fields.Char(string='Key',          required=True, index=True)
    name     = fields.Char(string='Display Name', required=True)
    sequence = fields.Integer(default=10)
    active   = fields.Boolean(default=True)
    icon     = fields.Char(string='FA Icon', default='fa-bolt')
    color    = fields.Integer(string='Color Index', default=0)

    _sql_constraints = [('key_uniq', 'UNIQUE(key)', 'Key must be unique.')]


# ─────────────────────────────────────────────────────────────────────────────
# farm.actuator.command.log  –  Immutable audit log
# ─────────────────────────────────────────────────────────────────────────────
class FarmActuatorCommandLog(models.Model):
    _name        = 'farm.actuator.command.log'
    _description = 'Actuator Command Log'
    _order       = 'create_date desc'
    _rec_name    = 'action_type'

    actuator_device_id = fields.Many2one(
        'farm.actuator.device', string='Actuator',
        ondelete='cascade', index=True, readonly=True,
    )
    decision_id = fields.Many2one(
        'farm.decision', string='Source Decision',
        ondelete='set null', readonly=True,
    )
    farm_id  = fields.Many2one('farm.farm',  string='Farm',  readonly=True)
    field_id = fields.Many2one('farm.field', string='Field', readonly=True)

    action_type   = fields.Char(string='Action Type',  readonly=True, index=True)
    command_topic = fields.Char(string='Topic',         readonly=True)
    payload       = fields.Text(string='Payload (JSON)', readonly=True)

    status = fields.Selection([
        ('sent',    'Sent'),
        ('acked',   'Acknowledged'),
        ('failed',  'Failed'),
        ('timeout', 'Timeout'),
    ], string='Status', default='sent', readonly=True)

    error_message = fields.Char(string='Error', readonly=True)
    sent_by       = fields.Many2one(
        'res.users', string='Sent By',
        default=lambda s: s.env.uid, readonly=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision  –  Extended: actuator auto-resolution + execute via actuator
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionActuatorLink(models.Model):
    _inherit = 'farm.decision'

    actuator_device_id = fields.Many2one(
        'farm.actuator.device',
        string='Assigned Actuator',
        compute='_compute_assigned_actuator',
        store=True,
        readonly=False,
        help='Auto-resolved from action_type + farm/field scope.',
    )
    actuator_command_count = fields.Integer(
        string='Commands',
        compute='_compute_actuator_command_count',
    )

    @api.depends('action_type', 'farm_id', 'field_id', 'status')
    def _compute_assigned_actuator(self):
        ActDev = self.env['farm.actuator.device']
        for dec in self:
            if not dec.action_type or dec.action_type in ('manual_check', 'alert_only'):
                dec.actuator_device_id = False
                continue
            dec.actuator_device_id = ActDev.resolve_for_action(
                dec.action_type,
                farm_id=dec.farm_id.id  if dec.farm_id  else None,
                field_id=dec.field_id.id if dec.field_id else None,
            ) or False

    def _compute_actuator_command_count(self):
        Log = self.env['farm.actuator.command.log']
        for dec in self:
            dec.actuator_command_count = Log.search_count([('decision_id', '=', dec.id)])

    def action_execute_via_actuator(self):
        """Execute decision by sending MQTT command to the assigned actuator."""
        self.ensure_one()
        if not self.actuator_device_id:
            raise UserError(_(
                'No actuator assigned for action "%s" on farm "%s".\n'
                'Assign an actuator device or execute manually.'
            ) % (self.action_type, self.farm_id.name if self.farm_id else '—'))

        log = self.actuator_device_id.send_command(
            action_type=self.action_type,
            decision=self,
        )
        if log.status == 'sent':
            self.write({
                'status':          'executed',
                'executed_by':     self.env.uid,
                'executed_at':     fields.Datetime.now(),
                'execution_notes': _(
                    'Executed via actuator "%s" → topic: %s'
                ) % (self.actuator_device_id.name, log.command_topic),
            })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title':   _('Command Sent') if log.status == 'sent' else _('Command Failed'),
                'message': (_('Command sent to %s') % self.actuator_device_id.name)
                           if log.status == 'sent'
                           else (log.error_message or _('Unknown error')),
                'type':    'success' if log.status == 'sent' else 'danger',
                'sticky':  log.status != 'sent',
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.sensor  –  Extended: linked actuators smart button
# ─────────────────────────────────────────────────────────────────────────────
class FarmSensorActuatorLink(models.Model):
    _inherit = 'farm.sensor'

    actuator_device_ids = fields.One2many(
        'farm.actuator.device', 'sensor_id', string='Linked Actuators',
    )
    actuator_device_count = fields.Integer(
        string='Actuators', compute='_compute_actuator_device_count',
    )

    def _compute_actuator_device_count(self):
        for s in self:
            s.actuator_device_count = len(s.actuator_device_ids)

    def action_view_actuator_devices(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Actuators — %s') % self.name,
            'res_model': 'farm.actuator.device',
            'view_mode': 'list,form',
            'domain':    [('sensor_id', '=', self.id)],
            'context':   {'default_sensor_id': self.id,
                          'default_farm_id':   self.farm_id.id},
        }
