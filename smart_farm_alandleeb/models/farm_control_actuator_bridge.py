# -*- coding: utf-8 -*-
"""
Smart Farm — Control Action ↔ Actuator Device Bridge
======================================================
Extends farm.control.action with:

  1. Auto-resolution of farm.actuator.device based on:
       farm_id  →  from decision (required)
       field_id →  from decision (preferred over farm-only)
       sensor_id → from decision (highest specificity)
       action_type → must be in device.supported_action_keys

  2. Online validation before command dispatch:
       If device.status is not 'online' → UserError (keeps state=draft).

  3. Warning notification when no actuator is found:
       state stays 'draft', result_message set, user is notified.

Resolution priority (most specific → least specific)
─────────────────────────────────────────────────────
  P1: sensor_id match  + action_type match
  P2: field_id  match  + action_type match
  P3: farm_id   match  + action_type match
  P4: any active online device with action_type match

Each level only falls to the next if no result is found.
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FarmControlActionActuatorBridge(models.Model):
    """
    Inherits farm.control.action and adds:
      - actuator_device_id field (points to farm.actuator.device)
      - auto-resolution method
      - online validation
      - warning-on-no-actuator flow
    """
    _inherit = 'farm.control.action'

    # ── New actuator device link ──────────────────────────────────────────────
    actuator_device_id = fields.Many2one(
        'farm.actuator.device',
        string='Actuator Device',
        ondelete='set null',
        tracking=True,
        help='Resolved actuator device. Auto-selected based on farm / field / sensor / action type.',
    )
    actuator_device_status = fields.Selection(
        related='actuator_device_id.status',
        string='Actuator Status',
        readonly=True,
    )
    resolution_log = fields.Text(
        string='Resolution Log',
        readonly=True,
        help='Records how the actuator was resolved (or why none was found).',
    )
    online_check_skipped = fields.Boolean(
        string='Online Check Skipped',
        default=False,
        help='If True, the online check was bypassed by a manager.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Auto-resolve on action_type / decision change
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('action_type', 'decision_id')
    def _onchange_auto_resolve_actuator_device(self):
        """
        Triggered when action_type or decision changes on the form.
        Attempts to auto-resolve actuator_device_id and shows a warning
        inline if none is found.
        """
        if not self.action_type:
            return

        device, log = self._resolve_actuator_device()
        self.actuator_device_id = device
        self.resolution_log     = log

        if not device:
            return {
                'warning': {
                    'title':   _('No Actuator Found'),
                    'message': log,
                }
            }

    # ────────────────────────────────────────────────────────────────────────
    # Resolution engine
    # ────────────────────────────────────────────────────────────────────────

    def _resolve_actuator_device(self):
        """
        Resolve the best farm.actuator.device for this control action.

        Returns:
            (farm.actuator.device|empty, log_str)
        """
        self.ensure_one()
        ActuatorDevice = self.env['farm.actuator.device']
        action_type    = self.action_type

        if not action_type:
            return ActuatorDevice.browse(), _('No action type set.')

        # Collect context from the linked decision
        farm_id   = self.farm_id.id   if self.farm_id   else None
        field_id  = self.field_id.id  if self.field_id  else None
        sensor_id = self.sensor_id.id if self.sensor_id else None

        base_domain = [
            ('active', '=', True),
            ('supported_action_keys', 'like', action_type),
        ]

        # ── P1: sensor-level match ────────────────────────────────────────────
        if sensor_id:
            device = ActuatorDevice.search(
                base_domain + [('sensor_id', '=', sensor_id)], limit=1,
                order='status asc',   # 'online' < 'offline' alphabetically → prefers online
            )
            if device:
                log = _(
                    'P1 — Sensor match: found "%s" [%s] via sensor "%s".'
                ) % (device.name, device.actuator_id, self.sensor_id.name)
                _logger.debug('Control action %s: %s', self.id or 'new', log)
                return device, log

        # ── P2: field-level match ─────────────────────────────────────────────
        if field_id:
            device = ActuatorDevice.search(
                base_domain + [('field_id', '=', field_id)], limit=1,
                order='status asc',
            )
            if device:
                log = _(
                    'P2 — Field match: found "%s" [%s] on field "%s".'
                ) % (device.name, device.actuator_id, self.field_id.name)
                _logger.debug('Control action %s: %s', self.id or 'new', log)
                return device, log

        # ── P3: farm-level match ──────────────────────────────────────────────
        if farm_id:
            device = ActuatorDevice.search(
                base_domain + [('farm_id', '=', farm_id)], limit=1,
                order='status asc',
            )
            if device:
                log = _(
                    'P3 — Farm match: found "%s" [%s] on farm "%s".'
                ) % (device.name, device.actuator_id, self.farm_id.name)
                _logger.debug('Control action %s: %s', self.id or 'new', log)
                return device, log

        # ── P4: global fallback ───────────────────────────────────────────────
        device = ActuatorDevice.search(base_domain, limit=1, order='status asc')
        if device:
            log = _(
                'P4 — Global fallback: found "%s" [%s] (no farm/field/sensor match).'
            ) % (device.name, device.actuator_id)
            _logger.debug('Control action %s: %s', self.id or 'new', log)
            return device, log

        # ── No match ──────────────────────────────────────────────────────────
        log = _(
            'No active actuator device found for action "%s"'
            ' (farm: %s, field: %s, sensor: %s).\n'
            'Register a farm.actuator.device with "%s" in its Supported Actions.'
        ) % (
            action_type,
            self.farm_id.name  if self.farm_id  else '—',
            self.field_id.name if self.field_id else '—',
            self.sensor_id.name if self.sensor_id else '—',
            action_type,
        )
        _logger.warning('Control action %s: %s', self.id or 'new', log)
        return ActuatorDevice.browse(), log

    # ── Public helper callable from wizard / cron / other models ─────────────

    def resolve_and_assign_actuator_device(self):
        """
        Resolve and assign actuator_device_id in a server-side write.
        Does NOT raise — sets state=draft + result_message if not found.
        Returns True if resolved, False if no actuator found.
        """
        self.ensure_one()
        device, log = self._resolve_actuator_device()
        vals = {'resolution_log': log}

        if device:
            vals['actuator_device_id'] = device.id
            self.write(vals)
            return True
        else:
            vals.update({
                'actuator_device_id': False,
                'state':              'draft',
                'result_message':     log,
            })
            self.write(vals)
            return False

    # ────────────────────────────────────────────────────────────────────────
    # Online validation
    # ────────────────────────────────────────────────────────────────────────

    def _validate_actuator_online(self):
        """
        Raise UserError if the actuator device is not online.
        Must be called before any MQTT publish attempt.

        Raises:
            UserError — if device is offline / maintenance / error / unknown
                        AND online_check_skipped is False.
        """
        self.ensure_one()
        device = self.actuator_device_id
        if not device:
            return   # No device linked — handled elsewhere

        if self.online_check_skipped:
            _logger.warning(
                'Control action %s: online check skipped for device "%s" [status=%s]',
                self.name, device.name, device.status,
            )
            return

        if device.status == 'online':
            return   # All good

        status_labels = {
            'offline':     _('Offline'),
            'maintenance': _('Under Maintenance'),
            'error':       _('In Error State'),
            'unknown':     _('Unknown (never reported online)'),
        }
        label = status_labels.get(device.status, device.status)
        raise UserError(_(
            'Cannot send command — actuator "%s" [%s] is currently %s.\n\n'
            'Options:\n'
            '  • Wait for the device to come online and retry.\n'
            '  • Fix the device and use "Mark Online".\n'
            '  • If you are sure the device is reachable, enable '
            '"Skip Online Check" and try again.'
        ) % (device.name, device.actuator_id, label))

    # ────────────────────────────────────────────────────────────────────────
    # Override execute() to inject resolution + online check
    # ────────────────────────────────────────────────────────────────────────

    def execute(self, force=False):
        """
        Extended execute():
          1. Auto-resolve actuator_device_id if not yet set.
          2. If no actuator found → warn, state stays draft, return early.
          3. Validate device is online (unless skipped).
          4. Call super().execute() for the actual MQTT dispatch.
          5. Mirror result onto actuator_device_id for status tracking.
        """
        self.ensure_one()

        # ── Step 1: auto-resolve if actuator_device_id is empty ───────────────
        if not self.actuator_device_id:
            found = self.resolve_and_assign_actuator_device()
            if not found:
                # No actuator — stay in draft, return warning
                _logger.warning(
                    'Control action %s: no actuator device found — staying draft.',
                    self.name,
                )
                return {
                    'success': False,
                    'message': self.result_message or _(
                        'No actuator device found for action "%s". '
                        'State kept as Draft.'
                    ) % self.action_type,
                    'payload': '',
                }

        # ── Step 2: validate online ────────────────────────────────────────────
        # This raises UserError on failure (state stays draft)
        self._validate_actuator_online()

        # ── Step 3: call original execute() ───────────────────────────────────
        result = super().execute(force=force)

        # ── Step 4: mirror result → actuator_device_id ────────────────────────
        device = self.actuator_device_id
        if device:
            now = fields.Datetime.now()
            device_vals = {'last_seen': now}
            if result.get('success'):
                device_vals.update({
                    'status':          'online',
                    'last_command':    self.action_type,
                    'last_command_at': now,
                    'last_result':     'success',
                })
            else:
                device_vals.update({
                    'last_command':    self.action_type,
                    'last_command_at': now,
                    'last_result':     'failed',
                })
            try:
                device.write(device_vals)
            except Exception as e:
                _logger.warning(
                    'Could not update actuator_device_id %d after execute: %s',
                    device.id, e,
                )

        return result

    # ────────────────────────────────────────────────────────────────────────
    # UI actions
    # ────────────────────────────────────────────────────────────────────────

    def action_resolve_actuator(self):
        """
        Button: manually trigger actuator resolution and show result.
        """
        self.ensure_one()
        found = self.resolve_and_assign_actuator_device()
        if found:
            msg   = _('Actuator resolved: %s [%s]') % (
                self.actuator_device_id.name,
                self.actuator_device_id.actuator_id,
            )
            ntype = 'success'
        else:
            msg   = self.resolution_log or _('No actuator found.')
            ntype = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {'title': _('Actuator Resolution'), 'message': msg,
                       'type': ntype, 'sticky': not found},
        }

    def action_skip_online_check(self):
        """Allow a manager to bypass the online check."""
        self.ensure_one()
        self.online_check_skipped = True
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Online Check Skipped'),
                'message': _('The online status check will be bypassed on next execution.'),
                'type':    'warning',
                'sticky':  False,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# farm.decision  –  Extended: create control action with auto-resolved actuator
# ─────────────────────────────────────────────────────────────────────────────
class FarmDecisionControlBridge(models.Model):
    _inherit = 'farm.decision'

    def action_create_control_action(self):
        """
        Create a farm.control.action from this decision with auto-resolved
        actuator device.  Shows a warning notification if no device is found
        (action is still created, state=draft, user can resolve manually).
        """
        self.ensure_one()

        if not self.action_type:
            raise UserError(_('This decision has no action type set.'))

        # Create the control action
        ca = self.env['farm.control.action'].create({
            'decision_id':  self.id,
            'action_type':  self.action_type,
        })

        # Auto-resolve actuator device
        found = ca.resolve_and_assign_actuator_device()

        # Build notification
        if found:
            device   = ca.actuator_device_id
            msg      = _('Control action %s created — actuator: %s [%s]') % (
                ca.name, device.name, device.actuator_id,
            )
            ntype    = 'success'
        else:
            msg      = _(
                'Control action %s created in Draft — no actuator device found '
                'for action "%s". Assign one manually before executing.'
            ) % (ca.name, self.action_type)
            ntype    = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Control Action Created'),
                'message': msg,
                'type':    ntype,
                'sticky':  not found,
                'next': {
                    'type':      'ir.actions.act_window',
                    'res_model': 'farm.control.action',
                    'res_id':    ca.id,
                    'view_mode': 'form',
                    'target':    'current',
                },
            },
        }

    def action_view_control_actions(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Control Actions — %s') % self.name,
            'res_model': 'farm.control.action',
            'view_mode': 'list,form',
            'domain':    [('decision_id', '=', self.id)],
            'context':   {'default_decision_id': self.id,
                          'default_action_type': self.action_type},
        }
