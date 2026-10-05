import asyncio
import json
import unittest

import httpx

from app.services.export.documents import ExportOption, ExportQuestion, ExportTest
from app.services.export.google_forms import GoogleFormsError, build_payload, create_google_form

TEST = ExportTest(title="Тест", questions=[
    ExportQuestion("true_false", "Go компілюється в машинний код.",
                   [ExportOption("Правда", True), ExportOption("Неправда", False)], explanation="Так."),
])
URL = "https://script.google.com/macros/s/X/exec"


def run(coro):
    return asyncio.run(coro)


def transport(handler):
    return httpx.MockTransport(handler)


class GoogleFormsTest(unittest.TestCase):
    def test_payload_contains_secret_and_correct_flags(self):
        p = build_payload(TEST, "t@example.com", "s3cret")
        self.assertEqual(p["secret"], "s3cret")
        self.assertEqual(p["teacher_email"], "t@example.com")
        self.assertEqual(p["questions"][0]["options"], [{"text": "Правда", "is_correct": True},
                                                        {"text": "Неправда", "is_correct": False}])

    def test_not_configured(self):
        with self.assertRaises(GoogleFormsError):
            run(create_google_form(TEST, "t@example.com", "", ""))

    def test_follows_apps_script_redirect(self):
        def handler(request: httpx.Request):
            if request.url.host == "script.google.com":
                assert json.loads(request.content)["title"] == "Тест"
                return httpx.Response(302, headers={"Location": "https://script.googleusercontent.com/echo"})
            return httpx.Response(200, json={"ok": True, "form_id": "F", "edit_url": "E",
                                             "respond_url": "R", "shared": "editor"})
        form = run(create_google_form(TEST, "t@example.com", URL, "s", transport=transport(handler)))
        self.assertEqual((form.form_id, form.edit_url, form.respond_url, form.shared), ("F", "E", "R", "editor"))

    def test_script_error_is_reported(self):
        handler = lambda r: httpx.Response(200, json={"ok": False, "error": "Невірний секрет"})
        with self.assertRaisesRegex(GoogleFormsError, "Невірний секрет"):
            run(create_google_form(TEST, "t@example.com", URL, "s", transport=transport(handler)))

    def test_html_instead_of_json(self):
        handler = lambda r: httpx.Response(200, text="<html>Sign in</html>")
        with self.assertRaisesRegex(GoogleFormsError, "доступом «Усі»"):
            run(create_google_form(TEST, "t@example.com", URL, "s", transport=transport(handler)))


if __name__ == "__main__":
    unittest.main()
