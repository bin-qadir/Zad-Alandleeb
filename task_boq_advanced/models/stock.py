from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    boq_task_id = fields.Many2one('project.task', string='BOQ Task', copy=False, index=True)
    task_boq_line_id = fields.Many2one('project.task.boq.line', string='Task BOQ Line', copy=False, index=True)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    boq_task_id = fields.Many2one('project.task', string='BOQ Task', copy=False, index=True)
