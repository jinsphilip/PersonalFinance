"""AI mutual-fund portfolio analysis via the Claude API.

Packages the app's current mutual-fund holdings plus a headless-adapted version
of the portfolio-auditor prompt, calls Claude (with the web-search server tool
for live expense-ratio / CAGR data), and stores each run as a timestamped
AnalysisReport so the user can compare periodic audits over time.

Requires ANTHROPIC_API_KEY in the environment and outbound access to
api.anthropic.com.
"""

import os
import json
from datetime import datetime, timezone

from models import db, MutualFund, AnalysisReport

MODEL = 'claude-3-5-sonnet-20241022'
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'prompts', 'portfolio_auditor.md')


class AnalysisError(Exception):
    """Raised for user-actionable problems (missing key, no holdings)."""


def _load_system_prompt():
    with open(_PROMPT_PATH, encoding='utf-8') as fh:
        return fh.read()


def build_holdings_context():
    """Structured, human-readable block of the current MF holdings for the model.

    Returns (text, snapshot_list). Raises AnalysisError if there are no funds."""
    funds = MutualFund.query.all()
    if not funds:
        raise AnalysisError('No mutual funds found. Add funds before running analysis.')

    lines, snapshot = [], []
    for f in funds:
        d = f.to_dict()
        snapshot.append(d)
        parts = [
            f"Fund: {d['fund_name']}",
            f"platform: {d['platform']}",
            f"units: {d['units']}",
            f"avg NAV: {d['avg_nav']}",
            f"current NAV: {d['current_nav']}",
            f"current value: Rs {d['current_value']}",
        ]
        if d.get('is_sip'):
            parts.append(
                f"SIP: Rs {d['sip_amount']} {d.get('sip_frequency', 'monthly')}"
                + (f" on day {d['sip_day']}" if d.get('sip_day') else '')
            )
        if d.get('scheme_code'):
            parts.append(f"scheme code: {d['scheme_code']}")
        lines.append(' | '.join(str(p) for p in parts))
    return '\n'.join(lines), snapshot


def run_portfolio_analysis(overlap_text=''):
    """Run one analysis and persist an AnalysisReport row. Returns the row.

    Raises AnalysisError for missing key / no holdings (surface as a 400)."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise AnalysisError(
            'ANTHROPIC_API_KEY is not set. Set it in the environment to enable '
            'AI portfolio analysis.'
        )

    holdings_text, snapshot = build_holdings_context()
    overlap_text = (overlap_text or '').strip()

    import anthropic

    system_prompt = _load_system_prompt()
    user_message = 'PORTFOLIO HOLDINGS FROM THE APP:\n\n' + holdings_text
    if overlap_text:
        user_message += (
            '\n\nOVERLAP (pasted by the user from 1Finance Portfolio Overlap):\n\n'
            + overlap_text
        )
    else:
        user_message += '\n\nOVERLAP: not supplied.'
    user_message += '\n\nProduce the single self-contained HTML dashboard now.'

    created = datetime.now(timezone.utc).isoformat(timespec='seconds')
    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

    try:
        # Claude 3.5 Sonnet: no extended thinking, and the basic web-search tool
        # version (dynamic-filtering web_search_20260209 is 4.6+ only).
        with client.messages.stream(
            model=MODEL,
            max_tokens=8192,
            system=system_prompt,
            tools=[{'type': 'web_search_20250305', 'name': 'web_search'}],
            messages=[{'role': 'user', 'content': user_message}],
        ) as stream:
            final = stream.get_final_message()
        html = ''.join(
            block.text for block in final.content
            if getattr(block, 'type', None) == 'text'
        ).strip()
        report = AnalysisReport(
            created_at=created,
            model=MODEL,
            holdings_snapshot=json.dumps(snapshot),
            overlap_input=overlap_text or None,
            report_html=html,
            summary=f'{len(snapshot)} fund(s) analyzed',
            status='ok',
        )
    except Exception as exc:   # network / API / SDK failure → store an error row
        report = AnalysisReport(
            created_at=created,
            model=MODEL,
            holdings_snapshot=json.dumps(snapshot),
            overlap_input=overlap_text or None,
            report_html='',
            summary='Analysis failed',
            status='error',
            error=f'{type(exc).__name__}: {exc}',
        )

    db.session.add(report)
    db.session.commit()
    return report
