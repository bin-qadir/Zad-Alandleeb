"""
SMART MAIL CONTROL CENTER — Email Sync Engine
=============================================

Cron-based sync from Odoo's mail.message model into mail.tracker.record.

How it works:
  1. Find all mail.message records with message_type = 'email' that have
     not yet been linked to a tracker record (via mail_message_id).
  2. Parse sender, recipient, subject, body, and attachments.
  3. Create mail.tracker.record for each new email.
  4. Immediately apply importance classification rules.

The sync window defaults to 90 days back (configurable via ir.config.parameter
  'mail_tracker.sync_days').

Duplicate prevention:
  - Primary key: mail_message_id (Odoo internal message ID)
  - Secondary key: external_message_id (RFC 2822 Message-ID header)
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Default sync window in days
_DEFAULT_SYNC_DAYS = 90
# Max emails per cron run (prevent timeouts on first install)
_BATCH_LIMIT = 200


class MailTrackerSync(models.AbstractModel):
    """Email sync engine — cron + manual scan."""

    _name = 'mail.tracker.sync'
    _description = 'Mail Tracker Sync Engine'

    # ── Cron entry point ──────────────────────────────────────────────────────

    @api.model
    def _cron_sync_emails(self):
        """Scheduled action: sync recent emails from mail.message."""
        _logger.info('Mail Tracker: starting email sync…')
        synced, skipped = self.env['mail.tracker.record']._sync_from_mail_messages()
        _logger.info('Mail Tracker: sync complete — created %d, skipped %d', synced, skipped)

    # ── Sync logic (called from cron + manual button) ─────────────────────────

    @api.model
    def _sync_from_mail_messages(self):
        """
        Scan mail.message for emails not yet in mail.tracker.record.

        Returns (created_count, skipped_count).
        """
        Tracker = self.env['mail.tracker.record']

        # Determine sync window
        try:
            sync_days = int(
                self.env['ir.config_parameter'].sudo().get_param(
                    'mail_tracker.sync_days', str(_DEFAULT_SYNC_DAYS)
                )
            )
        except (ValueError, TypeError):
            sync_days = _DEFAULT_SYNC_DAYS

        cutoff = fields.Datetime.now() - timedelta(days=sync_days)

        # IDs already tracked
        tracked_msg_ids = set(
            Tracker.search([('mail_message_id', '!=', False)])
            .mapped('mail_message_id')
            .ids
        )

        # Messages to process
        new_messages = self.env['mail.message'].sudo().search(
            [
                ('message_type', 'in', ['email', 'comment']),
                ('subtype_id.internal', '=', False),
                ('date', '>=', cutoff),
                ('id', 'not in', list(tracked_msg_ids)),
                ('email_from', '!=', False),
            ],
            order='date desc',
            limit=_BATCH_LIMIT,
        )

        created = 0
        skipped = 0

        for msg in new_messages:
            try:
                result = Tracker._create_from_mail_message(msg)
                if result:
                    created += 1
                else:
                    skipped += 1
            except Exception as exc:
                _logger.warning(
                    'Mail Tracker: failed to import message %d: %s', msg.id, exc
                )
                skipped += 1

        # Apply classification rules to all newly created 'new' records
        if created:
            new_records = Tracker.search([('state', '=', 'new')], limit=_BATCH_LIMIT)
            Tracker.apply_importance_rules(new_records)
            # Auto-link: classify type, detect project, route docs, auto-task
            new_records.run_full_auto_processing()

        return created, skipped

    # ─────────────────────────────────────────────────────────────────────────

    @api.model
    def _create_from_mail_message(self, msg):
        """
        Create a mail.tracker.record from a single mail.message.

        Returns the new record or False if skipped (duplicate).
        """
        Tracker = self.env['mail.tracker.record']

        # Duplicate check by external Message-ID
        ext_id = msg.message_id  # RFC 2822 Message-ID stored by Odoo
        if ext_id:
            existing = Tracker.search([('external_message_id', '=', ext_id)], limit=1)
            if existing:
                return False

        # Parse sender
        sender_name, sender_email = self._parse_email_address(msg.email_from or '')

        # Determine mailbox type
        mailbox_type = self._guess_mailbox_type(msg)

        # Body preview (strip HTML)
        body_preview = Tracker._strip_html(msg.body) if msg.body else ''

        # Build tracker values
        vals = {
            'name': msg.subject or msg.record_name or '(No Subject)',
            'received_date': msg.date or fields.Datetime.now(),
            'sender_name': sender_name,
            'sender_email': sender_email,
            'recipient_email': self._extract_recipient(msg),
            'mailbox_type': mailbox_type,
            'importance_level': 'normal',
            'state': 'new',
            'external_message_id': ext_id,
            'mail_message_id': msg.id,
            'body_preview': body_preview,
        }

        tracker = Tracker.create(vals)

        # Link attachments
        if msg.attachment_ids:
            tracker.attachment_ids = [(4, att.id) for att in msg.attachment_ids]

        return tracker

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_email_address(raw):
        """
        Parse 'Name <email@domain>' into (name, email).
        Falls back to (raw, raw) if no angle brackets.
        """
        if not raw:
            return '', ''
        raw = raw.strip()
        import re
        m = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', raw)
        if m:
            return m.group(1).strip(), m.group(2).strip().lower()
        # Plain email address
        if '@' in raw:
            return raw, raw.lower()
        return raw, ''

    @staticmethod
    def _guess_mailbox_type(msg):
        """
        Guess the mailbox type based on message direction indicators.

        Odoo marks outgoing emails via mail.mail with
        message_type = 'email' and a non-null mail_mail_id.
        Incoming emails don't have that link.
        """
        # If the message has an author that is an Odoo user, it's likely outgoing
        if msg.author_id and msg.author_id.user_ids:
            return 'sent'
        return 'inbox_other'

    @staticmethod
    def _extract_recipient(msg):
        """Extract the primary recipient email from partner_ids or record."""
        if msg.partner_ids:
            partner = msg.partner_ids[0]
            return partner.email or ''
        return ''


# Attach sync methods to mail.tracker.record for convenience
class MailTrackerRecordSync(models.Model):
    """Mixin: attach sync engine methods to mail.tracker.record."""

    _inherit = 'mail.tracker.record'

    @api.model
    def _sync_from_mail_messages(self):
        return self.env['mail.tracker.sync']._sync_from_mail_messages()

    @api.model
    def _create_from_mail_message(self, msg):
        return self.env['mail.tracker.sync']._create_from_mail_message(msg)

    def action_manual_scan(self):
        """Button: immediately run a sync and show result."""
        created, skipped = self._sync_from_mail_messages()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Email Sync Complete',
                'message': f'Created {created} new email records. Skipped {skipped} duplicates.',
                'type': 'success',
                'sticky': False,
            },
        }
