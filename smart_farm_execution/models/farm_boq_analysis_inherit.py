import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FarmBoqAnalysisExecution(models.Model):
    """Execution extension for BOQ Analysis Documents.

    Adds:
    - job_order_count stat button
    - action_generate_job_orders(): creates Job Orders from all lines of an
      approved Analysis document.  Line-level analysis_state is NOT checked —
      document approval is the single gate (lines are individual pricing-review
      steps that most users never change from 'draft').
    - action_view_job_orders(): opens related Job Orders
    """

    _inherit = 'farm.boq.analysis'

    # ── Stat button ───────────────────────────────────────────────────────────
    job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_job_order_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('line_ids.job_order_ids')
    def _compute_job_order_count(self):
        JobOrder = self.env['farm.job.order']
        for rec in self:
            rec.job_order_count = JobOrder.search_count(
                [('analysis_id', '=', rec.id)]
            )

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_generate_job_orders(self):
        """Generate Job Orders from ALL valid lines of an approved Analysis.

        Gate: the Analysis document must be in state 'approved'.
        Eligible line: has a valid BOQ subitem reference (subitem_id or
            boq_line_id) AND does NOT already have a Job Order.
        Structural/empty lines (no BOQ ref) are silently skipped.
        Idempotent: already-linked lines are skipped without error.
        """
        self.ensure_one()

        # ── Gate: document must be approved ──────────────────────────────────
        if self.analysis_state != 'approved':
            raise UserError(_(
                'The BOQ Analysis must be approved before generating Job Orders.\n'
                'Current status: %s',
                dict(
                    self._fields['analysis_state'].selection
                ).get(self.analysis_state, self.analysis_state),
            ))

        all_lines = self.line_ids
        _logger.info(
            'GenerateJobOrders [%s]: %d analysis lines found',
            self.name, len(all_lines),
        )

        # ── Eligible lines ────────────────────────────────────────────────────
        # Requirements for a valid line:
        #   1. Has a real BOQ subitem reference (subitem_id or boq_line_id)
        #   2. That BOQ line is a real subitem: display_type=False AND parent_id set
        #   3. Does not already have a Job Order (idempotency)
        #
        # NOTE: line-level analysis_state is intentionally NOT checked.
        # The document being 'approved' is sufficient.
        def _is_valid_subitem(line):
            bl = line.subitem_id or line.boq_line_id
            if not bl:
                return False
            if bl.display_type:          # structural row — block
                return False
            if not bl.parent_id:         # root item without sub-subdivision — block
                return False
            return not line.job_order_ids

        eligible_lines = all_lines.filtered(_is_valid_subitem)

        # Sort by BOQ code so Job Orders are created in proper hierarchy order
        eligible_lines = eligible_lines.sorted(
            key=lambda l: (
                l.subitem_id.display_code or l.boq_line_id.display_code or ''
            )
        )

        _logger.info(
            'GenerateJobOrders [%s]: %d eligible lines (real subitems, no existing JO)',
            self.name, len(eligible_lines),
        )

        if not eligible_lines:
            already_linked = all_lines.filtered(
                lambda l: (l.subitem_id or l.boq_line_id) and l.job_order_ids
            )
            if already_linked:
                raise UserError(_(
                    'All %d analysis line(s) already have Job Orders.\n'
                    'Use "View Job Orders" to open them.',
                    len(already_linked),
                ))
            # Check whether any lines exist but point to structural rows
            structural = all_lines.filtered(
                lambda l: (l.subitem_id or l.boq_line_id)
                and (
                    (l.subitem_id or l.boq_line_id).display_type
                    or not (l.subitem_id or l.boq_line_id).parent_id
                )
            )
            if structural:
                raise UserError(_(
                    'No valid analysis lines found.\n\n'
                    '%d line(s) are linked to structural BOQ rows (sections / '
                    'subdivisions) instead of executable subitems.\n\n'
                    'Job Orders can only be generated from executable subitems.\n'
                    'Use "Refresh from BOQ" after adding real subitem rows to the BOQ.',
                    len(structural),
                ))
            raise UserError(_(
                'No valid analysis lines found.\n\n'
                'Make sure:\n'
                '• The BOQ has subitem rows (not just section headers)\n'
                '• The Analysis was refreshed from the BOQ\n'
                'Use "Refresh from BOQ" on the Analysis to re-sync lines.'
            ))

        # ── Create job orders in BOQ hierarchy order ──────────────────────────
        JobOrder = self.env['farm.job.order']
        created_ids = []
        skipped = 0

        for al in eligible_lines:
            boq_line = al.subitem_id or al.boq_line_id
            if not boq_line:
                skipped += 1
                _logger.warning(
                    'GenerateJobOrders [%s]: line "%s" (id=%d) has no BOQ ref — skipped',
                    self.name, al.name, al.id,
                )
                continue

            # Final guard: never create a JO from a structural row
            if boq_line.display_type or not boq_line.parent_id:
                skipped += 1
                _logger.warning(
                    'GenerateJobOrders [%s]: line "%s" BOQ ref is structural '
                    '(display_type=%r, parent=%r) — skipped',
                    self.name, al.name, boq_line.display_type, bool(boq_line.parent_id),
                )
                continue

            jo = JobOrder.create({
                'project_id':         self.project_id.id,
                'analysis_id':        self.id,
                'boq_line_id':        boq_line.id,
                'analysis_line_id':   al.id,
                'planned_qty':        al.boq_qty or 1.0,
                'unit_id':            al.unit_id.id if al.unit_id else False,
                'planned_start_date': boq_line.start_date or False,
                'planned_end_date':   boq_line.end_date or False,
                'state':              'ready',
            })
            created_ids.append(jo.id)

            # ── Auto-populate planned materials from BOQ line template ────────
            # Safe: only if the BOQ subitem has a template with material lines.
            # Idempotent: after creation the JO has no materials yet, so no
            # duplicate check needed here.
            self._auto_create_materials_from_template(jo, boq_line)

        _logger.info(
            'GenerateJobOrders [%s]: created=%d  skipped=%d',
            self.name, len(created_ids), skipped,
        )

        if not created_ids:
            raise UserError(_(
                'No Job Orders were created.\n'
                '%d line(s) were skipped because their BOQ reference could not be resolved.',
                skipped,
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('analysis_id', '=', self.id)],
        }

    def action_view_job_orders(self):
        """Open all Job Orders for this analysis."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('analysis_id', '=', self.id)],
            'context': {
                'default_analysis_id': self.id,
                'default_project_id':  self.project_id.id,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _auto_create_materials_from_template(self, job_order, boq_line):
        """Create planned material consumption lines from the BOQ line template.

        Called immediately after a Job Order is created via
        action_generate_job_orders().

        Rules:
        - Only runs when boq_line.template_id exists and has material_ids.
        - Only creates lines for materials that have a product_id set.
        - Failures are logged as warnings, not raised — generation must
          not be blocked by missing template data.
        """
        template = boq_line.template_id if boq_line else False
        if not template or not template.material_ids:
            return

        Material = self.env['farm.material.consumption']
        created = 0
        for mat in template.material_ids:
            if not mat.product_id:
                continue
            try:
                Material.create({
                    'job_order_id': job_order.id,
                    'product_id':   mat.product_id.id,
                    'description':  mat.description or mat.product_id.name,
                    'uom_id':       (mat.uom_id or mat.product_id.uom_id).id,
                    'planned_qty':  mat.quantity or 1.0,
                    'unit_cost':    mat.unit_price or 0.0,
                })
                created += 1
            except Exception as e:
                _logger.warning(
                    '_auto_create_materials_from_template: '
                    'JO %s — failed to create material line for product "%s": %s',
                    job_order.name, mat.product_id.name, e,
                )
        if created:
            _logger.info(
                '_auto_create_materials_from_template: '
                'JO %s — %d planned material line(s) created from template "%s"',
                job_order.name, created, template.name,
            )
