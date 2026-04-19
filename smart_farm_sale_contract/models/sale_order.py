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

    # ── Stat button ───────────────────────────────────────────────────────────

    farm_job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_farm_job_order_count',
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
        """Submitted / Reply with Notes / In Progress → Approved."""
        self.filtered(
            lambda r: r.contract_stage in ('submitted', 'reply_with_notes', 'in_progress')
        ).write({'contract_stage': 'approved'})

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

        for sol in eligible:
            al = sol.boq_analysis_line_id
            boq_line = al.subitem_id or al.boq_line_id
            analysis = al.analysis_id

            jo = JobOrder.create({
                'project_id':         self.farm_project_id.id,
                'analysis_id':        analysis.id,
                'boq_line_id':        boq_line.id,
                'analysis_line_id':   al.id,
                'sale_order_id':      self.id,
                'sale_order_line_id': sol.id,
                'planned_qty':        sol.product_uom_qty or al.boq_qty or 1.0,
                'unit_id':            (
                    sol.product_uom.id
                    if sol.product_uom
                    else (al.unit_id.id if al.unit_id else False)
                ),
                'state':              'ready',
            })
            sol.job_order_id = jo.id
            created_ids.append(jo.id)

            _logger.info(
                'GenerateFarmJOs [SO %s]: created JO %s for line "%s"',
                self.name, jo.name, sol.name or sol.product_id.name,
            )

        _logger.info(
            'GenerateFarmJOs [SO %s]: %d Job Order(s) created',
            self.name, len(created_ids),
        )

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
