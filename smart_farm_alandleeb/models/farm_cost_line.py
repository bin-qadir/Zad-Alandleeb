# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmCostLine(models.Model):
    _name = 'farm.cost.line'
    _description = 'Farm Cost Line'
    _order = 'field_id, costing_section, sequence, id'

    field_id = fields.Many2one(
        'farm.field', string='Field', required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # ── Line type ─────────────────────────────────────────────────────────────
    # False           = normal costing item (default, Odoo convention)
    # line_section    = Works Division header
    # line_subsection = Sub-division Works header
    # line_note       = free-text note (kept for backward compat)
    display_type = fields.Selection([
        ('line_section',    'Works Division'),
        ('line_subsection', 'Sub-division Works'),
        ('line_note',       'Note'),
    ], default=False, string='Display Type')

    # ── Hierarchy parents ─────────────────────────────────────────────────────
    parent_section_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Division',
        ondelete='set null',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_section')]",
        index=True,
    )
    parent_subsection_id = fields.Many2one(
        'farm.cost.line',
        string='Parent Sub-division',
        ondelete='set null',
        domain="[('field_id', '=', field_id), ('display_type', '=', 'line_subsection')]",
        index=True,
    )

    # ── Auto-numbering ────────────────────────────────────────────────────────
    sequence_no = fields.Char(
        string='No.',
        compute='_compute_sequence_no',
        store=True,
        help='Auto-generated position number (01 / 01.02 / 01.02.03)',
    )

    # ── Classification ────────────────────────────────────────────────────────
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

    # ── Item fields (normal lines only) ──────────────────────────────────────
    name = fields.Char(string='Description')
    product_id = fields.Many2one(
        'product.product', string='Product', ondelete='restrict',
    )
    cost_type_id = fields.Many2one(
        'farm.cost.type', string='Cost Type', ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', digits=(16, 3), default=1.0)
    unit_cost = fields.Float(string='Unit Cost', digits=(16, 2))
    total_cost = fields.Float(
        string='Total Cost', digits=(16, 2),
        compute='_compute_total_cost', store=True,
    )

    # ── Category mirror ───────────────────────────────────────────────────────
    cost_category = fields.Selection(
        related='cost_type_id.category',
        string='Category',
        store=False,
    )

    # =========================================================================
    # COMPUTED — total cost
    # =========================================================================

    @api.depends('quantity', 'unit_cost', 'display_type')
    def _compute_total_cost(self):
        for rec in self:
            # Header rows (section / subsection / note) carry no cost
            if rec.display_type:
                rec.total_cost = 0.0
            else:
                rec.total_cost = rec.quantity * rec.unit_cost

    # =========================================================================
    # COMPUTED — hierarchical sequence number
    # =========================================================================

    @api.depends(
        'display_type', 'sequence',
        'parent_section_id', 'parent_section_id.sequence_no',
        'parent_subsection_id', 'parent_subsection_id.sequence_no',
        'field_id.cost_line_ids.display_type',
        'field_id.cost_line_ids.sequence',
        'field_id.cost_line_ids.parent_section_id',
        'field_id.cost_line_ids.parent_subsection_id',
    )
    def _compute_sequence_no(self):
        for rec in self:
            rec.sequence_no = rec._get_sequence_no()

    def _get_sequence_no(self):
        if not self.field_id:
            return ''

        all_lines = self.field_id.cost_line_ids

        if self.display_type == 'line_section':
            peers = all_lines.filtered(
                lambda l: l.display_type == 'line_section'
            ).sorted(lambda l: (l.sequence, l.id))
            idx = list(peers.ids).index(self.id) + 1 if self.id in peers.ids else len(peers) + 1
            return f'{idx:02d}'

        if self.display_type == 'line_subsection':
            if not self.parent_section_id:
                return ''
            peers = all_lines.filtered(
                lambda l: l.display_type == 'line_subsection'
                and l.parent_section_id == self.parent_section_id
            ).sorted(lambda l: (l.sequence, l.id))
            idx = list(peers.ids).index(self.id) + 1 if self.id in peers.ids else len(peers) + 1
            parent_no = self.parent_section_id.sequence_no or '??'
            return f'{parent_no}.{idx:02d}'

        # Normal line
        if not self.display_type:
            if not self.parent_subsection_id:
                return ''
            peers = all_lines.filtered(
                lambda l: not l.display_type
                and l.parent_subsection_id == self.parent_subsection_id
            ).sorted(lambda l: (l.sequence, l.id))
            idx = list(peers.ids).index(self.id) + 1 if self.id in peers.ids else len(peers) + 1
            parent_no = self.parent_subsection_id.sequence_no or '??'
            return f'{parent_no}.{idx:02d}'

        return ''

    # =========================================================================
    # ONCHANGES
    # =========================================================================

    @api.onchange('parent_section_id')
    def _onchange_parent_section_id(self):
        """Inherit costing_section from parent section."""
        if self.parent_section_id and self.parent_section_id.costing_section:
            self.costing_section = self.parent_section_id.costing_section
        # Clear subsection if it no longer belongs to this section
        if self.parent_subsection_id and \
                self.parent_subsection_id.parent_section_id != self.parent_section_id:
            self.parent_subsection_id = False

    @api.onchange('parent_subsection_id')
    def _onchange_parent_subsection_id(self):
        """Inherit section from parent subsection and auto-set parent_section_id."""
        if not self.parent_subsection_id:
            return
        sub = self.parent_subsection_id
        if sub.parent_section_id:
            self.parent_section_id = sub.parent_section_id
        if sub.costing_section:
            self.costing_section = sub.costing_section

    @api.onchange('costing_section')
    def _onchange_costing_section(self):
        """Clear work_type when section changes so domain is respected."""
        if self.work_type_id and self.work_type_id.costing_section != self.costing_section:
            self.work_type_id = False

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        """Auto-fill costing_section from selected work type."""
        if self.work_type_id and self.work_type_id.costing_section:
            if not self.costing_section or self.costing_section != self.work_type_id.costing_section:
                self.costing_section = self.work_type_id.costing_section

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-fill cost_type_id from product's default cost type when available."""
        if not self.product_id:
            return
        product_tmpl = self.product_id.product_tmpl_id
        if hasattr(product_tmpl, 'cost_type_id') and product_tmpl.cost_type_id:
            self.cost_type_id = product_tmpl.cost_type_id

    @api.onchange('cost_type_id')
    def _onchange_cost_type_id(self):
        """Auto-fill costing_section from selected cost type."""
        if self.cost_type_id and self.cost_type_id.costing_section:
            self.costing_section = self.cost_type_id.costing_section

    # =========================================================================
    # CREATE / DEFAULTS
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context

        # Section default from context (per-section tabs)
        if 'costing_section' in fields_list and not res.get('costing_section'):
            section = ctx.get('default_costing_section')
            if section:
                res['costing_section'] = section

        display_type = res.get('display_type') or ctx.get('default_display_type') or False
        field_id = res.get('field_id') or ctx.get('default_field_id')

        if field_id and display_type != 'line_section':
            # Auto-link subsection to the last section in the field
            if display_type == 'line_subsection' and 'parent_section_id' not in res:
                last_sec = self.search([
                    ('field_id', '=', field_id),
                    ('display_type', '=', 'line_section'),
                ], order='sequence desc, id desc', limit=1)
                if last_sec:
                    res['parent_section_id'] = last_sec.id

            # Auto-link normal line to the last subsection in the field
            if not display_type and 'parent_subsection_id' not in res:
                last_sub = self.search([
                    ('field_id', '=', field_id),
                    ('display_type', '=', 'line_subsection'),
                ], order='sequence desc, id desc', limit=1)
                if last_sub:
                    res['parent_subsection_id'] = last_sub.id
                    if 'parent_section_id' not in res and last_sub.parent_section_id:
                        res['parent_section_id'] = last_sub.parent_section_id.id

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Safety net: stamp costing_section from context if not set in vals."""
        section = self.env.context.get('default_costing_section', 'other')
        for vals in vals_list:
            if not vals.get('costing_section'):
                vals['costing_section'] = section
        return super().create(vals_list)
