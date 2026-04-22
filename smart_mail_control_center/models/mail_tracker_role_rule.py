"""
SMART MAIL CONTROL CENTER — Role Assignment Rules
==================================================

mail.tracker.role.rule maps email types (mail_type) to responsible
users / HR departments.

When the auto-link engine classifies an email, it calls
_auto_assign_by_role() which walks the rules in sequence order,
finds the first matching mail_type, and sets assigned_user_id on the
tracker record.

Seed rules (mail_type set, user/dept empty for admin to configure):
  claim     → QS role
  invoice   → Accounting
  boq       → Estimation
  contract  → Legal
  rfq       → Procurement
  delay     → Project Manager
  approval  → Management
  variation → QS role
"""
from odoo import fields, models


class MailTrackerRoleRule(models.Model):
    """Configurable mail-type → user/department assignment rules."""

    _name = 'mail.tracker.role.rule'
    _description = 'Mail Tracker Role Assignment Rule'
    _order = 'sequence asc, id asc'

    name = fields.Char(
        string='Rule Name',
        required=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Lower sequence = higher priority.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    mail_type = fields.Selection(
        selection=[
            ('boq',       'BOQ'),
            ('claim',     'Claim'),
            ('invoice',   'Invoice'),
            ('contract',  'Contract'),
            ('variation', 'Variation Order'),
            ('rfq',       'RFQ / Quotation'),
            ('approval',  'Approval Request'),
            ('delay',     'Delay Notice / EOT'),
            ('general',   'General (Fallback)'),
        ],
        string='Email Type',
        required=True,
        index=True,
        help='The email type that triggers this rule.',
    )
    assigned_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Assign To User',
        ondelete='set null',
        help='User to assign when this mail type is detected. '
             'Leave empty to skip user assignment.',
    )
    department_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        ondelete='set null',
        help='Informational — the department responsible for this type.',
    )
    notes = fields.Text(
        string='Notes',
    )
