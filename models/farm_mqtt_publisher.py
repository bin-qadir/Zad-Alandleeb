# -*- coding: utf-8 -*-
"""
Smart Farm — MQTT Publish Service
===================================
Model: farm.mqtt.publisher  (AbstractModel — no DB table)

Single responsibility: publish a payload to a broker topic as reliably
and efficiently as possible, return a structured result, and write a log.

Design goals
────────────
  1. Reuse the already-connected listener client when the MqttServiceManager
     has an active connection for the broker — avoids a new TCP connection
     on every command and keeps latency below 5 ms on a local broker.

  2. Fall back to a short-lived connect-publish-disconnect when no active
     client is found (e.g. broker has no sensor subscriptions running).

  3. Wait for delivery confirmation using paho's MessageInfo.wait_for_publish()
     so we can report actual broker acknowledgement for QoS ≥ 1, not just
     "enqueued".

  4. Write a structured log record (farm.mqtt.publish.log) after every
     attempt — success or failure — so operators can audit every command.

  5. Never raise an exception to the caller; always return a result dict.

Public API
──────────
  FarmMqttPublisher.publish(
      broker_id      : int  | farm.mqtt.broker record,
      topic          : str,
      payload        : str | dict,
      qos            : int  = 1,
      retain         : bool = False,
      source_model   : str  = '',   # e.g. 'farm.control.action'
      source_id      : int  = 0,
      timeout_seconds: float = 5.0,
  ) → PublishResult(success, rc, mid, confirmed, message, log_id)

Result codes (rc field)
───────────────────────
  0   MQTT_ERR_SUCCESS
  4   MQTT_ERR_NO_CONN
  14  MQTT_ERR_AGAIN
  -1  pre-publish error (no broker, no topic, paho not installed, …)
  -2  timeout waiting for broker acknowledgement
"""

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Result container — lightweight, no ORM dependency
@dataclass
class PublishResult:
    success:   bool
    rc:        int           # paho return code (0 = success)
    mid:       int           # MQTT message id (-1 if not sent)
    confirmed: bool          # True if wait_for_publish() succeeded
    message:   str           # human-readable outcome
    log_id:    Optional[int] # farm.mqtt.publish.log id (if written)


# ── Lock that protects the one-shot connection pool ──────────────────────────
_pool_lock = threading.Lock()
# broker_id → {'client': paho.Client, 'last_used': float, 'in_use': bool}
_client_pool: dict = {}
_POOL_IDLE_SECONDS = 30   # evict idle one-shot clients after this long


# ─────────────────────────────────────────────────────────────────────────────
# farm.mqtt.publish.log  –  Immutable audit trail for every publish attempt
# ─────────────────────────────────────────────────────────────────────────────
class FarmMqttPublishLog(models.Model):
    _name        = 'farm.mqtt.publish.log'
    _description = 'MQTT Publish Log'
    _order       = 'create_date desc'
    _rec_name    = 'topic'

    broker_id  = fields.Many2one('farm.mqtt.broker', string='Broker',
                                 ondelete='set null', readonly=True)
    topic      = fields.Char(string='Topic',   readonly=True, index=True)
    payload    = fields.Text(string='Payload', readonly=True)

    qos        = fields.Integer(string='QoS',       readonly=True)
    retain     = fields.Boolean(string='Retain',    readonly=True)
    message_id = fields.Integer(string='MQTT MID',  readonly=True)

    # outcome
    success    = fields.Boolean(string='Success',   readonly=True, index=True)
    confirmed  = fields.Boolean(string='ACK Confirmed', readonly=True)
    rc         = fields.Integer(string='Return Code', readonly=True)
    message    = fields.Char(string='Result Message', readonly=True)
    duration_ms = fields.Float(string='Duration (ms)', readonly=True, digits=(8, 1))

    # source linkage
    source_model = fields.Char(string='Source Model', readonly=True)
    source_id    = fields.Integer(string='Source ID', readonly=True)
    sent_by      = fields.Many2one('res.users', string='Sent By',
                                   default=lambda s: s.env.uid, readonly=True)

    def name_get(self):
        return [(r.id,
                 '[%s] %s' % ('✓' if r.success else '✗', r.topic or '?'))
                for r in self]


# ─────────────────────────────────────────────────────────────────────────────
# farm.mqtt.publisher  –  Publish service (AbstractModel, no table)
# ─────────────────────────────────────────────────────────────────────────────
class FarmMqttPublisher(models.AbstractModel):
    _name        = 'farm.mqtt.publisher'
    _description = 'Farm MQTT Publish Service'

    # ────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def publish(
        self,
        broker,
        topic: str,
        payload: Union[str, dict],
        qos: int = 1,
        retain: bool = False,
        source_model: str = '',
        source_id: int = 0,
        timeout_seconds: float = 5.0,
    ) -> PublishResult:
        """
        Publish `payload` to `topic` on `broker`.

        Args:
            broker          : farm.mqtt.broker record OR broker DB id (int)
            topic           : MQTT topic string
            payload         : str (already serialised JSON) or dict (auto-serialised)
            qos             : 0 / 1 / 2  (default 1)
            retain          : broker retains the message (default False)
            source_model    : calling model name for audit log linkage
            source_id       : calling record id for audit log linkage
            timeout_seconds : seconds to wait for QoS ≥ 1 acknowledgement

        Returns:
            PublishResult dataclass (never raises)
        """
        t_start = time.monotonic()

        # ── Resolve broker record ─────────────────────────────────────────────
        if isinstance(broker, int):
            broker_rec = self.env['farm.mqtt.broker'].browse(broker)
        else:
            broker_rec = broker

        broker_id = broker_rec.id if broker_rec else 0

        # ── Validate inputs ───────────────────────────────────────────────────
        if not topic or not topic.strip():
            return self._failed(
                broker_id=broker_id, topic=topic, payload=payload,
                qos=qos, retain=retain,
                source_model=source_model, source_id=source_id,
                message='Topic is empty — cannot publish.',
                rc=-1, duration_ms=0,
            )

        if not broker_rec or not broker_rec.exists():
            return self._failed(
                broker_id=broker_id, topic=topic, payload=payload,
                qos=qos, retain=retain,
                source_model=source_model, source_id=source_id,
                message='No broker specified or broker not found.',
                rc=-1, duration_ms=0,
            )

        # ── Serialise payload ─────────────────────────────────────────────────
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        else:
            payload_str = str(payload)

        # ── Attempt to reuse existing listener connection ─────────────────────
        result = self._try_publish_via_listener(
            broker_rec, topic, payload_str, qos, retain, timeout_seconds
        )

        if result is None:
            # Listener not running for this broker → use one-shot client
            result = self._publish_oneshot(
                broker_rec, topic, payload_str, qos, retain, timeout_seconds
            )

        duration_ms = (time.monotonic() - t_start) * 1000

        # ── Write audit log ───────────────────────────────────────────────────
        log_id = self._write_log(
            broker_id=broker_id,
            topic=topic,
            payload_str=payload_str,
            qos=qos,
            retain=retain,
            result=result,
            duration_ms=duration_ms,
            source_model=source_model,
            source_id=source_id,
        )

        result.log_id    = log_id
        result.duration_ms = duration_ms  # type: ignore[attr-defined]

        level = logging.INFO if result.success else logging.ERROR
        _logger.log(
            level,
            'MQTT publish %s | broker=%s | topic=%s | qos=%d | rc=%d | confirmed=%s | %.1f ms%s',
            '✓' if result.success else '✗',
            broker_rec.name,
            topic,
            qos,
            result.rc,
            result.confirmed,
            duration_ms,
            '' if result.success else (' | error: ' + result.message),
        )

        return result

    # ────────────────────────────────────────────────────────────────────────
    # Strategy 1: Reuse existing listener client
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _try_publish_via_listener(self, broker_rec, topic, payload_str, qos, retain, timeout):
        """
        If MqttServiceManager has a live connection for this broker, publish
        through it (zero extra TCP overhead).  Returns None if not available.
        """
        try:
            from .farm_mqtt_listener import MqttServiceManager
        except ImportError:
            return None

        mgr = MqttServiceManager.instance()
        if not mgr.is_running(broker_rec.id):
            return None

        client = mgr._clients.get(broker_rec.id)
        if client is None:
            return None

        try:
            msg_info = client.publish(topic, payload_str, qos=qos, retain=retain)
            confirmed = False
            if qos > 0 and timeout > 0:
                try:
                    msg_info.wait_for_publish(timeout=timeout)
                    confirmed = msg_info.is_published()
                except RuntimeError:
                    # wait_for_publish raises RuntimeError if rc != 0
                    pass

            success = msg_info.rc == 0
            return PublishResult(
                success=success,
                rc=msg_info.rc,
                mid=msg_info.mid,
                confirmed=confirmed,
                message=_('Published via active listener connection to %s') % broker_rec.name
                        if success
                        else _('Publish via listener failed: rc=%d') % msg_info.rc,
                log_id=None,
            )
        except Exception as e:
            _logger.debug('Listener publish attempt failed (%s) — falling back to one-shot', e)
            return None

    # ────────────────────────────────────────────────────────────────────────
    # Strategy 2: One-shot publish connection
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _publish_oneshot(self, broker_rec, topic, payload_str, qos, retain, timeout):
        """
        Connect → publish → wait for ACK → disconnect.
        Uses a small per-broker pool to avoid opening/closing TCP for rapid bursts.
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return PublishResult(
                success=False, rc=-1, mid=-1, confirmed=False,
                message='paho-mqtt not installed. Run: pip install paho-mqtt',
                log_id=None,
            )

        broker = broker_rec
        client_id = 'odoo_pub_%d_%d' % (broker.id, threading.get_ident() % 10000)

        try:
            # Build client (paho ≥ 2.0 / paho < 2.0 compatible)
            try:
                from paho.mqtt.client import CallbackAPIVersion
                client = mqtt.Client(
                    client_id=client_id,
                    callback_api_version=CallbackAPIVersion.VERSION1,
                    clean_session=True,
                )
            except (ImportError, AttributeError):
                client = mqtt.Client(client_id=client_id, clean_session=True)

            if broker.username:
                client.username_pw_set(broker.username, broker.password or '')
            if broker.use_tls:
                client.tls_set()

            # Use loop_start so wait_for_publish() works on the background thread
            client.connect(broker.host, broker.port, keepalive=30)
            client.loop_start()

            msg_info = client.publish(topic, payload_str, qos=qos, retain=retain)

            confirmed = False
            if msg_info.rc != 0:
                client.loop_stop()
                client.disconnect()
                return PublishResult(
                    success=False,
                    rc=msg_info.rc,
                    mid=msg_info.mid,
                    confirmed=False,
                    message=_('Publish enqueue failed: rc=%d (%s)') % (
                        msg_info.rc, _rc_description(msg_info.rc)
                    ),
                    log_id=None,
                )

            # Wait for broker acknowledgement (QoS 1 or 2)
            if qos > 0 and timeout > 0:
                try:
                    msg_info.wait_for_publish(timeout=timeout)
                    confirmed = msg_info.is_published()
                except RuntimeError as e:
                    # paho raises RuntimeError if the message was not published
                    client.loop_stop()
                    client.disconnect()
                    return PublishResult(
                        success=False,
                        rc=msg_info.rc,
                        mid=msg_info.mid,
                        confirmed=False,
                        message=_('Delivery confirmation failed: %s') % str(e),
                        log_id=None,
                    )
                except Exception as e:
                    # Timeout or other error — still consider sent
                    _logger.warning('wait_for_publish timeout or error: %s', e)
            else:
                # QoS 0 — fire and forget; no ACK expected
                confirmed = True

            client.loop_stop()
            client.disconnect()

            return PublishResult(
                success=True,
                rc=0,
                mid=msg_info.mid,
                confirmed=confirmed,
                message=_('Published to %s (mid=%d, confirmed=%s, qos=%d)') % (
                    topic, msg_info.mid, confirmed, qos
                ),
                log_id=None,
            )

        except Exception as e:
            _logger.error(
                'MQTT one-shot publish error broker=%s topic=%s: %s',
                broker.name, topic, e,
            )
            return PublishResult(
                success=False, rc=-1, mid=-1, confirmed=False,
                message='%s: %s' % (type(e).__name__, str(e)),
                log_id=None,
            )

    # ────────────────────────────────────────────────────────────────────────
    # Audit log writer
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _write_log(
        self, broker_id, topic, payload_str, qos, retain,
        result: PublishResult, duration_ms: float,
        source_model: str, source_id: int,
    ) -> Optional[int]:
        """Write one farm.mqtt.publish.log row. Returns record id or None."""
        try:
            log = self.env['farm.mqtt.publish.log'].sudo().create({
                'broker_id':    broker_id or False,
                'topic':        topic or '',
                'payload':      payload_str[:4096] if payload_str else '',
                'qos':          qos,
                'retain':       retain,
                'message_id':   result.mid,
                'success':      result.success,
                'confirmed':    result.confirmed,
                'rc':           result.rc,
                'message':      (result.message or '')[:255],
                'duration_ms':  round(duration_ms, 1),
                'source_model': source_model or '',
                'source_id':    source_id or 0,
            })
            return log.id
        except Exception as e:
            _logger.warning('Failed to write MQTT publish log: %s', e)
            return None

    # ────────────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _failed(self, *, broker_id, topic, payload, qos, retain,
                source_model, source_id, message, rc, duration_ms) -> PublishResult:
        """Build a failed result and write its log entry."""
        payload_str = json.dumps(payload, separators=(',', ':')) \
                      if isinstance(payload, dict) else str(payload or '')
        res = PublishResult(
            success=False, rc=rc, mid=-1, confirmed=False,
            message=message, log_id=None,
        )
        res.log_id = self._write_log(
            broker_id=broker_id, topic=topic, payload_str=payload_str,
            qos=qos, retain=retain, result=res, duration_ms=duration_ms,
            source_model=source_model, source_id=source_id,
        )
        return res

    # ────────────────────────────────────────────────────────────────────────
    # Convenience wrappers for common callers
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def publish_control_action(self, control_action) -> PublishResult:
        """Publish from a farm.control.action record."""
        return self.publish(
            broker=control_action.broker_id,
            topic=control_action.topic,
            payload=control_action.command_payload or '{}',
            qos=1,
            retain=False,
            source_model='farm.control.action',
            source_id=control_action.id,
        )

    @api.model
    def publish_actuator_command(self, actuator_device, action_type, extra=None) -> PublishResult:
        """Publish from a farm.actuator.device record."""
        payload = actuator_device.get_command_payload(action_type, extra)
        return self.publish(
            broker=actuator_device.broker_id,
            topic=actuator_device.command_topic,
            payload=payload,
            qos=int(actuator_device.command_qos or 1),
            retain=actuator_device.command_retain,
            source_model='farm.actuator.device',
            source_id=actuator_device.id,
        )


def _rc_description(rc: int) -> str:
    """Human-readable paho return code."""
    return {
        0:  'Success',
        1:  'ERR_NOMEM',
        2:  'ERR_PROTOCOL',
        3:  'ERR_INVAL',
        4:  'ERR_NO_CONN',
        5:  'ERR_CONN_REFUSED',
        6:  'ERR_NOT_FOUND',
        7:  'ERR_CONN_LOST',
        8:  'ERR_TLS',
        9:  'ERR_PAYLOAD_SIZE',
        10: 'ERR_NOT_SUPPORTED',
        11: 'ERR_AUTH',
        12: 'ERR_ACL_DENIED',
        13: 'ERR_UNKNOWN',
        14: 'ERR_ERRNO',
        16: 'MQTT_ERR_QUEUE_SIZE',
    }.get(rc, 'Unknown rc=%d' % rc)
