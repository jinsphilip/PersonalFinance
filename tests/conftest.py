"""Pytest fixtures — run the app against a throwaway SQLite DB so tests never
touch real data. FINTRACKER_DB is set before importing app."""
import os
import tempfile

import pytest

# Point the app at a temp DB and disable the login before importing it.
_TMP = os.path.join(tempfile.gettempdir(), 'fintracker_test.db')
os.environ['FINTRACKER_DB'] = _TMP
os.environ.pop('FINTRACKER_PASSWORD', None)

import app as app_module          # noqa: E402
from models import db             # noqa: E402
import services                   # noqa: E402


@pytest.fixture()
def app_ctx():
    """Fresh schema + seeded masters for each test, in an app context."""
    flask_app = app_module.app
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        services.seed_masters()
        yield flask_app
        db.session.remove()


@pytest.fixture()
def client(app_ctx):
    return app_ctx.test_client()
