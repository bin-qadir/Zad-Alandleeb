"""
mythos.alert — Mythos AI Alert
================================
Lightweight alert records created by the Mythos Basic Monitor cron and,
in future phases, by individual agents.

Safety rules (enforced by design):
  - No emails, no external messages, no API calls
  - Only creates records — never modifies existing operational data
  - Duplicate-safe: cron checks for open alerts before creating a new one

Step 4 addition:
  - _send_to_telegram(): finds matching active bot by domain_type and logs
    an outgoing mythos.telegram.message record. No real Telegram API call.
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

    # ── Telegram routing (Step 4) ─────────────────────────────────────────────

    telegram_sent = fields.Boolean(
        string='Sent to Telegram',
        default=False,
        help='True when a Telegram message record has been created for this alert.',
    )
    telegram_bot_id = fields.Many2one(
        comodel_name='mythos.telegram.bot',
        string='Telegram Bot',
        ondelete='set null',
        help='The Telegram bot that received the message record for this alert.',
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

    # ────────────────────────────────────────────────────────────────────────
    # Step 7 — Discuss Bot routing (internal Odoo messaging)
    # ────────────────────────────────────────────────────────────────────────

    def _send_to_discuss_bot(self):
        """Post this alert to the matching active Discuss Bot channel.

        Matching rule: bot.domain_type == alert.agent_id.domain_type
                       AND bot.active == True AND bot.channel_id is set

        SAFETY:
          - No external API calls.
          - Only posts to internal Discuss channel.
          - Skips silently if no matching bot or channel found.
          - Never raises — any error is caught and logged.
        """
        self.ensure_one()
        domain_type = self.agent_id.domain_type if self.agent_id else False
        if not domain_type:
            return False

        bot = self.env['mythos.discuss.bot'].search([
            ('domain_type', '=', domain_type),
            ('active',      '=', True),
            ('channel_id',  '!=', False),
        ], limit=1)

        if not bot:
            _logger.debug(
                'MythosAlert._send_to_discuss_bot: no active Discuss bot for domain "%s".',
                domain_type,
            )
            return False

        _SEVERITY_LABEL = {
            'low':      '🟡 Low',
            'medium':   '🟠 Medium',
            'high':     '🔴 High',
            'critical': '🚨 Critical',
        }
        text = (
            '[MYTHOS ALERT]\n'
            'Agent: {agent}\n'
            'Severity: {severity}\n\n'
            '{message}\n\n'
            'Ref: {model} / {record_id}'
        ).format(
            agent     = self.agent_id.name if self.agent_id else 'Unknown',
            severity  = _SEVERITY_LABEL.get(self.severity, self.severity),
            message   = self.message or '—',
            model     = self.related_model or '—',
            record_id = self.related_id or '—',
        )

        result = bot.send_internal_message(text)
        _logger.info(
            'MythosAlert._send_to_discuss_bot: alert "%s" → Discuss bot "%s" — %s.',
            self.name, bot.name, 'posted' if result else 'FAILED',
        )
        return result

    # ────────────────────────────────────────────────────────────────────────
    # Step 4 — Telegram routing (internal log only, no external API)
    # ────────────────────────────────────────────────────────────────────────

    def _send_to_telegram(self):
        """Find the active Telegram bot for this alert's domain and create an
        outgoing mythos.telegram.message record.

        Matching rule: bot.domain_type == alert.agent_id.domain_type
                       AND bot.state == 'active'

        SAFETY (Step 4):
          - No Telegram API call, no HTTP request, no webhook interaction.
          - Only creates a mythos.telegram.message record (internal log).
          - Skips silently if no matching active bot exists.
          - Never overwrites telegram_sent=True (idempotent).
        """
        self.ensure_one()

        # Already sent — do nothing (idempotent guard)
        if self.telegram_sent:
            return self.env['mythos.telegram.message']

        domain_type = self.agent_id.domain_type if self.agent_id else False
        if not domain_type:
            _logger.debug(
                'MythosAlert._send_to_telegram: alert "%s" skipped — agent has no domain_type.',
                self.name,
            )
            return self.env['mythos.telegram.message']

        # Find first active bot in the matching domain
        bot = self.env['mythos.telegram.bot'].search([
            ('domain_type', '=', domain_type),
            ('state',       '=', 'active'),
            ('active',      '=', True),
        ], limit=1)

        if not bot:
            _logger.debug(
                'MythosAlert._send_to_telegram: alert "%s" — no active bot for domain "%s".',
                self.name, domain_type,
            )
            return self.env['mythos.telegram.message']

        # ── Format message (spec Part 3) ──────────────────────────────────────
        _SEVERITY_LABEL = {
            'low':      'Low',
            'medium':   'Medium',
            'high':     'High',
            'critical': 'Critical',
        }
        text = (
            '[ALERT]\n'
            'Agent: {agent}\n'
            'Severity: {severity}\n\n'
            'Message:\n{message}\n\n'
            'Project:\n{model} / {record_id}'
        ).format(
            agent      = self.agent_id.name if self.agent_id else 'Unknown',
            severity   = _SEVERITY_LABEL.get(self.severity, self.severity),
            message    = self.message or '—',
            model      = self.related_model or '—',
            record_id  = self.related_id or '—',
        )

        # ── Create internal message record ────────────────────────────────────
        msg = self.env['mythos.telegram.message'].create({
            'bot_id':        bot.id,
            'agent_id':      self.agent_id.id if self.agent_id else False,
            'domain_type':   domain_type,
            'direction':     'outgoing',
            'message_text':  text,
            'related_model': self.related_model,
            'related_id':    self.related_id or 0,
            'state':         'processed',
        })

        # ── Step 5: attempt real Telegram API dispatch ────────────────────────
        if bot.bot_token and bot.chat_id:
            success = bot.send_telegram_message(text)
            if success:
                msg.state = 'sent'
                _logger.info(
                    'MythosAlert._send_to_telegram: alert "%s" → Telegram SENT via bot "%s".',
                    self.name, bot.name,
                )
            else:
                msg.state = 'failed'
                _logger.warning(
                    'MythosAlert._send_to_telegram: alert "%s" → Telegram send FAILED (bot: %s).',
                    self.name, bot.name,
                )

        # Update bot's last_message_date
        bot.write({'last_message_date': fields.Datetime.now()})

        # Mark alert as sent and record which bot handled it
        self.write({
            'telegram_sent':   True,
            'telegram_bot_id': bot.id,
        })

        _logger.info(
            'MythosAlert._send_to_telegram: alert "%s" → bot "%s" (domain: %s) — message record #%d created.',
            self.name, bot.name, domain_type, msg.id,
        )
        return msg
