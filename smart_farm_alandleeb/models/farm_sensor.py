# -*- coding: utf-8 -*-
import json
import logging
import threading
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class FarmMqttBroker(models.Model):
    _name = 'farm.mqtt.broker'
    _description = 'MQTT Broker Configuration'
    _order = 'name'

    name       = fields.Char(string='Broker Name', required=True)
    active     = fields.Boolean(default=True)
    host       = fields.Char(string='Host / IP', required=True, default='localhost')
    port       = fields.Integer(string='Port', default=1883)
    use_tls    = fields.Boolean(string='Use TLS/SSL', default=False)
    username   = fields.Char(string='Username')
    password   = fields.Char(string='Password')
    client_id  = fields.Char(string='Client ID', default=lambda self: 'odoo_smart_farm_%d' % (self.env.uid or 1))
    keepalive  = fields.Integer(string='Keepalive (s)', default=60)
    base_topic = fields.Char(string='Base Topic', default='smartfarm',
        help='Root MQTT topic. Sensors publish to: <base_topic>/<sensor_id>/<metric>')

    state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connected',    'Connected'),
        ('error',        'Error'),
    ], string='Status', default='disconnected', readonly=True)

    last_connected = fields.Datetime(string='Last Connected', readonly=True)
    last_error     = fields.Char(string='Last Error', readonly=True)
    sensor_count   = fields.Integer(string='Sensors', compute='_compute_sensor_count')

    def _compute_sensor_count(self):
        for rec in self:
            rec.sensor_count = self.env['farm.sensor'].search_count([('broker_id', '=', rec.id)])

    def action_test_connection(self):
        self.ensure_one()
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(client_id=self.client_id or 'odoo_test')
            if self.username:
                client.username_pw_set(self.username, self.password)
            client.connect(self.host, self.port, keepalive=5)
            client.disconnect()
            self.write({'state': 'connected', 'last_connected': fields.Datetime.now(), 'last_error': False})
            msg = _('Connected to %s:%d') % (self.host, self.port)
            ntype = 'success'
        except ImportError:
            self.write({'state': 'error', 'last_error': 'paho-mqtt not installed'})
            msg  = _('Install paho-mqtt: pip install paho-mqtt. Data can still be ingested via REST API.')
            ntype = 'warning'
        except Exception as e:
            self.write({'state': 'error', 'last_error': str(e)})
            msg  = str(e)
            ntype = 'danger'
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {'title': _('MQTT Test'), 'message': msg, 'type': ntype, 'sticky': ntype != 'success'},
        }

    def action_start_listener(self):
        """Start MQTT listener for this broker via the service manager."""
        self.ensure_one()
        svc     = self.env['farm.mqtt.listener.service']
        started = svc.start_one_broker(self)
        msg  = (
            _('Listener started — subscribing to farm/sensors/#')
            if started else
            _('Listener already running for %s:%d') % (self.host, self.port)
        )
        ntype = 'success' if started else 'info'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('MQTT Listener'), 'message': msg,
                       'type': ntype, 'sticky': False},
        }

    def action_stop_listener(self):
        """Stop the MQTT listener for this broker."""
        self.ensure_one()
        self.env['farm.mqtt.listener.service'].stop_one_broker(self.id)
        self.write({'state': 'disconnected'})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('MQTT Listener'),
                       'message': _('Listener stopped for broker %s') % self.name,
                       'type': 'warning', 'sticky': False},
        }

    def action_service_info(self):
        """Show full service status."""
        info = self.env['farm.mqtt.listener.service'].service_info()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('MQTT Service Status'), 'message': info,
                       'type': 'info', 'sticky': True},
        }

    def action_view_sensors(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Sensors'),
            'res_model': 'farm.sensor', 'view_mode': 'list,form',
            'domain': [('broker_id', '=', self.id)], 'context': {'default_broker_id': self.id},
        }


class FarmSensor(models.Model):
    _name = 'farm.sensor'
    _description = 'Farm Sensor Device'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'farm_id, name'

    name      = fields.Char(string='Sensor Name', required=True, tracking=True)
    sensor_id = fields.Char(string='Sensor ID / Topic', required=True, copy=False,
        help='Unique ID used in MQTT topic. E.g. "s01" → topic: smartfarm/s01/temperature')
    active    = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    sensor_type = fields.Selection([
        ('temperature', 'Temperature'),
        ('humidity',    'Humidity'),
        ('co2',         'CO₂ / Air Quality'),
        ('multi',       'Multi-sensor'),
    ], string='Sensor Type', required=True, default='multi', tracking=True)

    farm_id  = fields.Many2one('farm.farm',    string='Farm',  required=True, tracking=True)
    field_id = fields.Many2one('farm.field',   string='Field', domain="[('farm_id','=',farm_id)]", tracking=True)
    task_id  = fields.Many2one('project.task', string='Task',  tracking=True)

    broker_id  = fields.Many2one('farm.mqtt.broker', string='MQTT Broker', ondelete='set null')
    mqtt_topic = fields.Char(string='MQTT Topic', compute='_compute_mqtt_topic', store=True)

    # Thresholds
    temp_min     = fields.Float(string='Min Temp (°C)',      default=10.0)
    temp_max     = fields.Float(string='Max Temp (°C)',      default=45.0)
    humidity_min = fields.Float(string='Min Humidity (%)',   default=20.0)
    humidity_max = fields.Float(string='Max Humidity (%)',   default=90.0)
    co2_max      = fields.Float(string='Max CO₂ (ppm)',      default=1000.0)
    co2_warning  = fields.Float(string='CO₂ Warning (ppm)', default=800.0)

    # Live cache
    last_temperature = fields.Float(string='Last Temp (°C)',    readonly=True, digits=(6,2))
    last_humidity    = fields.Float(string='Last Humidity (%)', readonly=True, digits=(6,2))
    last_co2         = fields.Float(string='Last CO₂ (ppm)',    readonly=True, digits=(8,0))
    last_reading_at  = fields.Datetime(string='Last Reading',   readonly=True)

    status = fields.Selection([
        ('ok','OK'),('warning','Warning'),('critical','Critical'),('offline','Offline'),
    ], default='offline', readonly=True, tracking=True)

    reading_count = fields.Integer(string='Readings', compute='_compute_reading_count')
    alert_count   = fields.Integer(string='Open Alerts', compute='_compute_alert_count')

    @api.depends('broker_id', 'broker_id.base_topic', 'sensor_id')
    def _compute_mqtt_topic(self):
        for rec in self:
            base = (rec.broker_id.base_topic or 'smartfarm').rstrip('/') if rec.broker_id else 'smartfarm'
            rec.mqtt_topic = '%s/%s' % (base, rec.sensor_id or 'unknown')

    def _compute_reading_count(self):
        SD = self.env['farm.sensor.data']
        for rec in self:
            rec.reading_count = SD.search_count([('sensor_id','=',rec.id)])

    def _compute_alert_count(self):
        SA = self.env['farm.sensor.alert']
        for rec in self:
            rec.alert_count = SA.search_count([('sensor_id','=',rec.id),('resolved','=',False)])

    @api.constrains('sensor_id')
    def _check_unique_sensor_id(self):
        for rec in self:
            if self.search_count([('sensor_id','=',rec.sensor_id),('id','!=',rec.id)]):
                raise ValidationError(_('Sensor ID "%s" is already in use.') % rec.sensor_id)


    def write(self, vals):
        result = super().write(vals)
        # Invalidate MQTT listener cache when sensor identity changes
        if 'sensor_id' in vals or 'active' in vals:
            try:
                listener = self.env['farm.mqtt.listener.service']
                for rec in self:
                    listener.invalidate_sensor_cache(rec.sensor_id)
            except Exception:
                pass  # listener model may not be loaded yet during install
        return result

    def action_view_readings(self):
        self.ensure_one()
        return {'type':'ir.actions.act_window','name':_('Readings – %s') % self.name,
                'res_model':'farm.sensor.data','view_mode':'list,graph,form',
                'domain':[('sensor_id','=',self.id)],'context':{'default_sensor_id':self.id}}

    def action_view_alerts(self):
        self.ensure_one()
        return {'type':'ir.actions.act_window','name':_('Alerts – %s') % self.name,
                'res_model':'farm.sensor.alert','view_mode':'list,form',
                'domain':[('sensor_id','=',self.id),('resolved','=',False)]}


class FarmSensorData(models.Model):
    _name = 'farm.sensor.data'
    _description = 'Farm Sensor Reading'
    _order = 'reading_time desc'
    _rec_name = 'sensor_id'

    sensor_id    = fields.Many2one('farm.sensor', string='Sensor', required=True, ondelete='cascade', index=True)
    farm_id      = fields.Many2one(related='sensor_id.farm_id',  store=True, string='Farm')
    field_id     = fields.Many2one(related='sensor_id.field_id', store=True, string='Field')
    task_id      = fields.Many2one(related='sensor_id.task_id',  store=True, string='Task')

    reading_time = fields.Datetime(string='Reading Time', required=True, default=fields.Datetime.now, index=True)

    temperature  = fields.Float(string='Temperature (°C)', digits=(6,2))
    humidity     = fields.Float(string='Humidity (%)',      digits=(6,2))
    co2          = fields.Float(string='CO₂ (ppm)',         digits=(8,0))

    has_temperature = fields.Boolean(default=False)
    has_humidity    = fields.Boolean(default=False)
    has_co2         = fields.Boolean(default=False)

    status = fields.Selection([
        ('ok','Normal'),('warning','Warning'),('critical','Critical'),
    ], default='ok', readonly=True)

    raw_payload = fields.Text(string='Raw Payload (JSON)', readonly=True)
    source      = fields.Selection([('mqtt','MQTT'),('api','REST API'),('manual','Manual')], default='mqtt', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._evaluate_thresholds()
        return records

    def _evaluate_thresholds(self):
        sensor = self.sensor_id
        alerts = []
        worst  = 'ok'

        def _sev(cur, new):
            order = {'ok': 0, 'warning': 1, 'critical': 2}
            return new if order.get(new, 0) > order.get(cur, 0) else cur

        if self.has_temperature:
            if self.temperature > sensor.temp_max:
                alerts.append({'metric':'temperature','severity':'critical',
                    'value':self.temperature,'threshold':sensor.temp_max,
                    'message':_('Temp %.1f°C > max %.1f°C') % (self.temperature, sensor.temp_max)})
                worst = _sev(worst, 'critical')
            elif self.temperature < sensor.temp_min:
                alerts.append({'metric':'temperature','severity':'warning',
                    'value':self.temperature,'threshold':sensor.temp_min,
                    'message':_('Temp %.1f°C < min %.1f°C') % (self.temperature, sensor.temp_min)})
                worst = _sev(worst, 'warning')

        if self.has_humidity:
            if self.humidity > sensor.humidity_max:
                alerts.append({'metric':'humidity','severity':'critical',
                    'value':self.humidity,'threshold':sensor.humidity_max,
                    'message':_('Humidity %.1f%% > max %.1f%%') % (self.humidity, sensor.humidity_max)})
                worst = _sev(worst, 'critical')
            elif self.humidity < sensor.humidity_min:
                alerts.append({'metric':'humidity','severity':'warning',
                    'value':self.humidity,'threshold':sensor.humidity_min,
                    'message':_('Humidity %.1f%% < min %.1f%%') % (self.humidity, sensor.humidity_min)})
                worst = _sev(worst, 'warning')

        if self.has_co2:
            if self.co2 > sensor.co2_max:
                alerts.append({'metric':'co2','severity':'critical',
                    'value':self.co2,'threshold':sensor.co2_max,
                    'message':_('CO₂ %.0f ppm > max %.0f ppm') % (self.co2, sensor.co2_max)})
                worst = _sev(worst, 'critical')
            elif self.co2 > sensor.co2_warning:
                alerts.append({'metric':'co2','severity':'warning',
                    'value':self.co2,'threshold':sensor.co2_warning,
                    'message':_('CO₂ %.0f ppm > warning %.0f ppm') % (self.co2, sensor.co2_warning)})
                worst = _sev(worst, 'warning')

        self.status = worst

        SensorAlert = self.env['farm.sensor.alert']
        one_hour_ago = fields.Datetime.now() - timedelta(hours=1)
        for a in alerts:
            dup = SensorAlert.search_count([
                ('sensor_id','=',sensor.id),('metric','=',a['metric']),
                ('resolved','=',False),('create_date','>=',fields.Datetime.to_string(one_hour_ago)),
            ])
            if not dup:
                alert = SensorAlert.create({
                    'sensor_id': sensor.id, 'reading_id': self.id,
                    'farm_id': sensor.farm_id.id,
                    'field_id': sensor.field_id.id if sensor.field_id else False,
                    'task_id':  sensor.task_id.id  if sensor.task_id  else False,
                    'metric': a['metric'], 'severity': a['severity'],
                    'actual_value': a['value'], 'threshold_value': a['threshold'],
                    'message': a['message'],
                })
                alert._notify_recipients()

        update_vals = {'last_reading_at': self.reading_time, 'status': worst}
        if self.has_temperature:
            update_vals['last_temperature'] = self.temperature
        if self.has_humidity:
            update_vals['last_humidity'] = self.humidity
        if self.has_co2:
            update_vals['last_co2'] = self.co2
        sensor.write(update_vals)


class FarmSensorAlert(models.Model):
    _name = 'farm.sensor.alert'
    _description = 'Farm Sensor Alert'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    sensor_id  = fields.Many2one('farm.sensor',  string='Sensor',  required=True, ondelete='cascade', index=True)
    reading_id = fields.Many2one('farm.sensor.data', string='Reading', ondelete='set null')
    farm_id    = fields.Many2one('farm.farm',    string='Farm')
    field_id   = fields.Many2one('farm.field',   string='Field')
    task_id    = fields.Many2one('project.task', string='Task')

    metric = fields.Selection([
        ('temperature','Temperature'),('humidity','Humidity'),('co2','CO₂'),
    ], string='Metric', required=True)

    severity = fields.Selection([
        ('warning','Warning'),('critical','Critical'),
    ], string='Severity', required=True, tracking=True)

    actual_value    = fields.Float(string='Actual Value',  digits=(8,2))
    threshold_value = fields.Float(string='Threshold',     digits=(8,2))
    message         = fields.Char(string='Message',        readonly=True)

    resolved         = fields.Boolean(string='Resolved', default=False, tracking=True)
    resolved_at      = fields.Datetime(string='Resolved At',  readonly=True)
    resolved_by      = fields.Many2one('res.users', string='Resolved By', readonly=True)
    resolution_notes = fields.Text(string='Resolution Notes')

    metric_unit = fields.Char(compute='_compute_metric_unit')

    # Link to decision (computed — set by decision engine)
    recommended_action = fields.Char(
        string='Recommended Action',
        compute='_compute_recommended_action',
        help='Recommended action from the linked decision (if any).',
    )

    def _compute_recommended_action(self):
        Dec = self.env['farm.decision']
        for alert in self:
            dec = Dec.search([('alert_id', '=', alert.id)], limit=1, order='create_date desc')
            if dec:
                alert.recommended_action = dict([
                    ('cooling',      'Activate Cooling'),
                    ('heating',      'Activate Heating'),
                    ('irrigation',   'Start Irrigation'),
                    ('dehumidify',   'Dehumidify'),
                    ('co2_inject',   'CO₂ Injection'),
                    ('co2_reduce',   'Reduce CO₂'),
                    ('manual_check', 'Manual Check'),
                    ('alert_only',   'Alert Only'),
                ]).get(dec.action_type, dec.action_type)
            else:
                alert.recommended_action = False

    def _compute_metric_unit(self):
        units = {'temperature': '°C', 'humidity': '%', 'co2': 'ppm'}
        for rec in self:
            rec.metric_unit = units.get(rec.metric, '')

    def action_resolve(self):
        for rec in self:
            rec.write({'resolved': True, 'resolved_at': fields.Datetime.now(), 'resolved_by': self.env.uid})
        for s in self.mapped('sensor_id'):
            open_alerts = self.env['farm.sensor.alert'].search([('sensor_id','=',s.id),('resolved','=',False)])
            if not open_alerts:
                s.status = 'ok'
            elif any(a.severity == 'critical' for a in open_alerts):
                s.status = 'critical'
            else:
                s.status = 'warning'

    def _notify_recipients(self):
        sensor = self.sensor_id
        sev_emoji = '🔴' if self.severity == 'critical' else '⚠️'
        subject = _('%s Sensor Alert: %s — %s') % (sev_emoji, sensor.name, self.message)
        units   = {'temperature': '°C', 'humidity': '%', 'co2': 'ppm'}
        unit    = units.get(self.metric, '')

        body = _(
            '<p><b>%s SENSOR ALERT — %s</b></p>'
            '<table style="border-collapse:collapse;width:100%%"><tbody>'
            '<tr><td style="padding:4px 12px;color:#64748b">Sensor</td><td><b>%s</b> (%s)</td></tr>'
            '<tr><td style="padding:4px 12px;color:#64748b">Farm</td><td>%s</td></tr>'
            '<tr><td style="padding:4px 12px;color:#64748b">Field</td><td>%s</td></tr>'
            '<tr><td style="padding:4px 12px;color:#64748b">Metric</td><td>%s</td></tr>'
            '<tr><td style="padding:4px 12px;color:#64748b">Value</td><td style="color:%s"><b>%.2f %s</b></td></tr>'
            '<tr><td style="padding:4px 12px;color:#64748b">Threshold</td><td>%.2f %s</td></tr>'
            '</tbody></table>'
            '<p style="margin-top:12px">Please review and resolve this alert in Smart Farm.</p>'
        ) % (
            self.severity.upper(), sensor.name,
            sensor.name, sensor.sensor_id,
            sensor.farm_id.name if sensor.farm_id else '—',
            sensor.field_id.name if sensor.field_id else '—',
            self.metric.capitalize(),
            '#ef4444' if self.severity == 'critical' else '#d97706',
            self.actual_value, unit,
            self.threshold_value, unit,
        )

        recipients = self.env['res.users'].browse()
        for gref in ('smart_farm_alandleeb.group_farm_manager', 'smart_farm_alandleeb.group_farm_admin'):
            grp = self.env.ref(gref, raise_if_not_found=False)
            if grp:
                recipients |= grp.users
        if sensor.task_id and sensor.task_id.user_ids:
            recipients |= sensor.task_id.user_ids
        if sensor.farm_id and sensor.farm_id.manager_id:
            recipients |= sensor.farm_id.manager_id

        recipients  = recipients.filtered(lambda u: u.active and not u.share)
        partner_ids = recipients.mapped('partner_id').ids

        if partner_ids:
            sensor.message_post(body=body, subject=subject, message_type='comment',
                                subtype_xmlid='mail.mt_note', partner_ids=partner_ids)
        if sensor.task_id:
            try:
                sensor.task_id.message_post(body=body, subject=subject, message_type='comment',
                                            subtype_xmlid='mail.mt_note', partner_ids=partner_ids)
            except Exception as e:
                _logger.warning('Could not post sensor alert on task: %s', e)


class FarmSensorMqttListener(models.AbstractModel):
    """
    MQTT subscription engine. Starts a paho-mqtt client per broker in a daemon thread.

    Expected message formats
    ────────────────────────
    Per-metric topics (float payload):
        smartfarm/<sensor_id>/temperature  →  28.5
        smartfarm/<sensor_id>/humidity     →  65.2
        smartfarm/<sensor_id>/co2          →  420

    Multi-metric JSON (root topic):
        smartfarm/<sensor_id>  →  {"temperature":28.5,"humidity":65.2,"co2":420}
    """
    _name = 'farm.sensor.mqtt.listener'
    _description = 'MQTT Listener'

    _clients = {}
    _lock    = threading.Lock()

    @api.model
    def start_all_listeners(self):
        try:
            import paho.mqtt.client as mqtt  # noqa
        except ImportError:
            _logger.warning('paho-mqtt not installed — MQTT listeners not started. '
                            'Use REST endpoint or install paho-mqtt.')
            return
        for broker in self.env['farm.mqtt.broker'].search([('active', '=', True)]):
            self._start_broker_listener(broker)

    @api.model
    def _start_broker_listener(self, broker):
        import paho.mqtt.client as mqtt
        bid    = broker.id
        dbname = self.env.cr.dbname

        with self.__class__._lock:
            if bid in self.__class__._clients:
                return

        def on_connect(client, ud, flags, rc):
            if rc == 0:
                topic = (broker.base_topic or 'smartfarm').rstrip('/') + '/#'
                client.subscribe(topic)
                _logger.info('MQTT connected → subscribed to %s', topic)
                try:
                    import odoo
                    with odoo.registry(dbname).cursor() as cr:
                        odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})['farm.mqtt.broker'].browse(bid).write({
                            'state': 'connected', 'last_connected': fields.Datetime.now(), 'last_error': False,
                        })
                except Exception:
                    pass

        def on_message(client, ud, msg):
            try:
                self._ingest(dbname, bid, msg.topic, msg.payload)
            except Exception as e:
                _logger.error('MQTT ingest: %s', e)

        def on_disconnect(client, ud, rc):
            _logger.warning('MQTT disconnected from broker %d', bid)
            with self.__class__._lock:
                self.__class__._clients.pop(bid, None)

        client = mqtt.Client(client_id=broker.client_id or 'odoo_sf_%d' % bid)
        if broker.username:
            client.username_pw_set(broker.username, broker.password)
        if broker.use_tls:
            client.tls_set()
        client.on_connect    = on_connect
        client.on_message    = on_message
        client.on_disconnect = on_disconnect

        try:
            client.connect_async(broker.host, broker.port, keepalive=broker.keepalive or 60)
            client.loop_start()
            with self.__class__._lock:
                self.__class__._clients[bid] = client
            _logger.info('MQTT listener started for broker %d (%s:%d)', bid, broker.host, broker.port)
        except Exception as e:
            _logger.error('MQTT start failed for broker %d: %s', bid, e)
            broker.write({'state': 'error', 'last_error': str(e)})

    @api.model
    def _ingest(self, dbname, broker_id, topic, raw):
        import odoo
        with odoo.registry(dbname).cursor() as cr:
            env  = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            listener = env['farm.sensor.mqtt.listener']
            listener._ingest_env(env, broker_id, topic, raw)

    @api.model
    def _ingest_env(self, env, broker_id, topic, raw):
        broker = env['farm.mqtt.broker'].browse(broker_id)
        base   = (broker.base_topic or 'smartfarm').rstrip('/')
        rel    = topic[len(base):].lstrip('/')
        parts  = rel.split('/')
        if not parts:
            return

        sid    = parts[0]
        metric = parts[1] if len(parts) > 1 else None

        sensor = env['farm.sensor'].search([('sensor_id', '=', sid)], limit=1)
        if not sensor:
            return

        payload_str = (raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)).strip()
        vals = {
            'sensor_id': sensor.id, 'reading_time': fields.Datetime.now(),
            'raw_payload': payload_str, 'source': 'mqtt',
            'has_temperature': False, 'has_humidity': False, 'has_co2': False,
        }

        if metric:
            try:
                v = float(payload_str)
            except ValueError:
                return
            if metric == 'temperature':
                vals.update({'temperature': v, 'has_temperature': True})
            elif metric == 'humidity':
                vals.update({'humidity': v, 'has_humidity': True})
            elif metric in ('co2', 'co2_ppm'):
                vals.update({'co2': v, 'has_co2': True})
            else:
                return
        else:
            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                return
            if 'temperature' in data:
                vals.update({'temperature': float(data['temperature']), 'has_temperature': True})
            if 'humidity' in data:
                vals.update({'humidity': float(data['humidity']), 'has_humidity': True})
            if 'co2' in data or 'co2_ppm' in data:
                vals.update({'co2': float(data.get('co2') or data.get('co2_ppm', 0)), 'has_co2': True})
            if 'timestamp' in data:
                try:
                    from datetime import datetime as dt
                    ts = dt.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                    vals['reading_time'] = fields.Datetime.to_string(ts)
                except Exception:
                    pass

        if not any([vals['has_temperature'], vals['has_humidity'], vals['has_co2']]):
            return
        env['farm.sensor.data'].create(vals)

    @api.model
    def ingest_payload(self, sensor_id_str, payload_dict):
        """
        REST / RPC entry point: ingest sensor data programmatically.
        sensor_id_str : the sensor.sensor_id field value (not DB id)
        payload_dict  : {'temperature': 28.5, 'humidity': 65.0, 'co2': 420}
        """
        sensor = self.env['farm.sensor'].search([('sensor_id', '=', sensor_id_str)], limit=1)
        if not sensor:
            raise UserError(_('Sensor "%s" not found.') % sensor_id_str)
        vals = {
            'sensor_id': sensor.id, 'reading_time': fields.Datetime.now(),
            'raw_payload': json.dumps(payload_dict), 'source': payload_dict.get('source', 'api'),
            'has_temperature': 'temperature' in payload_dict,
            'has_humidity':    'humidity'    in payload_dict,
            'has_co2':         'co2'         in payload_dict,
        }
        if vals['has_temperature']:
            vals['temperature'] = float(payload_dict['temperature'])
        if vals['has_humidity']:
            vals['humidity'] = float(payload_dict['humidity'])
        if vals['has_co2']:
            vals['co2'] = float(payload_dict['co2'])
        return self.env['farm.sensor.data'].create(vals)


# ─────────────────────────────────────────────────────────────────────────────
# farm.sensor.cron  –  Scheduled maintenance: offline check + data purge
# ─────────────────────────────────────────────────────────────────────────────
class FarmSensorCron(models.AbstractModel):
    _name = 'farm.sensor.cron'
    _description = 'Farm Sensor Scheduled Jobs'

    @api.model
    def check_offline_sensors(self, timeout_minutes=30):
        """
        Mark active sensors offline if they haven't reported in `timeout_minutes`.
        Called by cron every 30 minutes.
        """
        from datetime import datetime as dt
        cutoff = fields.Datetime.now() - timedelta(minutes=timeout_minutes)
        offline_sensors = self.env['farm.sensor'].search([
            ('active',         '=', True),
            ('status',         'in', ('ok', 'warning', 'critical')),
            ('last_reading_at', '<', cutoff),
        ])
        if offline_sensors:
            offline_sensors.write({'status': 'offline'})
            _logger.info(
                'Sensor offline check: %d sensors marked offline (no reading for %d min)',
                len(offline_sensors), timeout_minutes,
            )

        # Also check for sensors that never reported
        never_reported = self.env['farm.sensor'].search([
            ('active',         '=', True),
            ('status',         '=', 'offline'),
            ('last_reading_at', '=', False),
        ])
        _logger.debug('Sensor offline check: %d sensors never reported', len(never_reported))
        return len(offline_sensors)

    @api.model
    def purge_old_readings(self, days=90):
        """
        Delete sensor data older than `days` days that did NOT trigger alerts.
        Alert-linked readings are kept for traceability.
        Called by weekly cron.
        """
        cutoff = fields.Datetime.now() - timedelta(days=days)
        alerted_reading_ids = self.env['farm.sensor.alert'].search([]).mapped('reading_id').ids
        to_purge = self.env['farm.sensor.data'].search([
            ('reading_time', '<', cutoff),
            ('id', 'not in', alerted_reading_ids),
            ('status', '=', 'ok'),
        ])
        count = len(to_purge)
        to_purge.unlink()
        _logger.info('Sensor data purge: removed %d readings older than %d days', count, days)
        return count

    @api.model
    def restart_mqtt_listeners(self):
        """Re-start MQTT listeners for all active brokers. Called hourly by cron."""
        self.env['farm.sensor.mqtt.listener'].start_all_listeners()


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Sensor smart button (safe: only added once)
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskSensorSmartButton(models.Model):
    _inherit = 'project.task'

    _sensor_smart_button_added = True  # guard against duplicate definitions

    task_sensor_count = fields.Integer(
        string='Sensors',
        compute='_compute_task_sensor_count',
    )

    def _compute_task_sensor_count(self):
        for task in self:
            task.task_sensor_count = self.env['farm.sensor'].search_count(
                [('task_id', '=', task.id)]
            )

    def action_view_task_sensors(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Sensors – %s') % self.name,
            'res_model': 'farm.sensor',
            'view_mode': 'list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'default_task_id': self.id},
        }