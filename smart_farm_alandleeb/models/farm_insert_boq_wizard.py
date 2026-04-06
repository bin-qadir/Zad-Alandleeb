# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmInsertBoqItemTemplateWizard(models.TransientModel):
    """Wizard to insert a BOQ Item Template into a field section.
    Creates a farm.boq.item record with all component lines from the template.
    """
    _name = 'farm.insert.boq.item.template.wizard'
    _description = 'Insert BOQ Item Template'

    field_id = fields.Many2one(
        'farm.field', string='Field', required=True, readonly=True,
    )
    template_id = fields.Many2one(
        'farm.boq.item.template', string='BOQ Item Template', required=True,
        domain="[('active', '=', True)]",
    )
    target_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Target Section',
        help='Leave empty to use the template default section.',
    )

    # ── Preview fields (updated on template change) ───────────────────────────
    template_section = fields.Selection(
        related='template_id.costing_section',
        string='Template Section',
    )
    template_description = fields.Text(
        related='template_id.description',
        string='Description',
    )
    template_total_cost = fields.Float(
        related='template_id.total_cost_per_item',
        string='Total Cost / Item',
    )
    template_material_total = fields.Float(
        related='template_id.material_total',
        string='Material',
    )
    template_labor_total = fields.Float(
        related='template_id.labor_total',
        string='Labor',
    )
    template_overhead_total = fields.Float(
        related='template_id.overhead_total',
        string='Overhead',
    )
    template_profit_percent = fields.Float(
        related='template_id.profit_percent',
        string='Profit %',
    )
    template_sales_price = fields.Float(
        related='template_id.total_sales_price_qty_item',
        string='Sales Price',
    )
    template_line_count = fields.Integer(
        string='Component Lines',
        compute='_compute_template_line_count',
    )

    @api.depends('template_id')
    def _compute_template_line_count(self):
        for rec in self:
            if rec.template_id:
                rec.template_line_count = len(
                    rec.template_id.line_ids.filtered(lambda l: not l.display_type)
                )
            else:
                rec.template_line_count = 0

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Auto-fill target_section from template's default section."""
        if self.template_id and not self.target_section:
            self.target_section = self.template_id.costing_section

    def action_insert(self):
        """Create farm.boq.item + farm.boq.item.line records from the template."""
        self.ensure_one()
        template = self.template_id
        section = self.target_section or template.costing_section

        boq_item = self.env['farm.boq.item'].create({
            'field_id': self.field_id.id,
            'costing_section': section,
            'name': template.name,
            'code': template.code or '',
            'description': template.description or '',
            'product_id': template.product_id.id if template.product_id else False,
            'unit_name': template.unit_name or '',
            'qty_item': template.qty_item,
            'profit_percent': template.profit_percent,
            'source_template_id': template.id,
        })

        for tl in template.line_ids.sorted('sequence'):
            self.env['farm.boq.item.line'].create({
                'boq_item_id': boq_item.id,
                'sequence': tl.sequence,
                'line_no': tl.line_no or '',
                'display_type': tl.display_type or False,
                'name': tl.description or '',
                'product_id': tl.product_id.id if tl.product_id else False,
                'unit_name': tl.unit_name or '',
                'qty_1': tl.qty_1,
                'cost_type_id': tl.cost_type_id.id if tl.cost_type_id else False,
                'cost_unit': tl.cost_unit,
            })

        return {'type': 'ir.actions.act_window_close'}
