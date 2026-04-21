{
    'name': 'Smart Farm Control',
    'version': '18.0.1.3.0',
    'summary': 'Enterprise project control: phase locking, committed cost, profit/variance engine',
    'description': (
        'Adds SAP-level project control discipline to Smart Farm:\n\n'
        '1. HARD PHASE LOCKING\n'
        '   Backend-enforced gates — creating JOs/Materials/Labour outside\n'
        '   Execution phase raises a clear UserError.  SO contract approval\n'
        '   is blocked before Contract phase.\n\n'
        '2. COMMITTED COST ENGINE\n'
        '   Committed cost from confirmed Purchase Orders (farm_project_id link).\n'
        '   committed_material_cost, committed_subcontract_cost, total_committed_cost.\n\n'
        '3. FULL COST CONTROL ENGINE\n'
        '   Every cost bucket tracked at project level:\n'
        '   Estimated / Contract / Committed / Actual (Mat+Lab+Sub+Other) /\n'
        '   Forecast Final / Gross Margin.\n\n'
        '4. PROFIT / VARIANCE ENGINE\n'
        '   estimated_profit, current_profit, committed_profit, projected_profit.\n'
        '   Three variance lines: Contract vs Estimate, Contract vs Actual,\n'
        '   Estimate vs Actual.\n\n'
        '5. EXECUTIVE COST CONTROL UI\n'
        '   Fully rebuilt Cost Control tab with clear sections, badge colours,\n'
        '   and contextual lock banners.\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_sale_contract',   # SO contract backbone + base cost fields
        'smart_farm_procurement',     # PO farm_project_id link (committed cost source)
    ],
    'data': [
        'views/farm_project_control_views.xml',
        'views/farm_project_phase_colors.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
