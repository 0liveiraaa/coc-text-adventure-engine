import unittest

from src.agent.llm_service import LLMService


class LLMJsonRetryTests(unittest.TestCase):
    def test_call_llm_json_retries_with_error_hint(self):
        service = object.__new__(LLMService)
        calls = []

        def fake_call_llm(prompt, response_format=None, max_retries=3, **kwargs):
            calls.append(prompt)
            # 第一次给坏JSON，第二次给正确JSON
            if len(calls) == 1:
                return {
                    "success": True,
                    "content": "{bad json}",
                    "model": "fake-model",
                    "usage": None,
                    "error": None,
                }
            return {
                "success": True,
                "content": '{"ok": true}',
                "model": "fake-model",
                "usage": None,
                "error": None,
            }

        service.call_llm = fake_call_llm  # type: ignore[attr-defined]

        result = LLMService.call_llm_json(
            service,
            prompt="测试",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            max_retries=3,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], {"ok": True})
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn("上一次输出存在错误", calls[1])


if __name__ == "__main__":
    unittest.main()
