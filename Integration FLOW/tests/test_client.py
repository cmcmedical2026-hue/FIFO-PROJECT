from __future__ import annotations

import unittest
from unittest.mock import patch

from flow.client import FlowClient, FlowError
from flow.credentials import Credentials


class LoginFallbackTests(unittest.TestCase):
    def setUp(self):
        credentials = Credentials("251", "Man03", "secret", "test")
        self.client = FlowClient(credentials, verbose=False)

    def test_prefers_legacy_login_without_retaining_unrelated_fields(self):
        legacy_response = (
            "LOGINUSRID=MAN03;USRNA=Test User;AUTH=1;EMPNO=7;LOGINERR=0;"
            "MAILPASS=must-not-be-retained;APIKEY=test-key==;"
        )
        with patch.object(
            self.client,
            "_request",
            return_value=(200, legacy_response),
        ) as request:
            self.assertEqual(self.client.login(), "test-key==")

        self.assertEqual(request.call_count, 1)
        self.assertIn("erp.mcbs-global.com/?OP=CHKUSR", request.call_args.args[0])
        self.assertEqual(self.client.session["usrid"], "MAN03")
        self.assertNotIn("MAILPASS", self.client.session)

    def test_falls_back_to_dedicated_api_when_legacy_login_is_unavailable(self):
        api_response = {
            "apiKey": "api-key",
            "errMsg": "",
            "acc": "251",
            "usrid": "MAN03",
        }
        with patch.object(
            self.client,
            "_request",
            side_effect=[FlowError("legacy unavailable"), (200, api_response)],
        ) as request:
            self.assertEqual(self.client.login(), "api-key")

        self.assertEqual(request.call_count, 2)
        self.assertIn("login.mcbs-global.com/api/chkusr/login", request.call_args.args[0])

    def test_rejects_login_when_both_surfaces_fail(self):
        with patch.object(
            self.client,
            "_request",
            side_effect=[
                (200, "LOGINLOGINERR=1;LSTERRMSG=bad;"),
                FlowError("HTTP 400"),
            ],
        ):
            with self.assertRaisesRegex(FlowError, "HTTP 400"):
                self.client.login()


if __name__ == "__main__":
    unittest.main()
