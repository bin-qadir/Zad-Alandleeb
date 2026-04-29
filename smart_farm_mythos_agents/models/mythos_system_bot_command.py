"""
mythos_system_bot_command.py — System Bot Executive Dashboard (Step 12)
========================================================================

Extends mythos.telegram.bot to handle the System Bot (code='system_bot')
as an admin-level, read-only executive monitoring panel.

Rules (SAFETY):
  - NEVER creates, modifies, or deletes operational data.
  - Blocks all Execution Bot commands (/progress /tasks /delays /crew /attendance).
  - Arabic-primary UI with clean single-response-per-click design.
  - All user-facing strings HTML-escaped before sending.
  - Webhook already handled by the generic controller:
      POST /mythos/telegram/system_bot/webhook

Supported commands:
  /start             — Arabic executive dashboard welcome (2×3 keyboard)
  /help              — alias for /start
  /status            — system health: bots, projects, alerts
  /alerts            — recent mythos.alert records (new + acknowledged)
  /projects          — full project list with state and progress
  /executive_summary — cross-project P&L snapshot
  /kpi               — key performance indicators
  /risk              — overdue projects + high-severity alerts

Smart text shortcuts (Arabic and English):
  "الحالة" / "status"    → /status
  "التنبيهات" / "alerts"  → /alerts
  "المشاريع" / "projects" → /projects
  "ملخص" / "summary"      → /executive_summary
  "مؤشرات" / "kpi"        → /kpi
  "مخاطر" / "risk"        → /risk
"""
import logging
from datetime import date

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


# ── re-use helpers from the Execution Bot file ─────────────────────────────────

def _esc(value):
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        str(value)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _progress_bar(pct, width=8):
    """Return a Unicode progress bar, e.g. '█████░░░' for 62%."""
    filled = round(min(max(float(pct), 0.0), 100.0) / 100.0 * width)
    return '█' * filled + '░' * (width - filled)


def _pct_emoji(pct):
    """Return a traffic-light emoji for a percentage value."""
    if pct >= 75:
        return '🟢'
    if pct >= 50:
        return '🟡'
    if pct >= 25:
        return '🟠'
    return '🔴'


# ── Execution-Bot-only commands that should be blocked ────────────────────────

_EXECUTION_ONLY_CMDS = frozenset({
    '/progress', '/tasks', '/delays', '/crew', '/attendance',
})

# ── Stage constants (mirrors execution bot) ───────────────────────────────────

_ACTIVE_STAGES = (
    'approved', 'in_progress', 'handover_requested',
    'under_inspection', 'partially_accepted',
)
_OPEN_STAGES = (
    'approved', 'in_progress', 'handover_requested',
    'under_inspection', 'partially_accepted', 'accepted', 'ready_for_claim',
)

# ── Alert severity display ────────────────────────────────────────────────────

_SEV_EMOJI = {
    'low':      '🟡',
    'medium':   '🟠',
    'high':     '🔴',
    'critical': '🚨',
}
_SEV_AR = {
    'low':      'منخفض',
    'medium':   'متوسط',
    'high':     'عالي',
    'critical': 'حرج',
}

# ── Smart-text keyword map (lower-case match substrings) ─────────────────────

_SMART_KEYWORDS = [
    (['الحالة', 'status', 'النظام'],            '/status'),
    (['التنبيهات', 'alerts', 'تنبيه', 'alert'], '/alerts'),
    (['المشاريع', 'projects', 'مشروع'],          '/projects'),
    (['ملخص', 'summary', 'تنفيذي'],             '/executive_summary'),
    (['مؤشرات', 'kpi', 'أداء'],                 '/kpi'),
    (['مخاطر', 'risk', 'خطر'],                  '/risk'),
]


# ═════════════════════════════════════════════════════════════════════════════
# System Bot Extension
# ═════════════════════════════════════════════════════════════════════════════

class MythosSystemBotCommands(models.Model):
    """Executive Dashboard handler for the System Bot.

    Overrides handle_telegram_update to intercept system_bot requests
    before the Execution Bot dispatch chain runs.
    """

    _inherit = 'mythos.telegram.bot'

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point override
    # ─────────────────────────────────────────────────────────────────────────

    def handle_telegram_update(self, update):
        """Intercept system_bot updates; delegate all others to super()."""
        self.ensure_one()
        if self.code == 'system_bot':
            try:
                if 'message' in update:
                    self._sys_handle_message(update['message'])
                elif 'callback_query' in update:
                    self._sys_handle_callback_query(update['callback_query'])
            except Exception as exc:
                _logger.warning(
                    'SystemBot: handle_telegram_update error — %s', exc,
                )
        else:
            return super().handle_telegram_update(update)

    # ─────────────────────────────────────────────────────────────────────────
    # Message handler
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_handle_message(self, message):
        """Route text messages for the System Bot."""
        text      = (message.get('text') or '').strip()
        chat_id   = str(message.get('chat', {}).get('id', ''))
        from_user = message.get('from', {})

        if not text or not chat_id:
            return

        if text.startswith('/'):
            parts   = text.split()
            command = parts[0].lower().split('@')[0]   # strip @BotUsername
            self._sys_dispatch_command(command, chat_id, from_user)
        else:
            # Smart text matching
            text_lower = text.lower()
            for keywords, cmd in _SMART_KEYWORDS:
                if any(kw in text_lower for kw in keywords):
                    self._sys_dispatch_command(cmd, chat_id, from_user)
                    return
            # Fallback hint
            self._sys_reply(
                chat_id,
                '❓ أرسل /start لعرض لوحة الإدارة العليا.',
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Callback query handler
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_handle_callback_query(self, callback_query):
        """Handle inline keyboard button presses.

        callback_data formats:
          sys:<command>        — e.g. sys:status, sys:kpi
        """
        cbq_id  = callback_query.get('id', '')
        data    = callback_query.get('data', '')
        chat_id = str(callback_query.get('message', {}).get('chat', {}).get('id', ''))

        if not chat_id or not data:
            return

        self._sys_answer_callback(cbq_id)

        parts  = data.split(':')
        prefix = parts[0] if parts else ''

        if prefix == 'sys' and len(parts) >= 2:
            self._sys_dispatch_command('/' + parts[1], chat_id, {})

    # ─────────────────────────────────────────────────────────────────────────
    # Command dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    _SYS_CMD_MAP = {
        '/start':             '_sys_cmd_start',
        '/help':              '_sys_cmd_start',
        '/status':            '_sys_cmd_status',
        '/alerts':            '_sys_cmd_alerts',
        '/projects':          '_sys_cmd_projects',
        '/executive_summary': '_sys_cmd_executive_summary',
        '/kpi':               '_sys_cmd_kpi',
        '/risk':              '_sys_cmd_risk',
    }

    def _sys_dispatch_command(self, command, chat_id, from_user):
        """Route a command string to the correct handler."""
        # Block Execution Bot commands with a helpful redirect message
        if command in _EXECUTION_ONLY_CMDS:
            self._sys_reply(
                chat_id,
                '⚠️ <b>هذا الأمر خاص بالتنفيذ.</b>\n'
                'يرجى استخدام <b>Execution Bot</b>.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'sys:start'}]],
            )
            return

        handler_name = self._SYS_CMD_MAP.get(command)
        if not handler_name:
            self._sys_reply(
                chat_id,
                f'❓ الأمر غير معروف: <code>{_esc(command)}</code>\n'
                f'أرسل /start لعرض القائمة.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'sys:start'}]],
            )
            return

        getattr(self, handler_name)(chat_id, from_user=from_user)

    # ─────────────────────────────────────────────────────────────────────────
    # /start
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_start(self, chat_id, from_user=None):
        """/start — Executive dashboard welcome with 2×3 Arabic keyboard."""
        first_name = (from_user or {}).get('first_name', '')
        greeting   = f'مرحباً، <b>{_esc(first_name)}</b>! 👋\n' if first_name else 'مرحباً! 👋\n'

        text = (
            '🤖 <b>Mythos — لوحة الإدارة العليا</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{greeting}\n'
            'هذه لوحة التحكم الخاصة بالإدارة العليا.\n\n'
            'اختر أحد الخيارات:'
        )
        keyboard = [
            [
                {'text': '📊 حالة النظام',       'callback_data': 'sys:status'},
                {'text': '🚨 التنبيهات',          'callback_data': 'sys:alerts'},
            ],
            [
                {'text': '🗂️ المشاريع',           'callback_data': 'sys:projects'},
                {'text': '📈 الملخص التنفيذي',    'callback_data': 'sys:executive_summary'},
            ],
            [
                {'text': '📌 مؤشرات الأداء',      'callback_data': 'sys:kpi'},
                {'text': '⚠️ المخاطر',            'callback_data': 'sys:risk'},
            ],
        ]
        self._sys_reply(chat_id, text, keyboard)

    # ─────────────────────────────────────────────────────────────────────────
    # /status
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_status(self, chat_id, from_user=None):
        """/status — System health overview: bots, projects, alerts."""
        # Bot counts
        Bot        = self.env['mythos.telegram.bot'].sudo()
        total_bots = Bot.search_count([])
        active_bots = Bot.search_count([('state', '=', 'active')])

        # Project counts
        FP      = self.env['farm.project'].sudo()
        total_p  = FP.search_count([])
        running_p = FP.search_count([('state', '=', 'running')])
        draft_p   = FP.search_count([('state', '=', 'draft')])
        done_p    = FP.search_count([('state', '=', 'done')])

        # Alert counts
        Alerts     = self.env['mythos.alert'].sudo()
        new_alerts  = Alerts.search_count([('state', '=', 'new')])
        crit_alerts = Alerts.search_count([
            ('state',    '=', 'new'),
            ('severity', 'in', ('high', 'critical')),
        ])

        # Job Order counts
        JO       = self.env['farm.job.order'].sudo()
        total_jo = JO.search_count([])
        active_jo = JO.search_count([('jo_stage', 'in', _ACTIVE_STAGES)])
        today    = date.today()
        overdue_jo = JO.search_count([
            ('jo_stage',         'in', _OPEN_STAGES),
            ('planned_end_date', '<',  str(today)),
        ])

        # Bot status emoji
        bot_e = '🟢' if active_bots > 0 else '🔴'
        # Alert urgency emoji
        alert_e = '🚨' if crit_alerts > 0 else ('🟠' if new_alerts > 0 else '🟢')

        text = (
            '📊 <b>حالة النظام</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n\n'

            '<b>🤖 البوتات:</b>\n'
            f'{bot_e} نشط: <b>{active_bots}</b> / {total_bots}\n\n'

            '<b>🗂️ المشاريع:</b>\n'
            f'🔵 إجمالي:  <b>{total_p}</b>\n'
            f'🟢 نشط:    <b>{running_p}</b>\n'
            f'📝 مسودة:  <b>{draft_p}</b>\n'
            f'✅ منجز:   <b>{done_p}</b>\n\n'

            '<b>📋 أوامر التنفيذ:</b>\n'
            f'🔢 إجمالي: <b>{total_jo}</b>\n'
            f'🔨 نشط:   <b>{active_jo}</b>\n'
            f'🚨 متأخر:  <b>{overdue_jo}</b>\n\n'

            '<b>🚨 التنبيهات:</b>\n'
            f'{alert_e} جديد:  <b>{new_alerts}</b>\n'
            f'🔴 حرج/عالي: <b>{crit_alerts}</b>'
        )

        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # /alerts
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_alerts(self, chat_id, from_user=None):
        """/alerts — Recent open and acknowledged mythos.alert records."""
        Alerts = self.env['mythos.alert'].sudo()
        alerts = Alerts.search(
            [('state', 'in', ('new', 'acknowledged'))],
            order='date desc, severity desc',
            limit=15,
        )

        if not alerts:
            self._sys_reply(
                chat_id,
                '🚨 <b>التنبيهات</b>\n'
                '━━━━━━━━━━━━━━━━━━━━━━\n\n'
                '✅ لا توجد تنبيهات مفتوحة.',
                self._sys_nav_keyboard(),
            )
            return

        total_new  = Alerts.search_count([('state', '=', 'new')])
        total_ack  = Alerts.search_count([('state', '=', 'acknowledged')])

        lines = [
            f'🚨 <b>التنبيهات</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'جديد: <b>{total_new}</b>  ·  مُؤكَّد: <b>{total_ack}</b>\n'
        ]

        state_ar = {'new': '🔴 جديد', 'acknowledged': '🟡 مُؤكَّد', 'resolved': '✅ محلول'}

        for alert in alerts:
            sev_e   = _SEV_EMOJI.get(alert.severity, '•')
            sev_ar  = _SEV_AR.get(alert.severity, alert.severity)
            st_ar   = state_ar.get(alert.state, alert.state)
            date_s  = alert.date.strftime('%Y-%m-%d %H:%M') if alert.date else '—'
            agent   = _esc(alert.agent_id.name) if alert.agent_id else '—'
            lines.append(
                f'\n{sev_e} <b>{_esc(alert.name)}</b>\n'
                f'   {st_ar} · {sev_ar} · {agent}\n'
                f'   🕐 {date_s}'
            )
            if alert.message:
                snippet = _esc(alert.message[:100])
                lines.append(f'   <i>{snippet}</i>')

        total = Alerts.search_count([('state', 'in', ('new', 'acknowledged'))])
        if total > 15:
            lines.append(f'\n<i>يعرض 15 من أصل {total} تنبيه مفتوح.</i>')

        text = '\n'.join(lines)
        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # /projects
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_projects(self, chat_id, from_user=None):
        """/projects — All projects with state and execution progress."""
        FP = self.env['farm.project'].sudo()
        projects = FP.search([], order='state, name', limit=20)

        if not projects:
            self._sys_reply(
                chat_id,
                '🗂️ <b>المشاريع</b>\n\n📭 لا توجد مشاريع.',
                self._sys_nav_keyboard(),
            )
            return

        state_ar  = {'draft': '📝 مسودة', 'running': '🟢 نشط', 'done': '✅ منجز'}
        lines     = ['🗂️ <b>المشاريع</b>\n━━━━━━━━━━━━━━━━━━━━━━\n']
        cur_state = None

        for p in projects:
            if p.state != cur_state:
                cur_state = p.state
                lines.append(f'\n{state_ar.get(p.state, p.state)}')

            pct     = getattr(p, 'execution_progress_pct', None) or 0.0
            bar     = _progress_bar(pct, 6)
            pct_e   = _pct_emoji(pct)
            jo_cnt  = self.env['farm.job.order'].sudo().search_count([
                ('project_id', '=', p.id),
            ])
            lines.append(
                f'  {pct_e} <b>{_esc(p.name)}</b>\n'
                f'     {bar} {pct:.0f}%  📋 {jo_cnt} أمر'
            )

        total = FP.search_count([])
        if total > 20:
            lines.append(f'\n<i>يعرض أول 20 من {total} مشروع.</i>')

        text = '\n'.join(lines)
        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # /executive_summary
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_executive_summary(self, chat_id, from_user=None):
        """/executive_summary — Cross-project progress and JO snapshot."""
        FP = self.env['farm.project'].sudo()
        JO = self.env['farm.job.order'].sudo()

        total_proj   = FP.search_count([])
        running_proj = FP.search_count([('state', '=', 'running')])
        done_proj    = FP.search_count([('state', '=', 'done')])
        draft_proj   = FP.search_count([('state', '=', 'draft')])

        today = date.today()
        total_jo    = JO.search_count([])
        active_jo   = JO.search_count([('jo_stage', 'in', _ACTIVE_STAGES)])
        done_jo     = JO.search_count([('jo_stage', 'in', ('claimed', 'closed'))])
        overdue_jo  = JO.search_count([
            ('jo_stage',         'in', _OPEN_STAGES),
            ('planned_end_date', '<',  str(today)),
        ])

        # Overall average execution progress across running projects
        running_projects = FP.search([('state', '=', 'running')])
        if running_projects:
            pct_vals = [getattr(p, 'execution_progress_pct', None) or 0.0
                        for p in running_projects]
            avg_pct  = sum(pct_vals) / len(pct_vals)
        else:
            avg_pct  = 0.0

        bar   = _progress_bar(avg_pct, 10)
        pct_e = _pct_emoji(avg_pct)

        # Delay ratio
        delay_ratio = (overdue_jo / active_jo * 100.0) if active_jo else 0.0

        text = (
            '📈 <b>الملخص التنفيذي</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n\n'

            '<b>📁 المشاريع:</b>\n'
            f'🔵 الإجمالي:   <b>{total_proj}</b>\n'
            f'🟢 نشط:       <b>{running_proj}</b>\n'
            f'📝 مسودة:     <b>{draft_proj}</b>\n'
            f'✅ منجز:      <b>{done_proj}</b>\n\n'

            '<b>📋 أوامر التنفيذ:</b>\n'
            f'🔢 الإجمالي:  <b>{total_jo}</b>\n'
            f'🔨 نشط:      <b>{active_jo}</b>\n'
            f'✅ منجز:     <b>{done_jo}</b>\n'
            f'🚨 متأخر:    <b>{overdue_jo}</b>\n\n'

            '<b>📊 التقدم العام (المشاريع النشطة):</b>\n'
            f'{pct_e} {bar} <b>{avg_pct:.1f}%</b>\n\n'

            f'⚠️ نسبة التأخير: <b>{delay_ratio:.1f}%</b>'
        )

        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # /kpi
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_kpi(self, chat_id, from_user=None):
        """/kpi — Key performance indicators."""
        FP = self.env['farm.project'].sudo()
        JO = self.env['farm.job.order'].sudo()

        today = date.today()

        # 1. Average execution completion across active projects
        active_projects = FP.search([('state', '=', 'running')])
        if active_projects:
            pcts    = [getattr(p, 'execution_progress_pct', None) or 0.0
                       for p in active_projects]
            avg_pct = sum(pcts) / len(pcts)
        else:
            avg_pct = 0.0

        # 2. Delay ratio: overdue / total active JOs
        active_jo  = JO.search_count([('jo_stage', 'in', _ACTIVE_STAGES)])
        overdue_jo = JO.search_count([
            ('jo_stage',         'in', _OPEN_STAGES),
            ('planned_end_date', '<',  str(today)),
        ])
        delay_ratio = (overdue_jo / active_jo * 100.0) if active_jo else 0.0

        # 3. Completion rate: done JOs / total JOs
        total_jo = JO.search_count([])
        done_jo  = JO.search_count([('jo_stage', 'in', ('claimed', 'closed'))])
        comp_rate = (done_jo / total_jo * 100.0) if total_jo else 0.0

        # 4. Projects on track (no overdue JOs)
        projects_with_overdue = len(set(
            JO.search([
                ('jo_stage',         'in', _OPEN_STAGES),
                ('planned_end_date', '<',  str(today)),
            ]).mapped('project_id.id')
        ))
        total_running = len(active_projects)
        on_track_count = total_running - projects_with_overdue

        # Emojis
        avg_e   = _pct_emoji(avg_pct)
        comp_e  = _pct_emoji(comp_rate)
        delay_e = '🟢' if delay_ratio < 10 else ('🟡' if delay_ratio < 25 else '🔴')
        track_e = '🟢' if projects_with_overdue == 0 else '🟠'

        bar_avg  = _progress_bar(avg_pct, 8)
        bar_comp = _progress_bar(comp_rate, 8)

        text = (
            '📌 <b>مؤشرات الأداء</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n\n'

            '⏱️ <b>متوسط الإنجاز (المشاريع النشطة):</b>\n'
            f'{avg_e} {bar_avg} <b>{avg_pct:.1f}%</b>\n\n'

            '✅ <b>معدل إتمام أوامر التنفيذ:</b>\n'
            f'{comp_e} {bar_comp} <b>{comp_rate:.1f}%</b>\n'
            f'   ({done_jo} من أصل {total_jo})\n\n'

            '⚠️ <b>نسبة التأخير:</b>\n'
            f'{delay_e} <b>{delay_ratio:.1f}%</b>\n'
            f'   ({overdue_jo} أمر متأخر من أصل {active_jo} نشط)\n\n'

            '🗂️ <b>المشاريع ضمن الجدول:</b>\n'
            f'{track_e} <b>{on_track_count}</b> من {total_running} مشروع'
        )

        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # /risk
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_cmd_risk(self, chat_id, from_user=None):
        """/risk — Overdue projects + high-severity alerts."""
        JO     = self.env['farm.job.order'].sudo()
        Alerts = self.env['mythos.alert'].sudo()
        today  = date.today()

        # ── Overdue JOs grouped by project ───────────────────────────────────
        overdue = JO.search([
            ('jo_stage',         'in', _OPEN_STAGES),
            ('planned_end_date', '<',  str(today)),
        ], order='project_id, planned_end_date asc', limit=30)

        # ── High / critical open alerts ───────────────────────────────────────
        danger_alerts = Alerts.search([
            ('state',    '=',  'new'),
            ('severity', 'in', ('high', 'critical')),
        ], order='date desc', limit=10)

        has_risk = overdue or danger_alerts

        lines = ['⚠️ <b>المخاطر الحالية</b>\n━━━━━━━━━━━━━━━━━━━━━━\n']

        if not has_risk:
            lines.append('✅ لا توجد مخاطر حرجة حالياً.')
            self._sys_reply(chat_id, '\n'.join(lines), self._sys_nav_keyboard())
            return

        # Group overdue by project
        if overdue:
            by_proj = {}
            for jo in overdue:
                pname = jo.project_id.name if jo.project_id else 'غير محدد'
                by_proj.setdefault(pname, []).append(jo)

            lines.append(f'🚨 <b>مشاريع بأوامر متأخرة ({len(by_proj)} مشروع):</b>')
            for proj_name, jos in by_proj.items():
                overdue_days_list = [(today - jo.planned_end_date).days for jo in jos]
                max_delay = max(overdue_days_list) if overdue_days_list else 0
                lines.append(
                    f'\n🔴 <b>{_esc(proj_name)}</b>\n'
                    f'   {len(jos)} أمر متأخر · أقصى تأخير: <b>{max_delay} يوم</b>'
                )
                # List first 3 JOs
                for jo in jos[:3]:
                    delay = (today - jo.planned_end_date).days
                    pct   = jo.progress_percent or 0.0
                    lines.append(
                        f'   • {_esc(jo.name[:40])}\n'
                        f'     📅 تأخر {delay} يوم · {pct:.0f}%'
                    )
                if len(jos) > 3:
                    lines.append(f'   <i>… و{len(jos) - 3} آخرون</i>')

        # High/critical alerts
        if danger_alerts:
            lines.append(f'\n🚨 <b>تنبيهات حرجة/عالية ({len(danger_alerts)}):</b>')
            for alert in danger_alerts:
                sev_e = _SEV_EMOJI.get(alert.severity, '•')
                sev_a = _SEV_AR.get(alert.severity, alert.severity)
                lines.append(
                    f'\n{sev_e} <b>{_esc(alert.name)}</b> [{sev_a}]'
                )
                if alert.message:
                    lines.append(f'   <i>{_esc(alert.message[:100])}</i>')

        text = '\n'.join(lines)
        self._sys_reply(chat_id, text, self._sys_nav_keyboard())

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation keyboard
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _sys_nav_keyboard():
        """Standard navigation keyboard for the System Bot."""
        return [
            [
                {'text': '📊 حالة النظام',    'callback_data': 'sys:status'},
                {'text': '🚨 التنبيهات',       'callback_data': 'sys:alerts'},
                {'text': '🗂️ المشاريع',        'callback_data': 'sys:projects'},
            ],
            [
                {'text': '📈 الملخص',          'callback_data': 'sys:executive_summary'},
                {'text': '📌 مؤشرات الأداء',   'callback_data': 'sys:kpi'},
                {'text': '⚠️ المخاطر',         'callback_data': 'sys:risk'},
            ],
            [
                {'text': '🏠 الرئيسية',        'callback_data': 'sys:start'},
            ],
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Low-level API helpers (System Bot copy — uses same bot_token field)
    # ─────────────────────────────────────────────────────────────────────────

    def _sys_api_call(self, endpoint, payload):
        """POST to Telegram Bot API. Returns parsed JSON or {}."""
        import requests
        self.ensure_one()
        if not self.bot_token:
            return {}
        url = f'https://api.telegram.org/bot{self.bot_token}/{endpoint}'
        try:
            r = requests.post(url, json=payload, timeout=10)
            return r.json() if r.content else {}
        except Exception as exc:
            _logger.warning(
                'SystemBot: API call "%s" failed — %s. Token not logged.',
                endpoint, exc,
            )
            return {}

    def _sys_reply(self, chat_id, text, keyboard=None):
        """Send an HTML message to chat_id with optional inline keyboard."""
        if len(text) > 4000:
            text = text[:4000] + '\n\n<i>… (message truncated)</i>'

        payload = {
            'chat_id':    chat_id,
            'text':       text,
            'parse_mode': 'HTML',
        }
        if keyboard:
            payload['reply_markup'] = {'inline_keyboard': keyboard}

        result = self._sys_api_call('sendMessage', payload)
        if not result.get('ok'):
            _logger.warning(
                'SystemBot: sendMessage to chat %s failed — %s',
                chat_id, result.get('description', '?'),
            )
        return result.get('ok', False)

    def _sys_answer_callback(self, callback_query_id, text=''):
        """Acknowledge a callback query to stop the spinner."""
        return self._sys_api_call('answerCallbackQuery', {
            'callback_query_id': callback_query_id,
            'text':              text,
        })
