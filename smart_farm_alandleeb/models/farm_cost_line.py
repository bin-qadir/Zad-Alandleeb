# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
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

    # ── Template origin (set when line was inserted from a BOQ template) ─────
    source_template_id = fields.Many2one(
        'farm.boq.item.template',
        string='Source Template',
        ondelete='set null',
        help='BOQ Item Template that was used to auto-create this cost line.',
        index=True,
    )

    # ── Source tracking ───────────────────────────────────────────────────────
    is_manual_item = fields.Boolean(
        string='Manual Item',
        default=True,
        help='True when the item was created directly in the costing sheet.\n'
             'False when it was inserted from a BOQ template.',
    )
    is_template_based = fields.Boolean(
        string='Template Based',
        compute='_compute_is_template_based',
        store=True,
        help='True when this line was inserted from a BOQ template.',
    )

    # ── BOQ Item parent-child hierarchy ───────────────────────────────────────
    # When a BOQ Item Template is inserted into the costing workspace, the
    # wizard creates one parent line (is_boq_item=True) and N child component
    # lines (boq_parent_id → parent).  The parent's totals roll up from its
    # children.  Component children are excluded from field-level totals to
    # avoid double-counting (the parent already carries the rolled-up values).
    is_boq_item = fields.Boolean(
        string='Is BOQ Item Header',
        default=False,
        help='True for the parent summary line created when a BOQ Item Template '
             'is inserted into the costing workspace.',
    )
    boq_parent_id = fields.Many2one(
        'farm.cost.line',
        string='Parent BOQ Item',
        ondelete='cascade',
        index=True,
        help='Set on component lines that belong to a parent BOQ item.',
    )
    boq_child_ids = fields.One2many(
        'farm.cost.line', 'boq_parent_id',
        string='Component Lines',
        help='Component cost lines that roll up into this BOQ item header.',
    )

    # ── Per-line cost breakdown (display purposes) ────────────────────────────
    material_amount = fields.Float(
        string='Material', digits=(16, 2),
        compute='_compute_category_amounts', store=True,
    )
    labor_amount = fields.Float(
        string='Labor', digits=(16, 2),
        compute='_compute_category_amounts', store=True,
    )
    overhead_amount = fields.Float(
        string='Overhead', digits=(16, 2),
        compute='_compute_category_amounts', store=True,
    )

    # ── Profit / sale ─────────────────────────────────────────────────────────
    profit_percent = fields.Float(
        string='Profit %', digits=(16, 2), default=0.0,
    )
    profit_amount = fields.Float(
        string='Profit Amount', digits=(16, 2),
        compute='_compute_profit', store=True,
    )
    sale_total = fields.Float(
        string='Sale Total', digits=(16, 2),
        compute='_compute_profit', store=True,
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

    @api.depends(
        'quantity', 'unit_cost', 'display_type', 'is_boq_item',
        'boq_child_ids.total_cost',
    )
    def _compute_total_cost(self):
        for rec in self:
            if rec.display_type:
                # Header rows (section / subsection / note) carry no cost
                rec.total_cost = 0.0
            elif rec.is_boq_item:
                # BOQ item header: roll up from component children
                rec.total_cost = sum(rec.boq_child_ids.mapped('total_cost'))
            else:
                rec.total_cost = rec.quantity * rec.unit_cost

    # =========================================================================
    # COMPUTED — category breakdown, profit, template tracking
    # =========================================================================

    @api.depends('source_template_id')
    def _compute_is_template_based(self):
        for rec in self:
            rec.is_template_based = bool(rec.source_template_id)

    @api.depends(
        'total_cost', 'cost_type_id', 'cost_type_id.category', 'display_type',
        'is_boq_item',
        'boq_child_ids.material_amount',
        'boq_child_ids.labor_amount',
        'boq_child_ids.overhead_amount',
    )
    def _compute_category_amounts(self):
        for rec in self:
            if rec.display_type:
                rec.material_amount = 0.0
                rec.labor_amount = 0.0
                rec.overhead_amount = 0.0
            elif rec.is_boq_item:
                # BOQ item header: roll up category amounts from children
                rec.material_amount = sum(rec.boq_child_ids.mapped('material_amount'))
                rec.labor_amount = sum(rec.boq_child_ids.mapped('labor_amount'))
                rec.overhead_amount = sum(rec.boq_child_ids.mapped('overhead_amount'))
            else:
                cat = rec.cost_type_id.category if rec.cost_type_id else False
                rec.material_amount = rec.total_cost if cat == 'material' else 0.0
                rec.labor_amount = rec.total_cost if cat == 'labor' else 0.0
                rec.overhead_amount = rec.total_cost if cat == 'overhead' else 0.0

    @api.depends(
        'total_cost', 'profit_percent', 'display_type', 'is_boq_item',
        'boq_child_ids.total_cost',
    )
    def _compute_profit(self):
        for rec in self:
            if rec.display_type:
                rec.profit_amount = 0.0
                rec.sale_total = 0.0
            elif rec.is_boq_item:
                # BOQ item header: apply profit % to children's rolled-up total
                child_cost = sum(rec.boq_child_ids.mapped('total_cost'))
                pct = rec.profit_percent or 0.0
                rec.profit_amount = child_cost * (pct / 100.0)
                rec.sale_total = child_cost + rec.profit_amount
            else:
                rec.profit_amount = rec.total_cost * (rec.profit_percent / 100.0)
                rec.sale_total = rec.total_cost + rec.profit_amount

    # =========================================================================
    # COMPUTED — hierarchical sequence number
    # =========================================================================

    @api.depends(
        'display_type', 'sequence', 'boq_parent_id',
        'parent_section_id', 'parent_section_id.sequence_no',
        'parent_subsection_id', 'parent_subsection_id.sequence_no',
        'field_id.cost_line_ids.display_type',
        'field_id.cost_line_ids.sequence',
        'field_id.cost_line_ids.parent_section_id',
        'field_id.cost_line_ids.parent_subsection_id',
        'field_id.cost_line_ids.boq_parent_id',
    )
    def _compute_sequence_no(self):
        for rec in self:
            rec.sequence_no = rec._get_sequence_no()

    def _get_sequence_no(self):
        # Component lines under a BOQ item header do not get their own sequence number
        if self.boq_parent_id:
            return ''
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
        """Safety net: stamp costing_section and is_manual_item."""
        section = self.env.context.get('default_costing_section', 'other')
        for vals in vals_list:
            if not vals.get('costing_section'):
                vals['costing_section'] = section
            # Lines created from a template are not manual items
            if vals.get('source_template_id') and 'is_manual_item' not in vals:
                vals['is_manual_item'] = False
        return super().create(vals_list)

    # =========================================================================
    # SAVE AS BOQ TEMPLATE
    # =========================================================================

    def action_save_as_boq_template(self):
        """Convert this cost line (or BOQ item header) into a new BOQ template.

        Supports two modes:
          • Normal individual line  → one component line in the new template
          • BOQ item header (is_boq_item=True)  → all child component lines
            are copied into the new template, preserving full breakdown
        """
        from odoo.exceptions import UserError

        self.ensure_one()

        if self.display_type:
            return  # Section / subsection / note headers cannot become templates

        if self.boq_parent_id:
            raise UserError(
                _('Component lines cannot be saved directly as templates. '
                  'Open the parent BOQ item header and save that as a template instead.')
            )

        if self.source_template_id and not self.is_boq_item:
            raise UserError(
                _('This item already originates from a template. '
                  'To create a new template from it, first clear the source '
                  'template link (Source Template field) and retry.')
            )

        name = self.name or (self.product_id.name if self.product_id else False) or _('Unnamed')

        # ── Duplicate check ───────────────────────────────────────────────────
        section_label = dict(
            self._fields['costing_section']._description_selection(self.env)
        ).get(self.costing_section, self.costing_section)

        domain = [
            ('name', '=', name),
            ('costing_section', '=', self.costing_section),
            ('active', '=', True),
        ]
        if self.work_type_id:
            domain.append(('work_type_id', '=', self.work_type_id.id))
        else:
            domain.append(('work_type_id', '=', False))

        existing = self.env['farm.boq.item.template'].search(domain, limit=1)
        if existing:
            raise UserError(
                _('A BOQ template named "%(name)s" already exists for '
                  '%(section)s / %(work_type)s.\n\n'
                  'Rename this item before saving as a template, or open '
                  'the existing template and update it manually.',
                  name=name,
                  section=section_label,
                  work_type=self.work_type_id.name if self.work_type_id else '—')
            )

        # ── Create template ───────────────────────────────────────────────────
        template = self.env['farm.boq.item.template'].create({
            'name': name,
            'costing_section': self.costing_section,
            'work_type_id': self.work_type_id.id if self.work_type_id else False,
            'product_id': self.product_id.id if self.product_id else False,
            'description': self.name,
            'qty_item': 1,
            'profit_percent': self.profit_percent,
            'active': True,
        })

        if self.is_boq_item and self.boq_child_ids:
            # BOQ item header: copy all component children as template lines
            for seq, child in enumerate(self.boq_child_ids.sorted('sequence'), start=10):
                self.env['farm.boq.item.template.line'].create({
                    'template_id': template.id,
                    'sequence': seq,
                    'description': child.name,
                    'product_id': child.product_id.id if child.product_id else False,
                    'cost_type_id': child.cost_type_id.id if child.cost_type_id else False,
                    'qty_1': child.quantity,
                    'cost_unit': child.unit_cost,
                })
        else:
            # Single normal line: one component line mirrors this line
            self.env['farm.boq.item.template.line'].create({
                'template_id': template.id,
                'sequence': 10,
                'description': self.name,
                'product_id': self.product_id.id if self.product_id else False,
                'cost_type_id': self.cost_type_id.id if self.cost_type_id else False,
                'qty_1': self.quantity,
                'cost_unit': self.unit_cost,
            })

        # Mark this line as now template-based
        self.source_template_id = template.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('New BOQ Template'),
            'res_model': 'farm.boq.item.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }
