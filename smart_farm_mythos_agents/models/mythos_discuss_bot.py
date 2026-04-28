"""
mythos.discuss.bot — Mythos Internal Discuss Bot
=================================================
Each record is an internal Discuss bot (like OdooBot) scoped to one
Mythos AI domain. Each bot owns:
  • a res.partner — its Discuss identity (avatar + name)
  • a discuss.channel — the dedicated internal channel

These bots are completely independent from Telegram.  They use
Odoo's internal messaging system only.

Step 7.
"""
import logging
from markupsafe import Markup, escape
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── Shared selection (extends existing domain_types + adds 'general') ─────────

DISCUSS_DOMAIN_SELECTION = [
    ('general',      'General'),
    ('pre_contract', 'Pre-Contract'),
    ('contract',     'Contract'),
    ('execution',    'Execution'),
    ('financial',    'Financial'),
    ('quality_risk', 'Quality & Risk'),
    ('system',       'System'),
    ('developer',    'Developer'),
]


class MythosDiscussBot(models.Model):
    """Internal Discuss bot — one per Mythos AI domain."""

    _name        = 'mythos.discuss.bot'
    _description = 'Mythos Discuss Bot'
    _order       = 'sequence, name'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Bot Name',
        required=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique machine-readable key (e.g. mythosbot_general).',
    )
    sequence = fields.Integer(default=10)

    domain_type = fields.Selection(
        selection=DISCUSS_DOMAIN_SELECTION,
        string='Domain',
        required=True,
        index=True,
    )
    agent_id = fields.Many2one(
        'mythos.agent',
        string='Linked Agent',
        ondelete='set null',
        help='The Mythos Agent whose alerts this bot surfaces in Discuss.',
    )

    # ── Discuss identity ──────────────────────────────────────────────────────

    partner_id = fields.Many2one(
        'res.partner',
        string='Bot Identity (Partner)',
        ondelete='set null',
        readonly=True,
        copy=False,
        help='The res.partner that acts as this bot in Discuss.',
    )
    channel_id = fields.Many2one(
        'discuss.channel',
        string='Discuss Channel',
        ondelete='set null',
        readonly=True,
        copy=False,
        help='Dedicated Discuss channel owned by this bot.',
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    active = fields.Boolean(default=True)
    welcome_message = fields.Text(
        string='Welcome Message',
        help='Posted once when the Discuss channel is first created.',
    )
    welcome_sent = fields.Boolean(
        string='Welcome Sent',
        default=False,
        copy=False,
        help='True once the welcome message has been posted (prevents duplicates).',
    )
    notes = fields.Text(string='Notes')

    # ── Computed helpers ──────────────────────────────────────────────────────

    channel_name = fields.Char(
        related='channel_id.name',
        string='Channel',
        readonly=True,
    )

    # ── Constraints ───────────────────────────────────────────────────────────

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Discuss bot code must be unique.'),
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # Public actions
    # ─────────────────────────────────────────────────────────────────────────

    def action_setup(self):
        """Ensure partner + channel exist; post welcome if not yet sent.

        Safe to call multiple times — all helpers are idempotent.
        """
        for bot in self:
            bot._ensure_partner()
            bot._ensure_channel()
            if bot.welcome_message and not bot.welcome_sent:
                bot._post_welcome_message()
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Discuss Bot Ready'),
                'message': _('Bot identity and channel configured successfully.'),
                'type':    'success',
                'sticky':  False,
            },
        }

    def action_open_discuss_channel(self):
        """Open the bot's channel in the Discuss sidebar."""
        self.ensure_one()
        if not self.channel_id:
            self._ensure_partner()
            self._ensure_channel()
        return {
            'type':   'ir.actions.client',
            'tag':    'mail.action_discuss',
            'params': {
                'default_active_id': f'discuss.channel_{self.channel_id.id}',
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Core posting API
    # ─────────────────────────────────────────────────────────────────────────

    def send_internal_message(self, message):
        """Post *message* to the bot's Discuss channel as the bot identity.

        Called by mythos.alert._send_to_discuss_bot() and any future
        routing code.  Never raises — returns False on any failure.
        """
        self.ensure_one()
        if not self.active:
            return False
        if not self.channel_id:
            _logger.debug(
                'MythosDiscussBot [%s]: no channel — skipping internal message.',
                self.code,
            )
            return False
        if not self.partner_id:
            self._ensure_partner()
        try:
            body = Markup('<p>%s</p>') % escape(message)
            self.channel_id.sudo().message_post(
                body=body,
                author_id=self.partner_id.id,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            _logger.info(
                'MythosDiscussBot [%s]: message posted to channel "%s".',
                self.code, self.channel_id.name,
            )
            return True
        except Exception as exc:
            _logger.warning(
                'MythosDiscussBot [%s]: failed to post message — %s',
                self.code, exc,
            )
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Class-level setup (called from XML data on every install/upgrade)
    # ─────────────────────────────────────────────────────────────────────────

    @api.model
    def _setup_all_bots(self):
        """Idempotent bootstrap — ensure every bot has a partner + channel.

        Called once per install and once per upgrade via <function> in data XML.
        Safe to run multiple times: all sub-helpers guard with early returns.
        """
        bots = self.search([])
        _logger.info('MythosDiscussBot._setup_all_bots: initialising %d bots.', len(bots))
        for bot in bots:
            try:
                bot._ensure_partner()
                bot._ensure_channel()
                if bot.welcome_message and not bot.welcome_sent:
                    bot._post_welcome_message()
            except Exception as exc:
                _logger.warning(
                    'MythosDiscussBot._setup_all_bots: error for bot "%s" — %s',
                    bot.code, exc,
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers (all idempotent)
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_partner(self):
        """Create or reuse the res.partner for this bot (idempotent)."""
        self.ensure_one()
        if self.partner_id:
            return
        ref = f'mythos_discuss_bot_{self.code}'
        partner = self.env['res.partner'].sudo().search(
            [('ref', '=', ref), ('active', 'in', [True, False])], limit=1
        )
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name':         self.name,
                'email':        f'mythosbot.{self.code}@internal.mythos',
                'ref':          ref,
                'active':       True,
                'company_type': 'person',
            })
            _logger.info(
                'MythosDiscussBot: partner created for bot "%s" (id=%d).',
                self.code, partner.id,
            )
        self.sudo().write({'partner_id': partner.id})

    def _ensure_channel(self):
        """Create or reuse the discuss.channel for this bot (idempotent)."""
        self.ensure_one()
        if self.channel_id:
            return
        # Search by a unique description key so renames don't cause duplicates
        key = f'mythos_discuss_bot_channel:{self.code}'
        channel = self.env['discuss.channel'].sudo().search(
            [('description', '=', key)], limit=1
        )
        if not channel:
            channel = self.env['discuss.channel'].sudo().create({
                'name':         self.name,
                'channel_type': 'channel',
                'description':  key,
            })
            _logger.info(
                'MythosDiscussBot: channel "%s" created (id=%d).',
                self.name, channel.id,
            )
        self.sudo().write({'channel_id': channel.id})
        # Add bot partner as channel member
        if self.partner_id:
            self._add_bot_to_channel(channel)

    def _add_bot_to_channel(self, channel):
        """Add bot partner to channel if not already a member (idempotent)."""
        existing = self.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', channel.id),
            ('partner_id', '=', self.partner_id.id),
        ], limit=1)
        if not existing:
            try:
                self.env['discuss.channel.member'].sudo().create({
                    'channel_id': channel.id,
                    'partner_id': self.partner_id.id,
                })
            except Exception as exc:
                _logger.warning(
                    'MythosDiscussBot._add_bot_to_channel: could not add partner — %s', exc
                )

    def _post_welcome_message(self):
        """Post the welcome message once and mark welcome_sent=True."""
        self.ensure_one()
        if not self.channel_id or not self.partner_id or not self.welcome_message:
            return
        try:
            body = Markup('<p>%s</p>') % escape(self.welcome_message)
            self.channel_id.sudo().message_post(
                body=body,
                author_id=self.partner_id.id,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            self.sudo().write({'welcome_sent': True})
            _logger.info(
                'MythosDiscussBot [%s]: welcome message posted to "%s".',
                self.code, self.channel_id.name,
            )
        except Exception as exc:
            _logger.warning(
                'MythosDiscussBot._post_welcome_message: error for bot "%s" — %s',
                self.code, exc,
            )
