from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    boq_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('overhead', 'Overhead'),
    ], string='BOQ Type', tracking=True)
    default_vendor_id = fields.Many2one('res.partner', string='Default Vendor', domain=[('supplier_rank', '>', 0)])
    labor_employee_id = fields.Many2one('hr.employee', string='Default Employee')
    default_waste_percent = fields.Float(string='Default Waste %')
    boq_track_in_stock = fields.Boolean(string='Track in Stock', default=False)
