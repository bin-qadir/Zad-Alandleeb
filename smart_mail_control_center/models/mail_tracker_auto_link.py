"""
SMART MAIL CONTROL CENTER — Auto-Link Engine
=============================================

Extends mail.tracker.record with intelligent auto-processing:

  Part 1 — Project Detection
    Scans subject + body for farm.project / project.project names.
    Sets project_id (and linked_model/res_id for farm.project).

  Part 2 — Document Type Classification
    Detects mail_type (BOQ / Claim / Invoice / Contract / Variation /
    RFQ / Approval) from subject + body keywords.

  Part 3 — Document Routing
    When mail_type is identified, tries to locate the actual farm document
    (farm.boq, farm.job.order, farm.contract, account.move) for the
    project and stores a generic link (linked_model, linked_res_id).

  Part 4 — Auto Task Creation
    If importance_level ∈ {very_high, high} AND email requires_action
    AND a project is linked → automatically creates project.task.

  Part 5 — Attachment Smart Linking
    Inspects attachment filenames; writes a short description tag
    ('Type: invoice', 'Type: drawing', …) on each ir.attachment.

Master entry-point:  record.run_full_auto_processing()
Called automatically after every sync + importance-rule pass.
"""
import logging
import re

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── Mail-type keyword map (first match wins, evaluated top-to-bottom) ─────────
# Keys must match the mail_type selection values defined in the field below.
_TYPE_KEYWORDS = {
    'variation': [
        'variation order', 'change order', 'vco', ' vo ', 'scope change',
        'variation request', 'أمر تغيير', 'تعديل عقد',
    ],
    'claim': [
        'payment claim', 'progress claim', 'interim claim', 'claim certificate',
        'claim no', 'payment application', 'مطالبة', 'مستخلص',
    ],
    'boq': [
        'bill of quantities', 'boq', 'cost structure', 'bill of material',
        'schedule of rates', 'كميات', 'جدول الكميات',
    ],
    'invoice': [
        'tax invoice', 'proforma invoice', 'invoice no', 'invoice #',
        'remittance', 'billing statement', 'receipt no', 'فاتورة',
        'receipt', 'billing',
    ],
    'contract': [
        'subcontract', 'contract agreement', 'contract no', 'purchase order',
        'letter of award', 'عقد', 'اتفاقية', 'خطاب ترسية',
    ],
    'rfq': [
        'request for quotation', 'rfq', 'quotation no', 'price inquiry',
        'call for bids', 'طلب عرض سعر', 'عرض سعر',
    ],
    'approval': [
        'approval required', 'for approval', 'please approve', 'sign-off',
        'authorization required', 'endorsement', 'موافقة', 'اعتماد',
    ],
    'delay': [
        'delay notice', 'eot', 'extension of time', 'delay claim',
        'delayed works', 'delay notification', 'إشعار تأخير', 'تأخير أعمال',
        'تمديد مدة', 'تمديد العقد',
    ],
}

# ── Attachment filename → document type ───────────────────────────────────────
_ATTACHMENT_TAGS = [
    ('drawing',   ['drawing', 'plan', 'layout', 'architecture', 'cad', '.dwg', '.dxf']),
    ('boq',       ['boq', 'bill_of_quantities', 'bill of quantities', 'quantities']),
    ('invoice',   ['invoice', 'tax_invoice', 'receipt', 'billing']),
    ('contract',  ['contract', 'agreement', 'purchase_order', 'po_']),
    ('variation', ['variation', 'change_order', 'vo_']),
    ('claim',     ['claim', 'progress_claim', 'payment_claim', 'extract']),
]

# ── Document model routing ─────────────────────────────────────────────────────
# mail_type → (odoo model, display label)
_TYPE_MODEL_MAP = {
    'boq':      ('farm.boq',          'Cost Structure (BOQ)'),
    'claim':    ('farm.job.order',    'Job Order / Claim'),
    'invoice':  ('account.move',      'Invoice'),
    'contract': ('farm.contract',     'Contract'),
    'variation':('farm.boq',          'BOQ / Variation'),
}

# Importance levels that trigger auto-task creation
_AUTO_TASK_LEVELS = {'very_high', 'high'}
# mail_types that always require action
_ACTION_TYPES = {'claim', 'contract', 'approval', 'variation', 'invoice', 'delay'}


class MailTrackerAutoLink(models.Model):
    """Auto-link extension for mail.tracker.record."""

    _inherit = 'mail.tracker.record'

    # ── New fields ─────────────────────────────────────────────────────────────

    mail_type = fields.Selection(
        selection=[
            ('boq',       'BOQ'),
            ('claim',     'Claim'),
            ('invoice',   'Invoice'),
            ('contract',  'Contract'),
            ('variation', 'Variation Order'),
            ('rfq',       'RFQ / Quotation'),
            ('approval',  'Approval Request'),
            ('delay',     'Delay Notice / EOT'),
            ('general',   'General'),
        ],
        string='Email Type',
        default='general',
        tracking=True,
        index=True,
    )

    requires_action = fields.Boolean(
        string='Requires Action',
        compute='_compute_requires_action',
        store=True,
        help='True when the email is high-priority or is a claim/contract/approval type.',
    )

    auto_task_created = fields.Boolean(
        string='Auto-Task Created',
        tracking=True,
        help='True when a task was automatically generated for this email.',
    )

    # Generic document link (avoids hard model dependencies)
    linked_model = fields.Char(
        string='Linked Model',
        readonly=True,
        help='Odoo model name of the linked document (e.g. farm.project).',
    )
    linked_res_id = fields.Integer(
        string='Linked Record ID',
        readonly=True,
        index=True,
    )
    linked_doc_name = fields.Char(
        string='Linked Document',
        readonly=True,
        help='Display name of the linked document record.',
    )
    linked_doc_type = fields.Char(
        string='Document Type',
        readonly=True,
        help='Human-readable type of linked document (BOQ, Invoice, etc.)',
    )

    # ── Compute ────────────────────────────────────────────────────────────────

    @api.depends('importance_level', 'mail_type', 'state')
    def _compute_requires_action(self):
        for rec in self:
            rec.requires_action = (
                rec.importance_level in _AUTO_TASK_LEVELS
                or rec.mail_type in _ACTION_TYPES
                or rec.state == 'escalated'
            )

    # ── Master processing method ───────────────────────────────────────────────

    def run_full_auto_processing(self):
        """
        Run the full auto-link pipeline on each record in self.

        Called by the sync engine after importance rules are applied.
        Safe to call multiple times (idempotent where possible).
        """
        for rec in self:
            try:
                rec._classify_mail_type()
                rec._detect_and_link_project()
                rec._route_to_document()
                rec._route_operational_links()    # Operational linking (typed)
                rec._auto_assign_by_role()
                rec._smart_escalate_if_needed()   # Decision Engine — before task
                rec._auto_create_task_if_needed()
                rec._smart_tag_attachments()
            except Exception as exc:
                _logger.warning(
                    'Mail Tracker AutoLink: failed on record %d: %s',
                    rec.id, exc, exc_info=True,
                )

    # ── Part 2: Document type classification ──────────────────────────────────

    def _classify_mail_type(self):
        """Detect mail_type from subject + body keywords."""
        if self.mail_type and self.mail_type != 'general':
            return  # Already classified

        corpus = ' '.join(filter(None, [
            self.name or '',
            self.body_preview or '',
        ])).lower()

        for mail_type, keywords in _TYPE_KEYWORDS.items():
            if any(kw in corpus for kw in keywords):
                self.mail_type = mail_type
                return

        # Keep 'general' if nothing matched
        if not self.mail_type:
            self.mail_type = 'general'

    # ── Part 1: Project detection ──────────────────────────────────────────────

    def _detect_and_link_project(self):
        """
        Try to match a farm.project (or project.project) from email content.

        Matching strategy:
          1. Email subject + body preview are combined into a search corpus.
          2. Each active farm.project name is tested as a substring.
          3. The first match with name length >= 4 characters wins.
          4. If found, set project_id (via odoo_project_id) and store the
             farm.project reference in linked_model / linked_res_id.
          5. Fall back to project.project name matching if farm.project
             produces no result.
        """
        # Skip if already linked to a project
        if self.project_id or self.linked_model == 'farm.project':
            return

        corpus = ' '.join(filter(None, [
            self.name or '',
            self.body_preview or '',
        ])).lower()

        if not corpus.strip():
            return

        # ── Try farm.project ──────────────────────────────────────────────────
        FarmProject = self.env.get('farm.project')
        if FarmProject is not None:
            farm_projects = FarmProject.sudo().search(
                [], order='name asc', limit=200
            )
            for fp in farm_projects:
                pname = (fp.name or '').strip()
                if len(pname) < 4:
                    continue
                if pname.lower() in corpus:
                    vals = {
                        'linked_model': 'farm.project',
                        'linked_res_id': fp.id,
                        'linked_doc_name': fp.name,
                    }
                    # Link to Odoo project too
                    if fp.odoo_project_id:
                        vals['project_id'] = fp.odoo_project_id.id
                    self.write(vals)
                    _logger.debug(
                        'Mail Tracker: linked record %d to farm.project "%s"',
                        self.id, fp.name,
                    )
                    return

        # ── Fall back to project.project ──────────────────────────────────────
        projects = self.env['project.project'].sudo().search(
            [('active', '=', True)], order='name asc', limit=200
        )
        for proj in projects:
            pname = (proj.name or '').strip()
            if len(pname) < 4:
                continue
            if pname.lower() in corpus:
                self.project_id = proj.id
                _logger.debug(
                    'Mail Tracker: linked record %d to project.project "%s"',
                    self.id, proj.name,
                )
                return

    # ── Part 3: Document routing ───────────────────────────────────────────────

    def _route_to_document(self):
        """
        When a mail_type is known AND a project is linked, attempt to locate
        the specific farm document (BOQ, Job Order, Contract, Invoice) and
        store its reference in linked_model / linked_res_id.

        Does NOT overwrite an existing link set by project detection.
        """
        if self.mail_type == 'general':
            return

        # Don't overwrite if already linked to a specific document
        if self.linked_model and self.linked_model not in ('farm.project',):
            return

        target_model, doc_type_label = _TYPE_MODEL_MAP.get(
            self.mail_type, (None, None)
        )
        if not target_model:
            return

        TargetModel = self.env.get(target_model)
        if TargetModel is None:
            return  # Model not installed

        # Build search domain scoped to project where possible
        domain = []
        farm_proj_id = (
            self.linked_res_id
            if self.linked_model == 'farm.project'
            else None
        )

        if farm_proj_id:
            # Most farm models have project_id field
            domain = [('project_id', '=', farm_proj_id)]
        elif self.project_id:
            domain = [('project_id', '=', self.project_id.id)]

        try:
            record = TargetModel.sudo().search(domain, limit=1, order='id desc')
            if record:
                self.write({
                    'linked_model': target_model,
                    'linked_res_id': record.id,
                    'linked_doc_name': record.display_name or target_model,
                    'linked_doc_type': doc_type_label,
                })
                _logger.debug(
                    'Mail Tracker: routed record %d (%s) → %s[%d]',
                    self.id, self.mail_type, target_model, record.id,
                )
        except Exception as exc:
            _logger.debug(
                'Mail Tracker: routing %s[%s] failed: %s',
                target_model, domain, exc,
            )

    # ── Part 4: Auto task creation ─────────────────────────────────────────────

    def _auto_create_task_if_needed(self):
        """
        Auto-create a project.task when:
          - importance_level ∈ {very_high, high}   AND
          - requires_action is True                AND
          - a project is linked (project_id set)   AND
          - not already converted to a task
        """
        if self.auto_task_created or self.converted_to_task:
            return
        if self.importance_level not in _AUTO_TASK_LEVELS:
            return
        if not self.requires_action:
            return
        if not self.project_id:
            return  # No project — skip (avoid orphan tasks)

        try:
            task_vals = {
                'name': f'[Email] {self.name}',
                'project_id': self.project_id.id,
                'priority': '1' if self.importance_level == 'very_high' else '0',
                'description': self._build_task_description(),
            }
            if self.assigned_user_id:
                task_vals['user_ids'] = [(4, self.assigned_user_id.id)]

            task = self.env['project.task'].sudo().create(task_vals)

            # Post a reference note on the task
            task.sudo().message_post(
                body=_(
                    'Auto-created from email tracker record <a href="#id=%(rid)s&model=mail.tracker.record">#%(rid)s</a>.<br/>'
                    'Type: <strong>%(mtype)s</strong> | Importance: <strong>%(imp)s</strong>',
                    rid=self.id,
                    mtype=dict(self._fields['mail_type'].selection).get(self.mail_type, ''),
                    imp=dict(self._fields['importance_level'].selection).get(self.importance_level, ''),
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

            self.write({
                'task_id': task.id,
                'converted_to_task': True,
                'auto_task_created': True,
                'state': 'in_progress',
            })

            _logger.info(
                'Mail Tracker: auto-created task %d for email record %d ("%s")',
                task.id, self.id, self.name,
            )
        except Exception as exc:
            _logger.warning(
                'Mail Tracker: auto-task creation failed for record %d: %s',
                self.id, exc,
            )

    def _build_task_description(self):
        """Build a structured HTML task description from email data."""
        lines = [
            '<h4>Email Details</h4>',
            f'<p><strong>From:</strong> {self.sender_name or ""} '
            f'&lt;{self.sender_email or ""}&gt;</p>',
            f'<p><strong>Date:</strong> {self.received_date}</p>',
            f'<p><strong>Type:</strong> {self.mail_type}</p>',
        ]
        if self.linked_doc_name:
            lines.append(f'<p><strong>Linked Document:</strong> {self.linked_doc_name}</p>')
        if self.body_preview:
            lines.append('<hr/><h4>Email Preview</h4>')
            lines.append(f'<p>{self.body_preview[:300]}</p>')
        return '\n'.join(lines)

    # ── Part 5: Attachment smart tagging ──────────────────────────────────────

    def _smart_tag_attachments(self):
        """
        Inspect attachment filenames and write a short document-type description
        on each ir.attachment that doesn't already have one.

        This is a soft tag (description field) — it does not move or copy
        the attachment; visibility follows the tracker record's access rules.
        """
        for att in self.attachment_ids:
            if att.description:
                continue  # Already tagged
            filename = (att.name or '').lower()
            for doc_type, keywords in _ATTACHMENT_TAGS:
                if any(kw in filename for kw in keywords):
                    try:
                        att.sudo().description = f'Type: {doc_type}'
                    except Exception:
                        pass  # Non-critical
                    break
