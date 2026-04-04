# -*- coding: utf-8 -*-
"""
Smart Farm — MQTT Listener Service
=====================================
Subscribes to ``farm/sensors/#`` and routes incoming payloads to
``farm.sensor.data`` records.

Architecture
────────────
  MqttServiceManager   — pure-Python class; owns paho clients and threads;
                         lives at module level so it survives ORM reloads.
  FarmMqttListenerService — Odoo AbstractModel; thin ORM wrapper that reads
                            configuration from ir.config_parameter and broker
                            records, then delegates to MqttServiceManager.

Auto-start
──────────
  _post_load_hook() is registered on odoo.addons.__init__ equivalent via
  post_load.  On first model load the hook fires once per Odoo worker process,
  reads active broker configs, and starts listeners.

  A cron job (data/cron.xml) calls start_all_listeners() hourly so that
  newly created brokers are picked up and dropped connections are revived.

Topic schema
────────────
  farm/sensors/<device_id>               →  JSON multi-metric payload
  farm/sensors/<device_id>/temperature   →  plain float
  farm/sensors/<device_id>/humidity      →  plain float
  farm/sensors/<device_id>/co2           →  plain float

JSON payload keys accepted
──────────────────────────
  temperature / temp / t
  humidity    / hum  / h
  co2         / co2_ppm / ppm
  timestamp   (ISO-8601 or Unix epoch — optional, falls back to now())

Error handling policy
─────────────────────
  • Unknown device_id   → DEBUG log, ignored silently
  • Malformed payload   → WARNING log, message dropped
  • Missing metric keys → WARNING per bad key, rest processed
  • DB write errors     → ERROR log, reading dropped, service stays alive
  • paho not installed  → WARNING at startup, REST/RPC path still works
  • Broker unreachable  → exponential back-off (5 → 10 → 20 → 30 s cap)
"""

import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# ── Topic / schema constants ──────────────────────────────────────────────────
CANONICAL_PREFIX = 'farm/sensors/'
CANONICAL_TOPIC  = 'farm/sensors/#'

# ── Reconnection tuning ───────────────────────────────────────────────────────
RECONNECT_INITIAL = 5    # seconds
RECONNECT_MAX     = 30   # seconds cap
KEEPALIVE_DEFAULT = 60   # seconds

# ── Sensor cache tuning ───────────────────────────────────────────────────────
CACHE_TTL     = 120   # seconds before re-querying DB
CACHE_MAXSIZE = 500   # max device_id entries

# ── Payload field mapping ─────────────────────────────────────────────────────
_KEY_MAP = {
    'temperature': 'temperature', 'temp': 'temperature', 't':     'temperature',
    'humidity':    'humidity',    'hum':  'humidity',    'h':     'humidity',
    'co2':         'co2',         'co2_ppm': 'co2',      'ppm':   'co2',
}

# ── PAHO RC code descriptions ─────────────────────────────────────────────────
_PAHO_RC = {
    1: 'bad protocol version',
    2: 'client ID rejected',
    3: 'server unavailable',
    4: 'bad username or password',
    5: 'not authorised',
}


# ─────────────────────────────────────────────────────────────────────────────
# TTL-LRU sensor cache
# ─────────────────────────────────────────────────────────────────────────────
class _SensorCache:
    """
    Thread-safe TTL-LRU cache mapping device_id → sensor DB id.
    Negative-caches unknown device IDs to prevent DB hammering.
    """

    _MISS = object()   # sentinel for "known miss" (sensor not in DB)

    def __init__(self, ttl=CACHE_TTL, maxsize=CACHE_MAXSIZE):
        self._store = OrderedDict()   # device_id → (value_or_MISS, monotonic_expiry)
        self._ttl   = ttl
        self._max   = maxsize
        self._lock  = threading.Lock()

    def get(self, device_id):
        """
        Return the cached sensor DB id (int), None if unknown, or
        the sentinel _MISS if the key isn't in cache at all.
        """
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return self._MISS
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._store[device_id]
                return self._MISS
            self._store.move_to_end(device_id)   # LRU bump
            return value   # int (sensor id) or None (known absent)

    def put(self, device_id, sensor_id_or_none):
        """Cache a positive (int) or negative (None) result."""
        with self._lock:
            if len(self._store) >= self._max:
                self._store.popitem(last=False)   # evict LRU
            self._store[device_id] = (sensor_id_or_none, time.monotonic() + self._ttl)

    def invalidate(self, device_id=None):
        """Flush one entry or the entire cache."""
        with self._lock:
            if device_id is not None:
                self._store.pop(device_id, None)
            else:
                self._store.clear()

    def __len__(self):
        with self._lock:
            return len(self._store)


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python service manager (module-level singleton, survives ORM reloads)
# ─────────────────────────────────────────────────────────────────────────────
class MqttServiceManager:
    """
    Module-level singleton that owns all paho MQTT client threads.
    Stored on the class so it is not garbage-collected when the Odoo ORM
    rebuilds its model registry (which happens on module updates).

    Usage (from Odoo code):
        manager = MqttServiceManager.instance()
        manager.start(broker_config)
        manager.stop(broker_id)
        manager.stop_all()
        manager.status()          # dict of broker_id → status string
    """

    _instance = None
    _lock     = threading.Lock()

    # ── per-broker state ──────────────────────────────────────────────────────
    #   _clients   : broker_id → paho.Client
    #   _threads   : broker_id → Thread
    #   _status    : broker_id → 'starting'|'connected'|'disconnected'|'error'
    #   _last_error: broker_id → str
    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self):
        self._clients     = {}
        self._threads     = {}
        self._status      = {}
        self._last_error  = {}
        self._state_lock  = threading.Lock()
        self.sensor_cache = _SensorCache()

    @classmethod
    def instance(cls):
        """Return (or create) the process-wide singleton."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Public control surface ────────────────────────────────────────────────

    def start(self, broker_config):
        """
        Start a listener for the given broker configuration dict.

        broker_config keys:
          id          (int)  — farm.mqtt.broker DB id
          host        (str)  — broker hostname / IP
          port        (int)  — broker port (default 1883)
          username    (str)  — optional
          password    (str)  — optional
          use_tls     (bool) — default False
          client_id   (str)  — MQTT client ID
          keepalive   (int)  — seconds (default 60)
          base_topic  (str)  — legacy topic prefix
          dbname      (str)  — Odoo database name

        Returns True if a new listener was started, False if already running.
        """
        bid = broker_config['id']
        with self._state_lock:
            thr = self._threads.get(bid)
            if thr and thr.is_alive():
                _logger.debug('MQTT manager: broker %d already running', bid)
                return False
            # Clean up a dead thread
            if thr:
                self._threads.pop(bid, None)
                self._clients.pop(bid, None)

        self._status[bid] = 'starting'
        _logger.info(
            'MQTT manager: starting listener for broker %d (%s:%d)',
            bid, broker_config['host'], broker_config['port'],
        )

        client = self._build_client(broker_config)
        if client is None:
            return False

        thread = threading.Thread(
            target=self._run_loop,
            args=(client, broker_config),
            daemon=True,
            name='mqtt_%d_%s' % (bid, broker_config.get('dbname', 'odoo')),
        )
        thread.start()

        with self._state_lock:
            self._clients[bid] = client
            self._threads[bid] = thread

        return True

    def stop(self, broker_id):
        """Gracefully stop a specific broker's listener."""
        with self._state_lock:
            client = self._clients.pop(broker_id, None)
            self._threads.pop(broker_id, None)

        if client:
            try:
                client.loop_stop()
                client.disconnect()
                _logger.info('MQTT manager: broker %d stopped', broker_id)
            except Exception as e:
                _logger.warning('MQTT manager: error stopping broker %d: %s', broker_id, e)
            self._status[broker_id] = 'disconnected'

    def stop_all(self):
        """Gracefully stop all listeners."""
        with self._state_lock:
            broker_ids = list(self._clients.keys())
        for bid in broker_ids:
            self.stop(bid)
        self.sensor_cache.invalidate()
        _logger.info('MQTT manager: all listeners stopped')

    def status(self):
        """Return a dict of broker_id → status string for logging / display."""
        with self._state_lock:
            return dict(self._status)

    def is_running(self, broker_id):
        thr = self._threads.get(broker_id)
        return bool(thr and thr.is_alive())

    # ── Client construction ───────────────────────────────────────────────────

    def _build_client(self, cfg):
        """Build and configure a paho MQTT client. Returns None on ImportError."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _logger.warning(
                'MQTT manager: paho-mqtt not installed — '
                'run: pip install paho-mqtt  then restart Odoo'
            )
            self._status[cfg['id']] = 'error'
            self._last_error[cfg['id']] = 'paho-mqtt not installed'
            return None

        bid = cfg['id']
        cid = cfg.get('client_id') or ('odoo_smartfarm_%d' % bid)

        # paho ≥ 2.0 requires explicit CallbackAPIVersion
        try:
            from paho.mqtt.client import CallbackAPIVersion
            client = mqtt.Client(
                client_id=cid,
                callback_api_version=CallbackAPIVersion.VERSION1,
                clean_session=True,
            )
        except (ImportError, AttributeError):
            # paho < 2.0
            client = mqtt.Client(client_id=cid, clean_session=True)

        if cfg.get('username'):
            client.username_pw_set(cfg['username'], cfg.get('password') or '')

        if cfg.get('use_tls'):
            try:
                client.tls_set()
            except Exception as e:
                _logger.warning('MQTT manager: TLS setup failed for broker %d: %s', bid, e)

        # Attach callbacks
        client.on_connect    = self._make_on_connect(cfg)
        client.on_disconnect = self._make_on_disconnect(cfg)
        client.on_message    = self._make_on_message(cfg)

        return client

    # ── Reconnect loop ────────────────────────────────────────────────────────

    def _run_loop(self, client, cfg):
        """
        Daemon thread body: connect → loop_forever → reconnect on failure.
        Exponential back-off: 5 → 10 → 20 → 30 s (capped).
        Exits cleanly only when stop() is called (loop_forever returns 0).
        """
        bid     = cfg['id']
        host    = cfg['host']
        port    = cfg['port']
        ka      = cfg.get('keepalive') or KEEPALIVE_DEFAULT
        backoff = RECONNECT_INITIAL

        while True:
            # Abort if we've been removed from the registry (stop() was called)
            with self._state_lock:
                if bid not in self._clients:
                    break

            try:
                _logger.info('MQTT: connecting to %s:%d (broker %d)', host, port, bid)
                client.connect(host, port, keepalive=ka)
                backoff = RECONNECT_INITIAL   # reset on success
                client.loop_forever(retry_first_connection=True)

                # loop_forever() returns when disconnect() is called intentionally
                _logger.info('MQTT: broker %d disconnected cleanly', bid)
                break

            except ConnectionRefusedError:
                self._status[bid] = 'error'
                self._last_error[bid] = 'Connection refused'
                _logger.warning(
                    'MQTT: broker %d (%s:%d) refused connection — retry in %ds',
                    bid, host, port, backoff,
                )
            except OSError as e:
                self._status[bid] = 'error'
                self._last_error[bid] = str(e)
                _logger.warning(
                    'MQTT: broker %d network error: %s — retry in %ds', bid, e, backoff
                )
            except Exception as e:
                self._status[bid] = 'error'
                self._last_error[bid] = str(e)
                _logger.error(
                    'MQTT: broker %d unexpected error: %s — retry in %ds', bid, e, backoff
                )

            # Update Odoo DB broker state on error
            self._db_update_broker_state(cfg['dbname'], bid, 'error', self._last_error[bid])
            time.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX)

        # Thread is exiting — clean up registry
        with self._state_lock:
            self._clients.pop(bid, None)
            self._threads.pop(bid, None)
        _logger.info('MQTT: listener thread for broker %d exited', bid)

    # ── paho callback factories ────────────────────────────────────────────────

    def _make_on_connect(self, cfg):
        bid        = cfg['id']
        dbname     = cfg['dbname']
        base_topic = cfg.get('base_topic') or ''

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                # Subscribe to canonical topic + legacy base_topic
                client.subscribe(CANONICAL_TOPIC, qos=1)
                _logger.info('MQTT broker %d: subscribed to %s', bid, CANONICAL_TOPIC)

                if base_topic and base_topic.rstrip('/') != 'farm/sensors':
                    legacy = base_topic.rstrip('/') + '/#'
                    client.subscribe(legacy, qos=1)
                    _logger.info('MQTT broker %d: also subscribed to legacy %s', bid, legacy)

                self._status[bid]         = 'connected'
                self._last_error[bid]     = ''
                self._db_update_broker_state(dbname, bid, 'connected')

            else:
                reason = _PAHO_RC.get(rc, 'rc=%d' % rc)
                self._status[bid]     = 'error'
                self._last_error[bid] = reason
                _logger.error('MQTT broker %d connection refused: %s', bid, reason)
                self._db_update_broker_state(dbname, bid, 'error', reason)

        return on_connect

    def _make_on_disconnect(self, cfg):
        bid = cfg['id']

        def on_disconnect(client, userdata, rc):
            prev_status = self._status.get(bid, 'unknown')
            if rc == 0:
                self._status[bid] = 'disconnected'
                _logger.info('MQTT broker %d: clean disconnect', bid)
            else:
                self._status[bid] = 'disconnected'
                _logger.warning(
                    'MQTT broker %d: unexpected disconnect rc=%d (was %s) — will reconnect',
                    bid, rc, prev_status,
                )

        return on_disconnect

    def _make_on_message(self, cfg):
        bid    = cfg['id']
        dbname = cfg['dbname']

        def on_message(client, userdata, msg):
            try:
                raw = msg.payload.decode('utf-8', errors='replace').strip()
            except Exception:
                raw = ''

            try:
                _route_message(
                    manager=self,
                    dbname=dbname,
                    broker_id=bid,
                    base_topic=cfg.get('base_topic') or '',
                    topic=msg.topic,
                    raw=raw,
                )
            except Exception as e:
                _logger.error(
                    'MQTT broker %d: unhandled error on topic=%s: %s',
                    bid, msg.topic, e, exc_info=False,
                )

        return on_message

    # ── DB helpers (called from paho threads — own cursor) ────────────────────

    @staticmethod
    def _db_update_broker_state(dbname, broker_id, state, error=None):
        """Best-effort DB update — never raises."""
        try:
            import odoo
            with odoo.registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                vals = {'state': state}
                if state == 'connected':
                    vals['last_connected'] = fields.Datetime.now()
                    vals['last_error']     = False
                elif error:
                    vals['last_error'] = str(error)[:255]
                env['farm.mqtt.broker'].browse(broker_id).write(vals)
                cr.commit()
        except Exception as e:
            _logger.debug('MQTT: could not update broker %d state in DB: %s', broker_id, e)


# ─────────────────────────────────────────────────────────────────────────────
# Message routing functions (module-level — no self, no ORM)
# ─────────────────────────────────────────────────────────────────────────────

def _route_message(manager, dbname, broker_id, base_topic, topic, raw):
    """Parse topic, resolve sensor, build vals, persist — all in one call."""

    # 1. Parse topic
    device_id, metric = _parse_topic(topic, base_topic)
    if device_id is None:
        _logger.debug('MQTT: ignoring topic outside schema: %s', topic)
        return

    # 2. Resolve sensor (cache-first)
    cache  = manager.sensor_cache
    cached = cache.get(device_id)

    if cached is cache._MISS:
        sensor_id = _db_lookup_sensor(dbname, device_id)
        cache.put(device_id, sensor_id)   # None = known miss
    else:
        sensor_id = cached

    if sensor_id is None:
        _logger.debug('MQTT: unknown device_id=%r on %s — ignored', device_id, topic)
        return

    # 3. Parse payload
    payload = _parse_payload(raw, metric, device_id, topic)
    if payload is None:
        return

    # 4. Persist
    _db_persist(dbname, sensor_id, payload, raw)


def _parse_topic(topic, base_topic):
    """
    Return (device_id, metric_or_None) from an MQTT topic.

    Canonical:  farm/sensors/<id>           → (<id>, None)
                farm/sensors/<id>/temp      → (<id>, 'temp')
    Legacy:     <base_topic>/<id>           → (<id>, None)
                <base_topic>/<id>/humidity  → (<id>, 'humidity')
    Other:      (None, None)
    """
    if topic.startswith(CANONICAL_PREFIX):
        rel = topic[len(CANONICAL_PREFIX):]
    elif base_topic:
        prefix = base_topic.rstrip('/') + '/'
        if topic.startswith(prefix):
            rel = topic[len(prefix):]
        else:
            return None, None
    else:
        return None, None

    parts = [p for p in rel.split('/') if p]
    if not parts:
        return None, None

    device_id = parts[0]
    metric    = parts[1].lower() if len(parts) > 1 else None
    return device_id, metric


def _parse_payload(raw, metric, device_id, topic):
    """
    Convert raw string to a metric dict.
    Returns None if the payload is unusable.
    Internal timestamps stored under key '_ts' (str, Odoo format).
    """
    result = {}

    if metric:
        # Per-metric: plain float expected
        field = _KEY_MAP.get(metric)
        if field is None:
            _logger.debug('MQTT: unsupported metric %r on %s', metric, topic)
            return None
        try:
            result[field] = float(raw)
        except (ValueError, TypeError):
            _logger.warning(
                'MQTT: non-numeric value for %s on %s: %r', metric, topic, raw[:50]
            )
            return None

    else:
        # JSON envelope
        if not raw:
            _logger.debug('MQTT: empty payload on %s', topic)
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            _logger.warning('MQTT: JSON parse error on %s: %s | payload: %r', topic, exc, raw[:80])
            return None
        if not isinstance(data, dict):
            _logger.warning('MQTT: payload is not a JSON object on %s', topic)
            return None

        for key, field in _KEY_MAP.items():
            if key in data and field not in result:
                try:
                    result[field] = float(data[key])
                except (ValueError, TypeError):
                    _logger.warning(
                        'MQTT: bad value for key=%r device=%s: %r', key, device_id, data[key]
                    )

        # Optional device_id override in payload (ignored — topic wins)

        # Optional timestamp
        if 'timestamp' in data:
            try:
                ts_raw = data['timestamp']
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                else:
                    ts = datetime.fromisoformat(str(ts_raw).replace('Z', '+00:00'))
                result['_ts'] = fields.Datetime.to_string(ts.replace(tzinfo=None))
            except Exception:
                pass   # fall through to now()

    # Must have at least one real metric
    if not {'temperature', 'humidity', 'co2'} & set(result):
        _logger.debug('MQTT: no metric keys found for device=%s on %s', device_id, topic)
        return None

    return result


def _db_lookup_sensor(dbname, device_id):
    """Query DB for active sensor by device_id. Returns int id or None."""
    try:
        import odoo
        with odoo.registry(dbname).cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            sensor = env['farm.sensor'].search(
                [('sensor_id', '=', device_id), ('active', '=', True)],
                limit=1,
            )
            sid = sensor.id
            if not sid:
                _logger.debug('MQTT: no active sensor for device_id=%r', device_id)
            return sid or None
    except Exception as e:
        _logger.error('MQTT: DB lookup failed for device_id=%r: %s', device_id, e)
        return None


def _db_persist(dbname, sensor_id, payload, raw):
    """Write a farm.sensor.data record. Commits its own cursor."""
    now = fields.Datetime.now()
    vals = {
        'sensor_id':       sensor_id,
        'reading_time':    payload.get('_ts', now),
        'source':          'mqtt',
        'raw_payload':     (raw or '')[:4096],
        'has_temperature': 'temperature' in payload,
        'has_humidity':    'humidity'    in payload,
        'has_co2':         'co2'         in payload,
    }
    if 'temperature' in payload:
        vals['temperature'] = payload['temperature']
    if 'humidity' in payload:
        vals['humidity'] = payload['humidity']
    if 'co2' in payload:
        vals['co2'] = payload['co2']

    try:
        import odoo
        with odoo.registry(dbname).cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            env['farm.sensor.data'].create(vals)
            cr.commit()
            _logger.debug(
                'MQTT: persisted reading sensor_id=%d temp=%s hum=%s co2=%s',
                sensor_id,
                payload.get('temperature', '-'),
                payload.get('humidity', '-'),
                payload.get('co2', '-'),
            )
    except Exception as e:
        _logger.error('MQTT: DB write failed for sensor_id=%d: %s', sensor_id, e)


# ─────────────────────────────────────────────────────────────────────────────
# Post-load hook — fires once per Odoo worker process after registry load
# ─────────────────────────────────────────────────────────────────────────────

def _post_load_hook():
    """
    Called by Odoo after the module registry is fully loaded.
    Reads broker configs from the DB and starts MQTT listeners.
    Skipped gracefully if:
      • paho-mqtt is not installed
      • No active brokers in DB
      • Broker is unreachable (reconnect loop handles it)
    """
    try:
        import paho.mqtt.client   # noqa: F401
    except ImportError:
        _logger.info(
            'Smart Farm MQTT: paho-mqtt not installed — listeners will not auto-start.\n'
            '  Install with: pip install "paho-mqtt>=1.6,<3"\n'
            '  Restart Odoo after installation.'
        )
        return

    try:
        import odoo
        dbname = odoo.tools.config.get('db_name') or ''
        if not dbname:
            _logger.debug('MQTT post-load: no db_name in config — skipping auto-start')
            return

        with odoo.registry(dbname).cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            brokers = env['farm.mqtt.broker'].search([('active', '=', True)])
            if not brokers:
                _logger.info('MQTT post-load: no active brokers configured — nothing started')
                return

            manager = MqttServiceManager.instance()
            started = 0
            for broker in brokers:
                cfg = _broker_to_config(broker, dbname)
                if manager.start(cfg):
                    started += 1

            _logger.info(
                'MQTT post-load: started %d listener(s) for %d active broker(s)',
                started, len(brokers),
            )

    except Exception as e:
        _logger.warning('MQTT post-load hook failed (non-fatal): %s', e)


def _broker_to_config(broker, dbname):
    """Convert a farm.mqtt.broker record to a plain config dict."""
    return {
        'id':         broker.id,
        'host':       broker.host or 'localhost',
        'port':       broker.port or 1883,
        'username':   broker.username or '',
        'password':   broker.password or '',
        'use_tls':    bool(broker.use_tls),
        'client_id':  broker.client_id or ('odoo_smartfarm_%d' % broker.id),
        'keepalive':  broker.keepalive or KEEPALIVE_DEFAULT,
        'base_topic': broker.base_topic or 'smartfarm',
        'dbname':     dbname,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Odoo AbstractModel — ORM wrapper / public API surface
# ─────────────────────────────────────────────────────────────────────────────
class FarmMqttListenerService(models.AbstractModel):
    """
    Thin ORM wrapper around MqttServiceManager.

    All heavy lifting (threading, reconnect, cursor management) lives in
    MqttServiceManager and the module-level functions above.  This class:
      • provides a stable Odoo RPC surface
      • reads ir.config_parameter overrides
      • is callable from cron, UI buttons, and the shell
    """

    _name        = 'farm.mqtt.listener.service'
    _description = 'Farm MQTT Listener Service'

    # ── Configuration parameter keys ─────────────────────────────────────────
    # Admins can set these in Settings → Technical → Parameters
    # to override individual broker defaults.
    PARAM_HOST     = 'smart_farm.mqtt_host'
    PARAM_PORT     = 'smart_farm.mqtt_port'
    PARAM_USER     = 'smart_farm.mqtt_username'
    PARAM_PASS     = 'smart_farm.mqtt_password'
    PARAM_TLS      = 'smart_farm.mqtt_use_tls'
    PARAM_TOPIC    = 'smart_farm.mqtt_base_topic'
    PARAM_ENABLED  = 'smart_farm.mqtt_enabled'

    # ── Public API ────────────────────────────────────────────────────────────

    @api.model
    def start_all_listeners(self):
        """
        Start listeners for all active brokers.  Idempotent.
        Reads ir.config_parameter overrides for host/port/credentials.
        Called by: hourly cron, broker form "Start Listener" button, shell.
        """
        if not self._is_globally_enabled():
            _logger.info('MQTT: service disabled via smart_farm.mqtt_enabled=false')
            return 0

        try:
            import paho.mqtt.client  # noqa: F401
        except ImportError:
            _logger.warning(
                'MQTT: paho-mqtt not installed — run: pip install paho-mqtt'
            )
            return 0

        brokers = self.env['farm.mqtt.broker'].search([('active', '=', True)])
        if not brokers:
            _logger.info('MQTT: no active brokers — nothing to start')
            return 0

        manager = MqttServiceManager.instance()
        dbname  = self.env.cr.dbname
        started = 0

        for broker in brokers:
            cfg = self._broker_to_config_with_overrides(broker, dbname)
            if manager.start(cfg):
                started += 1
                _logger.info(
                    'MQTT: started listener for broker %d (%s:%d)',
                    broker.id, cfg['host'], cfg['port'],
                )
            else:
                _logger.debug('MQTT: broker %d already running', broker.id)

        _logger.info('MQTT: %d new listener(s) started, %d total brokers', started, len(brokers))
        return started

    @api.model
    def stop_all_listeners(self):
        """Stop all running listeners. Useful for testing or maintenance."""
        MqttServiceManager.instance().stop_all()

    @api.model
    def start_one_broker(self, broker):
        """Start listener for a single broker record. Returns True if newly started."""
        if not self._is_globally_enabled():
            return False
        try:
            import paho.mqtt.client  # noqa: F401
        except ImportError:
            return False
        cfg = self._broker_to_config_with_overrides(broker, self.env.cr.dbname)
        return MqttServiceManager.instance().start(cfg)

    @api.model
    def stop_one_broker(self, broker_id):
        """Stop listener for a single broker by DB id."""
        MqttServiceManager.instance().stop(broker_id)

    @api.model
    def get_status(self):
        """
        Return listener status dict: { broker_id: status_str }.
        Status values: 'starting' | 'connected' | 'disconnected' | 'error'
        """
        return MqttServiceManager.instance().status()

    @api.model
    def invalidate_sensor_cache(self, device_id=None):
        """Flush sensor cache. Call after adding/renaming/deactivating a sensor."""
        MqttServiceManager.instance().sensor_cache.invalidate(device_id)

    @api.model
    def ingest_payload(self, device_id_str, payload_dict, source='api'):
        """
        REST / RPC / test entry point — ingest sensor data without MQTT.

        Args
        ────
        device_id_str  str   farm.sensor.sensor_id field value
        payload_dict   dict  e.g. {'temperature': 28.5, 'humidity': 65, 'co2': 420}
        source         str   'api' | 'manual' | 'test'

        Returns the created farm.sensor.data record.
        Raises UserError if the sensor is not found.
        """
        from odoo.exceptions import UserError

        sensor = self.env['farm.sensor'].search(
            [('sensor_id', '=', device_id_str), ('active', '=', True)],
            limit=1,
        )
        if not sensor:
            raise UserError(
                _('Sensor device_id "%s" not found or inactive.') % device_id_str
            )

        payload = {}
        for key, field in _KEY_MAP.items():
            if key in payload_dict and field not in payload:
                try:
                    payload[field] = float(payload_dict[key])
                except (ValueError, TypeError):
                    pass

        if not payload:
            raise UserError(
                _('Payload contains no recognised metric keys. '
                  'Use: temperature, humidity, co2.')
            )

        vals = {
            'sensor_id':       sensor.id,
            'reading_time':    fields.Datetime.now(),
            'source':          source,
            'raw_payload':     json.dumps(payload_dict)[:4096],
            'has_temperature': 'temperature' in payload,
            'has_humidity':    'humidity'    in payload,
            'has_co2':         'co2'         in payload,
        }
        vals.update(payload)
        return self.env['farm.sensor.data'].create(vals)

    @api.model
    def service_info(self):
        """
        Return a human-readable status block for the broker form / shell.
        """
        manager = MqttServiceManager.instance()
        status  = manager.status()
        cache   = manager.sensor_cache
        lines   = ['Smart Farm MQTT Service', '─' * 36]

        brokers = self.env['farm.mqtt.broker'].search([('active', '=', True)])
        for b in brokers:
            st         = status.get(b.id, 'not started')
            running    = '✓' if manager.is_running(b.id) else '✗'
            err        = manager._last_error.get(b.id, '')
            lines.append(
                '  [%s] Broker %d %s:%d — %s%s' % (
                    running, b.id, b.host, b.port, st,
                    ' (%s)' % err if err else '',
                )
            )

        lines.append('Sensor cache entries: %d' % len(cache))
        return '\n'.join(lines)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _is_globally_enabled(self):
        """
        Check ir.config_parameter smart_farm.mqtt_enabled.
        Defaults to True (enabled) if the parameter is not set.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            self.PARAM_ENABLED, default='true'
        )
        return str(param).lower() not in ('false', '0', 'no', 'off')

    def _broker_to_config_with_overrides(self, broker, dbname):
        """
        Build config dict from the broker record, then apply
        ir.config_parameter overrides (admin-set global defaults).
        """
        cfg = _broker_to_config(broker, dbname)

        get = lambda k, d=None: (
            self.env['ir.config_parameter'].sudo().get_param(k, default=d)
        )

        # Only override if the parameter is explicitly set
        host_param = get(self.PARAM_HOST)
        if host_param:
            cfg['host'] = host_param

        port_param = get(self.PARAM_PORT)
        if port_param:
            try:
                cfg['port'] = int(port_param)
            except ValueError:
                pass

        user_param = get(self.PARAM_USER)
        if user_param:
            cfg['username'] = user_param
            cfg['password'] = get(self.PARAM_PASS, '')

        tls_param = get(self.PARAM_TLS)
        if tls_param is not None:
            cfg['use_tls'] = str(tls_param).lower() in ('true', '1', 'yes')

        topic_param = get(self.PARAM_TOPIC)
        if topic_param:
            cfg['base_topic'] = topic_param

        return cfg
