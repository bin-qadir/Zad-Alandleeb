# -*- coding: utf-8 -*-
from . import models
from .models.farm_mqtt_listener import _post_load_hook

# ── Register the MQTT auto-start hook ─────────────────────────────────────────
# Odoo calls functions registered here after the module registry is fully built.
# This is the correct place to start background services that need DB access.
# The hook is idempotent: it checks MqttServiceManager._threads before starting.
def post_load():
    _post_load_hook()
