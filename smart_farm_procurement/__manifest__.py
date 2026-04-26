{
    'name': 'Lavandula Procurement',
    'version': '18.0.1.0.0',
    'summary': 'Procurement layer: BOQ Analysis → RFQ → Purchase Orders → Actual Cost Tracking',
    'description': (
        'Bridges BOQ Analysis with Odoo Purchase. '
        'Extends farm.boq.analysis.line with procurement fields (type, vendor, product, '
        'estimated cost, PO link, actual cost, variance). '
        'Adds Generate RFQ action on approved Analysis documents to create grouped POs by vendor. '
        'Tracks actual costs from PO receipts and vendor bills. '
        'Injects procurement columns into the Analysis line list and Purchases stat button.'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_boq_analysis',
        'purchase',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_boq_analysis_procurement_inherit.xml',
        'views/purchase_order_inherit.xml',
        'views/farm_project_views_inherit.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
