"""
mythos.telegram.message — Mythos AI Telegram Message Log
=========================================================
Records every Telegram message sent or received by a Mythos bot.
In Step 3 this model is populated only by internal placeholder actions.
Real webhook-based message ingestion is deferred to Step 4+.
"""
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)

# ── Shared selection (matches mythos.telegram.bot domain_type) ────────────────

DOMAIN_TYPE_MSG_SELECTION = [
    ('pre_contract',  'Pre-Contract'),
    ('contract',      'Contract'),
    ('execution',     'Execution'),
    ('financial',     'Financial'),
    ('quality_risk',  'Quality & Risk'),
    ('system',        'System'),
    ('developer',     'Developer'),
]


class MythosTelearamMessage(models.Model):
    """One record per Telegram message (incoming or outgoing) handled by a bot."""

    _name        = 'mythos.telegram.message'
    _description = 'Mythos Telegram Message'
    _order       = 'message_date desc, id desc'
    _rec_name    = 'message_text'

    # ── Bot & domain ──────────────────────────────────────────────────────────

    bot_id = fields.Many2one(
        'mythos.telegram.bot',
        string='Bot',
        ondelete='cascade',
        index=True,
        required=True,
    )
    agent_id = fields.Many2one(
        'mythos.agent',
        string='Agent',
        ondelete='set null',
        index=True,
    )
    domain_type = fields.Selection(
        selection=DOMAIN_TYPE_MSG_SELECTION,
        string='Domain',
        index=True,
    )

    # ── Direction & content ───────────────────────────────────────────────────

    direction = fields.Selection(
        selection=[
            ('incoming', 'Incoming'),
            ('outgoing', 'Outgoing'),
        ],
        string='Direction',
        required=True,
        index=True,
    )
    message_text = fields.Text(
        string='Message',
    )

    # ── Telegram context ──────────────────────────────────────────────────────

    telegram_user_id = fields.Char(
        string='Telegram User ID',
        help='Numeric Telegram user_id of the sender (incoming messages only).',
    )
    telegram_username = fields.Char(
        string='Telegram Username',
        help='@username of the sender (incoming messages only).',
    )
    chat_id = fields.Char(
        string='Chat ID',
        help='Telegram chat_id this message was sent to or received from.',
    )
    message_date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        index=True,
    )

    # ── Related Odoo record ───────────────────────────────────────────────────

    related_model = fields.Char(
        string='Related Model',
        help='Technical name of the Odoo model this message relates to.',
    )
    related_id = fields.Integer(
        string='Related Record ID',
        help='ID of the Odoo record this message relates to.',
    )

    # ── Processing state ──────────────────────────────────────────────────────
    # Step 5: 'sent' added — message was dispatched to Telegram API successfully.

    state = fields.Selection(
        selection=[
            ('received',  'Received'),
            ('processed', 'Processed'),
            ('sent',      'Sent'),
            ('failed',    'Failed'),
        ],
        string='State',
        default='received',
        required=True,
        index=True,
    )
    error_message = fields.Text(
        string='Error',
        help='Error details if processing failed.',
    )
