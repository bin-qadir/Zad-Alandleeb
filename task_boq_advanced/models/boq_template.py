from odoo import api, fields, models


class BoqTemplate(models.Model):
    _name = 'boq.template'
    _description = 'BOQ Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(default='New', copy=False)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    division_works = fields.Selection([
        ('civil', 'Civil Works'),
        ('architectural', 'Architectural Works'),
        ('mechanical', 'Mechanical Works'),
        ('electrical', 'Electrical Works'),
        ('plumbing', 'Plumbing Works'),
        ('irrigation', 'Irrigation Works'),
        ('general', 'General Works'),
    ], default='general', required=True)
    subdivision = fields.Char()
    description = fields.Text()
    note = fields.Text()
    line_ids = fields.One2many('boq.template.line', 'template_id', string='Lines')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)
    material_cost_total = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    labor_cost_total = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    overhead_cost_total = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    grand_total_cost = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    grand_total_sale = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    expected_profit = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    profit_margin_percent = fields.Float(compute='_compute_totals', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = seq.next_by_code('boq.template') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.total_cost', 'line_ids.total_sale', 'line_ids.section_type')
    def _compute_totals(self):
        for rec in self:
            material = labor = overhead = sale = 0.0
            for line in rec.line_ids:
                sale += line.total_sale
                if line.section_type == 'material':
                    material += line.total_cost
                elif line.section_type == 'labor':
                    labor += line.total_cost
                elif line.section_type == 'overhead':
                    overhead += line.total_cost
            rec.material_cost_total = material
            rec.labor_cost_total = labor
            rec.overhead_cost_total = overhead
            rec.grand_total_cost = material + labor + overhead
            rec.grand_total_sale = sale
            rec.expected_profit = rec.grand_total_sale - rec.grand_total_cost
            rec.profit_margin_percent = (rec.expected_profit / rec.grand_total_sale * 100.0) if rec.grand_total_sale else 0.0


class BoqTemplateLine(models.Model):
    _name = 'boq.template.line'
    _description = 'BOQ Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one('boq.template', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    section_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('overhead', 'Overhead'),
    ], required=True, default='material')
    product_id = fields.Many2one('product.product', required=True)
    description = fields.Char(required=True)
    uom_id = fields.Many2one('uom.uom', required=True)
    quantity = fields.Float(default=1.0)
    waste_percent = fields.Float(default=0.0)
    effective_quantity = fields.Float(compute='_compute_amounts', store=True)
    unit_cost = fields.Float(digits='Product Price', required=True)
    unit_sale = fields.Float(digits='Product Price', required=True)
    total_cost = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    total_sale = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    purchase_required = fields.Boolean(default=False)
    vendor_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)])
    employee_id = fields.Many2one('hr.employee', string='Default Employee')
    currency_id = fields.Many2one(related='template_id.currency_id', store=True)
    notes = fields.Text()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            p = rec.product_id
            if not p:
                continue
            rec.description = p.display_name
            rec.uom_id = p.uom_po_id.id or p.uom_id.id
            rec.section_type = p.product_tmpl_id.boq_type or rec.section_type
            rec.unit_cost = p.standard_price
            rec.unit_sale = p.lst_price
            rec.vendor_id = p.product_tmpl_id.default_vendor_id
            rec.employee_id = p.product_tmpl_id.labor_employee_id
            rec.waste_percent = p.product_tmpl_id.default_waste_percent
            rec.purchase_required = rec.section_type == 'material'

    @api.depends('quantity', 'waste_percent', 'unit_cost', 'unit_sale')
    def _compute_amounts(self):
        for rec in self:
            rec.effective_quantity = rec.quantity * (1.0 + (rec.waste_percent or 0.0) / 100.0)
            rec.total_cost = rec.effective_quantity * rec.unit_cost
            rec.total_sale = rec.quantity * rec.unit_sale
