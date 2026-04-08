# -*- coding: utf-8 -*-
{
    'name': 'Smart Farm - Al Andleeb',
    'version': '18.0.9.0.0',
    'category': 'Agriculture',
    'summary': 'Integrated Smart Farm Management System for Al Andleeb',
    'description': """
Smart Farm Al Andleeb
=====================
- Farm, Field, Crop, Livestock, Harvest management
- Purchase / Sale / Stock / Account integration
- Project Cost Control + RFQ + Quotation workflows
- Financial Performance Dashboard (Owl)
- Financial Alerts + Intelligent Decision Engine
- MQTT IoT Sensor Integration
- Actuator Device Registry
- Control Action Execution System
- MQTT Publish Service (farm.mqtt.publisher)
  - Connection reuse via MqttServiceManager
  - One-shot fallback with wait_for_publish() ACK
  - Structured audit log (farm.mqtt.publish.log)
    """,
    'author': 'Al Andleeb',
    'website': 'https://www.alandleeb.com',
    'license': 'LGPL-3',
    'depends': [
        'base', 'project', 'stock', 'purchase', 'sale', 'account', 'mail',
    ],
    'data': [
        'security/smart_farm_security.xml',
        'security/ir.model.access.csv',
        'data/smart_farm_data.xml',
        'data/smart_farm_alert_data.xml',
        'data/farm_decision_data.xml',
        'data/farm_actuator_data.xml',
        'data/farm_soil_type_data.xml',
        'data/farm_cost_type_data.xml',
        'data/farm_boq_work_type_data.xml',
        'data/farm_irrigation_type_data.xml',
        'data/cron.xml',
        'views/farm_boq_work_type_views.xml',
        'views/farm_product_extension_views.xml',
        'views/project_cost_analysis_views.xml',
        'views/farm_farm_views.xml',
        'views/farm_soil_type_views.xml',
        'views/farm_cost_type_views.xml',
        'views/farm_irrigation_type_views.xml',
        'views/farm_boq_item_template_views.xml',
        'views/farm_insert_boq_wizard_views.xml',
        'views/farm_cost_line_template_wizard_views.xml',
        'views/farm_cost_analysis_wizard_views.xml',
        'views/farm_field_views.xml',
        'views/farm_crop_views.xml',
        'views/farm_livestock_views.xml',
        'views/farm_harvest_views.xml',
        'views/farm_expense_views.xml',
        'views/farm_dashboard_views.xml',
        'views/task_cost_control_views.xml',
        'views/smart_farm_alert_views.xml',
        'views/farm_sensor_views.xml',
        'views/farm_decision_views.xml',
        'views/farm_actuator_device_views.xml',
        'views/farm_control_action_views.xml',
        'views/farm_control_actuator_bridge_views.xml',
        'views/farm_mqtt_publisher_views.xml',
        'views/smart_farm_menus.xml',
        'views/farm_sensor_menu.xml',
        'views/smart_farm_dashboard_action.xml',
    ],
    'assets': {},
    'external_dependencies': {'python': []},
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
