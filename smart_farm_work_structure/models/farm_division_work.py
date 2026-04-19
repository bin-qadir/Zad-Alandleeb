from odoo import api, fields, models


class FarmDivisionWork(models.Model):
    _name = 'farm.division.work'
    _description = 'Farm Division Work'
    _order = 'sequence, id'

    name = fields.Char(string='Name (English)', required=True)
    name_ar = fields.Char(string='الاسم (عربي)')
    code = fields.Char(string='Code')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    display_name_bilingual = fields.Char(
        string='Bilingual Label',
        compute='_compute_display_name_bilingual',
        store=True,
        help='Shows "English | Arabic" when both names are set, '
             'otherwise shows the English name only.',
    )

    @api.depends('name', 'name_ar')
    def _compute_display_name_bilingual(self):
        for rec in self:
            if rec.name_ar and rec.name_ar.strip():
                rec.display_name_bilingual = f'{rec.name}  |  {rec.name_ar.strip()}'
            else:
                rec.display_name_bilingual = rec.name or ''
