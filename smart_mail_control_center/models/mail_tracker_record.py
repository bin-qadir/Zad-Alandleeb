"""
SMART MAIL CONTROL CENTER — mail.tracker.record
================================================

Central model for company email tracking, classification, and follow-up.

Each record represents one email (incoming or outgoing) that has been
captured inside Odoo.  Records are created by:
  1. The nightly cron job (_cron_sync_emails) which scans mail.message
  2. Manual "Scan Now" button from the Email Control Center menu
  3. Direct creation (manual entry / testing)

Workflow states:
  new → assigned → in_progress ↔ waiting → done
                              ↘ escalated → done
"""
import logging
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Number of calendar days before an unresolved email is flagged as overdue
_OVERDUE_DAYS = 3


class MailTrackerRecord(models.Model):
    """Company email tracking record — classification, follow-up, attachments."""

    _name = 'mail.tracker.record'
    _description = 'Mail Tracker Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'received_date desc, id desc'
    _rec_name = 'name'

    # ── Core email fields ─────────────────────────────────────────────────────

    name = fields.Char(
        string='Subject',
        required=True,
        tracking=True,
        index=True,
        default='(No Subject)',
    )
    received_date = fields.Datetime(
        string='Received / Sent Date',
        default=fields.Datetime.now,
        tracking=True,
        index=True,
    )
    sender_name = fields.Char(string='Sender Name', index=True)
    sender_email = fields.Char(string='Sender Email', index=True)
    recipient_email = fields.Char(string='Recipient Email')

    # ── Classification ────────────────────────────────────────────────────────

    mailbox_type = fields.Selection(
        selection=[
            ('inbox_important', 'Important Inbox'),
            ('inbox_other',     'Other Inbox'),
            ('sent',            'Sent'),
            ('drafts',          'Drafts'),
        ],
        string='Mailbox',
        default='inbox_other',
        tracking=True,
        index=True,
    )

    importance_level = fields.Selection(
        selection=[
            ('very_high', 'Very High'),
            ('high',      'High'),
            ('normal',    'Normal'),
            ('low',       'Low'),
        ],
        string='Importance',
        default='normal',
        tracking=True,
        index=True,
    )

    # ── Assignment ────────────────────────────────────────────────────────────

    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
        index=True,
        default=lambda self: self.env.user,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )

    # ── Related documents ─────────────────────────────────────────────────────

    project_id = fields.Many2one(
        'project.project',
        string='Related Project',
        tracking=True,
    )
    converted_to_task = fields.Boolean(
        string='Converted to Task',
        tracking=True,
    )
    task_id = fields.Many2one(
        'project.task',
        string='Linked Task',
        tracking=True,
    )

    # ── Workflow state ────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('new',         'New'),
            ('assigned',    'Assigned'),
            ('in_progress', 'In Progress'),
            ('waiting',     'Waiting Reply'),
            ('escalated',   'Escalated'),
            ('done',        'Done'),
            ('archived',    'Archived'),
        ],
        string='Status',
        default='new',
        tracking=True,
        index=True,
    )

    # ── Content ───────────────────────────────────────────────────────────────

    notes = fields.Html(string='Notes / Internal Memo')
    body_preview = fields.Text(
        string='Body Preview',
        help='First 500 characters of the email body (HTML stripped).',
    )

    # ── Duplicate tracking ────────────────────────────────────────────────────

    external_message_id = fields.Char(
        string='External Message-ID',
        index=True,
        help='RFC 2822 Message-ID header; used to prevent duplicate imports.',
    )
    mail_message_id = fields.Many2one(
        'mail.message',
        string='Source Message',
        ondelete='set null',
        index=True,
        help='The Odoo mail.message record from which this tracker was created.',
    )

    # ── Attachments ───────────────────────────────────────────────────────────

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='mail_tracker_attachment_rel',
        column1='tracker_id',
        column2='attachment_id',
        string='Files',
    )
    attachment_count = fields.Integer(
        string='Files Count',
        compute='_compute_attachment_info',
        store=True,
    )
    has_attachment = fields.Boolean(
        string='Has Files',
        compute='_compute_attachment_info',
        store=True,
    )

    # ── Status flags ──────────────────────────────────────────────────────────

    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
        help=f'True when state is open and email is older than {_OVERDUE_DAYS} days.',
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('attachment_ids')
    def _compute_attachment_info(self):
        for rec in self:
            count = len(rec.attachment_ids)
            rec.attachment_count = count
            rec.has_attachment = bool(count)

    def _compute_is_overdue(self):
        """Flag emails unresolved longer than _OVERDUE_DAYS calendar days."""
        now = fields.Datetime.now()
        open_states = {'new', 'assigned', 'in_progress', 'waiting'}
        for rec in self:
            if rec.state in open_states and rec.received_date:
                rec.is_overdue = (now - rec.received_date).days >= _OVERDUE_DAYS
            else:
                rec.is_overdue = False

    # ── State actions ─────────────────────────────────────────────────────────

    def action_assign(self):
        self.write({'state': 'assigned'})

    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_waiting_reply(self):
        self.write({'state': 'waiting'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_escalate(self):
        self.write({
            'state': 'escalated',
            'mailbox_type': 'inbox_important',
            'importance_level': 'very_high',
        })

    def action_reopen(self):
        self.write({'state': 'assigned' if self.assigned_user_id else 'new'})

    # ── Task conversion ───────────────────────────────────────────────────────

    def action_convert_to_task(self):
        self.ensure_one()
        if self.converted_to_task and self.task_id:
            raise UserError(_(
                'This email has already been converted to task "%s".',
                self.task_id.name,
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Convert Email to Task'),
            'res_model': 'mail.tracker.convert.task.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tracker_id': self.id,
                'default_name': self.name,
                'default_project_id': self.project_id.id or False,
                'default_description': self.body_preview or '',
                'default_user_ids': [self.assigned_user_id.id] if self.assigned_user_id else [],
            },
        }

    # ── Smart button actions ──────────────────────────────────────────────────

    def action_open_task(self):
        self.ensure_one()
        if not self.task_id:
            raise UserError(_('No task linked to this email yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked Task'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'res_id': self.task_id.id,
        }

    def action_open_attachments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Email Attachments'),
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    # ── Importance rule application ───────────────────────────────────────────

    @api.model
    def apply_importance_rules(self, records=None):
        """
        Apply importance rules to classify email records.

        Called automatically after sync, and available as a button action.
        Rules are evaluated in sequence order; the first match wins.
        """
        rules = self.env['mail.importance.rule'].search([], order='sequence asc, id asc')
        if not rules:
            return

        if records is None:
            records = self.search([('state', '=', 'new')])

        for record in records:
            for rule in rules:
                if rule._matches(record):
                    vals = {'importance_level': rule.importance_level}
                    if rule.mailbox_type:
                        vals['mailbox_type'] = rule.mailbox_type
                    if rule.assigned_user_id:
                        vals['assigned_user_id'] = rule.assigned_user_id.id
                        vals['state'] = 'assigned'
                    if rule.department_id:
                        vals['department_id'] = rule.department_id.id
                    record.write(vals)
                    break  # First matching rule wins

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_html(html_body):
        """Return plain text preview from HTML email body."""
        if not html_body:
            return ''
        text = re.sub(r'<[^>]+>', ' ', html_body)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]
