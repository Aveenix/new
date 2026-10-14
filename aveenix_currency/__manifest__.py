# -*- coding: utf-8 -*-
#############################################################################
#
#    Anantam Innovision Private Limited.
#
#    Copyright (C) 2026-TODAY Anantam Innovision(<https://anantaminnovision.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name': 'Aveenix Live Currency Rates',
    'author': 'Anantam Innovision Private Limited',
    'website': 'https://anantaminnovision.com/',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'summary': 'Daily auto-update of exchange rates for all active currencies',
    'description': """
Auto-sets today's exchange rate for every activated currency, per company,
from a free daily FX API (open.er-api.com, ECB-style, 160+ currencies).
Runs via a daily scheduled action; rates can also be refreshed manually from
the currency list. No API key required.
""",
    'depends': ['base'],
    'data': [
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
}
