"""
SMART MAIL CONTROL CENTER — Convert Email to Task Wizard
=========================================================

Wizard that converts a mail.tracker.record into a project.task.

Steps:
  1. User clicks "Convert to Task" on an email record
  2. This wizard opens (target: new)
  3. User selects project, deadline, priority, and responsible
  4. On confirm: create project.task, link back to email record,
     set converted_to_task = True, state = in_progress
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MailTrackerConvertTaskWizard(models.TransientModel):
    """Wizard: convert a tracked email into a project task."""

    _name = 'mail.tracker.convert.task.wizard'
    _description = 'Convert Email to Task'

    tracker_id = fields.Many2one(
        'mail.tracker.record',
        string='Email Record',
        required=True,
        ondelete='cascade',
    )

    # ── Task fields ───────────────────────────────────────────────────────────

    name = fields.Char(
        string='Task Title',
        required=True,
        help='Pre-filled with email subject. Edit as needed.',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
    )
    user_ids = fields.Many2many(
        'res.users',
        string='Assigned To',
    )
    date_deadline = fields.Date(
        string='Deadline',
    )
    priority = fields.Selection(
        selection=[('0', 'Normal'), ('1', 'High')],
        string='Priority',
        default='0',
    )
    description = fields.Html(
        string='Description',
        help='Task description. Pre-filled with email body preview.',
    )
    tag_ids = fields.Many2many(
        'project.tags',
        string='Tags',
    )

    # ── Defaults ──────────────────────────────────────────────────────────────

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tracker_id = self.env.context.get('default_tracker_id')
        if tracker_id:
            tracker = self.env['mail.tracker.record'].browse(tracker_id)
            if tracker.exists():
                body = tracker.body_preview or ''
                if body:
                    # Wrap plain text preview in HTML for the Html field
                    body = f'<p><strong>From:</strong> {tracker.sender_name or ""} &lt;{tracker.sender_email or ""}&gt;</p>' \
                           f'<p><strong>Received:</strong> {tracker.received_date}</p>' \
                           f'<hr/><p>{body}</p>'
                res.setdefault('description', body)
        return res

    # ── Confirm action ────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        tracker = self.tracker_id

        if tracker.converted_to_task and tracker.task_id:
            raise UserError(_(
                'This email is already linked to task "%s".',
                tracker.task_id.name,
            ))

        # Create the task
        task_vals = {
            'name': self.name,
            'project_id': self.project_id.id,
            'user_ids': [(6, 0, self.user_ids.ids)],
            'date_deadline': self.date_deadline,
            'priority': self.priority,
            'description': self.description or '',
            'tag_ids': [(6, 0, self.tag_ids.ids)],
        }
        task = self.env['project.task'].create(task_vals)

        # Post a note on the task referencing the original email
        task.message_post(
            body=_(
                'Task created from email: <strong>%(subject)s</strong><br/>'
                'From: %(sender)s &lt;%(email)s&gt;',
                subject=tracker.name,
                sender=tracker.sender_name or '',
                email=tracker.sender_email or '',
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        # Link attachments to the task too
        if tracker.attachment_ids:
            task.message_post(
                body=_('Attachments from original email:'),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                attachment_ids=tracker.attachment_ids.ids,
            )

        # Update the tracker record
        tracker.write({
            'converted_to_task': True,
            'task_id': task.id,
            'state': 'in_progress',
        })

        # Open the new task
        return {
            'type': 'ir.actions.act_window',
            'name': _('Task Created'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'res_id': task.id,
            'target': 'current',
        }

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
