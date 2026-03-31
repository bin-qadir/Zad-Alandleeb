from base64 import b64encode
from io import BytesIO
import calendar
import datetime
import xlsxwriter
from odoo import api, fields, models


class BoqDashboardMailConfig(models.Model):
    _name = 'boq.dashboard.mail.config'
    _description = 'BOQ Dashboard Mail Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default='Management Dashboard Snapshot', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    recipient_ids = fields.Many2many('res.partner', string='Recipients')
    project_ids = fields.Many2many('project.project', string='Projects Filter')
    date_scope = fields.Selection([('all', 'All'), ('today', 'Today'), ('this_week', 'This Week'), ('this_month', 'This Month')], default='all', required=True)
    attach_excel = fields.Boolean(default=True)
    attach_pdf = fields.Boolean(default=True)
    subject = fields.Char(default='BOQ Dashboard Snapshot')
    note = fields.Html()
    last_sent_at = fields.Datetime(readonly=True)
    last_sent_count = fields.Integer(readonly=True)

    def _get_date_range(self):
        self.ensure_one()
        today = fields.Date.today()
        if self.date_scope == 'today':
            return today, today
        if self.date_scope == 'this_week':
            start = today - datetime.timedelta(days=today.weekday())
            return start, start + datetime.timedelta(days=6)
        if self.date_scope == 'this_month':
            start = today.replace(day=1)
            return start, today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return False, False

    def _build_excel_bytes(self, company_id=None, project_ids=None, date_from=None, date_to=None):
        domain = [('company_id', '=', company_id or self.company_id.id)]
        if project_ids:
            domain.append(('project_id', 'in', project_ids))
        if date_from:
            domain.append(('date_deadline', '>=', date_from))
        if date_to:
            domain.append(('date_deadline', '<=', date_to))
        records = self.env['boq.dashboard.report'].sudo().search(domain)
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Dashboard')
        head = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1})
        txt = workbook.add_format({'border': 1})
        num = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        headers = ['Project', 'Task', 'Stage', 'Deadline', 'Planned Cost', 'Actual Cost', 'Variance', 'Planned Profit', 'Actual Profit', 'AI Alerts']
        for col, header in enumerate(headers):
            ws.write(0, col, header, head)
        row = 1
        for rec in records:
            values = [rec.project_id.display_name if rec.project_id else '', rec.task_id.display_name if rec.task_id else '', rec.stage_id.name if rec.stage_id else '', str(rec.date_deadline or ''), rec.total_cost_planned, rec.total_cost_actual, rec.budget_variance, rec.total_profit_planned, rec.total_profit_actual, rec.ai_alert_count]
            for col, value in enumerate(values):
                ws.write(row, col, value, num if isinstance(value, (int, float)) else txt)
            row += 1
        workbook.close(); output.seek(0)
        return output.read()

    def action_send_snapshot_email(self):
        report_action = self.env.ref('task_boq_dashboard_owl.action_report_boq_dashboard_snapshot')
        template = self.env.ref('task_boq_dashboard_owl.mail_template_boq_dashboard_snapshot')
        Attachment = self.env['ir.attachment'].sudo()
        for rec in self:
            date_from, date_to = rec._get_date_range()
            project_ids = rec.project_ids.ids
            attachments = []
            if rec.attach_pdf:
                pdf_bytes, _ = report_action._render_qweb_pdf([], data={'company_id': rec.company_id.id, 'project_id': project_ids[0] if len(project_ids) == 1 else False, 'date_from': str(date_from) if date_from else False, 'date_to': str(date_to) if date_to else False})
                attachments.append(Attachment.create({'name': 'boq_dashboard_snapshot.pdf', 'type': 'binary', 'datas': b64encode(pdf_bytes), 'mimetype': 'application/pdf'}).id)
            if rec.attach_excel:
                excel_bytes = rec._build_excel_bytes(rec.company_id.id, project_ids, date_from, date_to)
                attachments.append(Attachment.create({'name': 'boq_dashboard_snapshot.xlsx', 'type': 'binary', 'datas': b64encode(excel_bytes), 'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}).id)
            template.with_context(dashboard_config_name=rec.name, dashboard_scope=rec.date_scope, dashboard_note=rec.note or '').send_mail(rec.id, force_send=True, email_values={'email_to': ','.join(rec.recipient_ids.mapped('email')), 'attachment_ids': [(6, 0, attachments)]})
            rec.last_sent_at = fields.Datetime.now()
            rec.last_sent_count = len(rec.recipient_ids.filtered(lambda r: r.email))
        return True

    @api.model
    def cron_send_dashboard_snapshots(self):
        self.search([('active', '=', True)]).action_send_snapshot_email()
        return True
