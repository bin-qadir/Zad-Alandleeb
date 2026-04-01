# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class TaskBoqLine(models.Model):
    _name = 'task.boq.line'
    _description = 'Task BOQ Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Description', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    task_id = fields.Many2one(
        'project.task',
        string='Task',
        domain="[('project_id', '=', project_id)]",
        ondelete='set null',
        tracking=True,
    )

    company_id = fields.Many2one(
        'res.company',
        related='project_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    division = fields.Selection([
        ('civil', 'Civil Works'),
        ('arch', 'Architectural Works'),
        ('mechanical', 'Mechanical Works'),
        ('electrical', 'Electrical Works'),
        ('plumbing', 'Plumbing Works'),
        ('hvac', 'HVAC Works'),
        ('irrigation', 'Irrigation Works'),
        ('agriculture', 'Agriculture Works'),
        ('control', 'Control & Automation'),
        ('other', 'Other'),
    ], string='Division', tracking=True)

    subdivision = fields.Char(string='Subdivision', tracking=True)

    qty = fields.Float(string='Quantity', default=1.0, tracking=True)
    product_uom_id = fields.Many2one('uom.uom', string='UoM', ondelete='restrict')

    planned_hours = fields.Float(string='Planned Hours')
    effective_hours = fields.Float(
        string='Effective Hours',
        related='task_id.effective_hours',
        readonly=True,
        store=True,
    )

    sale_price_unit = fields.Monetary(string='Sale Price Unit', tracking=True)
    sale_total = fields.Monetary(
        string='Sale Total',
        compute='_compute_sale_total',
        store=True,
    )

    material_cost = fields.Monetary(string='Material Cost', compute='_compute_costs', store=True)
    labor_cost = fields.Monetary(string='Labor Cost', compute='_compute_costs', store=True)
    overhead_cost = fields.Monetary(string='Overhead Cost', compute='_compute_costs', store=True)
    total_cost = fields.Monetary(string='Total Cost', compute='_compute_costs', store=True)

    profit_amount = fields.Monetary(string='Profit Amount', compute='_compute_profitability', store=True)
    profit_percent = fields.Float(string='Profit %', compute='_compute_profitability', store=True, digits=(16, 2))
    margin_percent = fields.Float(string='Margin %', compute='_compute_profitability', store=True, digits=(16, 2))

    procurement_state = fields.Selection([
        ('not_required', 'Not Required'),
        ('to_procure', 'To Procure'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ], string='Procurement Status', default='not_required', tracking=True)

    execution_state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Execution State', default='draft', tracking=True)

    need_review = fields.Boolean(string='Need Review', default=False, tracking=True)
    over_budget = fields.Boolean(string='Over Budget', compute='_compute_flags', store=True)
    delayed_flag = fields.Boolean(string='Delayed', compute='_compute_flags', store=True)
    is_loss_line = fields.Boolean(string='Loss Line', compute='_compute_flags', store=True)

    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain="[('customer_rank', '>', 0)]",
        ondelete='set null',
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Quotation',
        readonly=True,
        copy=False,
        ondelete='set null',
    )

    resource_line_ids = fields.One2many(
        'task.boq.resource.line',
        'boq_line_id',
        string='Resource Lines',
        copy=True,
    )

    ai_alert_ids = fields.One2many(
        'task.ai.alert',
        'boq_line_id',
        string='AI Alerts',
        readonly=True,
    )

    purchase_line_ids = fields.One2many(
        'purchase.order.line',
        'x_boq_line_id',
        string='Purchase Lines',
        readonly=True,
    )
    sale_line_ids = fields.One2many(
        'sale.order.line',
        'x_boq_line_id',
        string='Sale Lines',
        readonly=True,
    )

    rfq_count = fields.Integer(string='RFQ Count', compute='_compute_procurement_counts')
    purchase_order_count = fields.Integer(string='PO Count', compute='_compute_procurement_counts')
    sale_order_line_count = fields.Integer(string='Sale Line Count', compute='_compute_sale_order_line_count')
    alert_count = fields.Integer(string='Alert Count', compute='_compute_alert_count')

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Purchase Orders',
        compute='_compute_purchase_orders',
    )
    purchase_order_link_count = fields.Integer(
        string='Purchase Order Count',
        compute='_compute_purchase_orders',
    )

    note = fields.Text(string='Internal Notes')
    ai_note = fields.Text(string='AI Note', readonly=True)

    _sql_constraints = [
        ('task_boq_line_qty_non_negative', 'CHECK(qty >= 0)', 'Quantity must be zero or greater.'),
        ('task_boq_line_sale_price_non_negative', 'CHECK(sale_price_unit >= 0)', 'Sale price must be zero or greater.'),
    ]

    @api.depends('qty', 'sale_price_unit')
    def _compute_sale_total(self):
        for rec in self:
            rec.sale_total = rec.qty * rec.sale_price_unit

    @api.depends('resource_line_ids.total_cost', 'resource_line_ids.resource_type')
    def _compute_costs(self):
        for rec in self:
            material = labor = overhead = 0.0
            for line in rec.resource_line_ids:
                if line.resource_type == 'material':
                    material += line.total_cost
                elif line.resource_type == 'labor':
                    labor += line.total_cost
                elif line.resource_type == 'overhead':
                    overhead += line.total_cost
            rec.material_cost = material
            rec.labor_cost = labor
            rec.overhead_cost = overhead
            rec.total_cost = material + labor + overhead

    @api.depends('sale_total', 'total_cost')
    def _compute_profitability(self):
        for rec in self:
            profit = rec.sale_total - rec.total_cost
            rec.profit_amount = profit
            rec.profit_percent = (profit / rec.total_cost * 100.0) if rec.total_cost else 0.0
            rec.margin_percent = (profit / rec.sale_total * 100.0) if rec.sale_total else 0.0

    @api.depends('total_cost', 'sale_total', 'planned_hours', 'effective_hours')
    def _compute_flags(self):
        for rec in self:
            rec.over_budget = bool(rec.sale_total and rec.total_cost > rec.sale_total)
            rec.delayed_flag = bool(rec.planned_hours and rec.effective_hours > rec.planned_hours)
            rec.is_loss_line = bool(rec.sale_total and rec.total_cost > rec.sale_total)

    def _compute_procurement_counts(self):
        for rec in self:
            rfqs = rec.purchase_line_ids.mapped('order_id').filtered(lambda po: po.state in ['draft', 'sent'])
            pos = rec.purchase_line_ids.mapped('order_id').filtered(lambda po: po.state in ['purchase', 'done'])
            rec.rfq_count = len(rfqs)
            rec.purchase_order_count = len(pos)

    def _compute_sale_order_line_count(self):
        for rec in self:
            rec.sale_order_line_count = len(rec.sale_line_ids)

    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = len(rec.ai_alert_ids)

    def _compute_purchase_orders(self):
        for rec in self:
            orders = rec.purchase_line_ids.mapped('order_id')
            rec.purchase_order_ids = orders
            rec.purchase_order_link_count = len(orders)

    @api.constrains('qty')
    def _check_qty(self):
        for rec in self:
            if rec.qty < 0:
                raise ValidationError(_('Quantity cannot be negative.'))

    def action_set_draft(self):
        self.write({'execution_state': 'draft'})
        return True

    def action_submit_review(self):
        self.write({'execution_state': 'review', 'need_review': True})
        return True

    def action_approve(self):
        self.write({'execution_state': 'approved', 'need_review': False})
        return True

    def action_start(self):
        self.write({'execution_state': 'in_progress'})
        return True

    def action_done(self):
        self.write({'execution_state': 'done', 'need_review': False})
        return True

    def action_cancel(self):
        self.write({'execution_state': 'cancel'})
        return True

    def action_open_alerts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Alerts'),
            'res_model': 'task.ai.alert',
            'view_mode': 'list,form',
            'domain': [('boq_line_id', 'in', self.ids)],
            'context': {'default_boq_line_id': self.id if len(self) == 1 else False},
        }

    def action_open_purchase_lines(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Lines'),
            'res_model': 'purchase.order.line',
            'view_mode': 'list,form',
            'domain': [('x_boq_line_id', 'in', self.ids)],
        }

    def action_open_sale_lines(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Lines'),
            'res_model': 'sale.order.line',
            'view_mode': 'list,form',
            'domain': [('x_boq_line_id', 'in', self.ids)],
        }

    def action_open_purchase_orders(self):
        self.ensure_one()
        orders = self.purchase_line_ids.mapped('order_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
        }

    def _get_procurement_resource_lines(self):
        self.ensure_one()
        lines = self.resource_line_ids.filtered(lambda l: l.resource_type == 'material' and l.qty > 0)
        if not lines:
            raise UserError(_('No material resource lines found for procurement.'))
        return lines

    def action_create_rfq(self):
        self.ensure_one()

        if not self.project_id:
            raise UserError(_('Please set a project before creating RFQ.'))

        procurement_lines = self._get_procurement_resource_lines()
        vendor_map = defaultdict(lambda: self.env['task.boq.resource.line'])

        for line in procurement_lines:
            if not line.partner_id:
                raise UserError(_('Resource line "%s" has no preferred vendor.') % line.name)
            if not line.product_id:
                raise UserError(_('Resource line "%s" has no product selected.') % line.name)
            vendor_map[line.partner_id] |= line

        created_orders = self.env['purchase.order']

        for vendor, lines in vendor_map.items():
            po = self.env['purchase.order'].create({
                'partner_id': vendor.id,
                'origin': '%s - %s' % (self.project_id.name or '', self.name or ''),
                'company_id': self.company_id.id,
            })

            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': po.id,
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.display_name,
                    'product_qty': line.qty,
                    'product_uom': line.product_uom_id.id or line.product_id.uom_po_id.id or line.product_id.uom_id.id,
                    'price_unit': line.cost_price,
                    'date_planned': fields.Datetime.now(),
                    'x_boq_line_id': self.id,
                })
                line.purchase_state = 'rfq'

            created_orders |= po

        self.procurement_state = 'in_progress'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Requests for Quotation'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_orders.ids)],
        }

    def action_create_quotation(self):
        self.ensure_one()

        if not self.customer_id:
            raise UserError(_('Please set a customer first.'))
        if not self.project_id:
            raise UserError(_('Please set a project first.'))
        if self.sale_order_id:
            raise UserError(_('A quotation is already linked to this BOQ line.'))

        sale_product = self.resource_line_ids.filtered(
            lambda l: l.resource_type == 'material' and l.product_id
        )[:1].product_id

        if not sale_product:
            sale_product = self.env['product.product'].search([], limit=1)

        if not sale_product:
            raise UserError(_('No product found to create quotation line.'))

        sale_vals = {
            'partner_id': self.customer_id.id,
            'company_id': self.company_id.id,
            'origin': '%s - %s' % (self.project_id.name or '', self.name or ''),
        }

        sale_order = self.env['sale.order'].create(sale_vals)

        self.env['sale.order.line'].create({
            'order_id': sale_order.id,
            'product_id': sale_product.id,
            'name': self.name,
            'product_uom_qty': self.qty or 1.0,
            'product_uom': self.product_uom_id.id or sale_product.uom_id.id,
            'price_unit': self.sale_price_unit,
            'x_boq_line_id': self.id,
        })

        self.sale_order_id = sale_order.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotation'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }


class TaskBoqResourceLine(models.Model):
    _name = 'task.boq.resource.line'
    _description = 'Task BOQ Resource Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

    boq_line_id = fields.Many2one(
        'task.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
    )

    company_id = fields.Many2one(
        'res.company',
        related='boq_line_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='boq_line_id.currency_id',
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        'project.project',
        related='boq_line_id.project_id',
        store=True,
        readonly=True,
    )
    task_id = fields.Many2one(
        'project.task',
        related='boq_line_id.task_id',
        store=True,
        readonly=True,
    )

    resource_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('overhead', 'Overhead'),
    ], string='Resource Type', required=True, default='material')

    name = fields.Char(string='Description', required=True)
    product_id = fields.Many2one('product.product', string='Product', ondelete='restrict')
    partner_id = fields.Many2one(
        'res.partner',
        string='Preferred Vendor',
        domain="[('supplier_rank', '>', 0)]",
        ondelete='set null',
    )

    qty = fields.Float(string='Quantity', default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='UoM', ondelete='restrict')

    cost_price = fields.Monetary(string='Cost Price')
    sale_price = fields.Monetary(string='Sale Price')
    total_cost = fields.Monetary(string='Total Cost', compute='_compute_totals', store=True)
    total_sale = fields.Monetary(string='Total Sale', compute='_compute_totals', store=True)

    required_date = fields.Date(string='Required Date')
    purchase_state = fields.Selection([
        ('not_required', 'Not Required'),
        ('to_buy', 'To Buy'),
        ('rfq', 'RFQ'),
        ('po', 'Purchase Order'),
        ('received', 'Received'),
        ('cancel', 'Cancelled'),
    ], string='Purchase State', default='not_required')

    stock_qty_available = fields.Float(string='On Hand Qty', related='product_id.qty_available', readonly=True)
    stock_virtual_available = fields.Float(string='Forecast Qty', related='product_id.virtual_available', readonly=True)

    note = fields.Text(string='Notes')

    _sql_constraints = [
        ('task_boq_resource_qty_non_negative', 'CHECK(qty >= 0)', 'Resource quantity must be zero or greater.'),
        ('task_boq_resource_cost_non_negative', 'CHECK(cost_price >= 0)', 'Cost price must be zero or greater.'),
        ('task_boq_resource_sale_non_negative', 'CHECK(sale_price >= 0)', 'Sale price must be zero or greater.'),
    ]

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            if rec.product_id:
                rec.name = rec.product_id.display_name
                rec.product_uom_id = rec.product_id.uom_id.id
                rec.cost_price = rec.product_id.standard_price or 0.0
                rec.sale_price = rec.product_id.lst_price or 0.0
                if rec.resource_type == 'material':
                    rec.purchase_state = 'to_buy'

    @api.depends('qty', 'cost_price', 'sale_price')
    def _compute_totals(self):
        for rec in self:
            rec.total_cost = rec.qty * rec.cost_price
            rec.total_sale = rec.qty * rec.sale_price

    @api.constrains('qty')
    def _check_qty(self):
        for rec in self:
            if rec.qty < 0:
                raise ValidationError(_('Resource quantity cannot be negative.'))
