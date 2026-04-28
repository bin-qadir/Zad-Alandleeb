"""
mythos.telegram.bot — Mythos AI Telegram Bot Registry
======================================================
One record per Telegram bot, each scoped to a business domain.

SAFETY:
  - bot_token is NEVER written to any log line.
  - All Telegram API exceptions are caught — caller never crashes.
  - Timeout: 10 s hard limit per outbound request.
"""
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── Shared selection (mirrors mythos.agent domain_type + adds developer) ──────

DOMAIN_TYPE_BOT_SELECTION = [
    ('pre_contract',  'Pre-Contract'),
    ('contract',      'Contract'),
    ('execution',     'Execution'),
    ('financial',     'Financial'),
    ('quality_risk',  'Quality & Risk'),
    ('system',        'System'),
    ('developer',     'Developer'),
]


class MythosTelearamBot(models.Model):
    """Telegram Bot registry entry — one per business domain."""

    _name        = 'mythos.telegram.bot'
    _description = 'Mythos Telegram Bot'
    _order       = 'domain_type, name'
    _rec_name    = 'name'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Bot Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique machine-readable identifier (e.g. execution_bot).',
    )

    # ── Domain & Agent linkage ────────────────────────────────────────────────

    domain_type = fields.Selection(
        selection=DOMAIN_TYPE_BOT_SELECTION,
        string='Domain',
        required=True,
        index=True,
        tracking=True,
        help='Business domain this bot serves.',
    )
    agent_id = fields.Many2one(
        'mythos.agent',
        string='Linked Agent',
        ondelete='set null',
        index=True,
        tracking=True,
        help='Primary Mythos agent this bot channels alerts and messages for.',
    )

    # ── Telegram credentials (sensitive) ─────────────────────────────────────

    bot_token = fields.Char(
        string='Bot Token',
        copy=False,
        help=(
            'Telegram Bot API token (from @BotFather).\n'
            'NEVER logged. Visible only to system administrators.\n'
            'Leave empty until the bot is registered with Telegram.'
        ),
    )
    bot_username = fields.Char(
        string='Bot Username',
        help='Telegram username of the bot (e.g. @MythosExecutionBot).',
    )
    chat_id = fields.Char(
        string='Default Chat ID',
        help='Telegram chat_id where this bot sends default messages.',
    )
    webhook_url = fields.Char(
        string='Webhook URL',
        help='HTTPS URL registered as the Telegram webhook endpoint (deferred to Step 4+).',
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft',  'Draft'),
            ('active', 'Active'),
            ('paused', 'Paused'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
        help=(
            'Draft: bot configured but not yet enabled.\n'
            'Active: bot is operational.\n'
            'Paused: bot temporarily disabled.'
        ),
    )
    notes = fields.Text(
        string='Notes',
        help='Internal notes about this bot\'s purpose, configuration, or pending tasks.',
    )
    last_message_date = fields.Datetime(
        string='Last Message',
        readonly=True,
        copy=False,
        tracking=True,
        help='Date/time of the last message sent or received by this bot.',
    )

    # ── Messages (One2many) ───────────────────────────────────────────────────
    # NOTE: Named telegram_message_ids (not message_ids) to avoid inheriting
    # the domain [('message_type', '!=', 'user_notification')] from
    # mail.thread.message_ids, which would be applied to mythos.telegram.message
    # and raise "Invalid field mythos.telegram.message.message_type".

    telegram_message_ids = fields.One2many(
        'mythos.telegram.message',
        'bot_id',
        string='Messages',
    )
    message_count = fields.Integer(
        string='Messages',
        compute='_compute_message_count',
    )

    # ── Constraints ───────────────────────────────────────────────────────────

    _sql_constraints = [
        (
            'code_unique',
            'UNIQUE(code)',
            'Bot code must be unique across all Mythos Telegram bots.',
        ),
    ]

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends('telegram_message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.telegram_message_ids)

    # ── Actions — stat button ─────────────────────────────────────────────────

    def action_view_messages(self):
        """Open all messages for this bot."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Messages — %s') % self.name,
            'res_model': 'mythos.telegram.message',
            'view_mode': 'list,form',
            'domain':    [('bot_id', '=', self.id)],
            'context':   {'default_bot_id': self.id, 'default_domain_type': self.domain_type},
        }

    # ── Buttons ───────────────────────────────────────────────────────────────

    def action_test_connection(self):
        """Test the Telegram Bot API token using the getMe endpoint.

        Requires bot_token to be configured (chat_id is not needed here).
        On success the bot's Telegram username is auto-filled if still empty.
        On failure a danger notification is shown and a failed message record
        is created so the incident is traceable.
        """
        import requests

        self.ensure_one()

        if not self.bot_token:
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   _('Connection Test — %s') % self.name,
                    'message': _('No bot_token configured. Enter the token from @BotFather first.'),
                    'type':    'warning',
                    'sticky':  False,
                },
            }

        url = f'https://api.telegram.org/bot{self.bot_token}/getMe'
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: getMe — network error: %s. Token not logged.',
                self.code, exc,
            )
            self._create_internal_message(
                direction='outgoing',
                text='[Connection Test] FAILED — network error reaching Telegram API.',
                state='failed',
            )
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   _('Connection FAILED — %s') % self.name,
                    'message': _('Network error reaching Telegram API. Check Odoo logs for details.'),
                    'type':    'danger',
                    'sticky':  True,
                },
            }

        if response.status_code == 200 and data.get('ok'):
            result      = data.get('result', {})
            tg_name     = result.get('first_name', '?')
            tg_username = result.get('username', '?')
            _logger.info(
                'MythosBot [%s]: getMe OK — Telegram identity: %s (@%s).',
                self.code, tg_name, tg_username,
            )
            self._create_internal_message(
                direction='outgoing',
                text=f'[Connection Test] OK — Telegram bot: {tg_name} (@{tg_username})',
                state='processed',
            )
            # Auto-fill bot_username from Telegram if the field is still empty
            if not self.bot_username and tg_username:
                self.write({'bot_username': f'@{tg_username}'})
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   _('Connection OK — %s') % self.name,
                    'message': _('Telegram confirmed: %(name)s (@%(username)s)', name=tg_name, username=tg_username),
                    'type':    'success',
                    'sticky':  False,
                },
            }

        error_desc = data.get('description', 'Unknown error')
        _logger.warning(
            'MythosBot [%s]: getMe returned error — %s. Token not logged.',
            self.code, error_desc,
        )
        self._create_internal_message(
            direction='outgoing',
            text=f'[Connection Test] FAILED — Telegram error: {error_desc}',
            state='failed',
        )
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Connection FAILED — %s') % self.name,
                'message': _('Telegram API error: %s') % error_desc,
                'type':    'danger',
                'sticky':  True,
            },
        }

    def action_send_test_message(self):
        """Send a real test message to Telegram.

        Requires both bot_token and chat_id to be configured.
        Creates an internal mythos.telegram.message record (direction=outgoing)
        and attempts live delivery via the Telegram Bot API.
        The record state is set to 'sent' on success or 'failed' on error.
        """
        self.ensure_one()

        # ── Guard: credentials must be present ────────────────────────────────
        missing = []
        if not self.bot_token:
            missing.append('bot_token')
        if not self.chat_id:
            missing.append('chat_id')
        if missing:
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   _('Cannot Send — %s') % self.name,
                    'message': _('Missing required fields: %s. Configure them before sending.') % ', '.join(missing),
                    'type':    'warning',
                    'sticky':  False,
                },
            }

        domain_label = dict(DOMAIN_TYPE_BOT_SELECTION).get(self.domain_type, self.domain_type)
        text = (
            f'[Mythos AI — Test Message]\n'
            f'Bot: {self.name} ({self.code})\n'
            f'Domain: {domain_label}\n'
            f'Status: Live connection test from Odoo.'
        )

        # Create internal log record (state updated below based on API result)
        msg = self._create_internal_message(
            direction='outgoing',
            text=text,
            state='processed',
        )

        # ── Attempt real Telegram API send ────────────────────────────────────
        _logger.info(
            'MythosBot [%s]: sending real test message to chat_id=%s.',
            self.code, self.chat_id,
        )
        success = self.send_telegram_message(text)

        if success:
            msg.state = 'sent'
            _logger.info('MythosBot [%s]: test message SENT successfully.', self.code)
            return {
                'type':   'ir.actions.client',
                'tag':    'display_notification',
                'params': {
                    'title':   _('Message Sent — %s') % self.name,
                    'message': _('Test message delivered to Telegram successfully.'),
                    'type':    'success',
                    'sticky':  False,
                },
            }

        msg.state = 'failed'
        _logger.warning(
            'MythosBot [%s]: test message FAILED. Verify bot_token and chat_id. Token not logged.',
            self.code,
        )
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Send FAILED — %s') % self.name,
                'message': _('Telegram rejected the message. Verify bot_token and chat_id. See Odoo logs.'),
                'type':    'danger',
                'sticky':  True,
            },
        }

    def action_activate(self):
        """Set bot state to Active."""
        self.ensure_one()
        self.write({'state': 'active'})
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Bot Activated — %s') % self.name,
                'message': _('Bot marked as Active. Configure bot_token and chat_id before real use.'),
                'type':    'success',
                'sticky':  False,
            },
        }

    def action_pause(self):
        """Set bot state to Paused."""
        self.ensure_one()
        self.write({'state': 'paused'})
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Bot Paused — %s') % self.name,
                'message': _('Bot has been paused.'),
                'type':    'warning',
                'sticky':  False,
            },
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def send_telegram_message(self, message):
        """Send *message* to Telegram via the Bot API (Step 5).

        Returns True when the API accepted the message, False otherwise.

        SAFETY:
          - bot_token is NEVER written to any log line.
          - All network/parse exceptions are caught — never crashes the caller.
          - Timeout: 10 s hard limit per request.
        """
        import requests  # stdlib-adjacent; always available in Odoo containers

        self.ensure_one()

        if not self.bot_token or not self.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            # Log failure details without exposing the token
            _logger.warning(
                'MythosBot [%s]: Telegram API returned HTTP %s for chat_id=%s. '
                'Token not logged.',
                self.code, response.status_code, self.chat_id,
            )
            return False
        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: Telegram send failed — %s. Token not logged.',
                self.code, exc,
            )
            return False

    def _create_internal_message(self, direction, text, state='processed'):
        """Create a mythos.telegram.message record for internal tracking.
        Does NOT call any external API.
        """
        self.ensure_one()
        msg = self.env['mythos.telegram.message'].create({
            'bot_id':       self.id,
            'agent_id':     self.agent_id.id if self.agent_id else False,
            'domain_type':  self.domain_type,
            'direction':    direction,
            'message_text': text,
            'state':        state,
        })
        self.write({'last_message_date': fields.Datetime.now()})
        return msg
