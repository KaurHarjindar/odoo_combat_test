# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': "Zippsafe Sales PDF Quotation Builder",

    'summary': """
        This module will add feature to add custom header and footer in sales report.""",

    'description': """
        Zippsafe Sales PDF Quotation Builder
        Task ID - 3930025
    """,

    'category': 'Custom Development',
    'depends': ['sale_management'],

    'data': [
        'report/ir_actions_report_templates.xml',
        'report/ir_actions_report.xml',
        'views/sale_order_template_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],

    'assets': {
        'sale_report.assets': [
            'sale_pdf_quote_builder/static/src/css/sale_order_report.css',
            'sale_pdf_quote_builder/static/src/fonts/AvenirLTProBook.otf',
            'sale_pdf_quote_builder/static/src/fonts/AvenirLTProRoman.otf',
        ],
    },
    
    'installable': True,
}
