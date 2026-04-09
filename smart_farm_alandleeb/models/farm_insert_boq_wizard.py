# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmInsertBoqItemTemplateWizard(models.TransientModel):
    """Wizard to insert a BOQ Item Template into a field costing workspace.

    Creates:
      1. A parent farm.cost.line (is_boq_item=True) acting as the BOQ item
         header in the costing workspace, with totals rolled up from children.
      2. One child farm.cost.line per normal template component line, linked
         to the parent via boq_parent_id.
      3. A farm.boq.item record (with count_in_cost_total=False) for
         downstream RFQ / task-creation workflows.
      4. farm.boq.item.line records copied from the template.

    Editing the child cost lines (qty, unit cost, description) is per-field
    and does NOT affect the original template.
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
        string='Works Division',
        required=True,
        help='Works Division this BOQ item will be placed in.',
    )

    # ── Placement inside the cost line hierarchy ──────────────────────────────
    parent_section_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Division Line',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_section')]",
        help='Optional: place the BOQ item under this section header.',
    )
    parent_subsection_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Sub-division Line',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_subsection')]",
        help='Optional: place the BOQ item under this sub-section header.',
    )

    # ── Preview fields (updated on template change) ───────────────────────────
    template_section = fields.Selection(
        related='template_id.costing_section',
        string='Template Division',
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
        """Insert template into the costing workspace as parent + child cost lines."""
        self.ensure_one()
        template = self.template_id
        section = self.target_section or template.costing_section
        field_id = self.field_id.id

        # ── 1. Create the parent cost.line (BOQ item header) ─────────────────
        parent_line = self.env['farm.cost.line'].create({
            'field_id': field_id,
            'costing_section': section,
            'name': template.name,
            'work_type_id': template.work_type_id.id if template.work_type_id else False,
            'is_boq_item': True,
            'is_manual_item': False,
            'source_template_id': template.id,
            'profit_percent': template.profit_percent,
            'parent_section_id': self.parent_section_id.id if self.parent_section_id else False,
            'parent_subsection_id': self.parent_subsection_id.id if self.parent_subsection_id else False,
        })

        # ── 2. Create child cost.line for each normal template component ──────
        for tl in template.line_ids.filtered(lambda l: not l.display_type).sorted('sequence'):
            self.env['farm.cost.line'].create({
                'field_id': field_id,
                'costing_section': section,
                'boq_parent_id': parent_line.id,
                'sequence': tl.sequence,
                'name': tl.description or '',
                'product_id': tl.product_id.id if tl.product_id else False,
                'cost_type_id': tl.cost_type_id.id if tl.cost_type_id else False,
                'quantity': tl.qty_1 or 1.0,
                'unit_cost': tl.cost_unit,
                'is_manual_item': False,
                'source_template_id': template.id,
            })

        # ── 3. Create farm.boq.item (count_in_cost_total=False) ───────────────
        boq_item = self.env['farm.boq.item'].create({
            'field_id': field_id,
            'costing_section': section,
            'name': template.name,
            'code': template.code or '',
            'description': template.description or '',
            'product_id': template.product_id.id if template.product_id else False,
            'unit_name': template.unit_name or '',
            'qty_item': template.qty_item,
            'profit_percent': template.profit_percent,
            'source_template_id': template.id,
            'work_type_id': template.work_type_id.id if template.work_type_id else False,
            'count_in_cost_total': False,
        })

        # ── 4. Create farm.boq.item.line records ──────────────────────────────
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
