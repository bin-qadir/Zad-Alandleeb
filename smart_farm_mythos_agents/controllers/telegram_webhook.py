"""
Mythos Telegram Webhook Controller
====================================
Receives POST requests from Telegram and dispatches them to the correct bot.

Route:  POST /mythos/telegram/<bot_code>/webhook
Auth:   public (Telegram sends unsigned JSON; no Odoo session exists)
CSRF:   disabled (external HTTP caller)

SAFETY:
  - Always returns HTTP 200 to Telegram (prevents retries).
  - All parsing and dispatch exceptions are caught here.
  - bot_token is NEVER written to any log line.
"""
import json
import logging

from odoo.http import Controller, route, request, Response

_logger = logging.getLogger(__name__)


class MythosTeLegramWebhookController(Controller):

    @route(
        '/mythos/telegram/<string:bot_code>/webhook',
        type='http',
        auth='public',
        csrf=False,
        methods=['POST'],
        save_session=False,
    )
    def telegram_webhook(self, bot_code, **kwargs):
        """Receive a Telegram update and route it to the correct bot."""
        # ── Parse request body ────────────────────────────────────────────────
        try:
            body   = request.httprequest.data
            update = json.loads(body)
        except Exception as exc:
            _logger.warning(
                'MythosWebhook [%s]: JSON parse error — %s', bot_code, exc,
            )
            return Response('', status=200)

        # ── Look up the bot ───────────────────────────────────────────────────
        try:
            bot = request.env['mythos.telegram.bot'].sudo().search([
                ('code',   '=', bot_code),
                ('state',  '=', 'active'),
                ('active', '=', True),
            ], limit=1)
        except Exception as exc:
            _logger.warning(
                'MythosWebhook [%s]: bot lookup error — %s', bot_code, exc,
            )
            return Response('', status=200)

        if not bot:
            _logger.debug(
                'MythosWebhook [%s]: no active bot found with this code.',
                bot_code,
            )
            return Response('', status=200)

        # ── Dispatch to bot command engine ────────────────────────────────────
        try:
            bot.handle_telegram_update(update)
        except Exception as exc:
            _logger.warning(
                'MythosWebhook [%s]: dispatch error — %s', bot_code, exc,
            )

        # Always return 200 so Telegram does not retry
        return Response('', status=200)
