"""
SMART MAIL CONTROL CENTER — mail.importance.rule
=================================================

Configurable classification rules applied to incoming emails.

Rules are evaluated in ascending sequence order.
The FIRST matching rule wins (no fall-through).

Matching criteria (all optional, AND logic between criteria):
  - sender_email     — substring match against sender email address
  - sender_domain    — exact domain match (e.g. "client.com")
  - subject_keywords — comma-separated list; ANY keyword must appear in subject
  - require_attachment — rule only matches if email has at least one attachment

Actions on match:
  - importance_level  — override the level on the tracker record
  - mailbox_type      — move to the specified mailbox category
  - assigned_user_id  — auto-assign to a specific Odoo user
  - department_id     — tag with a department
"""
from odoo import api, fields, models


class MailImportanceRule(models.Model):
    """Classification rule for automatic email importance assignment."""

    _name = 'mail.importance.rule'
    _description = 'Mail Importance Classification Rule'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Rule Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(
        string='Priority',
        default=10,
        help='Lower number = evaluated first. First matching rule wins.',
    )
    notes = fields.Text(string='Description / Notes')

    # ── Matching criteria ─────────────────────────────────────────────────────

    sender_email = fields.Char(
        string='Sender Email (contains)',
        help='Rule matches if this text appears anywhere in the sender email.',
    )
    sender_domain = fields.Char(
        string='Sender Domain (exact)',
        help='e.g. "client.com" — matches emails from @client.com only.',
    )
    subject_keywords = fields.Char(
        string='Subject Keywords',
        help='Comma-separated list of keywords. Rule matches if ANY keyword appears in the subject.',
    )
    require_attachment = fields.Boolean(
        string='Requires Attachment',
        help='If enabled, rule only matches emails that have at least one attachment.',
    )

    # ── Actions applied on match ──────────────────────────────────────────────

    importance_level = fields.Selection(
        selection=[
            ('very_high', 'Very High'),
            ('high',      'High'),
            ('normal',    'Normal'),
            ('low',       'Low'),
        ],
        string='Set Importance',
        required=True,
        default='high',
    )
    mailbox_type = fields.Selection(
        selection=[
            ('inbox_important', 'Important Inbox'),
            ('inbox_other',     'Other Inbox'),
            ('sent',            'Sent'),
            ('drafts',          'Drafts'),
        ],
        string='Set Mailbox Type',
        help='Optionally move matched emails to this mailbox category.',
    )
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Auto-Assign To',
        help='Automatically assign matched emails to this Odoo user.',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Tag Department',
        help='Tag matched emails with this department.',
    )

    # ── Matching logic ────────────────────────────────────────────────────────

    def _matches(self, record):
        """
        Return True if this rule matches the given mail.tracker.record.

        All active criteria must match (AND logic).
        A criterion with an empty value is ignored (not required).
        """
        self.ensure_one()

        # sender_email: substring match
        if self.sender_email:
            if not record.sender_email:
                return False
            if self.sender_email.lower() not in record.sender_email.lower():
                return False

        # sender_domain: exact domain match
        if self.sender_domain:
            if not record.sender_email:
                return False
            domain = self.sender_domain.lower().lstrip('@')
            email_lower = record.sender_email.lower()
            if not (email_lower.endswith('@' + domain) or email_lower.endswith('.' + domain)):
                return False

        # subject_keywords: ANY keyword must appear in subject
        if self.subject_keywords:
            keywords = [
                kw.strip().lower()
                for kw in self.subject_keywords.split(',')
                if kw.strip()
            ]
            subject_lower = (record.name or '').lower()
            if not any(kw in subject_lower for kw in keywords):
                return False

        # require_attachment: email must have at least one attachment
        if self.require_attachment and not record.has_attachment:
            return False

        return True

    @api.model
    def get_default_keywords(self):
        """Return the list of built-in priority keywords."""
        return [
            'urgent', 'claim', 'contract', 'invoice', 'payment',
            'approval', 'boq', 'variation', 'escalation', 'deadline',
            'overdue', 'critical', 'penalty', 'dispute', 'legal',
        ]
