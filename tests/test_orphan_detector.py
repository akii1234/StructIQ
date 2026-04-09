"""Tests for orphan_file detector — framework/config exemptions."""
from __future__ import annotations

from StructIQ.architecture.detectors.orphan_detector import _skip_orphan_candidate


def test_apps_py_is_exempt():
    assert _skip_orphan_candidate("/proj/myapp/apps.py") is True


def test_wsgi_is_exempt():
    assert _skip_orphan_candidate("/proj/wsgi.py") is True


def test_asgi_is_exempt():
    assert _skip_orphan_candidate("/proj/asgi.py") is True


def test_settings_py_is_exempt():
    assert _skip_orphan_candidate("/proj/settings.py") is True


def test_settings_production_is_exempt():
    assert _skip_orphan_candidate("/proj/settings_production.py") is True


def test_settings_local_variant_is_exempt():
    assert _skip_orphan_candidate("/proj/settings_dev.py") is True


def test_vite_config_js_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/vite.config.js") is True


def test_vite_config_ts_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/vite.config.ts") is True


def test_eslint_config_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/eslint.config.js") is True


def test_jest_config_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/jest.config.ts") is True


def test_next_config_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/next.config.js") is True


def test_tailwind_config_is_exempt():
    assert _skip_orphan_candidate("/proj/frontend/tailwind.config.js") is True


def test_webpack_config_is_exempt():
    assert _skip_orphan_candidate("/proj/webpack.config.js") is True


def test_regular_model_file_not_exempt():
    assert _skip_orphan_candidate("/proj/myapp/models.py") is False


def test_regular_js_service_not_exempt():
    assert _skip_orphan_candidate("/proj/frontend/src/services/api.js") is False


def test_existing_init_still_exempt():
    assert _skip_orphan_candidate("/proj/myapp/__init__.py") is True


def test_existing_manage_still_exempt():
    assert _skip_orphan_candidate("/proj/manage.py") is True
