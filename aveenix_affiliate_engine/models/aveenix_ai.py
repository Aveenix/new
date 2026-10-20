"""Thin, non-raising wrapper around the AI endpoint Aveenix already uses.

Reuses the same three system parameters as the existing content generators in
`aveenix_website` (`aveenix.ai_endpoint`, `aveenix.ai_model`,
`aveenix.ai_api_key`), so the site keeps one set of AI credentials rather than
gaining a second.

The behavioural difference from those generators is deliberate: they are button
handlers and raise UserError so an admin sees what went wrong, whereas offer
matching runs unattended over a batch of articles. A missing key, a rate limit
or a dead endpoint must not abort the batch, so every failure here returns None
and the caller falls back to deterministic keyword extraction.
"""

import json
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'
_DEFAULT_MODEL = 'llama-3.3-70b-versatile'


class AveenixAffiliateAi(models.AbstractModel):
    _name = 'aveenix.affiliate.ai'
    _description = 'Aveenix Affiliate AI Helper'

    @api.model
    def _av_chat(self, system_prompt, user_prompt, timeout=20):
        """Return the assistant's reply text, or None when AI is unavailable."""
        params = self.env['ir.config_parameter'].sudo()
        endpoint = (params.get_param('aveenix.ai_endpoint') or _DEFAULT_ENDPOINT).strip()
        model = (params.get_param('aveenix.ai_model') or _DEFAULT_MODEL).strip()
        api_key = (params.get_param('aveenix.ai_api_key') or '').strip()
        if not api_key and 'groq' in endpoint:
            # Not an error: the engine is designed to run without AI.
            return None

        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = 'Bearer %s' % api_key
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        }
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            choices = response.json().get('choices') or []
            return (choices[0].get('message', {}).get('content') or '').strip() or None
        except Exception as error:
            _logger.warning('Affiliate AI call failed, falling back to keyword rules: %s', error)
            return None

    @api.model
    def _av_chat_json_list(self, system_prompt, user_prompt, timeout=20):
        """Ask for a JSON array of strings and return it, or [] on any problem.

        Used for topic/keyword extraction. The caller must treat the result as
        search terms only — never as a URL. See `affiliate_network` for why that
        separation is enforced by the link allowlist rather than by trust.
        """
        reply = self._av_chat(system_prompt, user_prompt, timeout=timeout)
        if not reply:
            return []
        # Models wrap JSON in prose or fences often enough that it is cheaper to
        # cut to the array than to re-prompt.
        start, end = reply.find('['), reply.rfind(']')
        if start == -1 or end <= start:
            return []
        try:
            parsed = json.loads(reply[start:end + 1])
        except ValueError:
            _logger.warning('Affiliate AI returned unparseable JSON: %r', reply[:200])
            return []
        if not isinstance(parsed, list):
            return []
        return [
            item.strip() for item in parsed
            if isinstance(item, str) and item.strip()
        ]
