from odoo import fields, models
from odoo.exceptions import UserError


class FarmBoqPrintWizard(models.TransientModel):
    """Print wizard for Project Cost Structure.

    Dispatches to a dedicated, self-contained report template per mode.
    No ``data`` dict is passed — each QWeb template is autonomous and the
    Odoo 18 render pipeline cannot silently drop the mode selector.

    Selection value  → report action xmlid
    ----------------------------------------
    full             → smart_farm_boq.action_report_boq_full
    details          → smart_farm_boq.action_report_boq_details
    division_summary → smart_farm_boq.action_report_boq_division_summary
    overall_summary  → smart_farm_boq.action_report_boq_overall_summary
    """

    _name = 'farm.boq.print.wizard'
    _description = 'Print Wizard — Project Cost Structure'

    boq_id = fields.Many2one(
        comodel_name='farm.boq',
        string='Project Cost Structure',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    report_type = fields.Selection(
        selection=[
            ('full',             'Full Report | التقرير الكامل'),
            ('details',          'Details Only | التقرير التفصيلي فقط'),
            ('division_summary', 'Division + Subdivision Summary | تجميع الأقسام مع الفروع'),
            ('overall_summary',  'Overall Summary Only | التجميع النهائي فقط'),
        ],
        string='Report Mode',
        default='full',
        required=True,
    )

    def action_print(self):
        self.ensure_one()

        boq = self.env['farm.boq'].browse(self._context.get('active_id'))

        if not boq:
            raise UserError("No BOQ record found")

        if self.report_type == 'full':
            xmlid = 'smart_farm_boq.action_report_boq_full'
        elif self.report_type == 'details':
            xmlid = 'smart_farm_boq.action_report_boq_details'
        elif self.report_type == 'division_summary':
            xmlid = 'smart_farm_boq.action_report_boq_division_summary'
        elif self.report_type == 'overall_summary':
            xmlid = 'smart_farm_boq.action_report_boq_overall_summary'
        else:
            raise UserError("Invalid report type")

        report = self.env.ref(xmlid)

        return report.report_action(boq)
