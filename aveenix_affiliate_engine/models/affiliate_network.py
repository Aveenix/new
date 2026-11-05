"""Network constants and the outbound-link trust boundary.

Both networks are *click redirectors*: the link Aveenix publishes points at the
network, which records the click and forwards the visitor to the merchant. So a
stored `target_url` is only trustworthy when its host belongs to the network the
offer claims to be on. That check lives here, in one place, because two callers
need exactly the same answer:

  * `affiliate.offer`, as a write-time constraint on links a human pasted in;
  * the public `/aveenix/affiliate/offer/<id>` route, which 302s to a stored URL
    and would otherwise be an open redirector.

It is also how "AI must never invent affiliate URLs" is enforced structurally
rather than by convention: nothing reaches a visitor unless it is a link on a
network click domain that was stored by discovery or approved by staff.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

NETWORK_CJ = 'cj'
NETWORK_CLICKBANK = 'clickbank'

NETWORKS = [
    (NETWORK_CJ, 'CJ Affiliate (Commission Junction)'),
    (NETWORK_CLICKBANK, 'ClickBank'),
]

# CJ serves affiliate clicks from a rotating pool of redirector domains, so a
# link returned by the Product Feed or Link Search API lands on one of these
# rather than on cj.com. Matched on the registrable suffix, which covers the
# "www." prefix CJ actually emits (www.anrdoezrs.net/click-123-456).
#
# If CJ introduces a domain that is not listed here, discovery does NOT drop the
# offer: it stores it as `draft` with a warning (see affiliate.offer), so a new
# domain degrades to "needs review" and never to an unverified redirect.
_HOSTS = {
    NETWORK_CJ: frozenset({
        'anrdoezrs.net', 'dpbolvw.net', 'jdoqocy.com', 'kqzyfj.com',
        'tkqlhce.com', 'qksrv.net', 'emjcd.com', 'ftjcfx.com', 'lduhtrp.net',
        'tqlkg.com', 'awltovhc.com', 'afcyhf.com', 'cualbr.com', 'rnsfpw.net',
        'cj.dotomi.com',
    }),
    # Covers both HopLink spellings: the readable
    # hop.clickbank.net/?affiliate=..&vendor=.. and the encrypted
    # <hash>.hop.clickbank.net, which differ only by subdomain.
    NETWORK_CLICKBANK: frozenset({'hop.clickbank.net'}),
}

# ClickBank accepts "a-z A-Z 0-9 space _ - +" in tracking parameters, but its
# HopLink guide warns that a dash silently breaks a TID. Sanitising to
# [A-Za-z0-9_] satisfies both rules with one pass, so there is no parameter
# where the safe character set has to be remembered separately.
_UNSAFE_TOKEN = re.compile(r'[^A-Za-z0-9_]+')


def network_hosts(network):
    """Click domains that may legitimately serve `network`'s affiliate links."""
    return _HOSTS.get(network, frozenset())


def verify_target_url(network, url):
    """True when `url` is an https link on one of `network`'s click domains."""
    if not url or not network:
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme != 'https' or not parts.netloc:
        return False
    host = parts.hostname or ''
    host = host.lower().rstrip('.')
    return any(
        host == allowed or host.endswith('.' + allowed)
        for allowed in network_hosts(network)
    )


def sanitize_token(value, limit=100):
    """Reduce `value` to a tracking-parameter-safe token, or '' if nothing survives.

    Networks reject or silently truncate parameters containing anything exotic,
    and a dropped parameter means a click we cannot attribute — so values are
    normalised on the way out rather than trusted.
    """
    if value is None:
        return ''
    token = _UNSAFE_TOKEN.sub('_', str(value)).strip('_')
    return token[:limit].rstrip('_')


def apply_params(url, params):
    """Append tracking `params` to `url`, leaving its existing query untouched.

    CJ click URLs carry the merchant destination in a percent-encoded `url=`
    parameter; decoding and re-encoding the whole query risks mangling it. So the
    new parameters are appended textually, and anything the network already put
    on the link wins over what we would have added.
    """
    parts = urlsplit(url)
    present = {key for key, _value in parse_qsl(parts.query, keep_blank_values=True)}
    extra = [(key, value) for key, value in params.items() if value and key not in present]
    if not extra:
        return url
    query = parts.query + ('&' if parts.query else '') + urlencode(extra)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
