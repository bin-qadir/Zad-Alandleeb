"""
SMART MAIL CONTROL CENTER — Intelligence Engine
================================================

Extends mail.tracker.record with smart parsing, auto-assignment,
deadline detection, alert flags, and auto-escalation.

  Part A — Email Parsing
    Extracts parsed_project_name, parsed_keywords, parsed_deadline
    from subject + body + attachment filenames.

  Part B — Auto Assignment by Role
    Looks up mail.tracker.role.rule for the detected mail_type.
    Sets assigned_user_id when not already assigned.
    Falls back to admin if no rule matches.

  Part C — Alert Flags
    not_assigned  : open email with no assigned user
    needs_action  : requires_action=True AND state in new/assigned

  Part D — Auto Escalation (cron)
    High-importance emails not handled within threshold hours
    are automatically escalated to management.
"""
import logging
import re
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# ── Keyword master list for parsed_keywords extraction ────────────────────────
_KEYWORD_LIST = [
    # Document types
    'invoice', 'boq', 'contract', 'claim', 'variation', 'rfq', 'approval',
    'delay', 'drawing', 'payment', 'receipt', 'statement',
    # Arabic equivalents
    'فاتورة', 'عقد', 'مطالبة', 'تأخير', 'كميات', 'عرض سعر', 'موافقة',
    # Construction terms
    'subcontract', 'purchase order', 'letter of award', 'site instruction',
    'progress certificate', 'extension of time', 'eot', 'defects liability',
    'handover', 'completion', 'retention', 'mobilisation', 'demobilisation',
    # Finance terms
    'remittance', 'advance', 'withholding', 'vat', 'tax', 'deduction',
    # Priority markers
    'urgent', 'critical', 'immediate', 'asap', 'priority', 'deadline',
    'عاجل', 'مستعجل',
]

# ── Deadline detection patterns ────────────────────────────────────────────────
# Tries to find "by DD/MM/YYYY", "deadline: ...", "due date: ..." etc.
_DEADLINE_PATTERNS = [
    r'\bby\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
    r'\bdeadline[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
    r'\bdue\s*(?:date|by)[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
    r'\bresponse\s+(?:required|needed|by)[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
    r'\bno\s+later\s+than\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
    r'\bتاريخ\s+الاستحقاق[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b',
]

# Hours before high-importance email auto-escalates
_ESCALATION_THRESHOLD_HOURS = 24


class MailTrackerIntelligence(models.Model):
    """Intelligence engine extension for mail.tracker.record."""

    _inherit = 'mail.tracker.record'

    # ── Parsed extraction fields ───────────────────────────────────────────────

    parsed_project_name = fields.Char(
        string='Detected Project',
        compute='_compute_parsed_info',
        store=True,
        readonly=True,
        help='Project name detected from subject/body.',
    )
    parsed_keywords = fields.Char(
        string='Detected Keywords',
        compute='_compute_parsed_info',
        store=True,
        readonly=True,
        help='Comma-separated keywords found in the email.',
    )
    parsed_deadline = fields.Date(
        string='Detected Deadline',
        compute='_compute_parsed_info',
        store=True,
        readonly=True,
        help='Deadline date parsed from email body.',
    )

    # ── Alert flags ───────────────────────────────────────────────────────────

    not_assigned = fields.Boolean(
        string='Not Assigned',
        compute='_compute_alert_flags',
        store=True,
        help='True when the email is open but has no assigned user.',
    )
    needs_action = fields.Boolean(
        string='Needs Action',
        compute='_compute_alert_flags',
        store=True,
        help='True when requires_action=True and state is new or assigned.',
    )

    # ── Compute: parsed info ───────────────────────────────────────────────────

    @api.depends('name', 'body_preview', 'attachment_ids.name')
    def _compute_parsed_info(self):
        for rec in self:
            corpus = ' '.join(filter(None, [
                rec.name or '',
                rec.body_preview or '',
                ' '.join(rec.attachment_ids.mapped('name') or []),
            ]))
            rec.parsed_project_name = rec._extract_project_name(corpus)
            rec.parsed_keywords = rec._extract_keywords(corpus)
            rec.parsed_deadline = rec._detect_deadline(corpus)

    # ── Compute: alert flags ───────────────────────────────────────────────────

    @api.depends('assigned_user_id', 'state', 'requires_action')
    def _compute_alert_flags(self):
        open_states = {'new', 'assigned', 'in_progress', 'waiting', 'escalated'}
        for rec in self:
            rec.not_assigned = (
                not rec.assigned_user_id
                and rec.state in open_states
            )
            rec.needs_action = (
                rec.requires_action
                and rec.state in {'new', 'assigned'}
            )

    # ── Part A helpers: extraction ─────────────────────────────────────────────

    def _extract_project_name(self, corpus):
        """Return the first farm.project name found in corpus, or empty string."""
        if not corpus:
            return ''
        corpus_lower = corpus.lower()
        FarmProject = self.env.get('farm.project')
        if FarmProject is not None:
            farm_projects = FarmProject.sudo().search([], order='name asc', limit=200)
            for fp in farm_projects:
                pname = (fp.name or '').strip()
                if len(pname) >= 4 and pname.lower() in corpus_lower:
                    return fp.name
        # Fall back to project.project
        projects = self.env['project.project'].sudo().search(
            [('active', '=', True)], order='name asc', limit=200
        )
        for proj in projects:
            pname = (proj.name or '').strip()
            if len(pname) >= 4 and pname.lower() in corpus_lower:
                return proj.name
        return ''

    def _extract_keywords(self, corpus):
        """Return comma-separated keywords found in corpus."""
        if not corpus:
            return ''
        corpus_lower = corpus.lower()
        found = [kw for kw in _KEYWORD_LIST if kw in corpus_lower]
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for kw in found:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        return ', '.join(unique[:10])  # cap at 10

    def _detect_deadline(self, corpus):
        """Parse a deadline date from corpus. Returns date or False."""
        if not corpus:
            return False
        for pattern in _DEADLINE_PATTERNS:
            m = re.search(pattern, corpus, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                date = self._parse_date_string(raw)
                if date:
                    return date
        return False

    @staticmethod
    def _parse_date_string(raw):
        """Try multiple date formats, return date object or None."""
        import datetime
        separators = r'[/\-\.]'
        parts = re.split(separators, raw)
        if len(parts) != 3:
            return None
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if y < 100:
            y += 2000
        try:
            return datetime.date(y, m, d)
        except ValueError:
            pass
        # Maybe MM/DD/YYYY
        try:
            return datetime.date(y, d, m)
        except ValueError:
            return None

    # ── Part B: Auto assignment by role ───────────────────────────────────────

    def _auto_assign_by_role(self):
        """
        Look up mail.tracker.role.rule for self.mail_type.
        Set assigned_user_id if not already assigned.
        Falls back to res.users administrator if no rule matches.
        """
        if self.assigned_user_id:
            return  # Already assigned — don't overwrite

        mail_type = self.mail_type or 'general'

        # Search for a matching active rule
        rule = self.env['mail.tracker.role.rule'].sudo().search(
            [('mail_type', '=', mail_type), ('active', '=', True)],
            order='sequence asc',
            limit=1,
        )
        if not rule:
            # Try general fallback rule
            rule = self.env['mail.tracker.role.rule'].sudo().search(
                [('mail_type', '=', 'general'), ('active', '=', True)],
                order='sequence asc',
                limit=1,
            )

        if rule and rule.assigned_user_id:
            self.assigned_user_id = rule.assigned_user_id
            _logger.debug(
                'Mail Tracker Intelligence: assigned record %d to user %s via rule "%s"',
                self.id, rule.assigned_user_id.name, rule.name,
            )
            return

        # Final fallback: assign to admin (uid=1)
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        if admin:
            self.assigned_user_id = admin
            _logger.debug(
                'Mail Tracker Intelligence: no role rule matched for type "%s" '
                'on record %d — assigning to admin',
                mail_type, self.id,
            )

    # ── Part D: Auto escalation cron ──────────────────────────────────────────

    @api.model
    def _cron_auto_escalate(self):
        """
        Scheduled action: escalate high-importance emails that have not been
        handled within _ESCALATION_THRESHOLD_HOURS.

        Criteria:
          - importance_level in {very_high, high}
          - state in {new, assigned}
          - received_date <= now - threshold
        """
        threshold = fields.Datetime.now() - timedelta(hours=_ESCALATION_THRESHOLD_HOURS)
        candidates = self.search([
            ('importance_level', 'in', ['very_high', 'high']),
            ('state', 'in', ['new', 'assigned']),
            ('received_date', '<=', threshold),
        ])

        if not candidates:
            return

        _logger.info(
            'Mail Tracker Auto-Escalate: escalating %d records', len(candidates)
        )

        for rec in candidates:
            try:
                rec.write({'state': 'escalated'})
                rec.message_post(
                    body=(
                        '<strong>⚠ Auto-Escalated</strong> — '
                        f'Email not handled within {_ESCALATION_THRESHOLD_HOURS} hours. '
                        'Importance: <strong>' + (rec.importance_level or '') + '</strong>.'
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as exc:
                _logger.warning(
                    'Mail Tracker Auto-Escalate: failed on record %d: %s', rec.id, exc
                )
