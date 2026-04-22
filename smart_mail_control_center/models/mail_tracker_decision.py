"""
SMART MAIL CONTROL CENTER — Decision Engine
=============================================

Transforms mail.tracker.record from a passive tracker into an active
decision engine.  For every email the engine computes:

  priority_score      — 0-100 composite urgency index
  recommended_action  — next-best-action for the responsible team
  route_confidence    — how certain is the type classification (%)
  link_confidence     — how certain is the project link (%)
  decision_reason     — HTML rationale shown in the form view

Pipeline position:
  _classify_mail_type() → _detect_and_link_project() → _route_to_document()
  → _auto_assign_by_role() → [DECISION ENGINE] → _smart_escalate_if_needed()
  → _auto_create_task_if_needed()

Computed fields (stored) update automatically whenever their dependencies
change; _smart_escalate_if_needed() is called explicitly from
run_full_auto_processing() since it has side-effects (state change).
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Minimum priority score that triggers immediate escalation
_ESCALATION_THRESHOLD = 70
# Deadline horizon for "critical" classification (calendar days)
_DEADLINE_CRITICAL_DAYS = 3

# ── mail_type → recommended_action ────────────────────────────────────────────
_TYPE_ACTION_MAP = {
    'claim':     'assign_to_qs',
    'invoice':   'assign_to_finance',
    'contract':  'assign_to_legal',
    'rfq':       'procurement',
    'variation': 'assign_to_qs',
    'boq':       'review',
    'approval':  'escalate',
    'delay':     'escalate',
}

# ── Keywords per type — mirrors auto_link for confidence scoring ───────────────
_TYPE_KW_MAP = {
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

# ── Bootstrap color per recommended_action ────────────────────────────────────
_ACTION_BADGE = {
    'escalate':          'danger',
    'assign_to_qs':      'warning',
    'assign_to_finance': 'info',
    'assign_to_legal':   'primary',
    'procurement':       'secondary',
    'review':            'light border',
    'archive':           'light border',
    'general':           'light border',
}


def _badge(action):
    return _ACTION_BADGE.get(action or 'general', 'light border')


# ══════════════════════════════════════════════════════════════════════════════

class MailTrackerDecision(models.Model):
    """Decision Engine — fields and logic for mail.tracker.record."""

    _inherit = 'mail.tracker.record'

    # ── Part 1: Decision Fields ────────────────────────────────────────────────

    priority_score = fields.Float(
        string='Priority Score',
        compute='_compute_priority_score',
        store=True,
        digits=(6, 1),
        help='0–100 composite urgency score. '
             'Factors: importance (+50/+30), requires_action (+20), '
             'critical deadline (+20–30), delay/claim type (+30).',
    )
    recommended_action = fields.Selection(
        selection=[
            ('assign_to_qs',      'Assign to QS / Quantity Surveyor'),
            ('assign_to_finance', 'Assign to Finance / Accounting'),
            ('assign_to_legal',   'Assign to Legal / Contracts'),
            ('procurement',       'Forward to Procurement'),
            ('escalate',          'Escalate to Management'),
            ('review',            'Review Required'),
            ('archive',           'Low Priority — Archive'),
            ('general',           'No Action Required'),
        ],
        string='Recommended Action',
        compute='_compute_recommended_action',
        store=True,
        tracking=True,
        help='AI-recommended next action derived from type, importance, and urgency.',
    )
    route_confidence = fields.Float(
        string='Route Confidence (%)',
        compute='_compute_route_confidence',
        store=True,
        digits=(6, 1),
        help='Confidence in the email-type classification (0–100%). '
             'Based on keyword match ratio for the detected type.',
    )
    link_confidence = fields.Float(
        string='Link Confidence (%)',
        compute='_compute_link_confidence',
        store=True,
        digits=(6, 1),
        help='Confidence in the project link (0–100%). '
             'Higher for farm.project exact matches.',
    )
    decision_reason = fields.Html(
        string='Decision Rationale',
        compute='_compute_decision_reason',
        store=True,
        readonly=True,
        sanitize=True,
        help='Human-readable explanation of the AI decision.',
    )

    # ── Part 2: Priority Score ─────────────────────────────────────────────────

    @api.depends(
        'mail_type', 'importance_level', 'requires_action',
        'parsed_deadline', 'has_attachment',
    )
    def _compute_priority_score(self):
        today = fields.Date.today()
        for rec in self:
            score = 0.0

            # Importance
            if rec.importance_level == 'very_high':
                score += 50
            elif rec.importance_level == 'high':
                score += 30
            elif rec.importance_level == 'normal':
                score += 10

            # Requires action flag
            if rec.requires_action:
                score += 20

            # Deadline proximity
            if rec.parsed_deadline:
                days_left = (rec.parsed_deadline - today).days
                if days_left <= _DEADLINE_CRITICAL_DAYS:
                    score += 20
                if days_left <= 1:
                    score += 10   # extra for tomorrow / today
                if days_left < 0:
                    score += 10   # already past deadline

            # Type weighting
            if rec.mail_type in ('delay', 'claim'):
                score += 30
            elif rec.mail_type in ('contract', 'approval', 'variation'):
                score += 15
            elif rec.mail_type in ('invoice', 'rfq'):
                score += 8

            # Attachments add mild weight (real documents present)
            if rec.has_attachment:
                score += 5

            rec.priority_score = min(score, 100.0)

    # ── Part 2: Recommended Action ────────────────────────────────────────────

    @api.depends('mail_type', 'importance_level', 'priority_score')
    def _compute_recommended_action(self):
        escalate_levels = {'very_high', 'high'}
        for rec in self:
            mt = rec.mail_type or 'general'

            # Escalation conditions — checked first
            if mt == 'delay' and rec.importance_level in escalate_levels:
                rec.recommended_action = 'escalate'
            elif rec.priority_score >= _ESCALATION_THRESHOLD:
                rec.recommended_action = 'escalate'
            elif mt in _TYPE_ACTION_MAP:
                rec.recommended_action = _TYPE_ACTION_MAP[mt]
            else:
                rec.recommended_action = 'general'

    # ── Part 3: Route Confidence ───────────────────────────────────────────────

    @api.depends('mail_type', 'name', 'body_preview', 'attachment_ids.name')
    def _compute_route_confidence(self):
        for rec in self:
            mt = rec.mail_type or 'general'
            if mt == 'general':
                rec.route_confidence = 0.0
                continue

            kws = _TYPE_KW_MAP.get(mt, [])
            if not kws:
                rec.route_confidence = 50.0
                continue

            corpus = ' '.join(filter(None, [
                rec.name or '',
                rec.body_preview or '',
                ' '.join(rec.attachment_ids.mapped('name') or []),
            ])).lower()

            matched = sum(1 for kw in kws if kw in corpus)

            if matched == 0:
                # Classified by auto_link but keywords no longer in cached corpus
                confidence = 30.0
            else:
                # Base 30 (any match), scale remaining 70 by ratio
                confidence = 30.0 + (matched / len(kws)) * 70.0

            rec.route_confidence = min(round(confidence, 1), 100.0)

    # ── Part 3: Link Confidence ───────────────────────────────────────────────

    @api.depends('linked_model', 'linked_res_id', 'linked_doc_name', 'parsed_project_name')
    def _compute_link_confidence(self):
        for rec in self:
            if not rec.linked_res_id:
                rec.link_confidence = 0.0
                continue

            if rec.linked_model == 'farm.project':
                base = 95.0
            elif rec.linked_model == 'project.project':
                base = 80.0
            else:
                # Linked to a specific farm document (BOQ, invoice, etc.)
                base = 88.0

            # Bonus when parsed name matches linked name
            parsed = (rec.parsed_project_name or '').strip().lower()
            linked  = (rec.linked_doc_name or '').strip().lower()
            if parsed and linked:
                if parsed == linked or parsed in linked or linked in parsed:
                    base = min(base + 5.0, 100.0)

            rec.link_confidence = base

    # ── Part 6: Decision Reason (HTML rationale) ──────────────────────────────

    @api.depends(
        'priority_score', 'recommended_action', 'route_confidence',
        'link_confidence', 'mail_type', 'importance_level',
        'parsed_deadline', 'parsed_keywords', 'linked_doc_name',
        'has_attachment', 'requires_action',
    )
    def _compute_decision_reason(self):
        today = fields.Date.today()

        action_map = dict(self._fields['recommended_action'].selection or [])
        type_map   = dict(self._fields['mail_type'].selection or [])

        for rec in self:
            lines = ['<div class="smcc-ai-reasoning">']

            # — Recommended action line ———————————————————————————————————————
            action_label = action_map.get(rec.recommended_action or 'general', 'No Action Required')
            type_label   = type_map.get(rec.mail_type or 'general', 'General')
            conf_cls     = 'success' if rec.route_confidence >= 75 else ('warning' if rec.route_confidence >= 50 else 'danger')

            lines.append(
                f'<p>'
                f'<strong>Decision:</strong> '
                f'<span class="badge bg-{_badge(rec.recommended_action)} text-dark">{action_label}</span>'
                f' — Email classified as <em>{type_label}</em> '
                f'<span class="badge bg-{conf_cls}">{rec.route_confidence:.0f}% confidence</span>'
                f'</p>'
            )

            # — Priority score breakdown ———————————————————————————————————————
            parts = []
            if rec.importance_level == 'very_high':
                parts.append('very high importance <span class="text-danger">(+50)</span>')
            elif rec.importance_level == 'high':
                parts.append('high importance <span class="text-warning">(+30)</span>')
            elif rec.importance_level == 'normal':
                parts.append('normal importance (+10)')
            if rec.requires_action:
                parts.append('requires action (+20)')
            if rec.parsed_deadline:
                dl = (rec.parsed_deadline - today).days
                if dl <= _DEADLINE_CRITICAL_DAYS:
                    parts.append(f'deadline in {dl} day(s) <span class="text-danger">(+20)</span>')
                if dl <= 1:
                    parts.append('very imminent deadline <span class="text-danger">(+10)</span>')
                if dl < 0:
                    parts.append('deadline already passed <span class="text-danger">(+10)</span>')
            if rec.mail_type in ('delay', 'claim'):
                parts.append(f'{type_label} type <span class="text-danger">(+30)</span>')
            elif rec.mail_type in ('contract', 'approval', 'variation'):
                parts.append(f'{type_label} type (+15)')
            elif rec.mail_type in ('invoice', 'rfq'):
                parts.append(f'{type_label} type (+8)')
            if rec.has_attachment:
                parts.append('attachments present (+5)')

            score_cls = 'danger' if rec.priority_score >= 70 else ('warning' if rec.priority_score >= 40 else 'secondary')
            breakdown = '; '.join(parts) if parts else 'no scoring factors applied'
            lines.append(
                f'<p>'
                f'<strong>Priority Score: '
                f'<span class="badge bg-{score_cls}">{rec.priority_score:.0f}/100</span></strong>'
                f' — {breakdown}'
                f'</p>'
            )

            # — Project link ——————————————————————————————————————————————————
            if rec.linked_doc_name and rec.link_confidence > 0:
                lc_cls = 'success' if rec.link_confidence >= 90 else ('warning' if rec.link_confidence >= 70 else 'danger')
                lines.append(
                    f'<p>'
                    f'<strong>Project:</strong> '
                    f'<em>{rec.linked_doc_name}</em> '
                    f'<span class="badge bg-{lc_cls}">{rec.link_confidence:.0f}% confidence</span>'
                    f'</p>'
                )
            else:
                lines.append(
                    '<p><strong>Project:</strong> '
                    '<span class="text-muted">No project detected in email content.</span></p>'
                )

            # — Keywords ———————————————————————————————————————————————————————
            if rec.parsed_keywords:
                lines.append(
                    f'<p><strong>Keywords:</strong> '
                    f'<span class="text-muted fst-italic">{rec.parsed_keywords}</span></p>'
                )

            # — Deadline ———————————————————————————————————————————————————————
            if rec.parsed_deadline:
                dl = (rec.parsed_deadline - today).days
                dl_cls = 'danger' if dl <= 1 else ('warning' if dl <= _DEADLINE_CRITICAL_DAYS else 'info')
                lines.append(
                    f'<p><strong>Deadline detected:</strong> '
                    f'<span class="badge bg-{dl_cls}">{rec.parsed_deadline} '
                    f'({dl} day(s) remaining)</span></p>'
                )

            lines.append('</div>')
            rec.decision_reason = '\n'.join(lines)

    # ── Part 4: Smart Escalation ──────────────────────────────────────────────

    def _smart_escalate_if_needed(self):
        """
        Immediately set state = 'escalated' when ANY critical condition is met:
          - priority_score >= _ESCALATION_THRESHOLD  (default 70)
          - delay type  AND  importance in {high, very_high}
          - parsed_deadline within _DEADLINE_CRITICAL_DAYS

        Only acts on new / assigned records (idempotent).
        """
        if self.state in ('escalated', 'done', 'archived'):
            return

        today = fields.Date.today()
        trigger = None

        if self.priority_score >= _ESCALATION_THRESHOLD:
            trigger = f'priority score {self.priority_score:.0f} ≥ {_ESCALATION_THRESHOLD}'
        elif self.mail_type == 'delay' and self.importance_level in ('high', 'very_high'):
            trigger = f'delay notice — importance: {self.importance_level}'
        elif self.parsed_deadline:
            days_left = (self.parsed_deadline - today).days
            if days_left <= _DEADLINE_CRITICAL_DAYS:
                trigger = f'deadline in {days_left} day(s) ({self.parsed_deadline})'

        if not trigger:
            return

        action_map = dict(self._fields['recommended_action'].selection or [])
        action_label = action_map.get(self.recommended_action or '', '')

        try:
            self.write({'state': 'escalated'})
            self.message_post(
                body=(
                    f'<strong>⚡ Decision Engine — Auto-Escalated</strong><br/>'
                    f'<strong>Trigger:</strong> {trigger}<br/>'
                    f'<strong>Priority Score:</strong> {self.priority_score:.0f}/100<br/>'
                    f'<strong>Recommended Action:</strong> {action_label}'
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            _logger.info(
                'Mail Tracker Decision Engine: escalated record %d — %s',
                self.id, trigger,
            )
        except Exception as exc:
            _logger.warning(
                'Mail Tracker Decision Engine: escalation failed for record %d: %s',
                self.id, exc,
            )
