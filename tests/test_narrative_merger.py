import unittest

from src.narrative.narrative_merger import NarrativeMerger


class _FakeLLMService:
    def call_llm(self, prompt, **kwargs):
        return {
            "success": True,
            "content": "玩家试探地开口后，守卫压低声音回应，气氛更加紧张。",
            "model": "fake",
            "usage": None,
            "error": None,
        }


class NarrativeMergerTests(unittest.TestCase):
    def test_merge_falls_back_to_join_when_llm_unavailable(self):
        merger = NarrativeMerger(llm_service=None, system_prompt="test")
        merger.llm_service = None

        merged = merger.merge(
            [
                {"actor_id": "player", "text": "你向守卫走近。"},
                {"actor_id": "guard", "text": "守卫盯着你，没有退后。"},
            ],
            context="",
        )

        self.assertIn("你向守卫走近", merged)
        self.assertIn("守卫盯着你", merged)

    def test_merge_uses_llm_when_available(self):
        merger = NarrativeMerger(llm_service=_FakeLLMService(), system_prompt="test")

        merged = merger.merge(
            [
                {"actor_id": "player", "text": "你抬手示意。"},
                {"actor_id": "guard", "text": "守卫靠近并回应。"},
            ],
            context="",
        )

        self.assertIn("守卫", merged)
        self.assertIn("玩家", merged)


if __name__ == "__main__":
    unittest.main()
