from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    boq_template_id = fields.Many2one('boq.template', string='BOQ Template')
    boq_line_ids = fields.One2many('project.task.boq.line', 'task_id', string='BOQ Lines')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    material_cost_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    labor_cost_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    overhead_cost_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    total_cost_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    total_sale_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    material_cost_actual = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    labor_cost_actual = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    overhead_cost_actual = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    total_cost_actual = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    total_profit_planned = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    total_profit_actual = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    planned_margin_percent = fields.Float(compute='_compute_boq_analysis', store=True)
    actual_margin_percent = fields.Float(compute='_compute_boq_analysis', store=True)
    budget_variance = fields.Monetary(compute='_compute_boq_analysis', store=True, currency_field='currency_id')
    budget_variance_percent = fields.Float(compute='_compute_boq_analysis', store=True)
    stock_move_count = fields.Integer(compute='_compute_related_counts')
    purchase_count = fields.Integer(compute='_compute_related_counts')
    timesheet_count = fields.Integer(compute='_compute_related_counts')
    ai_alert_count = fields.Integer(compute='_compute_related_counts')

    @api.depends('boq_line_ids.total_cost_planned', 'boq_line_ids.total_sale_planned', 'boq_line_ids.total_cost_actual', 'boq_line_ids.section_type')
    def _compute_boq_analysis(self):
        for task in self:
            mp = lp = op = sp = 0.0
            ma = la = oa = 0.0
            for line in task.boq_line_ids:
                sp += line.total_sale_planned
                if line.section_type == 'material':
                    mp += line.total_cost_planned
                    ma += line.total_cost_actual
                elif line.section_type == 'labor':
                    lp += line.total_cost_planned
                    la += line.total_cost_actual
                elif line.section_type == 'overhead':
                    op += line.total_cost_planned
                    oa += line.total_cost_actual
            task.material_cost_planned = mp
            task.labor_cost_planned = lp
            task.overhead_cost_planned = op
            task.total_cost_planned = mp + lp + op
            task.total_sale_planned = sp
            task.material_cost_actual = ma
            task.labor_cost_actual = la
            task.overhead_cost_actual = oa
            task.total_cost_actual = ma + la + oa
            task.total_profit_planned = sp - task.total_cost_planned
            task.total_profit_actual = sp - task.total_cost_actual
            task.planned_margin_percent = (task.total_profit_planned / sp * 100.0) if sp else 0.0
            task.actual_margin_percent = (task.total_profit_actual / sp * 100.0) if sp else 0.0
            task.budget_variance = task.total_cost_actual - task.total_cost_planned
            task.budget_variance_percent = (task.budget_variance / task.total_cost_planned * 100.0) if task.total_cost_planned else 0.0

    def _compute_related_counts(self):
        for task in self:
            task.stock_move_count = self.env['stock.move'].search_count([('boq_task_id', '=', task.id)])
            task.purchase_count = self.env['purchase.order'].search_count([('boq_task_id', '=', task.id)])
            task.timesheet_count = self.env['account.analytic.line'].search_count([('boq_task_id', '=', task.id)])
            task.ai_alert_count = self.env['ai.controller.alert'].search_count([('task_id', '=', task.id)])

    def action_load_template(self):
        for task in self:
            if not task.boq_template_id:
                raise UserError(_('Please select a BOQ template first.'))
            task.boq_line_ids.unlink()
            vals_list = []
            for line in task.boq_template_id.line_ids:
                vals_list.append((0, 0, {
                    'sequence': line.sequence,
                    'source_template_line_id': line.id,
                    'section_type': line.section_type,
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'uom_id': line.uom_id.id,
                    'quantity_planned': line.quantity,
                    'unit_cost_planned': line.unit_cost,
                    'unit_sale_planned': line.unit_sale,
                    'waste_percent': line.waste_percent,
                    'purchase_required': line.purchase_required,
                    'vendor_id': line.vendor_id.id,
                    'employee_id': line.employee_id.id,
                    'track_in_stock': bool(line.product_id.product_tmpl_id.boq_track_in_stock),
                    'notes': line.notes,
                }))
            task.write({'boq_line_ids': vals_list})
        return True

    def action_create_rfq(self):
        PurchaseOrder = self.env['purchase.order']
        for task in self:
            lines = task.boq_line_ids.filtered(lambda l: l.section_type == 'material' and l.purchase_required and l.qty_to_procure > 0)
            if not lines:
                raise UserError(_('No material lines require procurement.'))
            vendor_map = defaultdict(list)
            for line in lines:
                vendor = line.vendor_id or line.product_id.product_tmpl_id.default_vendor_id
                if not vendor:
                    raise UserError(_('Vendor missing on line: %s') % (line.description or line.product_id.display_name))
                vendor_map[vendor.id].append(line)
            created = []
            for vendor_id, grouped_lines in vendor_map.items():
                po_vals = {'partner_id': vendor_id, 'origin': '%s / %s' % (task.project_id.display_name or '', task.display_name), 'boq_task_id': task.id, 'order_line': []}
                for line in grouped_lines:
                    po_vals['order_line'].append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.description,
                        'product_qty': line.qty_to_procure,
                        'product_uom': line.uom_id.id,
                        'price_unit': line.unit_cost_planned,
                        'date_planned': fields.Datetime.now(),
                        'x_task_boq_line_id': line.id,
                    }))
                po = PurchaseOrder.create(po_vals)
                grouped_lines.write({'purchase_order_id': po.id})
                created.append(po.id)
            return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order', 'view_mode': 'list,form', 'domain': [('id', 'in', created)]}

    def action_view_stock_moves(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.move', 'view_mode': 'list,form', 'domain': [('boq_task_id', '=', self.id)]}

    def action_view_purchases(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order', 'view_mode': 'list,form', 'domain': [('boq_task_id', '=', self.id)]}

    def action_view_timesheets(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.analytic.line', 'view_mode': 'list,form', 'domain': [('boq_task_id', '=', self.id)]}

    def action_view_ai_alerts(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'ai.controller.alert', 'view_mode': 'list,form', 'domain': [('task_id', '=', self.id)]}


class ProjectTaskBoqLine(models.Model):
    _name = 'project.task.boq.line'
    _description = 'Project Task BOQ Line'
    _order = 'sequence, id'

    task_id = fields.Many2one('project.task', required=True, ondelete='cascade')
    source_template_line_id = fields.Many2one('boq.template.line', readonly=True)
    sequence = fields.Integer(default=10)
    section_type = fields.Selection([('material', 'Material'), ('labor', 'Labor'), ('overhead', 'Overhead')], required=True)
    product_id = fields.Many2one('product.product', required=True)
    description = fields.Char(required=True)
    uom_id = fields.Many2one('uom.uom', required=True)
    quantity_planned = fields.Float(default=1.0)
    quantity_actual = fields.Float(default=0.0)
    waste_percent = fields.Float(default=0.0)
    effective_quantity_planned = fields.Float(compute='_compute_amounts', store=True)
    effective_quantity_actual = fields.Float(compute='_compute_amounts', store=True)
    unit_cost_planned = fields.Float(digits='Product Price')
    unit_cost_actual = fields.Float(digits='Product Price', compute='_compute_amounts', store=True)
    unit_sale_planned = fields.Float(digits='Product Price')
    total_cost_planned = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    total_cost_actual = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    total_sale_planned = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    purchase_required = fields.Boolean(default=False)
    vendor_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)])
    purchase_order_id = fields.Many2one('purchase.order', readonly=True)
    track_in_stock = fields.Boolean(default=False)
    stock_move_ids = fields.One2many('stock.move', 'task_boq_line_id')
    qty_reserved = fields.Float(compute='_compute_inventory', store=True)
    qty_issued = fields.Float(compute='_compute_inventory', store=True)
    qty_to_procure = fields.Float(compute='_compute_inventory', store=True)
    employee_id = fields.Many2one('hr.employee')
    timesheet_line_ids = fields.One2many('account.analytic.line', 'boq_line_id')
    timesheet_hours = fields.Float(compute='_compute_timesheet', store=True)
    labor_cost_from_timesheet = fields.Monetary(compute='_compute_timesheet', store=True, currency_field='currency_id')
    notes = fields.Text()
    currency_id = fields.Many2one(related='task_id.currency_id', store=True)

    @api.depends('quantity_planned', 'quantity_actual', 'waste_percent', 'unit_cost_planned', 'unit_sale_planned', 'stock_move_ids.price_unit', 'labor_cost_from_timesheet')
    def _compute_amounts(self):
        for rec in self:
            rec.effective_quantity_planned = rec.quantity_planned * (1.0 + (rec.waste_percent or 0.0) / 100.0)
            rec.effective_quantity_actual = rec.quantity_actual * (1.0 + (rec.waste_percent or 0.0) / 100.0)
            actual_price = rec.unit_cost_planned
            valued = [m.price_unit for m in rec.stock_move_ids if m.price_unit]
            if valued:
                actual_price = sum(valued) / len(valued)
            rec.unit_cost_actual = actual_price
            rec.total_cost_planned = rec.effective_quantity_planned * rec.unit_cost_planned
            rec.total_cost_actual = rec.labor_cost_from_timesheet if rec.section_type == 'labor' and rec.labor_cost_from_timesheet else rec.effective_quantity_actual * rec.unit_cost_actual
            rec.total_sale_planned = rec.quantity_planned * rec.unit_sale_planned

    @api.depends('effective_quantity_planned', 'stock_move_ids.product_uom_qty', 'stock_move_ids.quantity', 'stock_move_ids.state')
    def _compute_inventory(self):
        for rec in self:
            reserved = issued = 0.0
            for move in rec.stock_move_ids:
                if move.state in ('confirmed', 'assigned', 'waiting', 'partially_available'):
                    reserved += move.product_uom_qty
                if move.state == 'done':
                    issued += move.quantity
            rec.qty_reserved = reserved
            rec.qty_issued = issued
            base_qty = rec.effective_quantity_planned if rec.section_type == 'material' else 0.0
            rec.qty_to_procure = max(base_qty - issued, 0.0)

    @api.depends('timesheet_line_ids.unit_amount', 'timesheet_line_ids.amount')
    def _compute_timesheet(self):
        for rec in self:
            rec.timesheet_hours = sum(rec.timesheet_line_ids.mapped('unit_amount'))
            rec.labor_cost_from_timesheet = abs(sum(rec.timesheet_line_ids.mapped('amount')))

    def action_create_internal_issue(self):
        self.ensure_one()
        StockPicking = self.env['stock.picking']
        internal_picking_type = self.env['stock.picking.type'].search([('code', '=', 'internal'), ('warehouse_id.company_id', '=', self.task_id.company_id.id)], limit=1)
        if not internal_picking_type:
            raise UserError(_('No internal transfer operation type found.'))
        if self.section_type != 'material':
            raise UserError(_('Only material lines can create stock issues.'))
        qty = self.qty_to_procure or self.effective_quantity_planned
        if qty <= 0:
            raise UserError(_('Nothing to issue for this line.'))
        picking = StockPicking.create({'picking_type_id': internal_picking_type.id, 'location_id': internal_picking_type.default_location_src_id.id, 'location_dest_id': internal_picking_type.default_location_dest_id.id, 'origin': self.task_id.display_name, 'boq_task_id': self.task_id.id})
        self.env['stock.move'].create({'name': self.description, 'product_id': self.product_id.id, 'product_uom_qty': qty, 'product_uom': self.uom_id.id, 'location_id': picking.location_id.id, 'location_dest_id': picking.location_dest_id.id, 'picking_id': picking.id, 'boq_task_id': self.task_id.id, 'task_boq_line_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.picking', 'res_id': picking.id, 'view_mode': 'form'}
