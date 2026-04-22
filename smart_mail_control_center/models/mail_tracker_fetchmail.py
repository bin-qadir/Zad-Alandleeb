"""
SMART MAIL CONTROL CENTER — Fetchmail Server Integration
=========================================================

Extends fetchmail.server with a Mail Tracker toggle.
After every successful email fetch, triggers our sync engine
so that new mail.message records are immediately converted to
mail.tracker.record entries.

Also implements message_new() on mail.tracker.record so that
users can point a fetchmail server directly at this model
(Settings → Technical → Incoming Mail Servers → Create New Record Model).
"""
import logging
from email.utils import parseaddr

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FetchmailServerTracker(models.Model):
    """Extend fetchmail.server: trigger mail tracker sync after each fetch."""

    _inherit = 'fetchmail.server'

    enable_mail_tracker = fields.Boolean(
        string='Enable Mail Tracker',
        default=True,
        help=(
            'When enabled, every email fetched by this server will be '
            'automatically captured as a Mail Tracker record.'
        ),
    )

    def fetch_mail(self, raise_exception=True):
        """Override: run tracker sync immediately after each mail fetch."""
        result = super().fetch_mail(raise_exception=raise_exception)
        # Sync only for servers with tracker enabled
        if any(s.enable_mail_tracker for s in self):
            try:
                _logger.info('Mail Tracker: post-fetch sync triggered by fetchmail server.')
                created, skipped = self.env['mail.tracker.sync'].sudo()._sync_from_mail_messages()
                _logger.info(
                    'Mail Tracker: post-fetch sync — created %d, skipped %d.',
                    created, skipped,
                )
            except Exception as exc:
                _logger.warning('Mail Tracker: post-fetch sync failed: %s', exc)
        return result


class MailTrackerRecordMessageNew(models.Model):
    """
    Extend mail.tracker.record with proper message_new() implementation.

    When a fetchmail server is configured to route to 'mail.tracker.record'
    (Settings → Incoming Mail Servers → select this model), Odoo calls
    message_new() for every fetched email.  This implementation parses the
    raw email dict and populates all tracker fields properly.
    """

    _inherit = 'mail.tracker.record'

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """
        Create a tracker record from a raw incoming email.

        Called by Odoo's mail routing when a fetchmail server is configured
        to create new mail.tracker.record objects.
        """
        email_from = msg_dict.get('email_from', '') or ''
        sender_name, sender_email = parseaddr(email_from)
        if not sender_name:
            sender_name = sender_email

        # Body preview (strip HTML)
        body_preview = self._strip_html(msg_dict.get('body', '') or '')[:500]

        # Received date
        date_val = msg_dict.get('date') or fields.Datetime.now()

        # Duplicate check: if we already have a record with this Message-ID, skip
        ext_id = msg_dict.get('message_id', '') or ''
        if ext_id:
            existing = self.search([('external_message_id', '=', ext_id)], limit=1)
            if existing:
                _logger.info(
                    'Mail Tracker: skipping duplicate message_id %s (tracker %d exists)',
                    ext_id, existing.id,
                )
                return existing

        values = dict(custom_values or {})
        values.setdefault('name', msg_dict.get('subject') or '(No Subject)')
        values.setdefault('received_date', date_val)
        values.setdefault('sender_name', sender_name)
        values.setdefault('sender_email', sender_email.lower())
        values.setdefault('recipient_email', msg_dict.get('to', '') or '')
        values.setdefault('external_message_id', ext_id)
        values.setdefault('body_preview', body_preview)
        values.setdefault('mailbox_type', 'inbox_other')
        values.setdefault('importance_level', 'normal')
        values.setdefault('state', 'new')

        record = super().message_new(msg_dict, custom_values=values)

        # Immediately apply importance classification
        try:
            self.apply_importance_rules(record)
        except Exception as exc:
            _logger.warning(
                'Mail Tracker: importance rule apply failed for record %d: %s',
                record.id, exc,
            )

        return record

    @api.model
    def message_update(self, msg_dict, update_vals=None):
        """
        Called when an email is a reply to an existing tracker thread.
        Update the state to 'new' if previously done (re-opens the conversation).
        """
        vals = update_vals or {}
        for rec in self:
            if rec.state == 'done':
                vals['state'] = 'assigned' if rec.assigned_user_id else 'new'
        return super().message_update(msg_dict, update_vals=vals)
