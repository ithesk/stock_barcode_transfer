# -*- coding: utf-8 -*-
{
    'name': "stock_barcode_transfer",

    'summary': """
        direct print to printer""",

    'description': """
        Gestión de transferencias entre localidades usando códigos de barras
    """,

    'author': "axedev",
    'website': "http://www.ithesk.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'tools',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['point_of_sale','base','product','account','contacts','purchase', 'stock','mail'],

    # always loaded
    'data': [
        # 'views/pos_uber_views.xml',
        # 'static/src/xml/pos_uber_templates.xml',
          'views/pos_assets.xml',
        #   'views/pos_config_view.xml',
        #   'reports/ncf_pos_papel.xml',
        #   'reports/report_pos_receipt.xml',
        #   'reports/ncf_pos_templates.xml',
        # 'static/src/xml/uber.xml',
          'security/ir.model.access.csv',
          'views/stock_location_transfer_views.xml',
          'data/stock_location_transfer_sequence.xml',
          'reports/reception_report.xml',
          'views/barcode_printer_views.xml',
          'views/product_views.xml',
          'reports/barcode_report.xml',
          'views/stock_location_transfer_wizard_views.xml',
        # 'views/pos_order_views.xml',
        # 'views/print_menu_action.xml',
        #'views/product_cost.xml',
        #'data/ir_cron.xml',
       ],
       'qweb': [
        # 'static/src/xml/pos_uber.xml',
    ],
        'installable': True,
        'application': True,
        'auto_install': False,
    
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}