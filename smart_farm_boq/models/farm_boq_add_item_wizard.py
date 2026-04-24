from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmBoqAddSubitemWizard(models.TransientModel):
    """Wizard to add a subitem under a Sub-Subdivision row.

    Opened from the 'Add Subitem' button on every line_sub_subsection row.

    ## Two entry modes

    use_template
        Select a template filtered by division + subdivision + sub-subdivision.
        Enter the project quantity.
        BOQ subitem: unit_price = template.unit_price, total = qty × unit_price.

    create_new
        Enter a name for the new subitem (quantity=1 baseline).
        Opens the subitem form for materials / labor / overhead entry.
    """

    _name = 'farm.boq.add.subitem.wizard'
    _description = 'Add Subitem Wizard'

    # ── Context (pre-filled, readonly) ───────────────────────────────────────
    boq_id = fields.Many2one(
        'farm.boq', string='BOQ Document', required=True, ondelete='cascade',
    )
    project_phase_id = fields.Many2one(
        'project.phase.master', string='Project Phase', ondelete='set null',
    )
    division_id = fields.Many2one(
        'farm.division.work', string='Division', required=True,
    )
    subdivision_id = fields.Many2one(
        'farm.subdivision.work', string='Subdivision', required=True,
    )
    sub_subdivision_id = fields.Many2one(
        'farm.sub_subdivision.work', string='Sub-Subdivision', required=True,
    )
    sub_subsection_line_id = fields.Many2one(
        'farm.boq.line', string='Sub-Subsection Row',
        help='The line_sub_subsection row that will be the parent of the new subitem.',
    )

    # ── Entry mode ────────────────────────────────────────────────────────────
    mode = fields.Selection(
        selection=[
            ('use_template', 'Use Ready Template'),
            ('create_new',   'Create New Subitem'),
        ],
        string='Entry Mode',
        required=True,
        default='use_template',
    )

    # ── Template mode ─────────────────────────────────────────────────────────
    template_id = fields.Many2one(
        'farm.boq.line.template',
        string='Template',
        domain="[('division_id', '=', division_id), ('subdivision_id', '=', subdivision_id)]",
    )
    boq_qty = fields.Float(
        string='BOQ Qty | كمية البند',
        default=1.0,
        digits=(16, 2),
    )

    # ── Create-new mode ───────────────────────────────────────────────────────
    name = fields.Char(string='Subitem Name')
    unit_id = fields.Many2one(
        'uom.uom', string='Unit of Measure',
        default=lambda self: self.env.ref('uom.uom_square_meter', raise_if_not_found=False),
        ondelete='set null',
    )
    start_date = fields.Date(string='Start Date')
    end_date   = fields.Date(string='End Date')

    # ────────────────────────────────────────────────────────────────────────
    # Onchange
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('mode')
    def _onchange_mode(self):
        self.template_id = False
        self.name = False

    # ────────────────────────────────────────────────────────────────────────
    # Public action
    # ────────────────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        if self.boq_id.state not in ('draft', 'start'):
            raise UserError(
                _('Cannot add items to BOQ "%s" in state "%s".')
                % (self.boq_id.name, self.boq_id.state)
            )

        if self.mode == 'use_template':
            if not self.template_id:
                raise UserError(_('Please select a template.'))
            if (self.boq_qty or 0) <= 0:
                raise UserError(_('BOQ Qty must be greater than zero.'))
            self._create_from_template()
            return {'type': 'ir.actions.act_window_close'}
        else:
            if not (self.name or '').strip():
                raise UserError(_('Please enter a name for the new subitem.'))
            if (self.boq_qty or 0) <= 0:
                raise UserError(_('BOQ Qty must be greater than zero.'))
            self._create_new_subitem()
            return {'type': 'ir.actions.act_window_close'}

    # ────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────────────────────────────────

    def _get_sub_subsection_line(self):
        """Return the sub-subsection line that is the parent of the new subitem."""
        if self.sub_subsection_line_id:
            return self.sub_subsection_line_id

        boq    = self.boq_id
        BoqLine = self.env['farm.boq.line']

        existing = boq.line_ids.filtered(
            lambda l: (
                l.display_type == 'line_sub_subsection'
                and l.sub_subdivision_id.id == self.sub_subdivision_id.id
            )
        )
        if existing:
            return existing[0]

        # Fallback: rebuild structure on-the-fly for legacy BOQs
        boq._auto_create_structure()
        existing = boq.line_ids.filtered(
            lambda l: (
                l.display_type == 'line_sub_subsection'
                and l.sub_subdivision_id.id == self.sub_subdivision_id.id
            )
        )
        return existing[0] if existing else None

    def _create_from_template(self):
        """Create a parent BOQ line + ALL cost component lines from the template.

        The template is read-only source — never modified.
        Each cost line gets base_ratio_qty = component.qty / template.qty so
        that child.quantity = parent.boq_qty × base_ratio_qty at all times.
        """
        template    = self.template_id
        main_qty    = self.boq_qty
        parent_line = self._get_sub_subsection_line()
        if not parent_line:
            raise UserError(_('Cannot find the sub-subdivision row in the BOQ.'))

        # ── Create the parent BOQ line ────────────────────────────────────────
        BoqLine = self.env['farm.boq.line']
        subitem_vals = {
            'boq_id':             self.boq_id.id,
            'parent_id':          parent_line.id,
            'name':               template.name,
            'description':        template.description or False,
            'division_id':        self.division_id.id,
            'subdivision_id':     self.subdivision_id.id,
            'sub_subdivision_id': self.sub_subdivision_id.id,
            'quantity':           1.0,
            'boq_qty':            main_qty,
            'unit_id':            template.unit_id.id if template.unit_id else False,
        }
        if 'margin_percent' in BoqLine._fields:
            subitem_vals['margin_percent'] = template.margin_percent or 0.0

        subitem = BoqLine.create(subitem_vals)

        # ── Create child cost lines from ALL template types ───────────────────
        CostLine = self.env.get('farm.boq.line.cost')
        if CostLine is not None:
            for vals in self._template_to_cost_vals(template, subitem.id, main_qty):
                CostLine.create(vals)

    def _template_to_cost_vals(self, template, boq_line_id, main_qty):
        """Return a list of farm.boq.line.cost creation dicts from ALL template types.

        base_ratio_qty is normalised to per-unit (component.qty / template.qty)
        so quantity = main_qty × base_ratio_qty is always correct.
        """
        tmpl_qty = max(template.quantity or 1.0, 1e-9)
        lines = []

        for m in template.material_ids:
            ratio = (m.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'material',
                'product_id':     m.product_id.id if m.product_id else False,
                'description':    m.description or (m.product_id.name if m.product_id else 'Material'),
                'uom_id':         m.uom_id.id if m.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      m.unit_price,
            })

        for l in template.labor_ids:
            ratio = (l.hours or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'labour',
                'product_id':     l.product_id.id if l.product_id else False,
                'description':    l.description or (l.product_id.name if l.product_id else 'Labour'),
                'uom_id':         l.uom_id.id if l.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      l.cost_per_hour,
            })

        for s in template.subcontractor_ids:
            ratio = (s.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'subcontractor',
                'product_id':     s.product_id.id if s.product_id else False,
                'description':    s.description or (s.product_id.name if s.product_id else 'Subcontractor'),
                'uom_id':         s.uom_id.id if s.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      s.unit_price,
            })

        for eq in template.equipment_ids:
            ratio = (eq.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'equipment',
                'product_id':     eq.product_id.id if eq.product_id else False,
                'description':    eq.description or (eq.product_id.name if eq.product_id else 'Equipment'),
                'uom_id':         eq.uom_id.id if eq.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      eq.unit_price,
            })

        for t in template.tools_ids:
            ratio = (t.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'tools',
                'product_id':     t.product_id.id if t.product_id else False,
                'description':    t.description or (t.product_id.name if t.product_id else 'Tools'),
                'uom_id':         t.uom_id.id if t.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      t.unit_price,
            })

        for o in template.overhead_ids:
            ratio = (o.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'other',
                'product_id':     o.product_id.id if o.product_id else False,
                'description':    o.name or (o.product_id.name if o.product_id else 'Other'),
                'uom_id':         o.uom_id.id if o.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      o.unit_price,
            })

        return lines

    def _create_new_subitem(self):
        parent_line = self._get_sub_subsection_line()
        if not parent_line:
            raise UserError(_('Cannot find the sub-subdivision row in the BOQ.'))
        vals = {
            'boq_id':             self.boq_id.id,
            'parent_id':          parent_line.id,
            'name':               self.name.strip(),
            'division_id':        self.division_id.id,
            'subdivision_id':     self.subdivision_id.id,
            'sub_subdivision_id': self.sub_subdivision_id.id,
            'quantity':           1.0,
            'boq_qty':            self.boq_qty or 1.0,
        }
        if self.unit_id:
            vals['unit_id'] = self.unit_id.id
        if self.start_date:
            vals['start_date'] = self.start_date
        if self.end_date:
            vals['end_date'] = self.end_date
        return self.env['farm.boq.line'].create(vals)
