"""AI Analyst — answer finance questions / build reports by having Claude write
Python that runs against your portfolio inside a Daytona sandbox.

Flow: gather the portfolio as JSON → ask Claude to write a Python script that
answers the question (print text, optionally save one chart to /tmp/chart.png) →
run that script in an isolated Daytona sandbox with the data → return the
printed answer, any chart, and the generated code.

Requires ANTHROPIC_API_KEY (code generation) and DAYTONA_API_KEY (sandbox).
Both are read from the environment. Nothing runs on the app host — the
AI-generated code executes only inside the throwaway sandbox.

NOTE: the Daytona SDK surface (delete method, code_run response) is handled
defensively; verify against your SDK version on first real run.
"""

import os
import io
import re
import json
import base64
from datetime import datetime, timezone

from models import (
    db, Stock, MutualFund, Account, Loan, FixedDeposit, ChitFund, CreditGiven,
    AnalysisReport,
)

CODE_MODEL = (os.environ.get('AI_ANALYST_MODEL') or os.environ.get('AI_MODEL')
              or 'claude-sonnet-4-6')
DATA_PATH = '/tmp/portfolio.json'
CHART_PATH = '/tmp/chart.png'


class SandboxError(Exception):
    """User-actionable problem (missing key, no data, sandbox/codegen failure)."""


# ─── Portfolio context ───────────────────────────────────────────────────────

def build_portfolio():
    """Serialize the whole portfolio to a plain dict the sandbox code can load."""
    return {
        'stocks': [s.to_dict() for s in Stock.query.all()],
        'mutual_funds': [f.to_dict() for f in MutualFund.query.all()],
        'accounts': [a.to_dict() for a in Account.query.filter(Account.account_type_code != 'EXTERNAL').all()],
        'loans': [l.to_dict() for l in Loan.query.all()],
        'fixed_deposits': [f.to_dict() for f in FixedDeposit.query.all()],
        'chit_funds': [c.to_dict() for c in ChitFund.query.all()],
        'credits': [c.to_dict() for c in CreditGiven.query.all()],
    }


def _schema_hint(portfolio):
    """A compact description of each collection's keys, for the codegen prompt."""
    lines = []
    for name, rows in portfolio.items():
        keys = sorted(rows[0].keys()) if rows else []
        lines.append(f'- {name} ({len(rows)} rows): {", ".join(keys) or "empty"}')
    return '\n'.join(lines)


_SYSTEM = f"""You are a meticulous Python data analyst for a personal-finance app.

A JSON file is available at {DATA_PATH}. It is an object with these collections
(all monetary values are in INR unless a `currency` field says otherwise):

{{schema}}

Write ONE complete, self-contained Python 3 script that answers the user's
request using this data. Rules:
- Load the data with: `import json; data = json.load(open("{DATA_PATH}"))`.
- Print a clear, concise plain-text answer to stdout (this is what the user
  sees). Include the key numbers. No markdown.
- If a chart genuinely helps, use matplotlib with a non-interactive backend
  (`import matplotlib; matplotlib.use("Agg")`) and save EXACTLY ONE PNG to
  "{CHART_PATH}". Never call plt.show(). Skip the chart if it doesn't add value.
- Use only the standard library plus pandas, numpy, and matplotlib.
- Handle empty/missing collections gracefully.
- Output ONLY the Python code — no explanations, no markdown fences."""


_BACKTEST_SYSTEM = f"""You are a quantitative analyst writing a Python backtest
/ what-if simulation for a personal-finance app.

A JSON file at {DATA_PATH} holds the user's portfolio (INR unless a `currency`
field says otherwise):

{{schema}}

You HAVE internet access. Fetch historical prices/NAVs yourself:
- Indian stocks: Yahoo symbol = TICKER + ".NS" (NSE) or ".BO" (BSE). US stocks:
  bare TICKER. Use yfinance: `yfinance.Ticker(sym).history(period="max")`.
- Mutual funds: GET https://api.mfapi.in/mf/<scheme_code> → JSON `data` list of
  {{date:"DD-MM-YYYY", nav:".."}} (newest first).

Write ONE complete Python 3 script that simulates the user's what-if scenario
against ACTUAL history. Rules:
- Load holdings: `import json; data = json.load(open("{DATA_PATH}"))`.
- Fetch the historical series you need (handle missing symbols gracefully — skip
  and note them; never crash).
- Compare the scenario vs what actually happened where relevant. Print a clear
  plain-text result: final values, absolute and % difference, and CAGR/XIRR if
  meaningful. State every assumption you make.
- Save ONE comparison chart (matplotlib, `matplotlib.use("Agg")`) to
  "{CHART_PATH}" — e.g. portfolio value over time, scenario vs actual. Never
  plt.show().
- Use only stdlib, pandas, numpy, matplotlib, yfinance, requests.
- Output ONLY the Python code — no markdown, no fences."""


def _clientmsg(system, messages, max_tokens=8000):
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=CODE_MODEL, max_tokens=max_tokens, system=system, messages=messages)
    text = ''.join(b.text for b in msg.content if getattr(b, 'type', None) == 'text').strip()
    m = re.search(r'```(?:python)?\s*(.*?)```', text, re.S)   # strip accidental fences
    return (m.group(1) if m else text).strip()


def _generate_code(question, portfolio, system_template=None):
    """Ask Claude for a Python script for `question` using the given system prompt."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise SandboxError('ANTHROPIC_API_KEY is not set (needed to generate the analysis code).')
    system = (system_template or _SYSTEM).replace('{schema}', _schema_hint(portfolio))
    return _clientmsg(system, [{'role': 'user', 'content': question.strip()}])


def _repair_code(code, error_output):
    """One-shot fix: give Claude the broken code + error and get corrected code."""
    system = ('You fix Python scripts. Return ONLY the corrected, complete Python '
              'code — no markdown, no explanation. Keep the same behavior and the '
              'same output/chart paths.')
    user = f'This script failed:\n\n{code}\n\n--- error ---\n{error_output[:3000]}\n\nReturn the fixed script.'
    return _clientmsg(system, [{'role': 'user', 'content': user}])


def _looks_like_error(stdout):
    s = (stdout or '')
    return ('Traceback (most recent call last)' in s or 'SyntaxError' in s
            or 'NameError' in s or 'IndentationError' in s)


# ─── Daytona sandbox execution ───────────────────────────────────────────────

def _run_in_sandbox(code, portfolio):
    """Execute `code` in a fresh Daytona sandbox with the portfolio uploaded.
    Returns (stdout, chart_bytes_or_None). Always tears the sandbox down."""
    if not os.environ.get('DAYTONA_API_KEY'):
        raise SandboxError('DAYTONA_API_KEY is not set. Add it to enable the AI Analyst.')
    try:
        from daytona import Daytona, DaytonaConfig
    except ImportError:
        raise SandboxError('The `daytona` package is not installed. Run: pip install daytona')

    daytona = Daytona(DaytonaConfig(api_key=os.environ['DAYTONA_API_KEY']))
    sandbox = None
    try:
        sandbox = daytona.create()
        # Upload the data file.
        sandbox.fs.upload_file(json.dumps(portfolio).encode('utf-8'), DATA_PATH)
        # Best-effort: make sure the analysis libraries are present.
        try:
            sandbox.process.exec('pip install -q pandas numpy matplotlib yfinance requests')
        except Exception:
            pass
        def _run(src):
            resp = sandbox.process.code_run(src)
            out = getattr(resp, 'result', None)
            if out is None:
                out = str(resp)
            try:
                ch = sandbox.fs.download_file(CHART_PATH)
            except Exception:
                ch = None
            return out, ch

        stdout, chart = _run(code)
        final_code = code
        # One automatic repair pass if the script errored (e.g. truncated code).
        if _looks_like_error(stdout) and not chart:
            try:
                fixed = _repair_code(code, stdout)
                out2, ch2 = _run(fixed)
                if ch2 or not _looks_like_error(out2):
                    stdout, chart, final_code = out2, ch2, fixed
            except Exception:
                pass
        return stdout, chart, final_code
    finally:
        # SDK delete method varies by version — try both, ignore failures.
        if sandbox is not None:
            for attempt in (lambda: sandbox.delete(),
                            lambda: daytona.delete(sandbox),
                            lambda: daytona.remove(sandbox)):
                try:
                    attempt()
                    break
                except Exception:
                    continue


# ─── Public entry point ──────────────────────────────────────────────────────

def run_query(question, mode='analyst'):
    """Generate code for `question`, run it in a sandbox, persist + return the
    result. mode='analyst' answers from stored data; mode='backtest' also fetches
    historical prices in-sandbox for what-if simulations."""
    question = (question or '').strip()
    if not question:
        raise SandboxError('Please enter a question.')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise SandboxError('ANTHROPIC_API_KEY is not set (needed to generate the analysis code).')
    if not os.environ.get('DAYTONA_API_KEY'):
        raise SandboxError('DAYTONA_API_KEY is not set. Add it to enable this feature.')
    portfolio = build_portfolio()
    system = _BACKTEST_SYSTEM if mode == 'backtest' else _SYSTEM
    tag = 'daytona-backtest' if mode == 'backtest' else 'daytona'

    created = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        code = _generate_code(question, portfolio, system)
        stdout, chart, code = _run_in_sandbox(code, portfolio)
        chart_b64 = base64.b64encode(chart).decode('ascii') if chart else None
        report = AnalysisReport(
            created_at=created, model=f'{CODE_MODEL} + {tag}',
            holdings_snapshot=json.dumps({'question': question}),
            overlap_input=code,                       # reuse column to store the (final) code
            report_html=_render_html(question, stdout, chart_b64),
            summary=question[:200], status='ok',
        )
    except SandboxError:
        raise
    except Exception as exc:
        report = AnalysisReport(
            created_at=created, model=f'{CODE_MODEL} + {tag}',
            holdings_snapshot=json.dumps({'question': question}),
            report_html='', summary=question[:200], status='error',
            error=f'{type(exc).__name__}: {exc}',
        )
    db.session.add(report)
    db.session.commit()
    return report


def _render_html(question, stdout, chart_b64):
    """Small self-contained HTML block: question, printed answer, optional chart."""
    from markupsafe import escape
    img = (f'<img src="data:image/png;base64,{chart_b64}" '
           f'style="max-width:100%;border:1px solid #e6e9ee;border-radius:10px;margin-top:12px" />'
           if chart_b64 else '')
    return (
        f'<div style="font-family:system-ui,sans-serif">'
        f'<div style="color:#64748b;font-size:13px;margin-bottom:6px">Q: {escape(question)}</div>'
        f'<pre style="white-space:pre-wrap;font-size:14px;background:#f8fafc;border:1px solid #e6e9ee;'
        f'border-radius:10px;padding:14px;overflow-x:auto">{escape(stdout or "(no output)")}</pre>'
        f'{img}</div>'
    )
