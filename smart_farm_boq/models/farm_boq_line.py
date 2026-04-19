from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmBoqLine(models.Model):
    """BOQ Line — 4-level flat hierarchy stored in one table.

    ## Structure

    line_section        (display_type='line_section')
        Division header.  Code: 01, 02, …

    line_subsection     (display_type='line_subsection')
        Subdivision header.  Code: 1.01, 1.02, …

    line_sub_subsection (display_type='line_sub_subsection')
        Sub-Subdivision header.  Code: 1.01.01, 1.01.02, …
        Has child_ids = its subitems.

    subitem             (display_type=False, parent_id=sub_subsection_row)
        Real costing item.  Code: 1.01.01.01, 1.01.01.02, …
        Only this level carries quantity / unit_price / total / costing lines.
    """

    _name = 'farm.boq.line'
    _description = 'Cost Structure Line | بند هيكل التكلفة'
    _order = 'boq_id, div_rank, sub_rank, sub_sub_rank, row_level, sequence_sub'
    _parent_name = 'parent_id'

    # ── Document link ────────────────────────────────────────────────────────
    boq_id = fields.Many2one(
        'farm.boq', string='BOQ Document',
        required=True, ondelete='cascade', index=True,
    )
    project_id = fields.Many2one(
        'farm.project', string='Farm Project',
        related='boq_id.project_id', store=True, index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='boq_id.currency_id', store=False,
    )

    # ── Row type ─────────────────────────────────────────────────────────────
    display_type = fields.Selection(
        selection=[
            ('line_section',         'Division Section'),
            ('line_subsection',      'Subdivision Section'),
            ('line_sub_subsection',  'Sub-Subdivision Section'),
        ],
        string='Display Type',
        default=False,
    )

    # ── Hierarchy level discriminator ─────────────────────────────────────────
    # Critical for correct ordering when div_rank/sub_rank/sub_sub_rank/sequence_sub
    # are otherwise identical between a structural row and its first child.
    #
    #   line_section        → row_level = 0   (Division header)
    #   line_subsection     → row_level = 1   (Subdivision header)
    #   line_sub_subsection → row_level = 2   (Sub-Subdivision header)
    #   subitem             → row_level = 3   (Real costing item)
    #
    # Included in _order between sub_sub_rank and sequence_sub so that
    # the parent structural row always sorts before its children.
    row_level = fields.Integer(
        string='Row Level',
        compute='_compute_row_level',
        store=True,
        index=True,
    )

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')

    # ── Project Phase ─────────────────────────────────────────────────────────
    # Related stored field: inherits automatically from the parent BOQ document.
    # Changing the phase on the BOQ header propagates to every line instantly.
    project_phase_id = fields.Many2one(
        comodel_name='project.phase.master',
        string='Project Phase',
        related='boq_id.project_phase_id',
        store=True,
        readonly=True,
        index=True,
    )

    # ── Classification ────────────────────────────────────────────────────────
    division_id = fields.Many2one(
        'farm.division.work', string='Division', ondelete='set null',
    )
    subdivision_id = fields.Many2one(
        'farm.subdivision.work', string='Subdivision', ondelete='set null',
    )
    sub_subdivision_id = fields.Many2one(
        'farm.sub_subdivision.work', string='Sub-Subdivision', ondelete='set null',
    )

    # ── Stored ranks (for ordering without JOINs) ─────────────────────────────
    div_rank     = fields.Integer(string='Division Rank',      default=0)
    sub_rank     = fields.Integer(string='Subdivision Rank',   default=0)
    sub_sub_rank = fields.Integer(string='Sub-Subdivision Rank', default=0)

    # ── Section reference links ────────────────────────────────────────────────
    section_line_id = fields.Many2one(
        'farm.boq.line', string='Division Section Line',
        domain=[('display_type', '=', 'line_section')],
        ondelete='set null', index=True,
    )
    subsection_line_id = fields.Many2one(
        'farm.boq.line', string='Subdivision Section Line',
        domain=[('display_type', '=', 'line_subsection')],
        ondelete='set null', index=True,
    )
    sub_subsection_line_id = fields.Many2one(
        'farm.boq.line', string='Sub-Subdivision Section Line',
        domain=[('display_type', '=', 'line_sub_subsection')],
        ondelete='set null', index=True,
    )

    # ── Sub-item hierarchy ─────────────────────────────────────────────────────
    # Subitems: parent_id = their sub_subsection row (line_sub_subsection)
    parent_id = fields.Many2one(
        'farm.boq.line', string='Parent',
        ondelete='cascade', index=True,
    )
    child_ids = fields.One2many(
        'farm.boq.line', 'parent_id', string='Sub Items',
    )
    child_count = fields.Integer(
        string='Sub-item Count',
        compute='_compute_child_count', store=True,
    )

    # ── Sequencing ────────────────────────────────────────────────────────────
    sequence      = fields.Integer(string='Sequence', default=10)
    sequence_main = fields.Integer(string='Item Seq.', default=0)
    sequence_sub  = fields.Integer(string='Sub Seq.',  default=0)
    display_code  = fields.Char(
        string='Code', compute='_compute_display_code', store=True,
    )

    # ── Planning dates (subitems only) ───────────────────────────────────────
    start_date = fields.Date(string='Start Date')
    end_date   = fields.Date(string='End Date')

    # ── Subitem workflow state (subitems only) ────────────────────────────────
    item_state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('study',       'Study'),
            ('submitted',   'Submitted'),
            ('approved',    'Approved'),
            ('rejected',    'Rejected'),
            ('resubmitted', 'Resubmitted'),
        ],
        string='Item Status | حالة البند',
        default='draft',
        index=True,
    )

    # ── BOQ Line pricing status ───────────────────────────────────────────────
    # Tracks whether this line's unit_price has been reviewed and locked.
    # Set to 'approved' by analysis approval actions; locks unit_price edits.
    boq_state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('review',   'Review'),
            ('approved', 'Approved'),
        ],
        string='BOQ Status',
        default='draft',
        index=True,
        copy=False,
        help=(
            'Draft: price not yet set.\n'
            'Review: analysis in progress.\n'
            'Approved: price locked by approved analysis.'
        ),
    )
    is_editable = fields.Boolean(
        string='Is Editable',
        compute='_compute_is_editable',
        help='False when boq_state is approved — used to lock price fields.',
    )

    # ── Quantities & pricing ──────────────────────────────────────────────────
    quantity   = fields.Float(string='Quantity', default=1.0)
    boq_qty    = fields.Float(string='BOQ Qty | كمية البند', default=1.0, digits=(16, 2))
    unit_id    = fields.Many2one(
        'uom.uom', string='Unit of Measure',
        default=lambda self: self.env.ref('uom.uom_square_meter', raise_if_not_found=False),
        domain=lambda self: [
            ('category_id', '=', self.env.ref('uom.uom_categ_surface').id)
        ],
        ondelete='set null',
    )
    unit_price = fields.Float(string='Unit Price', digits=(16, 2))
    total      = fields.Float(
        string='Total', compute='_compute_total', store=True, digits=(16, 2),
    )

    # ── Template loader ───────────────────────────────────────────────────────
    template_id = fields.Many2one(
        'farm.boq.line.template', string='Load from Template',
        ondelete='set null',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed fields
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('display_type')
    def _compute_row_level(self):
        """Assign a numeric level so the _order key discriminates parent from child.

        Without this, a line_sub_subsection row and its first subitem can share
        identical (div_rank, sub_rank, sub_sub_rank, sequence_sub) tuples, causing
        the DB to return them in undefined order.  row_level breaks the tie:

            line_section        → 0
            line_subsection     → 1
            line_sub_subsection → 2
            subitem             → 3   (display_type is False)
        """
        for rec in self:
            dt = rec.display_type
            if dt == 'line_section':
                rec.row_level = 0
            elif dt == 'line_subsection':
                rec.row_level = 1
            elif dt == 'line_sub_subsection':
                rec.row_level = 2
            else:
                rec.row_level = 3

    @api.depends('boq_state')
    def _compute_is_editable(self):
        for rec in self:
            rec.is_editable = rec.boq_state != 'approved'

    # ────────────────────────────────────────────────────────────────────────
    # BOQ State workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_boq_state_review(self):
        """Draft → Review."""
        self.filtered(lambda r: r.boq_state == 'draft').write({'boq_state': 'review'})

    def action_boq_state_approve(self):
        """Review → Approved (locks unit_price)."""
        self.filtered(lambda r: r.boq_state == 'review').write({'boq_state': 'approved'})

    def action_boq_state_reset(self):
        """Approved / Review → Draft (unlocks editing)."""
        self.filtered(lambda r: r.boq_state != 'draft').write({'boq_state': 'draft'})

    @api.constrains('sequence_sub', 'parent_id', 'display_type')
    def _check_unique_sequence_sub(self):
        """No two subitems under the same parent may share a sequence_sub.

        This prevents duplicate display codes (1.01.01.02 appearing twice).
        Skipped when ``skip_sequence_check`` is in context (used by rebuild).
        """
        if self.env.context.get('skip_sequence_check'):
            return
        for rec in self:
            if not rec.display_type and rec.parent_id:
                duplicate = self.search([
                    ('parent_id', '=', rec.parent_id.id),
                    ('sequence_sub', '=', rec.sequence_sub),
                    ('id', '!=', rec.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(_(
                        'Subitem "%s" has a duplicate sequence number (%s) under the '
                        'same Sub-Subdivision. BOQ item codes must be unique.',
                        rec.name, rec.sequence_sub,
                    ))

    @api.constrains('display_type', 'parent_id', 'division_id', 'subdivision_id', 'sub_subdivision_id')
    def _check_hierarchy(self):
        for rec in self:
            if rec.display_type == 'line_section':
                if not rec.division_id:
                    raise ValidationError(_(
                        'Division row "%s" must have a Division set.', rec.name
                    ))
            elif rec.display_type == 'line_subsection':
                if not rec.division_id:
                    raise ValidationError(_(
                        'Subdivision row "%s" must have a Division set.', rec.name
                    ))
                if not rec.subdivision_id:
                    raise ValidationError(_(
                        'Subdivision row "%s" must have a Subdivision set.', rec.name
                    ))
            elif rec.display_type == 'line_sub_subsection':
                if not rec.division_id:
                    raise ValidationError(_(
                        'Sub-Subdivision row "%s" must have a Division set.', rec.name
                    ))
                if not rec.subdivision_id:
                    raise ValidationError(_(
                        'Sub-Subdivision row "%s" must have a Subdivision set.', rec.name
                    ))
                if not rec.sub_subdivision_id:
                    raise ValidationError(_(
                        'Sub-Subdivision row "%s" must have a Sub-Subdivision master set.', rec.name
                    ))
            elif not rec.display_type and rec.parent_id:
                if rec.parent_id.display_type != 'line_sub_subsection':
                    raise ValidationError(_(
                        'Subitem "%s" can only be placed under a Sub-Subdivision row. '
                        'It cannot be placed under a Division or Subdivision level.',
                        rec.name,
                    ))
                if not rec.division_id:
                    raise ValidationError(_(
                        'Subitem "%s" must have a Division set.', rec.name
                    ))
                if not rec.subdivision_id:
                    raise ValidationError(_(
                        'Subitem "%s" must have a Subdivision set.', rec.name
                    ))
                if not rec.sub_subdivision_id:
                    raise ValidationError(_(
                        'Subitem "%s" must have a Sub-Subdivision set.', rec.name
                    ))

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_(
                    'End Date cannot be earlier than Start Date on line "%s".'
                ) % rec.name)

    @api.depends('child_ids')
    def _compute_child_count(self):
        for rec in self:
            rec.child_count = len(rec.child_ids)

    @api.depends(
        'display_type',
        'div_rank', 'sub_rank', 'sub_sub_rank', 'sequence_main', 'sequence_sub',
        'parent_id', 'parent_id.display_type',
        'parent_id.div_rank', 'parent_id.sub_rank', 'parent_id.sub_sub_rank',
    )
    def _compute_display_code(self):
        """4-level hierarchical codes.

        line_section        → 01, 02, …
        line_subsection     → 1.01, 1.02, …
        line_sub_subsection → 1.01.01, 1.01.02, …
        subitem             → 1.01.01.01, 1.01.01.02, …
        """
        for rec in self:
            if rec.display_type == 'line_section':
                seq = max(rec.div_rank or rec.sequence_main or 1, 1)
                rec.display_code = f'{seq:02d}'

            elif rec.display_type == 'line_subsection':
                div_r = max(rec.div_rank or 1, 1)
                sub_r = max(rec.sub_rank or 1, 1)
                rec.display_code = f'{div_r}.{sub_r:02d}'

            elif rec.display_type == 'line_sub_subsection':
                div_r     = max(rec.div_rank or 1, 1)
                sub_r     = max(rec.sub_rank or 1, 1)
                sub_sub_r = max(rec.sub_sub_rank or 1, 1)
                rec.display_code = f'{div_r}.{sub_r:02d}.{sub_sub_r:02d}'

            elif rec.parent_id:
                p = rec.parent_id
                if p.display_type == 'line_sub_subsection':
                    # New 4-level subitem
                    div_r     = max(p.div_rank or 1, 1)
                    sub_r     = max(p.sub_rank or 1, 1)
                    sub_sub_r = max(p.sub_sub_rank or 1, 1)
                    sub_seq   = max(rec.sequence_sub, 1)
                    rec.display_code = f'{div_r}.{sub_r:02d}.{sub_sub_r:02d}.{sub_seq:02d}'
                else:
                    # Legacy: subitem under subsection (backward compat)
                    div_r   = p.div_rank or 1
                    sub_r   = p.sub_rank or max(p.sequence_main or 1, 1)
                    sub_seq = max(rec.sequence_sub, 1)
                    rec.display_code = f'{div_r}.{sub_r:02d}.{sub_seq:02d}'

            else:
                # Legacy root item
                div_r    = rec.div_rank or 0
                main_seq = rec.sub_rank or max(rec.sequence_main, 1)
                rec.display_code = f'{div_r}.{main_seq:02d}' if div_r else f'{main_seq:02d}'

    @api.depends('boq_qty', 'unit_price', 'display_type')
    def _compute_total(self):
        for rec in self:
            if rec.display_type:
                rec.total = 0.0
            else:
                rec.total = round(rec.boq_qty * rec.unit_price, 2)

    # ────────────────────────────────────────────────────────────────────────
    # Onchange
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if not self.template_id:
            return
        tmpl = self.template_id
        self.name          = tmpl.name
        self.description   = tmpl.description
        self.division_id   = tmpl.division_id
        self.subdivision_id = tmpl.subdivision_id
        self.boq_qty       = tmpl.quantity
        self.unit_id       = tmpl.unit_id

    @api.onchange('division_id')
    def _onchange_division_id(self):
        self.subdivision_id     = False
        self.sub_subdivision_id = False
        self.template_id        = False

    @api.onchange('subdivision_id')
    def _onchange_subdivision_id(self):
        self.sub_subdivision_id = False
        self.template_id        = False

    @api.onchange('sub_subdivision_id')
    def _onchange_sub_subdivision_id(self):
        self.template_id = False

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    # ────────────────────────────────────────────────────────────────────────
    # Subitem workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_item_study(self):
        """Draft → Study"""
        for rec in self.filtered(lambda r: r.parent_id and r.item_state == 'draft'):
            rec.item_state = 'study'

    def action_item_submit(self):
        """Draft / Study → Submitted"""
        for rec in self.filtered(lambda r: r.parent_id and r.item_state in ('draft', 'study')):
            rec.item_state = 'submitted'

    def action_item_approve(self):
        """Submitted / Resubmitted → Approved"""
        for rec in self.filtered(lambda r: r.parent_id and r.item_state in ('submitted', 'resubmitted')):
            rec.item_state = 'approved'

    def action_item_reject(self):
        """Study / Submitted / Resubmitted → Rejected"""
        for rec in self.filtered(lambda r: r.parent_id and r.item_state in ('study', 'submitted', 'resubmitted')):
            rec.item_state = 'rejected'

    def action_item_resubmit(self):
        """Rejected → Resubmitted"""
        for rec in self.filtered(lambda r: r.parent_id and r.item_state == 'rejected'):
            rec.item_state = 'resubmitted'

    def action_view_details(self):
        self.ensure_one()
        # Lock classification fields when viewing an existing subitem
        ctx = {'lock_classification': bool(self.parent_id)}
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'farm.boq.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_add_subitem(self):
        """Open the Add Subitem wizard for this Sub-Subdivision row."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Subitem',
            'res_model': 'farm.boq.add.subitem.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_boq_id':                self.boq_id.id,
                'default_division_id':           self.division_id.id,
                'default_subdivision_id':         self.subdivision_id.id,
                'default_sub_subdivision_id':     self.sub_subdivision_id.id,
                'default_sub_subsection_line_id': self.id,
                # Pass project phase so the subitem form can inherit it
                'default_project_phase_id':       self.project_phase_id.id or False,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Rank helpers
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _get_division_rank(self, division_id):
        all_divs = self.env['farm.division.work'].search([], order='sequence asc, name asc')
        ids = list(all_divs.ids)
        return (ids.index(division_id) + 1) if division_id in ids else 1

    @api.model
    def _get_subdivision_rank(self, subdivision_id):
        sub = self.env['farm.subdivision.work'].browse(subdivision_id)
        all_subs = self.env['farm.subdivision.work'].search(
            [('division_id', '=', sub.division_id.id)],
            order='sequence asc, name asc',
        )
        ids = list(all_subs.ids)
        return (ids.index(subdivision_id) + 1) if subdivision_id in ids else 1

    @api.model
    def _get_sub_subdivision_rank(self, sub_subdivision_id):
        sub_sub = self.env['farm.sub_subdivision.work'].browse(sub_subdivision_id)
        all_sub_subs = self.env['farm.sub_subdivision.work'].search(
            [('subdivision_id', '=', sub_sub.subdivision_id.id)],
            order='sequence asc, name asc',
        )
        ids = list(all_sub_subs.ids)
        return (ids.index(sub_subdivision_id) + 1) if sub_subdivision_id in ids else 1

    # ────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            boq_id       = vals.get('boq_id')
            display_type = vals.get('display_type') or False
            parent_id    = vals.get('parent_id')

            if display_type == 'line_section':
                if vals.get('division_id') and vals.get('sequence_main', 0) <= 0:
                    rank = self._get_division_rank(vals['division_id'])
                    vals['sequence_main'] = rank
                    vals.setdefault('div_rank', rank)
                elif vals.get('sequence_main', 0) <= 0 and boq_id:
                    last = self.search(
                        [('boq_id', '=', boq_id),
                         ('display_type', '=', 'line_section')],
                        order='sequence_main desc', limit=1,
                    )
                    vals['sequence_main'] = (last.sequence_main or 0) + 1

            elif display_type == 'line_subsection':
                if vals.get('division_id'):
                    vals.setdefault('div_rank', self._get_division_rank(vals['division_id']))
                if vals.get('subdivision_id'):
                    rank = self._get_subdivision_rank(vals['subdivision_id'])
                    vals.setdefault('sub_rank', rank)
                    if vals.get('sequence_sub', 0) <= 0:
                        vals['sequence_sub'] = rank

            elif display_type == 'line_sub_subsection':
                if vals.get('division_id'):
                    vals.setdefault('div_rank', self._get_division_rank(vals['division_id']))
                if vals.get('subdivision_id'):
                    vals.setdefault('sub_rank', self._get_subdivision_rank(vals['subdivision_id']))
                if vals.get('sub_subdivision_id'):
                    rank = self._get_sub_subdivision_rank(vals['sub_subdivision_id'])
                    vals.setdefault('sub_sub_rank', rank)
                    if vals.get('sequence_sub', 0) <= 0:
                        vals['sequence_sub'] = rank

            elif parent_id:
                # Subitem — auto-inherit classification from parent sub-subdivision row
                parent = self.browse(parent_id)
                if parent.exists() and parent.display_type == 'line_sub_subsection':
                    if not vals.get('division_id') and parent.division_id:
                        vals['division_id'] = parent.division_id.id
                    if not vals.get('subdivision_id') and parent.subdivision_id:
                        vals['subdivision_id'] = parent.subdivision_id.id
                    if not vals.get('sub_subdivision_id') and parent.sub_subdivision_id:
                        vals['sub_subdivision_id'] = parent.sub_subdivision_id.id

                # Subitem — inherit ranks from parent or explicit fields
                if vals.get('division_id') and not vals.get('div_rank'):
                    vals['div_rank'] = self._get_division_rank(vals['division_id'])
                if vals.get('subdivision_id') and not vals.get('sub_rank'):
                    vals['sub_rank'] = self._get_subdivision_rank(vals['subdivision_id'])
                if vals.get('sub_subdivision_id') and not vals.get('sub_sub_rank'):
                    vals['sub_sub_rank'] = self._get_sub_subdivision_rank(vals['sub_subdivision_id'])
                if vals.get('sequence_sub', 0) <= 0:
                    last = self.search(
                        [('parent_id', '=', parent_id)],
                        order='sequence_sub desc', limit=1,
                    )
                    vals['sequence_sub'] = (last.sequence_sub or 0) + 1

            else:
                # Legacy root item (old standalone / main item — backward compat)
                if boq_id:
                    if vals.get('division_id'):
                        vals['div_rank'] = self._get_division_rank(vals['division_id'])
                    if vals.get('subdivision_id'):
                        vals['sub_rank'] = self._get_subdivision_rank(vals['subdivision_id'])
                    if vals.get('sequence_main', 0) <= 0:
                        last = self.search(
                            [('boq_id', '=', boq_id),
                             ('display_type', '=', False),
                             ('parent_id', '=', False)],
                            order='sequence_main desc', limit=1,
                        )
                        vals['sequence_main'] = (last.sequence_main or 0) + 1

        return super().create(vals_list)

    def write(self, vals):
        """Update stored ranks when classification changes.

        Also guards subitems (parent_id is set) against reclassification:
        ``boq_id`` and ``parent_id`` cannot be changed on an existing subitem
        unless the caller explicitly sets ``allow_classification_change`` in
        context (used by internal structure-rebuild routines).
        """
        if not self.env.context.get('allow_classification_change'):
            protected = {'boq_id', 'parent_id'}
            changing  = protected & set(vals)
            if changing:
                for rec in self.filtered('parent_id'):
                    if 'boq_id' in vals and vals['boq_id'] != rec.boq_id.id:
                        raise UserError(_(
                            'Cannot move subitem "%s" to a different BOQ Document.',
                            rec.name,
                        ))
                    if 'parent_id' in vals and vals['parent_id'] != rec.parent_id.id:
                        raise UserError(_(
                            'Cannot change the parent of subitem "%s". '
                            'Delete and recreate it under the correct hierarchy.',
                            rec.name,
                        ))

        if 'division_id' in vals:
            div_id = vals.get('division_id')
            vals['div_rank'] = self._get_division_rank(div_id) if div_id else 0
        if 'subdivision_id' in vals:
            sub_id = vals.get('subdivision_id')
            vals['sub_rank'] = self._get_subdivision_rank(sub_id) if sub_id else 0
        if 'sub_subdivision_id' in vals:
            sub_sub_id = vals.get('sub_subdivision_id')
            vals['sub_sub_rank'] = self._get_sub_subdivision_rank(sub_sub_id) if sub_sub_id else 0
        return super().write(vals)

    def unlink(self):
        """After deleting subitems, renumber the remaining siblings so that
        sequence_sub values are always contiguous (1, 2, 3 …) with no gaps.
        Gaps cause broken display_code numbering (e.g. 1.01.01.01 → 1.01.01.03).
        """
        # Collect parents of subitems being deleted, before the delete
        parents_to_rebuild = self.env['farm.boq.line']
        for rec in self:
            if not rec.display_type and rec.parent_id:
                parents_to_rebuild |= rec.parent_id

        result = super().unlink()

        # Renumber remaining siblings under each affected parent
        for parent in parents_to_rebuild:
            if not parent.exists():
                continue
            siblings = self.search(
                [('parent_id', '=', parent.id)],
                order='sequence_sub asc, id asc',
            )
            for i, sib in enumerate(siblings, start=1):
                if sib.sequence_sub != i:
                    sib.write({'sequence_sub': i})

        return result

    # ────────────────────────────────────────────────────────────────────────
    # BOQ Structure Screen — list header action buttons
    # Called from the <header> of the farm.boq.line list view.
    # The BOQ is resolved from context (default_boq_id) or from self[0].boq_id.
    # ────────────────────────────────────────────────────────────────────────

    def _get_context_boq(self):
        """Return the farm.boq from context or from the first selected line."""
        boq_id = self.env.context.get('default_boq_id')
        if not boq_id and self:
            boq_id = self[0].boq_id.id
        if not boq_id:
            raise UserError(_(
                'No Cost Structure context found.\n\n'
                'Open the BOQ Structure screen from a Cost Structure document.'
            ))
        return self.env['farm.boq'].browse(boq_id)

    def action_structure_open_add_wizard(self):
        """Open the Add BOQ Structure wizard for the current BOQ."""
        boq = self._get_context_boq()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add BOQ Structure'),
            'res_model': 'farm.boq.add_structure.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': boq.id},
        }

    def action_structure_rebuild(self):
        """Deduplicate + resequence all hierarchy rows for the current BOQ."""
        boq = self._get_context_boq()
        return boq.action_cleanup_structure()

    def action_sequence_rebuild(self):
        """Rebuild display codes and sequence numbers without deduplication."""
        boq = self._get_context_boq()
        return boq.rebuild_boq_sequence()

    def action_open_excel_import(self):
        """Open the Excel Import wizard for the current BOQ."""
        boq = self._get_context_boq()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import BOQ from Excel'),
            'res_model': 'farm.boq.excel.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': boq.id},
        }

    def action_delete_selected_lines(self):
        """Safe hierarchical delete of selected BOQ lines.

        Expands the selection to include all children of any selected parent.
        Blocks deletion if subitems have downstream analysis or job-order links.
        Rebuilds the BOQ sequence after deletion.
        """
        if not self:
            raise UserError(_('No lines selected. Select one or more BOQ lines to delete.'))

        to_delete = self._collect_with_children()
        subitems = to_delete.filtered(lambda l: not l.display_type)
        warnings = self._check_downstream_links(subitems)

        if warnings:
            raise UserError(_(
                'Cannot delete — the following downstream links exist on the selected items:\n\n'
                '%s\n\n'
                'Remove or re-link these records before deleting the BOQ lines.',
                '\n'.join('  • %s' % w for w in warnings),
            ))

        boq_id = to_delete[0].boq_id.id if to_delete else False
        count = len(to_delete)
        to_delete.unlink()

        if boq_id:
            boq = self.env['farm.boq'].browse(boq_id)
            if boq.exists():
                boq._rebuild_sequence()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Lines Deleted'),
                'message': _('%d BOQ line(s) deleted and sequence rebuilt.', count),
                'type': 'success',
                'sticky': False,
            },
        }

    def _collect_with_children(self):
        """Expand a recordset to include all hierarchy descendants."""
        Line = self.env['farm.boq.line']
        result = self.env['farm.boq.line']

        for line in self:
            result |= line
            if line.display_type == 'line_section':
                subsections = Line.search([('section_line_id', '=', line.id)])
                result |= subsections
                for sub in subsections:
                    sub_subs = Line.search([('subsection_line_id', '=', sub.id)])
                    result |= sub_subs
                    for ss in sub_subs:
                        result |= Line.search([('parent_id', '=', ss.id)])
            elif line.display_type == 'line_subsection':
                sub_subs = Line.search([('subsection_line_id', '=', line.id)])
                result |= sub_subs
                for ss in sub_subs:
                    result |= Line.search([('parent_id', '=', ss.id)])
            elif line.display_type == 'line_sub_subsection':
                result |= Line.search([('parent_id', '=', line.id)])

        return result

    def _check_downstream_links(self, subitems):
        """Return list of human-readable warning strings for downstream links."""
        if not subitems:
            return []
        ids = subitems.ids
        warnings = []

        AnalysisLine = self.env.get('farm.boq.analysis.line')
        if AnalysisLine is not None:
            count = AnalysisLine.search_count([('boq_line_id', 'in', ids)])
            if count:
                warnings.append(_('%d BOQ Analysis line(s)') % count)

        JobOrder = self.env.get('farm.job.order')
        if JobOrder is not None and 'boq_line_id' in JobOrder._fields:
            count = JobOrder.search_count([('boq_line_id', 'in', ids)])
            if count:
                warnings.append(_('%d Job Order(s)') % count)

        return warnings
