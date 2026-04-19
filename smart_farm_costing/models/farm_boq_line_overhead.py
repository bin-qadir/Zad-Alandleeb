from odoo import fields, models


class FarmBoqLineOverhead(models.Model):
    _name = 'farm.boq.line.overhead'
    _description = 'BOQ Line Overhead'
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
    amount = fields.Float(string='Amount')
