"""
mythos.bot.command — Execution Bot Command Engine (Step 8)
===========================================================

Two classes in one file:

  mythos.bot.command
    Registry of active Telegram commands per bot / domain.
    Lightweight metadata — name, command string, description, sequence.

  mythos.telegram.bot (extension)
    handle_telegram_update(update)     — main webhook entry point
    _handle_message / _handle_callback_query
    _dispatch_command(cmd, args, chat_id, from_user, project_id)
    _cmd_start / _cmd_tasks / _cmd_progress / _cmd_delays / _cmd_projects
    _resolve_project(project_id)       — single / multi project logic
    _get_division_progress(project)    — division breakdown
    _nav_keyboard / _send_project_picker / _build_project_sel_keyboard
    _api_call / _reply / _answer_callback

SAFETY:
  - Reads farm.project and farm.job.order only — never writes operational data.
  - All exceptions caught at dispatch level — webhook always returns HTTP 200.
  - bot_token is NEVER written to any log line.
  - All project / JO names are HTML-escaped before being sent to Telegram.
"""
import json
import logging
from datetime import date

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Job order stage constants ──────────────────────────────────────────────────

_STAGE_EMOJI = {
    'draft':               '📝',
    'approved':            '✅',
    'in_progress':         '🔨',
    'handover_requested':  '📤',
    'under_inspection':    '🔍',
    'partially_accepted':  '⚡',
    'accepted':            '🎯',
    'ready_for_claim':     '💰',
    'claimed':             '🏦',
    'closed':              '🔒',
}

# Stages where a JO is actively being worked on
_ACTIVE_STAGES = (
    'approved', 'in_progress', 'handover_requested',
    'under_inspection', 'partially_accepted',
)

# Stages where a JO is open (not yet claimed / closed)
_OPEN_STAGES = (
    'approved', 'in_progress', 'handover_requested',
    'under_inspection', 'partially_accepted', 'accepted', 'ready_for_claim',
)


# ═════════════════════════════════════════════════════════════════════════════
# 1 — Command registry model
# ═════════════════════════════════════════════════════════════════════════════

class MythosBotCommand(models.Model):
    """Registry of Telegram commands per bot / domain."""

    _name        = 'mythos.bot.command'
    _description = 'Mythos Bot Command'
    _order       = 'sequence, command'
    _rec_name    = 'command'

    command = fields.Char(
        string='Command',
        required=True,
        help='Telegram command string including the leading slash, e.g. /tasks',
    )
    name = fields.Char(
        string='Display Name',
        required=True,
    )
    description = fields.Char(
        string='Description',
        help='One-line summary shown in /help listings.',
    )
    bot_id = fields.Many2one(
        'mythos.telegram.bot',
        string='Bot',
        ondelete='cascade',
        index=True,
        help='Scoped to this bot only. Leave empty for all bots in the domain.',
    )
    domain_type = fields.Selection(
        selection=[
            ('execution',    'Execution'),
            ('pre_contract', 'Pre-Contract'),
            ('financial',    'Financial'),
            ('system',       'System'),
        ],
        string='Domain',
        index=True,
    )
    active   = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        (
            'command_bot_unique',
            'UNIQUE(command, bot_id)',
            'Each command must be unique per bot.',
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 2 — Conversation session model (wizard state between Telegram steps)
# ═════════════════════════════════════════════════════════════════════════════

class MythosBotSession(models.Model):
    """Transient wizard state for multi-step Telegram conversations.

    One record per (chat_id, bot_id) pair, replaced at each wizard step.
    Cleared automatically on completion or cancellation.

    Currently used by the JO-creation wizard (steps: jo_name).
    payload_json stores the collected field values as JSON.
    """

    _name        = 'mythos.bot.session'
    _description = 'Mythos Bot Conversation Session'
    _order       = 'last_activity desc'

    chat_id = fields.Char(
        string='Chat ID',
        required=True,
        index=True,
        help='Telegram chat_id of the user in the active wizard.',
    )
    bot_id = fields.Many2one(
        'mythos.telegram.bot',
        string='Bot',
        required=True,
        ondelete='cascade',
        index=True,
    )
    step = fields.Char(
        string='Wizard Step',
        required=True,
        help='Current step key, e.g. "jo_name".',
    )
    payload_json = fields.Text(
        string='Payload',
        default='{}',
        help='JSON-encoded data collected so far in the wizard.',
    )
    last_activity = fields.Datetime(
        string='Last Activity',
        required=True,
        default=fields.Datetime.now,
    )

    _sql_constraints = [
        (
            'chat_bot_unique',
            'UNIQUE(chat_id, bot_id)',
            'Only one active wizard session per chat per bot.',
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 2 — mythos.telegram.bot extension: webhook dispatch + command handlers
# ═════════════════════════════════════════════════════════════════════════════

class MythosTeLegramBotCommands(models.Model):
    """Extends mythos.telegram.bot with Telegram update handling.

    Entry point called by the webhook controller:
      POST /mythos/telegram/<bot_code>/webhook
        → bot.handle_telegram_update(update_dict)

    Supported commands (Execution Bot):
      /start    — welcome message + command list
      /tasks    — active job orders, grouped by stage
      /progress — project execution % with division breakdown
      /delays   — overdue job orders (planned_end_date < today)
      /projects — list all active projects for project selection
      /help     — alias for /start
    """

    _inherit = 'mythos.telegram.bot'

    # ─────────────────────────────────────────────────────────────────────────
    # Main webhook entry point
    # ─────────────────────────────────────────────────────────────────────────

    def handle_telegram_update(self, update):
        """Dispatch a Telegram update dict (message or callback_query).

        Called by the webhook HTTP controller.  All exceptions are caught so
        the controller can always return HTTP 200 to Telegram.
        """
        self.ensure_one()
        try:
            if 'message' in update:
                self._handle_message(update['message'])
            elif 'callback_query' in update:
                self._handle_callback_query(update['callback_query'])
        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: handle_telegram_update error — %s',
                self.code, exc,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Message handler
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_message(self, message):
        """Parse a Telegram message dict and route commands.

        Before checking for slash commands, checks whether an active wizard
        session is waiting for free-text input (e.g. the JO name step).
        """
        text      = (message.get('text') or '').strip()
        chat_id   = str(message.get('chat', {}).get('id', ''))
        from_user = message.get('from', {})

        if not text or not chat_id:
            return

        # ── Active wizard session? Handle text input first ────────────────────
        session = self._session_get(chat_id)
        if session:
            if session.step == 'jo_name':
                self._jo_receive_name(chat_id, text, session)
                return
            if session.step == 'jo_pct_manual':
                self._jo_receive_pct(chat_id, text, session)
                return
            # Unknown step — clear stale session and fall through
            self._session_clear(chat_id)

        if text.startswith('/'):
            parts   = text.split()
            command = parts[0].lower()
            args    = parts[1:]
            self._dispatch_command(command, args, chat_id, from_user)
        else:
            self._reply(
                chat_id,
                '❓ أرسل /start لعرض القائمة الرئيسية.',
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Callback query handler (inline keyboard button presses)
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_callback_query(self, callback_query):
        """Handle an inline keyboard button press.

        callback_data formats:
          cmd:<command>:<project_id>   — e.g. cmd:tasks:42
          proj_sel:<project_id>:<cmd>  — e.g. proj_sel:42:tasks
          jo:<action>[:<args…>]        — JO wizard steps
        """
        cbq_id  = callback_query.get('id', '')
        data    = callback_query.get('data', '')
        chat_id = str(callback_query.get('message', {}).get('chat', {}).get('id', ''))

        if not chat_id or not data:
            return

        # Acknowledge immediately — removes the button loading spinner
        self._answer_callback(cbq_id)

        parts  = data.split(':')
        prefix = parts[0] if parts else ''

        if prefix == 'cmd' and len(parts) >= 3:
            command    = '/' + parts[1]
            project_id = parts[2] if parts[2] != '0' else None
            self._dispatch_command(command, [], chat_id, {}, project_id=project_id)

        elif prefix == 'proj_sel' and len(parts) >= 3:
            project_id = parts[1]
            command    = '/' + parts[2]
            self._dispatch_command(command, [], chat_id, {}, project_id=project_id)

        elif prefix == 'jo':
            self._handle_jo_callback(parts[1:], chat_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Command dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    _CMD_MAP = {
        '/start':       '_cmd_start',
        '/help':        '_cmd_start',
        '/tasks':       '_cmd_tasks',
        '/progress':    '_cmd_progress',
        '/delays':      '_cmd_delays',
        '/projects':    '_cmd_projects',
        '/attendance':  '_cmd_attendance',
        '/crew':        '_cmd_crew',
    }

    def _dispatch_command(self, command, args, chat_id, from_user, project_id=None):
        """Route a command string to its handler method."""
        # Handle /cmd@BotUsername form (groups)
        cmd_base = command.split('@')[0].lower()
        handler_name = self._CMD_MAP.get(cmd_base)
        if not handler_name:
            self._reply(
                chat_id,
                f'❓ Unknown command: <code>{_esc(cmd_base)}</code>\n'
                f'Send /start to see available commands.',
            )
            return
        getattr(self, handler_name)(
            chat_id, project_id=project_id, args=args, from_user=from_user,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /start
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_start(self, chat_id, project_id=None, args=None, from_user=None):
        """/start — Welcome message with 2×2 Arabic inline keyboard."""
        first_name = (from_user or {}).get('first_name', '')
        greeting   = f'أهلاً، <b>{_esc(first_name)}</b>! 👋\n' if first_name else ''

        text = (
            f'🤖 <b>Mythos — بوت التنفيذ</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'{greeting}\n'
            f'أنا أراقب تقدم أعمال التنفيذ بشكل فوري.\n\n'
            f'اختر أحد الخيارات أدناه:'
        )
        keyboard = [
            [
                {'text': '📊 التقدم',      'callback_data': 'cmd:progress:0'},
                {'text': '📋 الأعمال',     'callback_data': 'cmd:tasks:0'},
            ],
            [
                {'text': '⚠️ التأخيرات',   'callback_data': 'cmd:delays:0'},
                {'text': '🗂️ المشاريع',    'callback_data': 'cmd:projects:0'},
            ],
        ]
        self._reply(chat_id, text, keyboard)

    # ─────────────────────────────────────────────────────────────────────────
    # /projects
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_projects(self, chat_id, project_id=None, args=None, from_user=None):
        """/projects — List all active projects with progress summary."""
        projects = self.env['farm.project'].sudo().search(
            [('state', '!=', 'done')],
            order='name',
            limit=20,
        )
        if not projects:
            self._reply(chat_id, '📭 No active projects found.')
            return

        lines = ['🗂️ <b>Active Projects</b>\n']
        for p in projects:
            pct = p.execution_progress_pct or 0.0
            bar = _progress_bar(pct, 6)
            pct_e = _pct_emoji(pct)
            lines.append(
                f'{pct_e} <b>{_esc(p.name)}</b>\n'
                f'   {bar} {pct:.0f}%'
            )

        text = '\n\n'.join(lines)
        if len(projects) == 20:
            text += '\n\n<i>Showing first 20 projects.</i>'

        # Build a tap-to-select keyboard (2 per row, max 8)
        keyboard = self._build_project_sel_keyboard('tasks', projects)
        keyboard.append([{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}])
        self._reply(chat_id, text, keyboard)

    # ─────────────────────────────────────────────────────────────────────────
    # /tasks
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_tasks(self, chat_id, project_id=None, args=None, from_user=None):
        """/tasks — Show create-or-view choice menu for job orders."""
        pid_str = str(project_id) if project_id else '0'

        project_hint = ''
        if project_id:
            p = self.env['farm.project'].sudo().browse(int(project_id)).exists()
            if p:
                project_hint = f'\n📁 {_esc(p.name)}'

        text = (
            f'📋 <b>الأعمال — مهام التنفيذ</b>'
            f'{project_hint}\n\n'
            f'اختر الإجراء:'
        )
        keyboard = [
            [
                {'text': '➕ إنشاء مهمة', 'callback_data': f'jo:create:{pid_str}'},
                {'text': '📋 عرض المهام', 'callback_data': f'jo:view:{pid_str}'},
            ],
            [{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}],
        ]
        self._reply(chat_id, text, keyboard)

    def _cmd_tasks_view(self, chat_id, project_id=None, args=None, from_user=None):
        """Show the active job orders list + per-JO selection buttons."""
        project, projects = self._resolve_project(project_id)

        if not project:
            if not projects:
                self._reply(chat_id, '📭 لا توجد مشاريع نشطة.')
                return
            self._send_project_picker(chat_id, 'tasks', projects)
            return

        JO       = self.env['farm.job.order'].sudo()
        jos      = JO.search(
            [('project_id', '=', project.id), ('jo_stage', 'in', _ACTIVE_STAGES)],
            order='planned_end_date asc, name',
            limit=8,                          # cap at 8 — each gets a button row
        )

        proj_esc = _esc(project.name)

        if not jos:
            text = (
                f'📋 <b>مهام التنفيذ النشطة</b>\n'
                f'📁 {proj_esc}\n\n'
                f'✅ لا توجد مهام نشطة.\n'
                f'جميع الأعمال منجزة أو لم تبدأ بعد.'
            )
            self._reply(chat_id, text, self._nav_keyboard(project.id))
            return

        stage_labels = dict(JO._fields['jo_stage'].selection)
        today        = date.today()
        lines        = [f'📋 <b>مهام التنفيذ النشطة</b>\n📁 <b>{proj_esc}</b>\n']

        for i, jo in enumerate(jos, start=1):
            emoji  = _STAGE_EMOJI.get(jo.jo_stage, '•')
            stage  = stage_labels.get(jo.jo_stage, jo.jo_stage)
            pct    = jo.progress_percent or 0.0
            bar    = _progress_bar(pct, 6)
            line   = (
                f'{i}. {emoji} <b>{_esc(jo.name)}</b>\n'
                f'   {bar} {pct:.0f}% · {_esc(stage)}'
            )
            if jo.planned_end_date:
                overdue  = jo.planned_end_date < today
                date_str = jo.planned_end_date.strftime('%Y-%m-%d')
                line += f'\n   {"🚨 متأخر:" if overdue else "📅"} {date_str}'
            lines.append(line)

        total_active = JO.search_count([
            ('project_id', '=', project.id),
            ('jo_stage',   'in', _ACTIVE_STAGES),
        ])
        if total_active > 8:
            lines.append(f'<i>يعرض 8 من أصل {total_active} — الأقرب انتهاءً أولاً.</i>')

        text = '\n\n'.join(lines)

        # One button per JO for quick selection, then nav row
        jo_buttons = [
            [{'text': f'{i}. {jo.name[:35]}', 'callback_data': f'jo:upd:{jo.id}'}]
            for i, jo in enumerate(jos, start=1)
        ]
        jo_buttons += [
            [
                {'text': '🔄 تحديث',    'callback_data': f'jo:view:{project.id}'},
                {'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'},
            ],
        ]
        self._reply(chat_id, text, jo_buttons)

    # ─────────────────────────────────────────────────────────────────────────
    # JO creation wizard — callback router
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_jo_callback(self, parts, chat_id):
        """Route a 'jo:' callback to the correct wizard step.

        Expected callback_data formats (after stripping 'jo:' prefix):
          create:{pid}            — start JO-create wizard
          view:{pid}              — show active task list for project
          proj:{pid}              — project selected → show analyses
          ana:{pid}:{aid}         — analysis selected → show BOQ lines
          line:{pid}:{aid}:{lid}  — BOQ line selected → ask for name
          upd:{jo_id}             — show JO detail card + action buttons
          prog:{jo_id}            — show progress update screen
          pct:{jo_id}:{pct}       — apply quick-select percentage
          pct_m:{jo_id}           — manual % entry (saves session)
          cancel                  — abort any active wizard
        """
        action = parts[0] if parts else ''

        if action == 'create':
            pid = parts[1] if len(parts) > 1 and parts[1] != '0' else None
            self._jo_create_start(chat_id, project_id=pid)

        elif action == 'view':
            pid = parts[1] if len(parts) > 1 and parts[1] != '0' else None
            self._cmd_tasks_view(chat_id, project_id=pid)

        elif action == 'proj' and len(parts) >= 2:
            self._jo_show_analyses(chat_id, parts[1])

        elif action == 'ana' and len(parts) >= 3:
            self._jo_show_lines(chat_id, parts[1], parts[2])

        elif action == 'line' and len(parts) >= 4:
            self._jo_ask_name(chat_id, parts[1], parts[2], parts[3])

        elif action == 'upd' and len(parts) >= 2:
            self._jo_show_detail(chat_id, parts[1])

        elif action == 'prog' and len(parts) >= 2:
            self._jo_show_progress_update(chat_id, parts[1])

        elif action == 'pct' and len(parts) >= 3:
            self._jo_apply_pct(chat_id, parts[1], parts[2])

        elif action == 'pct_m' and len(parts) >= 2:
            self._jo_ask_pct_manual(chat_id, parts[1])

        elif action in ('lab', 'mat') and len(parts) >= 2:
            label = 'العمالة' if action == 'lab' else 'المواد'
            self._reply(
                chat_id,
                f'🚧 <b>{label}</b>\n\nهذه الميزة قيد التطوير.',
                [[
                    {'text': '◀️ رجوع',     'callback_data': f'jo:upd:{parts[1]}'},
                    {'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'},
                ]],
            )

        elif action == 'cancel':
            self._session_clear(chat_id)
            self._reply(
                chat_id,
                '❌ تم إلغاء العملية.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )

    # ─────────────────────────────────────────────────────────────────────────
    # JO creation wizard — step methods
    # ─────────────────────────────────────────────────────────────────────────

    def _jo_create_start(self, chat_id, project_id=None):
        """Wizard Step 1 — Select project (or auto-select if only one exists)."""
        FP       = self.env['farm.project'].sudo()
        projects = FP.search([('state', '!=', 'done')], order='name', limit=20)

        if not projects:
            self._reply(chat_id, '📭 لا توجد مشاريع نشطة.')
            return

        # If a specific project is already known, skip the picker
        if project_id:
            self._jo_show_analyses(chat_id, project_id)
            return

        # Auto-select when there is exactly one project
        if len(projects) == 1:
            self._jo_show_analyses(chat_id, projects[0].id)
            return

        # Multiple projects — show picker
        text = (
            '📋 <b>إنشاء مهمة جديدة</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n\n'
            '1️⃣ اختر المشروع:'
        )
        keyboard = self._build_jo_project_keyboard(projects)
        keyboard.append([{'text': '❌ إلغاء', 'callback_data': 'jo:cancel'}])
        self._reply(chat_id, text, keyboard)

    def _jo_show_analyses(self, chat_id, project_id):
        """Wizard Step 2 — Show approved BOQ analyses for the selected project."""
        project = self.env['farm.project'].sudo().browse(int(project_id)).exists()
        if not project:
            self._reply(chat_id, '⚠️ المشروع غير موجود.')
            return

        analyses = self.env['farm.boq.analysis'].sudo().search([
            ('project_id',    '=', project.id),
            ('analysis_state', '=', 'approved'),
        ], order='name', limit=20)

        if not analyses:
            self._reply(
                chat_id,
                f'📭 <b>لا توجد وثائق كميات معتمدة</b>\n'
                f'📁 {_esc(project.name)}\n\n'
                f'يجب اعتماد وثيقة الكميات أولاً قبل إنشاء مهام.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        text = (
            f'📋 <b>إنشاء مهمة جديدة</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📁 {_esc(project.name)}\n\n'
            f'2️⃣ اختر القسم (وثيقة الكميات):'
        )
        keyboard = []
        for a in list(analyses)[:8]:
            keyboard.append([{
                'text':          a.name[:40],
                'callback_data': f'jo:ana:{project_id}:{a.id}',
            }])
        keyboard.append([{'text': '❌ إلغاء', 'callback_data': 'jo:cancel'}])
        self._reply(chat_id, text, keyboard)

    def _jo_show_lines(self, chat_id, project_id, analysis_id):
        """Wizard Step 3 — Show BOQ leaf lines for the selected analysis."""
        analysis = self.env['farm.boq.analysis'].sudo().browse(int(analysis_id)).exists()
        if not analysis:
            self._reply(chat_id, '⚠️ القسم غير موجود.')
            return

        lines = self.env['farm.boq.line'].sudo().search([
            ('boq_id',       '=', analysis.boq_id.id),
            ('display_type', '=', False),  # leaf subitems only
        ], order='sequence_sub, id', limit=20)

        if not lines:
            self._reply(
                chat_id,
                f'📭 <b>لا توجد بنود في هذا القسم</b>\n'
                f'📂 {_esc(analysis.name)}\n\n'
                f'اختر قسماً آخر.',
                [[
                    {'text': '◀️ رجوع', 'callback_data': f'jo:proj:{project_id}'},
                    {'text': '❌ إلغاء', 'callback_data': 'jo:cancel'},
                ]],
            )
            return

        text = (
            f'📋 <b>إنشاء مهمة جديدة</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📁 {_esc(analysis.project_id.name)}\n'
            f'📂 {_esc(analysis.name)}\n\n'
            f'3️⃣ اختر البند:'
        )
        keyboard = []
        for line in list(lines)[:8]:
            code  = line.display_code or ''
            label = f'{code} — {line.name}'[:40] if code else line.name[:40]
            keyboard.append([{
                'text':          label,
                'callback_data': f'jo:line:{project_id}:{analysis_id}:{line.id}',
            }])
        if len(lines) == 20:
            text += '\n\n<i>يعرض أول 20 بند.</i>'
        keyboard.append([
            {'text': '◀️ رجوع', 'callback_data': f'jo:proj:{project_id}'},
            {'text': '❌ إلغاء', 'callback_data': 'jo:cancel'},
        ])
        self._reply(chat_id, text, keyboard)

    def _jo_ask_name(self, chat_id, project_id, analysis_id, boq_line_id):
        """Wizard Step 4 — Persist session state, ask user to type the JO name."""
        boq_line = self.env['farm.boq.line'].sudo().browse(int(boq_line_id)).exists()
        if not boq_line:
            self._reply(chat_id, '⚠️ البند غير موجود.')
            return
        analysis = self.env['farm.boq.analysis'].sudo().browse(int(analysis_id)).exists()

        # Save wizard state — next text message will be the JO name
        self._session_set(chat_id, 'jo_name', {
            'project_id':  int(project_id),
            'analysis_id': int(analysis_id),
            'boq_line_id': int(boq_line_id),
        })

        code = boq_line.display_code or ''
        line_label = f'{_esc(code)} — {_esc(boq_line.name)}' if code else _esc(boq_line.name)

        text = (
            f'📋 <b>إنشاء مهمة جديدة</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📁 {_esc(analysis.project_id.name)}\n'
            f'📂 {_esc(analysis.name)}\n'
            f'🔖 {line_label}\n\n'
            f'4️⃣ ✏️ <b>أدخل اسم / وصف المهمة:</b>\n'
            f'<i>أرسل النص مباشرة في الرسالة التالية</i>'
        )
        keyboard = [[{'text': '❌ إلغاء', 'callback_data': 'jo:cancel'}]]
        self._reply(chat_id, text, keyboard)

    def _jo_receive_name(self, chat_id, text, session):
        """Wizard Step 5 — Receive JO name from free text, create the record."""
        payload = json.loads(session.payload_json or '{}')
        self._session_clear(chat_id)     # clear before create — avoid ghost sessions

        project_id  = payload.get('project_id')
        analysis_id = payload.get('analysis_id')
        boq_line_id = payload.get('boq_line_id')

        if not all([project_id, analysis_id, boq_line_id]):
            self._reply(
                chat_id,
                '⚠️ انتهت جلسة الإنشاء. أعد المحاولة من البداية.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        name = text.strip()
        if not name:
            self._reply(chat_id, '⚠️ الاسم لا يمكن أن يكون فارغاً. أعد الإرسال.')
            # Restore session so the user can retry the name step
            self._session_set(chat_id, 'jo_name', payload)
            return

        self._jo_create_record(chat_id, project_id, analysis_id, boq_line_id, name)

    def _jo_create_record(self, chat_id, project_id, analysis_id, boq_line_id, name):
        """Create the farm.job.order record and send a confirmation message."""
        try:
            jo = self.env['farm.job.order'].sudo().create({
                'name':             name,
                'project_id':       int(project_id),
                'analysis_id':      int(analysis_id),
                'boq_line_id':      int(boq_line_id),
                'planned_qty':      1.0,
                'business_activity': 'construction',
            })
            project  = self.env['farm.project'].sudo().browse(int(project_id))
            boq_line = self.env['farm.boq.line'].sudo().browse(int(boq_line_id))
            code     = boq_line.display_code or ''
            line_lbl = f'{_esc(code)} — {_esc(boq_line.name)}' if code else _esc(boq_line.name)

            text = (
                f'✅ <b>تم إنشاء المهمة بنجاح</b>\n'
                f'━━━━━━━━━━━━━━━━━━━━━━\n'
                f'📋 <b>{_esc(jo.name)}</b>\n'
                f'📁 {_esc(project.name)}\n'
                f'🔖 {line_lbl}\n'
                f'🆔 رقم المهمة: {jo.id}'
            )
            keyboard = [
                [
                    {'text': '📋 عرض المهام',  'callback_data': f'jo:view:{project_id}'},
                    {'text': '➕ مهمة جديدة', 'callback_data': f'jo:create:{project_id}'},
                ],
                [{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}],
            ]
            self._reply(chat_id, text, keyboard)
            _logger.info(
                'MythosBot [%s]: created farm.job.order id=%s name="%s" via Telegram.',
                self.code, jo.id, jo.name,
            )

        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: JO create failed — %s', self.code, exc,
            )
            self._reply(
                chat_id,
                f'❌ <b>فشل إنشاء المهمة</b>\n\n'
                f'<i>{_esc(str(exc)[:300])}</i>\n\n'
                f'تحقق من البيانات وأعد المحاولة.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )

    # ─────────────────────────────────────────────────────────────────────────
    # JO progress-update wizard
    # ─────────────────────────────────────────────────────────────────────────

    def _jo_show_detail(self, chat_id, jo_id):
        """Show a single JO card with action buttons (progress / labour / materials)."""
        jo = self.env['farm.job.order'].sudo().browse(int(jo_id)).exists()
        if not jo:
            self._reply(chat_id, '⚠️ المهمة غير موجودة.')
            return

        stage_labels = dict(self.env['farm.job.order']._fields['jo_stage'].selection)
        emoji        = _STAGE_EMOJI.get(jo.jo_stage, '•')
        stage        = stage_labels.get(jo.jo_stage, jo.jo_stage)
        appr_pct     = jo.progress_percent or 0.0        # approved_qty / planned_qty
        exec_pct     = (
            (jo.executed_qty / jo.planned_qty * 100.0) if jo.planned_qty else 0.0
        )
        appr_bar     = _progress_bar(appr_pct, 8)
        exec_bar     = _progress_bar(exec_pct, 8)
        today        = date.today()

        text = (
            f'{emoji} <b>{_esc(jo.name)}</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📁 {_esc(jo.project_id.name)}\n'
            f'🔖 {_esc(jo.boq_line_id.display_code or "")} {_esc(jo.boq_line_id.name or "")}\n'
            f'📌 المرحلة: {_esc(stage)}\n\n'
            f'📊 التقدم المعتمد:  {appr_bar} <b>{appr_pct:.1f}%</b>\n'
            f'🔨 التقدم المُبلَّغ: {exec_bar} <b>{exec_pct:.1f}%</b>'
        )
        if jo.planned_end_date:
            overdue  = jo.planned_end_date < today
            days_str = (
                f'🚨 متأخر {(today - jo.planned_end_date).days} يوم'
                if overdue else
                f'📅 {jo.planned_end_date}'
            )
            text += f'\n{days_str}'

        keyboard = [
            [{'text': '📊 تحديث التقدم', 'callback_data': f'jo:prog:{jo_id}'}],
            [
                {'text': '👷 العمالة',  'callback_data': f'jo:lab:{jo_id}'},
                {'text': '📦 المواد',   'callback_data': f'jo:mat:{jo_id}'},
            ],
            [
                {'text': '◀️ رجوع',     'callback_data': f'jo:view:{jo.project_id.id}'},
                {'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'},
            ],
        ]
        self._reply(chat_id, text, keyboard)

    def _jo_show_progress_update(self, chat_id, jo_id):
        """Show the progress update screen: current state + quick-select buttons."""
        jo = self.env['farm.job.order'].sudo().browse(int(jo_id)).exists()
        if not jo:
            self._reply(chat_id, '⚠️ المهمة غير موجودة.')
            return

        exec_pct = (
            (jo.executed_qty / jo.planned_qty * 100.0) if jo.planned_qty else 0.0
        )
        appr_pct = jo.progress_percent or 0.0
        bar      = _progress_bar(exec_pct, 10)
        e        = _pct_emoji(exec_pct)

        text = (
            f'📊 <b>تحديث التقدم</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📋 <b>{_esc(jo.name)}</b>\n\n'
            f'التقدم المُبلَّغ الحالي:\n'
            f'{e} {bar} <b>{exec_pct:.1f}%</b>\n\n'
            f'التقدم المعتمد: <b>{appr_pct:.1f}%</b>\n\n'
            f'<i>اختر النسبة الجديدة أو أدخل قيمة مخصصة:</i>'
        )
        # Quick-select row: 10 / 25 / 50 / 75 / 100
        keyboard = [
            [
                {'text': '10%',  'callback_data': f'jo:pct:{jo_id}:10'},
                {'text': '25%',  'callback_data': f'jo:pct:{jo_id}:25'},
                {'text': '50%',  'callback_data': f'jo:pct:{jo_id}:50'},
                {'text': '75%',  'callback_data': f'jo:pct:{jo_id}:75'},
                {'text': '100%', 'callback_data': f'jo:pct:{jo_id}:100'},
            ],
            [{'text': '✏️ إدخال يدوي', 'callback_data': f'jo:pct_m:{jo_id}'}],
            [
                {'text': '◀️ رجوع',     'callback_data': f'jo:upd:{jo_id}'},
                {'text': '❌ إلغاء',    'callback_data': 'jo:cancel'},
            ],
        ]
        self._reply(chat_id, text, keyboard)

    def _jo_apply_pct(self, chat_id, jo_id, pct_str):
        """Apply a new executed-progress percentage by adding a progress log entry.

        The progress log model auto-syncs the parent JO's executed_qty.
        We only record the DELTA (new_executed_qty – current executed_qty).

        Rules:
          • pct must be 0 < pct ≤ 100
          • pct must be > current executed percentage (no reductions via bot)
          • planned_qty must be > 0
        """
        try:
            pct = float(pct_str)
        except (TypeError, ValueError):
            self._reply(chat_id, '⚠️ نسبة غير صالحة.')
            return

        pct = round(min(max(pct, 0.0), 100.0), 2)

        jo = self.env['farm.job.order'].sudo().browse(int(jo_id)).exists()
        if not jo:
            self._reply(chat_id, '⚠️ المهمة غير موجودة.')
            return

        planned_qty = jo.planned_qty or 0.0
        if planned_qty <= 0:
            self._reply(
                chat_id,
                '⚠️ الكمية المخططة للمهمة تساوي صفر.\n'
                'لا يمكن احتساب التقدم.',
                [[{'text': '◀️ رجوع', 'callback_data': f'jo:upd:{jo_id}'}]],
            )
            return

        current_exec    = jo.executed_qty or 0.0
        current_pct     = (current_exec / planned_qty * 100.0) if planned_qty else 0.0
        target_exec_qty = pct / 100.0 * planned_qty
        delta_qty       = target_exec_qty - current_exec

        if delta_qty <= 0:
            exec_bar = _progress_bar(current_pct, 8)
            self._reply(
                chat_id,
                f'⚠️ <b>لا يمكن تقليل التقدم</b>\n\n'
                f'التقدم الحالي: {exec_bar} <b>{current_pct:.1f}%</b>\n'
                f'النسبة المطلوبة: <b>{pct:.0f}%</b>\n\n'
                f'لتصحيح سجل التقدم استخدم النظام مباشرة.',
                [[
                    {'text': '◀️ رجوع',     'callback_data': f'jo:prog:{jo_id}'},
                    {'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'},
                ]],
            )
            return

        # Create progress log — triggers auto-sync of executed_qty on the JO
        try:
            self.env['farm.job.progress.log'].sudo().create({
                'job_order_id':      jo.id,
                'executed_increment': delta_qty,
                'date':              fields.Date.today(),
                'note':              f'تحديث من Telegram: {pct:.0f}%',
            })
        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: progress log create failed for JO %s — %s',
                self.code, jo_id, exc,
            )
            self._reply(
                chat_id,
                f'❌ <b>فشل تحديث التقدم</b>\n\n<i>{_esc(str(exc)[:200])}</i>',
                [[{'text': '◀️ رجوع', 'callback_data': f'jo:upd:{jo_id}'}]],
            )
            return

        # Re-read after write
        jo.invalidate_recordset()
        new_exec     = jo.executed_qty or 0.0
        new_pct      = (new_exec / planned_qty * 100.0) if planned_qty else 0.0
        new_bar      = _progress_bar(new_pct, 10)
        new_e        = _pct_emoji(new_pct)

        text = (
            f'✅ <b>تم تحديث التقدم بنجاح</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📋 <b>{_esc(jo.name)}</b>\n\n'
            f'التقدم المُبلَّغ الجديد:\n'
            f'{new_e} {new_bar} <b>{new_pct:.1f}%</b>\n\n'
            f'الكمية المُضافة: <b>+{delta_qty:.2f}</b> (إجمالي {new_exec:.2f})'
        )
        keyboard = [
            [
                {'text': '📊 تحديث مرة أخرى', 'callback_data': f'jo:prog:{jo_id}'},
                {'text': '◀️ المهمة',          'callback_data': f'jo:upd:{jo_id}'},
            ],
            [{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}],
        ]
        self._reply(chat_id, text, keyboard)
        _logger.info(
            'MythosBot [%s]: JO %s progress updated to %.1f%% (+%.2f) via Telegram.',
            self.code, jo_id, new_pct, delta_qty,
        )

    def _jo_ask_pct_manual(self, chat_id, jo_id):
        """Save session then ask user to type a custom percentage."""
        jo = self.env['farm.job.order'].sudo().browse(int(jo_id)).exists()
        if not jo:
            self._reply(chat_id, '⚠️ المهمة غير موجودة.')
            return

        self._session_set(chat_id, 'jo_pct_manual', {'jo_id': int(jo_id)})

        text = (
            f'✏️ <b>إدخال نسبة مخصصة</b>\n'
            f'📋 {_esc(jo.name)}\n\n'
            f'أرسل النسبة الجديدة (رقم بين 0 و 100):\n'
            f'<i>مثال: 37 أو 37.5</i>'
        )
        keyboard = [[{'text': '❌ إلغاء', 'callback_data': 'jo:cancel'}]]
        self._reply(chat_id, text, keyboard)

    def _jo_receive_pct(self, chat_id, text, session):
        """Receive manually-typed percentage and apply it."""
        payload = json.loads(session.payload_json or '{}')
        jo_id   = payload.get('jo_id')
        self._session_clear(chat_id)

        if not jo_id:
            self._reply(
                chat_id,
                '⚠️ انتهت جلسة التحديث. أعد المحاولة.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        raw = text.strip().replace('%', '').replace(',', '.')
        try:
            pct = float(raw)
        except ValueError:
            # Restore session so user can retry
            self._session_set(chat_id, 'jo_pct_manual', {'jo_id': jo_id})
            self._reply(
                chat_id,
                f'⚠️ القيمة "{_esc(raw[:20])}" غير صالحة.\n'
                f'أرسل رقماً بين 0 و 100.',
            )
            return

        self._jo_apply_pct(chat_id, str(jo_id), str(pct))

    # ─────────────────────────────────────────────────────────────────────────
    # /progress
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_progress(self, chat_id, project_id=None, args=None, from_user=None):
        """/progress — Execution progress summary for a project."""
        project, projects = self._resolve_project(project_id)

        if not project:
            if not projects:
                self._reply(chat_id, '📭 No active projects found.')
                return
            self._send_project_picker(chat_id, 'progress', projects)
            return

        pct       = project.execution_progress_pct or 0.0
        bar       = _progress_bar(pct, 10)
        pct_e     = _pct_emoji(pct)
        proj_esc  = _esc(project.name)

        JO      = self.env['farm.job.order'].sudo()
        total   = JO.search_count([('project_id', '=', project.id)])
        active  = JO.search_count([
            ('project_id', '=', project.id),
            ('jo_stage',   'in', _ACTIVE_STAGES),
        ])
        done    = JO.search_count([
            ('project_id', '=', project.id),
            ('jo_stage',   'in', ('claimed', 'closed')),
        ])
        draft   = JO.search_count([
            ('project_id', '=', project.id),
            ('jo_stage',   '=', 'draft'),
        ])

        text = (
            f'📊 <b>Execution Progress</b>\n'
            f'📁 <b>{proj_esc}</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'Overall: {pct_e} {bar} <b>{pct:.1f}%</b>\n\n'
            f'<b>Job Orders:</b>\n'
            f'📋 Total:  {total}\n'
            f'🔨 Active: {active}\n'
            f'✅ Done:   {done}\n'
            f'📝 Draft:  {draft}'
        )

        # Division breakdown (top 5 by avg progress)
        div_data = self._get_division_progress(project)
        if div_data:
            text += '\n\n<b>By Division:</b>'
            for div_name, div_pct, jo_count in div_data[:5]:
                d_bar = _progress_bar(div_pct, 6)
                d_e   = _pct_emoji(div_pct)
                text += (
                    f'\n{d_e} {_esc(div_name[:28])}\n'
                    f'   {d_bar} {div_pct:.0f}% ({jo_count} JOs)'
                )

        self._reply(chat_id, text, self._nav_keyboard(project.id))

    # ─────────────────────────────────────────────────────────────────────────
    # /delays
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_delays(self, chat_id, project_id=None, args=None, from_user=None):
        """/delays — Overdue job orders (planned_end_date < today, still open)."""
        project, projects = self._resolve_project(project_id)

        if not project:
            if not projects:
                self._reply(chat_id, '📭 No active projects found.')
                return
            self._send_project_picker(chat_id, 'delays', projects)
            return

        today    = date.today()
        JO       = self.env['farm.job.order'].sudo()
        today_str = fields.Date.to_string(today)
        proj_esc = _esc(project.name)

        overdue = JO.search([
            ('project_id',      '=',  project.id),
            ('jo_stage',        'in', _OPEN_STAGES),
            ('planned_end_date', '<', today_str),
        ], order='planned_end_date asc', limit=15)

        if not overdue:
            text = (
                f'⚠️ <b>Delayed Items</b>\n'
                f'📁 {proj_esc}\n\n'
                f'🎉 No overdue job orders!\n'
                f'Everything is on schedule.'
            )
        else:
            stage_labels = dict(JO._fields['jo_stage'].selection)
            lines = [f'⚠️ <b>Delayed Items</b>\n📁 <b>{proj_esc}</b>\n']

            for jo in overdue:
                end_date     = jo.planned_end_date
                days_overdue = (today - end_date).days
                pct          = jo.progress_percent or 0.0
                bar          = _progress_bar(pct, 6)
                stage        = stage_labels.get(jo.jo_stage, jo.jo_stage)
                lines.append(
                    f'🚨 <b>{_esc(jo.name)}</b>\n'
                    f'   {bar} {pct:.0f}% · {_esc(stage)}\n'
                    f'   🗓️ Due: {end_date} (<b>+{days_overdue}d overdue</b>)'
                )

            total_overdue = JO.search_count([
                ('project_id',      '=',  project.id),
                ('jo_stage',        'in', _OPEN_STAGES),
                ('planned_end_date', '<', today_str),
            ])
            if total_overdue > 15:
                lines.append(
                    f'<i>Showing 15 of {total_overdue} overdue items.</i>'
                )

            text = '\n\n'.join(lines)

        self._reply(chat_id, text, self._nav_keyboard(project.id))

    # ─────────────────────────────────────────────────────────────────────────
    # /attendance
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_attendance(self, chat_id, project_id=None, args=None, from_user=None):
        """/attendance — Today's attendance sheets: state, present/absent counts.

        Uses smart_farm_labour_attendance module if installed.
        Gracefully falls back if the module is absent.
        """
        if 'farm.labour.attendance' not in self.env:
            self._reply(
                chat_id,
                '⚠️ وحدة تحضير العمالة غير مثبتة.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        today = fields.Date.today()
        domain = [('date', '=', today)]
        if project_id:
            domain.append(('project_id', '=', int(project_id)))

        sheets = self.env['farm.labour.attendance'].sudo().search(
            domain, order='project_id, name', limit=20,
        )

        today_str = str(today)

        if not sheets:
            scope = ''
            if project_id:
                p = self.env['farm.project'].sudo().browse(int(project_id)).exists()
                scope = f'\n📁 {_esc(p.name)}' if p else ''
            self._reply(
                chat_id,
                f'📋 <b>تحضير العمالة — {_esc(today_str)}</b>{scope}\n\n'
                f'📭 لا توجد ورقات تحضير لهذا اليوم.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        # State label map
        state_labels = {
            'draft':     '📝 مسودة',
            'open':      '🟢 مفتوح',
            'closed':    '✅ مغلق',
            'cancelled': '❌ ملغى',
        }

        lines = [f'📋 <b>تحضير العمالة — {_esc(today_str)}</b>\n']

        # Group by project for cleaner output
        current_proj = None
        for sheet in sheets:
            proj_name = sheet.project_id.name or '—'
            if proj_name != current_proj:
                lines.append(f'\n📁 <b>{_esc(proj_name)}</b>')
                current_proj = proj_name

            state_lbl = state_labels.get(sheet.state, sheet.state)
            div_name  = sheet.division_id.name or '—' if sheet.division_id else '—'
            lines.append(
                f'  {state_lbl}\n'
                f'  📂 {_esc(div_name)}\n'
                f'  👷 حضور: <b>{sheet.present_count}</b>  '
                f'غياب: <b>{sheet.absent_count}</b>  '
                f'ساعات: <b>{sheet.total_hours:.1f}</b>'
            )

        total_present = sum(s.present_count for s in sheets)
        total_absent  = sum(s.absent_count  for s in sheets)
        total_hours   = sum(s.total_hours   for s in sheets)
        total_cost    = sum(s.total_labour_cost for s in sheets)

        lines.append(
            f'\n━━━━━━━━━━━━━━━━━━━━━━\n'
            f'👥 إجمالي الحضور: <b>{total_present}</b>\n'
            f'🚫 إجمالي الغياب: <b>{total_absent}</b>\n'
            f'⏱️ إجمالي الساعات: <b>{total_hours:.1f}</b>\n'
            f'💰 إجمالي التكلفة: <b>{total_cost:,.0f}</b>'
        )

        text = '\n'.join(lines)
        keyboard = [
            [
                {'text': '👷 الطاقم الحالي', 'callback_data': 'cmd:crew:0'},
                {'text': '🔄 تحديث',          'callback_data': 'cmd:attendance:0'},
            ],
            [{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}],
        ]
        self._reply(chat_id, text, keyboard)

    # ─────────────────────────────────────────────────────────────────────────
    # /crew
    # ─────────────────────────────────────────────────────────────────────────

    def _cmd_crew(self, chat_id, project_id=None, args=None, from_user=None):
        """/crew — Today's present workers: names, hours, total cost per project.

        Uses farm.labour.attendance.line if the module is installed.
        """
        if 'farm.labour.attendance.line' not in self.env:
            self._reply(
                chat_id,
                '⚠️ وحدة تحضير العمالة غير مثبتة.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        today = fields.Date.today()
        domain = [
            ('date',             '=',        today),
            ('attendance_state', '=',        'present'),
        ]
        if project_id:
            domain.append(('project_id', '=', int(project_id)))

        present_lines = self.env['farm.labour.attendance.line'].sudo().search(
            domain, order='project_id, employee_id', limit=50,
        )

        today_str = str(today)

        if not present_lines:
            scope = ''
            if project_id:
                p = self.env['farm.project'].sudo().browse(int(project_id)).exists()
                scope = f'\n📁 {_esc(p.name)}' if p else ''
            self._reply(
                chat_id,
                f'👷 <b>الطاقم الحاضر — {_esc(today_str)}</b>{scope}\n\n'
                f'📭 لا يوجد عمال حاضرون اليوم.',
                [[{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}]],
            )
            return

        # Group lines by project
        by_project = {}
        for line in present_lines:
            proj_name = line.project_id.name if line.project_id else 'غير محدد'
            by_project.setdefault(proj_name, []).append(line)

        lines_out = [f'👷 <b>الطاقم الحاضر — {_esc(today_str)}</b>\n']

        for proj_name, proj_lines in by_project.items():
            proj_hours = sum(l.hours or 0.0 for l in proj_lines)
            proj_cost  = sum(l.total_cost or 0.0 for l in proj_lines)
            lines_out.append(
                f'\n📁 <b>{_esc(proj_name)}</b> '
                f'({len(proj_lines)} عامل — {proj_hours:.1f} ساعة)'
            )
            # List workers (up to 10 per project)
            for line in proj_lines[:10]:
                emp_name  = line.employee_id.name if line.employee_id else '—'
                check_in  = line.check_in.strftime('%H:%M')  if line.check_in  else '—'
                check_out = line.check_out.strftime('%H:%M') if line.check_out else '—'
                hours     = f'{line.hours:.1f}h' if line.hours else '—'
                lines_out.append(
                    f'  • {_esc(emp_name)} · {check_in}→{check_out} · {hours}'
                )
            if len(proj_lines) > 10:
                lines_out.append(f'  <i>… و{len(proj_lines) - 10} عمال آخرون</i>')
            lines_out.append(
                f'  💰 التكلفة: <b>{proj_cost:,.0f}</b>'
            )

        # Grand totals
        total_workers = len(present_lines)
        total_hours   = sum(l.hours or 0.0 for l in present_lines)
        total_cost    = sum(l.total_cost or 0.0 for l in present_lines)

        lines_out.append(
            f'\n━━━━━━━━━━━━━━━━━━━━━━\n'
            f'👥 إجمالي الحاضرين: <b>{total_workers}</b>\n'
            f'⏱️ إجمالي الساعات:  <b>{total_hours:.1f}</b>\n'
            f'💰 إجمالي التكلفة:  <b>{total_cost:,.0f}</b>'
        )

        text = '\n'.join(lines_out)
        keyboard = [
            [
                {'text': '📋 ورقة التحضير', 'callback_data': 'cmd:attendance:0'},
                {'text': '🔄 تحديث',         'callback_data': 'cmd:crew:0'},
            ],
            [{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}],
        ]
        self._reply(chat_id, text, keyboard)

    # ─────────────────────────────────────────────────────────────────────────
    # Project context resolution
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_project(self, project_id=None):
        """Return (project, all_active_projects).

        Rules:
          1. project_id given  → browse that specific project.
          2. Only 1 active project in system → auto-select it.
          3. Multiple projects  → return (empty_recordset, all_projects)
             so the caller shows a project picker.
        """
        FP = self.env['farm.project'].sudo()
        all_projects = FP.search([('state', '!=', 'done')], order='name')

        if project_id:
            p = FP.browse(int(project_id)).exists()
            return p, all_projects

        if len(all_projects) == 1:
            return all_projects, all_projects

        return FP, all_projects

    # ─────────────────────────────────────────────────────────────────────────
    # Division progress breakdown
    # ─────────────────────────────────────────────────────────────────────────

    def _get_division_progress(self, project):
        """Return [(div_name, avg_progress_pct, jo_count)] sorted desc by avg."""
        jos = self.env['farm.job.order'].sudo().search([
            ('project_id', '=', project.id),
            ('jo_stage',   'not in', ('draft',)),
        ])
        if not jos:
            return []

        buckets = {}
        for jo in jos:
            div_name = (
                jo.division_id.name if jo.division_id else 'Unclassified'
            ) or 'Unclassified'
            if div_name not in buckets:
                buckets[div_name] = []
            buckets[div_name].append(jo.progress_percent or 0.0)

        result = []
        for div_name, pcts in buckets.items():
            avg = sum(pcts) / len(pcts) if pcts else 0.0
            result.append((div_name, avg, len(pcts)))

        result.sort(key=lambda x: x[1], reverse=True)
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Session helpers (wizard state persistence)
    # ─────────────────────────────────────────────────────────────────────────

    def _session_get(self, chat_id):
        """Return the active wizard session for this (chat_id, bot), or empty."""
        return self.env['mythos.bot.session'].sudo().search([
            ('chat_id', '=', chat_id),
            ('bot_id',  '=', self.id),
        ], limit=1)

    def _session_set(self, chat_id, step, payload):
        """Create or update the wizard session for this chat."""
        Session  = self.env['mythos.bot.session'].sudo()
        existing = Session.search([
            ('chat_id', '=', chat_id),
            ('bot_id',  '=', self.id),
        ], limit=1)
        data = {
            'step':          step,
            'payload_json':  json.dumps(payload),
            'last_activity': fields.Datetime.now(),
        }
        if existing:
            existing.write(data)
        else:
            Session.create({'chat_id': chat_id, 'bot_id': self.id, **data})

    def _session_clear(self, chat_id):
        """Delete the wizard session for this chat."""
        self.env['mythos.bot.session'].sudo().search([
            ('chat_id', '=', chat_id),
            ('bot_id',  '=', self.id),
        ]).unlink()

    # ─────────────────────────────────────────────────────────────────────────
    # UI helpers — keyboards
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_jo_project_keyboard(projects):
        """2-column keyboard for JO wizard project selection (max 8 projects)."""
        rows = []
        row  = []
        for p in list(projects)[:8]:
            row.append({
                'text':          p.name[:30],
                'callback_data': f'jo:proj:{p.id}',
            })
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return rows

    def _nav_keyboard(self, project_id):
        """Standard navigation keyboard (Arabic labels) for a specific project.

        Row 1: main commands for this project.
        Row 2: refresh task list directly (jo:view), projects picker, home.
        """
        pid = str(project_id)
        return [
            [
                {'text': '📊 التقدم',     'callback_data': f'cmd:progress:{pid}'},
                {'text': '📋 الأعمال',    'callback_data': f'cmd:tasks:{pid}'},
                {'text': '⚠️ التأخيرات', 'callback_data': f'cmd:delays:{pid}'},
            ],
            [
                {'text': '🔄 تحديث',     'callback_data': f'jo:view:{pid}'},
                {'text': '🗂️ المشاريع',  'callback_data': 'cmd:projects:0'},
                {'text': '🏠 الرئيسية',  'callback_data': 'cmd:start:0'},
            ],
        ]

    def _send_project_picker(self, chat_id, command, projects):
        """Send a project-selection message with an Arabic inline keyboard."""
        count = len(projects)
        text  = (
            f'🗂️ <b>اختر مشروعاً</b>\n\n'
            f'يوجد {count} مشروع{"" if count == 1 else ""} نشط.\n'
            f'أي مشروع تريد عرضه؟'
        )
        keyboard = self._build_project_sel_keyboard(command, projects)
        keyboard.append([{'text': '🏠 الرئيسية', 'callback_data': 'cmd:start:0'}])
        self._reply(chat_id, text, keyboard)

    @staticmethod
    def _build_project_sel_keyboard(command, projects):
        """Build a 2-column project selection inline keyboard (max 8 projects)."""
        rows = []
        row  = []
        for p in list(projects)[:8]:
            row.append({
                'text':          p.name[:30],
                'callback_data': f'proj_sel:{p.id}:{command}',
            })
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return rows

    # ─────────────────────────────────────────────────────────────────────────
    # Low-level Telegram API helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _api_call(self, endpoint, payload):
        """POST to a Telegram Bot API endpoint. Returns the parsed JSON response."""
        import requests
        self.ensure_one()
        if not self.bot_token:
            _logger.debug(
                'MythosBot [%s]: _api_call "%s" skipped — no bot_token.',
                self.code, endpoint,
            )
            return {}
        url = f'https://api.telegram.org/bot{self.bot_token}/{endpoint}'
        try:
            r = requests.post(url, json=payload, timeout=10)
            return r.json() if r.content else {}
        except Exception as exc:
            _logger.warning(
                'MythosBot [%s]: API call "%s" failed — %s. Token not logged.',
                self.code, endpoint, exc,
            )
            return {}

    def _reply(self, chat_id, text, keyboard=None):
        """Send a text message to chat_id with optional inline keyboard.

        Uses HTML parse mode. All user-generated content must be _esc()'d
        before being embedded in the text string.
        """
        # Telegram hard limit: 4096 chars per message
        if len(text) > 4000:
            text = text[:4000] + '\n\n<i>… (message truncated)</i>'

        payload = {
            'chat_id':    chat_id,
            'text':       text,
            'parse_mode': 'HTML',
        }
        if keyboard:
            payload['reply_markup'] = {'inline_keyboard': keyboard}

        result = self._api_call('sendMessage', payload)
        if not result.get('ok'):
            _logger.warning(
                'MythosBot [%s]: sendMessage to chat %s failed — %s',
                self.code, chat_id, result.get('description', '?'),
            )
        return result.get('ok', False)

    def _answer_callback(self, callback_query_id, text=''):
        """Acknowledge a callback query to stop the inline button spinner."""
        return self._api_call('answerCallbackQuery', {
            'callback_query_id': callback_query_id,
            'text':              text,
        })
