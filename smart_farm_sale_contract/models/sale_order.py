import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrderContract(models.Model):
    """Extend sale.order to serve as the approved commercial contract backbone.

    Adds a dedicated contract approval workflow (contract_stage) that is
    separate from the native SO state machine (quotation / order).

    Flow:
        new → in_progress → submitted → [reply_with_notes →] approved
                                      → rejected / canceled

    Job Orders can ONLY be generated when contract_stage == 'approved'.
    Each JO is tied to exactly one sale.order.line, which must be linked
    to a farm.boq.analysis.line for full BOQ traceability.
    """

    _inherit = 'sale.order'

    # ── Contract workflow ─────────────────────────────────────────────────────

    contract_stage = fields.Selection(
        selection=[
            ('new',              'New'),
            ('in_progress',      'In Progress'),
            ('submitted',        'Submitted'),
            ('reply_with_notes', 'Reply with Notes'),
            ('approved',         'Approved'),
            ('rejected',         'Rejected'),
            ('canceled',         'Canceled'),
        ],
        string='Contract Stage',
        default='new',
        required=True,
        copy=False,
        tracking=True,
        help=(
            'Contract approval workflow — separate from the native Quotation/Order status.\n'
            'new → in_progress → submitted → approved\n'
            'Approved = execution gate passed; Job Orders can be generated.'
        ),
    )

    is_contract_approved = fields.Boolean(
        string='Contract Approved',
        compute='_compute_is_contract_approved',
        store=True,
        tracking=True,
        help='True when contract_stage == Approved. Unlocks Job Order generation.',
    )

    revision_ref = fields.Char(
        string='Revision Ref',
        copy=False,
        help='Revision identifier, e.g. REV-00, REV-01. Used when a contract is revised.',
    )

    # ── Farm Project link ──────────────────────────────────────────────────────

    farm_project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Farm Project this Sales Order / Contract applies to.',
    )

    # ── Stat buttons ──────────────────────────────────────────────────────────

    farm_job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_farm_job_order_count',
    )

    farm_contract_count = fields.Integer(
        string='Contracts',
        compute='_compute_farm_contract_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('contract_stage')
    def _compute_is_contract_approved(self):
        for rec in self:
            rec.is_contract_approved = rec.contract_stage == 'approved'

    def _compute_farm_job_order_count(self):
        JobOrder = self.env['farm.job.order']
        for rec in self:
            rec.farm_job_order_count = JobOrder.search_count(
                [('sale_order_id', '=', rec.id)]
            )

    def _compute_farm_contract_count(self):
        FarmContract = self.env['farm.contract']
        for rec in self:
            rec.farm_contract_count = FarmContract.search_count(
                [('sale_order_id', '=', rec.id)]
            )

    # ────────────────────────────────────────────────────────────────────────
    # Contract stage transitions
    # ────────────────────────────────────────────────────────────────────────

    def action_contract_start(self):
        """New → In Progress."""
        self.filtered(
            lambda r: r.contract_stage == 'new'
        ).write({'contract_stage': 'in_progress'})

    def action_contract_submit(self):
        """In Progress → Submitted."""
        self.filtered(
            lambda r: r.contract_stage == 'in_progress'
        ).write({'contract_stage': 'submitted'})

    def action_contract_reply_with_notes(self):
        """Submitted / In Progress → Reply with Notes."""
        self.filtered(
            lambda r: r.contract_stage in ('submitted', 'in_progress')
        ).write({'contract_stage': 'reply_with_notes'})

    def action_contract_approve(self):
        """Submitted / Reply with Notes / In Progress → Approved.

        After approval, automatically generates Job Orders for every eligible
        order line (those with a linked BOQ Analysis Line and no existing JO).
        Creates a project.task hierarchy: Division task → Subdivision subtask → JO task.
        Non-blocking: skips ineligible lines with a warning log only.
        """
        approved = self.filtered(
            lambda r: r.contract_stage in ('submitted', 'reply_with_notes', 'in_progress')
        )
        approved.write({'contract_stage': 'approved'})
        # Auto-generate Job Orders for newly approved contracts
        for so in approved:
            if so.farm_project_id:
                so._auto_generate_job_orders()

    def action_contract_reject(self):
        """Any → Rejected."""
        self.filtered(
            lambda r: r.contract_stage not in ('approved', 'canceled', 'rejected')
        ).write({'contract_stage': 'rejected'})

    def action_contract_cancel(self):
        """Any → Canceled."""
        self.filtered(
            lambda r: r.contract_stage != 'canceled'
        ).write({'contract_stage': 'canceled'})

    def action_contract_reset_to_new(self):
        """Rejected → New (correction)."""
        self.filtered(
            lambda r: r.contract_stage == 'rejected'
        ).write({'contract_stage': 'new'})

    # ────────────────────────────────────────────────────────────────────────
    # Job Order generation
    # ────────────────────────────────────────────────────────────────────────

    def action_generate_farm_job_orders(self):
        """Generate Job Orders from each eligible order line.

        Prerequisites:
        - contract_stage must be 'approved'
        - farm_project_id must be set
        - Each eligible line must have boq_analysis_line_id set (for full
          BOQ traceability: analysis_id + boq_line_id are derived from it)

        Idempotent: lines already linked to a job_order_id are skipped.
        """
        self.ensure_one()

        # ── Gate: contract must be approved ───────────────────────────────────
        if not self.is_contract_approved:
            raise UserError(_(
                'Job Orders can only be generated from an Approved Contract.\n\n'
                'Current contract stage: %(stage)s\n\n'
                'Click "Approve Contract" to approve this Sales Order first.',
                stage=dict(
                    self._fields['contract_stage'].selection
                ).get(self.contract_stage, self.contract_stage),
            ))

        # ── Gate: project must be linked ──────────────────────────────────────
        if not self.farm_project_id:
            raise UserError(_(
                'A Farm Project must be linked to this Sales Order '
                'before generating Job Orders.\n\n'
                'Set the "Farm Project" field and save first.'
            ))

        # ── Find eligible lines ───────────────────────────────────────────────
        # Eligible = has product_id, has boq_analysis_line_id, no job_order_id yet
        eligible = self.order_line.filtered(
            lambda l: l.product_id and not l.job_order_id
        )

        if not eligible:
            already = self.order_line.filtered(lambda l: l.job_order_id)
            if already:
                raise UserError(_(
                    'All %d order line(s) already have Job Orders generated.\n'
                    'Use "View Job Orders" to open them.',
                    len(already),
                ))
            raise UserError(_(
                'No eligible order lines found.\n\n'
                'Add product lines to this Sales Order first.'
            ))

        # ── Validate BOQ links for all eligible lines before creating anything ─
        missing_analysis = eligible.filtered(lambda l: not l.boq_analysis_line_id)
        if missing_analysis:
            line_names = ', '.join(
                (l.name or l.product_id.name or 'Line %d' % i)
                for i, l in enumerate(missing_analysis, 1)
            )
            raise UserError(_(
                'The following %(count)d line(s) have no BOQ Analysis Line linked:\n\n'
                '%(lines)s\n\n'
                'Each Sales Order line must be linked to a BOQ Analysis Line '
                'for full traceability.\n\n'
                'Set the "Analysis Line" field on each line before generating Job Orders.',
                count=len(missing_analysis),
                lines=line_names,
            ))

        # ── Validate that each analysis line has a valid BOQ subitem ──────────
        invalid_boq = []
        for line in eligible:
            al = line.boq_analysis_line_id
            boq_line = al.subitem_id or al.boq_line_id
            if not boq_line:
                invalid_boq.append(line)
            elif boq_line.display_type:
                invalid_boq.append(line)
            elif not boq_line.parent_id:
                invalid_boq.append(line)

        if invalid_boq:
            names = ', '.join(
                (l.name or l.product_id.name or 'Line')
                for l in invalid_boq
            )
            raise UserError(_(
                '%(count)d line(s) are linked to invalid BOQ rows (structural sections '
                'instead of executable subitems):\n\n%(lines)s\n\n'
                'Link each line to a BOQ Analysis Line that references a real subitem '
                '(not a division/subdivision/sub-subdivision header).',
                count=len(invalid_boq),
                lines=names,
            ))

        # ── Create Job Orders ─────────────────────────────────────────────────
        JobOrder = self.env['farm.job.order']
        created_ids = []

        created_jos = self.env['farm.job.order']

        for sol in eligible:
            al = sol.boq_analysis_line_id
            boq_line = al.subitem_id or al.boq_line_id
            analysis = al.analysis_id

            jo = JobOrder.create({
                'project_id':           self.farm_project_id.id,
                'analysis_id':          analysis.id,
                'boq_line_id':          boq_line.id,
                'analysis_line_id':     al.id,
                'sale_order_id':        self.id,
                'sale_order_line_id':   sol.id,
                'boq_item_template_id': (
                    sol.boq_item_template_id.id
                    if sol.boq_item_template_id
                    else (boq_line.template_id.id if boq_line.template_id else False)
                ),
                'planned_qty':          sol.product_uom_qty or al.boq_qty or 1.0,
                'unit_id':              (
                    sol.product_uom.id
                    if sol.product_uom
                    else (al.unit_id.id if al.unit_id else False)
                ),
                'state':                'ready',
            })
            sol.job_order_id = jo.id
            created_ids.append(jo.id)
            created_jos |= jo

            # Load template components
            template = (
                sol.boq_item_template_id
                or (boq_line.template_id if boq_line else False)
            )
            if template:
                self._load_template_components(jo, template, jo.planned_qty)

            _logger.info(
                'GenerateFarmJOs [SO %s]: created JO %s for line "%s"',
                self.name, jo.name, sol.name or sol.product_id.name,
            )

        _logger.info(
            'GenerateFarmJOs [SO %s]: %d Job Order(s) created',
            self.name, len(created_ids),
        )

        # Create task hierarchy for newly created Job Orders
        if created_jos and self.farm_project_id and self.farm_project_id.odoo_project_id:
            self._create_job_order_task_hierarchy(created_jos)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_project_id': self.farm_project_id.id,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Auto-generation (called on contract approval)
    # ────────────────────────────────────────────────────────────────────────

    def _auto_generate_job_orders(self):
        """Auto-create Job Orders when contract_stage changes to 'approved'.

        Non-blocking: logs warnings instead of raising errors for ineligible
        lines.  Eligible lines: have product_id + boq_analysis_line_id + no
        existing job_order_id.  After each JO is created, template components
        are loaded and a project.task hierarchy is created.
        """
        self.ensure_one()
        if not self.is_contract_approved or not self.farm_project_id:
            return

        JobOrder = self.env['farm.job.order']
        eligible = self.order_line.filtered(
            lambda l: l.product_id and l.boq_analysis_line_id and not l.job_order_id
        )
        if not eligible:
            return

        created_jos = self.env['farm.job.order']

        for sol in eligible:
            al = sol.boq_analysis_line_id
            boq_line = al.subitem_id or al.boq_line_id

            # Skip invalid BOQ structure silently
            if not boq_line or boq_line.display_type or not boq_line.parent_id:
                _logger.warning(
                    'AutoGenerateJOs [SO %s]: skipping line "%s" — invalid BOQ structure',
                    self.name, sol.name or (sol.product_id.name if sol.product_id else 'unknown'),
                )
                continue

            try:
                jo = JobOrder.create({
                    'project_id':           self.farm_project_id.id,
                    'analysis_id':          al.analysis_id.id,
                    'boq_line_id':          boq_line.id,
                    'analysis_line_id':     al.id,
                    'sale_order_id':        self.id,
                    'sale_order_line_id':   sol.id,
                    'boq_item_template_id': (
                        sol.boq_item_template_id.id
                        if sol.boq_item_template_id
                        else (boq_line.template_id.id if boq_line.template_id else False)
                    ),
                    'planned_qty':          sol.product_uom_qty or al.boq_qty or 1.0,
                    'unit_id':              (
                        sol.product_uom.id if sol.product_uom
                        else (al.unit_id.id if al.unit_id else False)
                    ),
                    'state': 'ready',
                })
                sol.job_order_id = jo.id
                created_jos |= jo

                # Load template components
                template = (
                    sol.boq_item_template_id
                    or (boq_line.template_id if boq_line else False)
                )
                if template:
                    self._load_template_components(jo, template, jo.planned_qty)

                _logger.info(
                    'AutoGenerateJOs [SO %s]: created JO %s for line "%s"',
                    self.name, jo.name, sol.name or sol.product_id.name,
                )
            except Exception as exc:
                _logger.warning(
                    'AutoGenerateJOs [SO %s]: failed for line "%s": %s',
                    self.name,
                    sol.name or (sol.product_id.name if sol.product_id else 'unknown'),
                    exc,
                )

        # Build task hierarchy for created JOs
        if created_jos and self.farm_project_id.odoo_project_id:
            self._create_job_order_task_hierarchy(created_jos)

        _logger.info(
            'AutoGenerateJOs [SO %s]: %d Job Order(s) auto-created on contract approval',
            self.name, len(created_jos),
        )

    # ────────────────────────────────────────────────────────────────────────
    # Template component loader
    # ────────────────────────────────────────────────────────────────────────

    def _load_template_components(self, jo, template, main_qty):
        """Populate a Job Order with components from a BOQ item template.

        Materials  → farm.material.consumption records (planned lines)
        Labour     → instruction_notes summary (employee unknown at this stage)
        Equipment  → equipment_notes summary
        Tools      → tool_notes summary
        Subcontractors → subcontractor_notes summary
        Overhead   → notes summary
        """
        tmpl_qty = template.quantity or 1.0
        Material = self.env['farm.material.consumption']

        # ── Materials ────────────────────────────────────────────────────────
        existing_products = set(jo.material_ids.mapped('product_id').ids)
        for mat in template.material_ids:
            if not mat.product_id:
                continue
            if mat.product_id.id in existing_products:
                continue
            ratio = (mat.quantity or 1.0) / tmpl_qty
            Material.create({
                'job_order_id': jo.id,
                'product_id':   mat.product_id.id,
                'description':  mat.description or mat.product_id.name,
                'uom_id':       (mat.uom_id or mat.product_id.uom_id).id,
                'planned_qty':  round(main_qty * ratio, 4),
                'unit_cost':    mat.unit_price or 0.0,
            })

        # ── Labour → instruction notes (employee not known at auto-creation) ─
        if template.labor_ids:
            lines = ['[Labour from template: %s]' % template.name]
            for lab in template.labor_ids:
                ratio = (lab.hours or 1.0) / tmpl_qty
                lines.append('  • %s — %.2f hrs @ %.4f/hr' % (
                    lab.description or '',
                    round(main_qty * ratio, 2),
                    lab.cost_per_hour or 0.0,
                ))
            labour_text = '\n'.join(lines)
            jo.instruction_notes = (
                (jo.instruction_notes + '\n\n' if jo.instruction_notes else '') + labour_text
            )

        # ── Equipment → equipment_notes ───────────────────────────────────────
        if template.equipment_ids:
            lines = ['[Equipment from template: %s]' % template.name]
            for eq in template.equipment_ids:
                label = eq.description or (eq.product_id.name if eq.product_id else '')
                lines.append('  • %s' % label)
            eq_text = '\n'.join(lines)
            jo.equipment_notes = (
                (jo.equipment_notes + '\n\n' if jo.equipment_notes else '') + eq_text
            )

        # ── Tools → tool_notes ────────────────────────────────────────────────
        if template.tools_ids:
            lines = ['[Tools from template: %s]' % template.name]
            for t in template.tools_ids:
                label = t.description or (t.product_id.name if t.product_id else '')
                lines.append('  • %s' % label)
            tool_text = '\n'.join(lines)
            jo.tool_notes = (
                (jo.tool_notes + '\n\n' if jo.tool_notes else '') + tool_text
            )

        # ── Subcontractors → subcontractor_notes ──────────────────────────────
        if template.subcontractor_ids:
            lines = ['[Subcontractors from template: %s]' % template.name]
            for sub in template.subcontractor_ids:
                label = sub.description or (sub.product_id.name if sub.product_id else '')
                lines.append('  • %s' % label)
            sub_text = '\n'.join(lines)
            jo.subcontractor_notes = (
                (jo.subcontractor_notes + '\n\n' if jo.subcontractor_notes else '') + sub_text
            )

        # ── Overhead/Others → notes ───────────────────────────────────────────
        if template.overhead_ids:
            lines = ['[Overhead/Others from template: %s]' % template.name]
            for oh in template.overhead_ids:
                ratio = (oh.quantity or 1.0) / tmpl_qty
                lines.append('  • %s — qty %.2f, unit cost %.4f' % (
                    oh.name or '',
                    round(main_qty * ratio, 2),
                    oh.unit_price or 0.0,
                ))
            oh_text = '\n'.join(lines)
            jo.notes = (
                (jo.notes + '\n\n' if jo.notes else '') + oh_text
            )

    # ────────────────────────────────────────────────────────────────────────
    # Task hierarchy builder
    # ────────────────────────────────────────────────────────────────────────

    def _create_job_order_task_hierarchy(self, job_orders):
        """Create project.task hierarchy for a set of Job Orders.

        Division   → parent task (no job_order_id)
        Subdivision → child task of division (no job_order_id)
        Job Order  → child task of subdivision (job_order_id set)

        Existing division/subdivision tasks are reused (find-or-create).
        Skipped silently when odoo_project_id is not set.
        """
        odoo_project = self.farm_project_id.odoo_project_id
        if not odoo_project:
            return

        Task = self.env['project.task']
        division_tasks = {}     # division.id → project.task
        subdivision_tasks = {}  # (division.id, subdivision.id) → project.task

        for jo in job_orders:
            division = jo.division_id
            subdivision = jo.subdivision_id

            # ── Division task ─────────────────────────────────────────────────
            if division and division.id not in division_tasks:
                div_task = Task.search([
                    ('project_id', '=', odoo_project.id),
                    ('name', '=', division.name),
                    ('parent_id', '=', False),
                ], limit=1)
                if not div_task:
                    div_task = Task.create({
                        'project_id': odoo_project.id,
                        'name': division.name,
                    })
                division_tasks[division.id] = div_task

            div_task = division_tasks.get(division.id if division else None)

            # ── Subdivision task ──────────────────────────────────────────────
            if subdivision and div_task:
                key = (division.id, subdivision.id)
                if key not in subdivision_tasks:
                    sub_task = Task.search([
                        ('project_id', '=', odoo_project.id),
                        ('name', '=', subdivision.name),
                        ('parent_id', '=', div_task.id),
                    ], limit=1)
                    if not sub_task:
                        sub_task = Task.create({
                            'project_id': odoo_project.id,
                            'name': subdivision.name,
                            'parent_id': div_task.id,
                        })
                    subdivision_tasks[key] = sub_task
                parent_task = subdivision_tasks[(division.id, subdivision.id)]
            else:
                parent_task = div_task

            # ── Job Order task ────────────────────────────────────────────────
            if parent_task:
                Task.create({
                    'project_id':   odoo_project.id,
                    'name':         jo.name,
                    'parent_id':    parent_task.id,
                    'job_order_id': jo.id,
                })

    def action_view_farm_job_orders(self):
        """Open all Job Orders linked to this Sales Order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_project_id': (
                    self.farm_project_id.id if self.farm_project_id else False
                ),
            },
        }

    def action_create_farm_contract(self):
        """Create a Farm Contract from this approved Sale Order.

        Prerequisites:
        - contract_stage must be 'approved'
        - farm_project_id must be set
        - No contract already linked to this Sale Order (idempotent guard)
        """
        self.ensure_one()

        if not self.is_contract_approved:
            raise UserError(_(
                'A Farm Contract can only be created from an Approved Sale Order.\n\n'
                'Current contract stage: %(stage)s\n\n'
                'Click "Approve Contract" to approve this Sales Order first.',
                stage=dict(
                    self._fields['contract_stage'].selection
                ).get(self.contract_stage, self.contract_stage),
            ))

        if not self.farm_project_id:
            raise UserError(_(
                'A Farm Project must be linked to this Sales Order '
                'before creating a Farm Contract.\n\n'
                'Set the "Farm Project" field and save first.'
            ))

        existing = self.env['farm.contract'].search(
            [('sale_order_id', '=', self.id)], limit=1
        )
        if existing:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Contract — %s') % self.name,
                'res_model': 'farm.contract',
                'view_mode': 'form',
                'res_id': existing.id,
                'target': 'current',
            }

        contract = self.env['farm.contract'].with_context(
            from_sale_contract_approved=True
        ).create({
            'project_id': self.farm_project_id.id,
            'sale_order_id': self.id,
            'contract_amount': self.amount_total,
            'date_start': self.date_order.date() if self.date_order else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract — %s') % self.name,
            'res_model': 'farm.contract',
            'view_mode': 'form',
            'res_id': contract.id,
            'target': 'current',
        }

    def action_view_farm_contracts(self):
        """Open all Farm Contracts linked to this Sales Order."""
        self.ensure_one()
        contracts = self.env['farm.contract'].search(
            [('sale_order_id', '=', self.id)]
        )
        if len(contracts) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Contract — %s') % self.name,
                'res_model': 'farm.contract',
                'view_mode': 'form',
                'res_id': contracts.id,
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts — %s') % self.name,
            'res_model': 'farm.contract',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
        }


class SaleOrderLineContract(models.Model):
    """Extend sale.order.line with BOQ traceability for JO generation.

    Each order line can be linked to one farm.boq.analysis.line.
    From that link, the JO generation derives analysis_id and boq_line_id
    (both required by farm.job.order).

    job_order_id is set automatically when the line's JO is generated
    and acts as an idempotency marker.
    """

    _inherit = 'sale.order.line'

    boq_analysis_line_id = fields.Many2one(
        'farm.boq.analysis.line',
        string='Analysis Line',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            'Link to the BOQ Analysis Line this order line prices.\n\n'
            'Required for Job Order generation (provides analysis_id + boq_line_id).'
        ),
    )

    # Read-only mirror for display convenience
    boq_line_display_code = fields.Char(
        string='BOQ Code',
        related='boq_analysis_line_id.display_code',
        readonly=True,
    )

    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        ondelete='set null',
        readonly=True,
        copy=False,
        index=True,
        help='Populated automatically after Job Orders are generated from this Sales Order.',
    )

    boq_item_template_id = fields.Many2one(
        'farm.boq.line.template',
        string='BOQ Item Template',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            'Optional: BOQ template for this line.\n'
            'When set, materials/notes are loaded into the generated Job Order automatically.'
        ),
    )
