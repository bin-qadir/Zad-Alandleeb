# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmCostLineInsertWizard(models.TransientModel):
    """Wizard to insert a BOQ Item Template as a cost line in the All Costing Sheet.

    Creates a single farm.cost.line from the chosen template using the template's
    total_cost_per_item as the unit_cost and the wizard's quantity as the line qty.
    """
    _name = 'farm.cost.line.insert.wizard'
    _description = 'Insert BOQ Template into Costing Sheet'

    field_id = fields.Many2one(
        'farm.field', string='Field', required=True, readonly=True,
    )
    template_id = fields.Many2one(
        'farm.boq.item.template', string='BOQ Item Template', required=True,
        domain="[('active', '=', True)]",
    )
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Works Division',
        required=True,
        default='other',
    )
    work_type_id = fields.Many2one(
        'farm.boq.work.type',
        string='Sub-division Works',
        ondelete='set null',
        domain="[('costing_section', '=', costing_section), ('active', '=', True)]",
    )
    parent_section_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Works Division',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_section')]",
        ondelete='set null',
    )
    parent_subsection_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Sub-division',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_subsection')]",
        ondelete='set null',
    )
    quantity = fields.Float(string='Quantity', digits=(16, 3), default=1.0, required=True)

    # ── Template preview (read-only) ──────────────────────────────────────────
    template_description = fields.Text(
        related='template_id.description', string='Description',
    )
    template_unit_cost = fields.Float(
        related='template_id.total_cost_per_item', string='Unit Cost (from Template)',
    )
    template_material_total = fields.Float(
        related='template_id.material_total', string='Material',
    )
    template_labor_total = fields.Float(
        related='template_id.labor_total', string='Labor',
    )
    template_overhead_total = fields.Float(
        related='template_id.overhead_total', string='Overhead',
    )
    template_line_count = fields.Integer(
        string='Component Lines', compute='_compute_template_line_count',
    )

    @api.depends('template_id')
    def _compute_template_line_count(self):
        for rec in self:
            rec.template_line_count = len(
                rec.template_id.line_ids.filtered(lambda l: not l.display_type)
            ) if rec.template_id else 0

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Auto-fill section and work type from template defaults."""
        if not self.template_id:
            return
        tpl = self.template_id
        self.costing_section = tpl.costing_section
        if tpl.work_type_id:
            self.work_type_id = tpl.work_type_id
        else:
            self.work_type_id = False

    @api.onchange('costing_section')
    def _onchange_costing_section(self):
        if self.work_type_id and self.work_type_id.costing_section != self.costing_section:
            self.work_type_id = False

    @api.onchange('parent_subsection_id')
    def _onchange_parent_subsection_id(self):
        """Auto-fill parent_section_id from the chosen subsection."""
        if self.parent_subsection_id and self.parent_subsection_id.parent_section_id:
            self.parent_section_id = self.parent_subsection_id.parent_section_id
            if self.parent_subsection_id.costing_section:
                self.costing_section = self.parent_subsection_id.costing_section

    def action_insert(self):
        """Create one farm.cost.line from the selected template."""
        self.ensure_one()
        tpl = self.template_id
        section = self.costing_section or tpl.costing_section

        self.env['farm.cost.line'].create({
            'field_id': self.field_id.id,
            'costing_section': section,
            'work_type_id': (self.work_type_id.id
                             or (tpl.work_type_id.id if tpl.work_type_id else False)),
            'name': tpl.name,
            'product_id': tpl.product_id.id if tpl.product_id else False,
            'quantity': self.quantity,
            'unit_cost': tpl.total_cost_per_item,
            'source_template_id': tpl.id,
            'parent_section_id': self.parent_section_id.id if self.parent_section_id else False,
            'parent_subsection_id': self.parent_subsection_id.id if self.parent_subsection_id else False,
        })

        return {'type': 'ir.actions.act_window_close'}
