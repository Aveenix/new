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
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Free, no-key daily FX rates (160+ currencies, refreshed once a day).
_RATE_API_URL = 'https://open.er-api.com/v6/latest/%s'


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def av_cron_update_currency_rates(self):
        """Auto-set today's rate for every ACTIVE currency, per company.

        Rates are fetched with each company's currency as base, matching
        Odoo's rate semantics: res.currency.rate.rate = units of this currency
        per 1 unit of the company currency. Never raises — a failed fetch for
        one company logs a warning and moves on to the next.
        """
        companies = self.env['res.company'].search([])
        active_currencies = self.search([])
        today = fields.Date.context_today(self)
        Rate = self.env['res.currency.rate']

        to_create = []
        refreshed_keys = set()  # (currency_id, company_id) pairs being replaced
        for company in companies:
            base = company.currency_id.name
            try:
                response = requests.get(_RATE_API_URL % base, timeout=15)
                data = response.json()
            except Exception as exc:
                _logger.warning(
                    "Aveenix currency rates: fetch failed for base %s (company %s): %s",
                    base, company.name, exc,
                )
                continue
            rates = (data or {}).get('rates') or {}
            if data.get('result') != 'success' or not rates:
                _logger.warning(
                    "Aveenix currency rates: bad API response for base %s (company %s)",
                    base, company.name,
                )
                continue

            for currency in active_currencies:
                if currency == company.currency_id:
                    continue
                value = rates.get(currency.name)
                if not value or value <= 0:
                    continue
                refreshed_keys.add((currency.id, company.id))
                to_create.append({
                    'currency_id': currency.id,
                    'company_id': company.id,
                    'name': today,
                    'rate': value,
                })

        if not to_create:
            _logger.info("Aveenix currency rates: nothing to update")
            return

        # Replace today's rates in bulk: one unlink + one batch create — no
        # per-record DB calls inside the loops above.
        stale = Rate.search([('name', '=', today)]).filtered(
            lambda r: (r.currency_id.id, r.company_id.id) in refreshed_keys
        )
        stale.unlink()
        Rate.create(to_create)
        _logger.info(
            "Aveenix currency rates: set %s rates for %s", len(to_create), today,
        )
