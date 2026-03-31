from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    boq_task_id = fields.Many2one('project.task', string='BOQ Task', copy=False, readonly=True)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_task_boq_line_id = fields.Many2one('project.task.boq.line', string='Task BOQ Line', copy=False, readonly=True)
