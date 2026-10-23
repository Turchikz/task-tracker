from pathlib import Path

from django.test import SimpleTestCase
from django.template.loader import get_template


class HeaderMicroInteractionsTests(SimpleTestCase):
    def test_theme_control_partial_compiles(self):
        get_template('partials/theme_bulb.html')

    def test_base_template_compiles(self):
        get_template('base.html')

    def test_theme_js_uses_existing_storage_key(self):
        src = Path(__file__).resolve().parents[1] / 'static/js/theme_toggle.js'
        self.assertIn('task-tracker-theme', src.read_text(encoding='utf-8'))

    def test_logout_is_protected_by_django_csrf(self):
        src = Path(__file__).resolve().parents[1] / 'templates/base.html'
        markup = src.read_text(encoding='utf-8')
        self.assertIn('method="post"', markup)
        self.assertIn('{% csrf_token %}', markup)
        self.assertIn('class="logout-action" type="submit"', markup)
