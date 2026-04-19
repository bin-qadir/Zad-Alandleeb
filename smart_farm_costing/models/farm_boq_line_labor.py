from odoo import api, fields, models


class FarmBoqLineLabor(models.Model):
    _name = 'farm.boq.line.labor'
    _description = 'BOQ Line Labor'
    _order = 'id'

    boq_line_id = fields.Many2one(
        comodel_name='farm.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='boq_line_id.currency_id',
        store=False,
    )
    name = fields.Char(string='Description', required=True)
    hours = fields.Float(string='Hours', default=1.0)
    cost_per_hour = fields.Float(string='Cost / Hour')
    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True,
    )

    @api.depends('hours', 'cost_per_hour')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.hours * rec.cost_per_hour
