import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

os.environ.setdefault("SESSION_SECRET", "mindtrack-chat-tests-only")

import main


class ChatFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.app.config["TESTING"] = True
        with main.app.app_context():
            user = main.User(
                username=f"chat-test-{uuid4().hex[:12]}",
                password_hash="test-only",
            )
            main.db.session.add(user)
            main.db.session.commit()
            cls.user_id = user.id
            cls.private_journal_text = "PRIVATE JOURNAL ENTRY MUST NOT REACH CHAT"
            journal_entry = main.Entry(
                user_id=cls.user_id,
                text=cls.private_journal_text,
                emotion="neutral",
                scores_json=json.dumps({emotion: 0.0 for emotion in main.EMOTIONS}),
                sentiment_score=0.0,
            )
            main.db.session.add(journal_entry)
            main.db.session.commit()
            cls.entry_id = journal_entry.id

    @classmethod
    def tearDownClass(cls):
        with main.app.app_context():
            entry = main.db.session.get(main.Entry, cls.entry_id)
            user = main.db.session.get(main.User, cls.user_id)
            if entry:
                main.db.session.delete(entry)
            if user:
                main.db.session.delete(user)
            main.db.session.commit()

    def setUp(self):
        self.client = main.app.test_client()
        self.csrf_token = f"test-token-{uuid4().hex}"
        with self.client.session_transaction() as test_session:
            test_session["user_id"] = self.user_id
            test_session["_csrf_token"] = self.csrf_token
        with main._chat_rate_lock:
            main._chat_requests_by_user.pop(self.user_id, None)

    def tearDown(self):
        with main._chat_rate_lock:
            main._chat_requests_by_user.pop(self.user_id, None)

    def post_chat(self, message, history=None):
        return self.client.post(
            "/api/chat",
            json={"message": message, "history": history or []},
            headers={"X-CSRF-Token": self.csrf_token},
        )

    @staticmethod
    def groq_response(reply="That sounds like a lot to carry. What feels most important right now?"):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": reply}}],
        }
        return response

    def test_normal_message_gets_reply_with_at_most_six_recent_messages(self):
        history = [
            {"role": "user", "content": f"Earlier message {index}"}
            for index in range(8)
        ]
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            os.environ.pop("GROQ_MODEL", None)
            with patch("main.requests.post", return_value=self.groq_response()) as groq:
                response = self.post_chat("Today felt overwhelming.", history)

        self.assertEqual(response.status_code, 200)
        self.assertIn("That sounds like a lot", response.json["reply"])
        call = groq.call_args
        self.assertEqual(
            call.args[0],
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.assertEqual(call.kwargs["timeout"], 20)
        sent_messages = call.kwargs["json"]["messages"]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertEqual(len(sent_messages) - 1, 6)
        self.assertEqual(
            [item["content"] for item in sent_messages[1:6]],
            [f"Earlier message {index}" for index in range(3, 8)],
        )
        self.assertEqual(sent_messages[-1], {
            "role": "user",
            "content": "Today felt overwhelming.",
        })
        self.assertNotIn(
            self.private_journal_text,
            json.dumps(call.kwargs["json"]),
        )
        self.assertEqual(
            call.kwargs["json"]["model"],
            "openai/gpt-oss-120b",
        )

    def test_distress_message_returns_helplines_without_calling_groq(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with patch("main.requests.post") as groq:
                response = self.post_chat("I feel hopeless and want to give up")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["distress"])
        self.assertEqual(response.json["helplines"][0]["phone"], "14416")
        self.assertIn("someone you trust", response.json["reply"])
        groq.assert_not_called()

    def test_missing_groq_key_returns_friendly_message(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_API_KEY", None)
            with patch("main.requests.post") as groq:
                response = self.post_chat("I had a long day.")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json["reply"],
            main.CHAT_UNAVAILABLE_MESSAGE,
        )
        groq.assert_not_called()

    def test_chat_page_requires_login(self):
        anonymous_client = main.app.test_client()
        response = anonymous_client.get("/chat")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_chat_page_shows_privacy_notices_and_message_limit(self):
        response = self.client.get("/chat")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Chat messages are processed by an external AI service.", response.data)
        self.assertIn(
            b"MindTrack is not a medical tool and not a substitute for professional help.",
            response.data,
        )
        self.assertIn(b'maxlength="500"', response.data)
        self.assertIn(b'href="/chat"', response.data)

    def test_groq_failure_returns_friendly_message(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with patch(
                "main.requests.post",
                side_effect=main.requests.Timeout("test timeout"),
            ):
                response = self.post_chat("I am feeling stressed.")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["reply"], main.CHAT_UNAVAILABLE_MESSAGE)

    def test_rate_limit_rejects_the_twenty_first_message_in_one_minute(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with patch("main.requests.post", return_value=self.groq_response()):
                for index in range(20):
                    response = self.post_chat(f"Message {index}")
                    self.assertEqual(response.status_code, 200)
                limited = self.post_chat("One more message")

        self.assertEqual(limited.status_code, 429)
        self.assertIn("wait", limited.json["error"])


if __name__ == "__main__":
    unittest.main()
