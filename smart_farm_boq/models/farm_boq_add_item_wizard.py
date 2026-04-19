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
        template     = self.template_id
        project_qty  = self.boq_qty
        parent_line  = self._get_sub_subsection_line()
        if not parent_line:
            raise UserError(_('Cannot find the sub-subdivision row in the BOQ.'))

        tmpl_qty = max(template.quantity or 1.0, 1e-9)
        scale    = project_qty / tmpl_qty

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
            'boq_qty':            project_qty,
            'unit_id':            template.unit_id.id if template.unit_id else False,
        }
        if 'margin_percent' in BoqLine._fields:
            subitem_vals['margin_percent'] = template.margin_percent or 0.0
        else:
            subitem_vals['unit_price'] = round(template.unit_price, 2)

        subitem = BoqLine.create(subitem_vals)

        if 'cost_ids' in BoqLine._fields:
            CostLine = self.env.get('farm.boq.line.cost')
            if CostLine:
                for mat in template.material_ids:
                    CostLine.create({
                        'boq_line_id': subitem.id,
                        'job_type':    'material',
                        'product_id':  mat.product_id.id if mat.product_id else False,
                        'description': mat.description or (mat.product_id.name if mat.product_id else 'Material'),
                        'uom_id':      mat.uom_id.id if mat.uom_id else False,
                        'quantity':    mat.quantity * scale,
                        'unit_cost':   round(mat.unit_price, 2),
                    })

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
