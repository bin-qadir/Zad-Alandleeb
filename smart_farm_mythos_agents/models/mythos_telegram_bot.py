"""
mythos.telegram.bot — Mythos AI Telegram Bot Registry
======================================================
One record per Telegram bot, each scoped to a business domain.

SAFETY (Step 3):
  - No external API calls are made here.
  - bot_token is NEVER written to logs.
  - Buttons create internal mythos.telegram.message records only.
  - Webhook and actual Telegram API integration are deferred to later steps.
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

    message_ids = fields.One2many(
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

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

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

    # ── Buttons — NO external API calls (Step 3) ──────────────────────────────

    def action_test_connection(self):
        """Simulate a connection test — creates an internal message record only.
        No Telegram API call is made here (deferred to Step 4+).
        """
        self.ensure_one()
        _logger.info('MythosBot [%s]: connection test triggered (no external call, Step 3).', self.code)
        self._create_internal_message(
            direction='outgoing',
            text=_(
                '[Test Connection] Bot configuration check triggered from Odoo.\n'
                'Bot: %(name)s (%(code)s) | Domain: %(domain)s\n'
                'Status: Draft only — no Telegram API call (Step 3 structure only).',
                name=self.name,
                code=self.code,
                domain=dict(DOMAIN_TYPE_BOT_SELECTION).get(self.domain_type, self.domain_type),
            ),
            state='processed',
        )
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Connection Test — %s') % self.name,
                'message': _('Test logged as internal message. No external API call made (Step 3).'),
                'type':    'info',
                'sticky':  False,
            },
        }

    def action_send_test_message(self):
        """Simulate sending a test message — creates an internal record only."""
        self.ensure_one()
        _logger.info('MythosBot [%s]: send test message triggered (no external call, Step 3).', self.code)
        self._create_internal_message(
            direction='outgoing',
            text=_(
                '[Test Message] Hello from Mythos AI — %(name)s!\n'
                'This is a placeholder test message. Real sending will be enabled in Step 4+.',
                name=self.name,
            ),
            state='processed',
        )
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Test Message — %s') % self.name,
                'message': _('Test message logged internally. No real Telegram message sent (Step 3).'),
                'type':    'info',
                'sticky':  False,
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
