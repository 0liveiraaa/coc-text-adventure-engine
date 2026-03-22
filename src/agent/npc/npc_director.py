"""LLM-first NPC director with structured fallback."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agent.llm_service import LLMService
from src.data.models import DMAgentOutput, GameState
from src.data.npc_planning_models import NPCActionDecision, NPCActionForm, NPCActionType

from .prompt_loader import load_npc_director_prompt

logger = logging.getLogger(__name__)


NPC_DIRECTOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "npc_id": {"type": "string"},
                    "action_type": {
                        "type": "string",
                        "enum": ["attack", "move", "talk", "use_item", "investigate", "wait", "custom"],
                    },
                    "target_id": {"type": ["string", "null"]},
                    "intent_description": {"type": "string"},
                    "expected_outcome": {"type": ["string", "null"]},
                    "check": {
                        "type": "object",
                        "properties": {
                            "check_needed": {"type": "boolean"},
                            "check_attributes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "difficulty": {
                                "type": "string",
                                "enum": ["regular", "hard", "extreme"],
                            },
                            "check_target_id": {"type": ["string", "null"]},
                        },
                        "required": ["check_needed", "check_attributes", "difficulty"],
                    },
                    "trigger_source": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["npc_id", "action_type", "intent_description", "check", "trigger_source"],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["actions"],
}


class NPCDirector:
    """Centralized NPC planner that outputs structured action forms."""

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        system_prompt: Optional[str] = None,
        use_llm: bool = True,
    ):
        self.use_llm = bool(use_llm)
        self.llm_service = llm_service
        if self.use_llm and self.llm_service is None:
            try:
                self.llm_service = LLMService()
            except Exception as e:
                logger.warning("NPCDirector无法初始化LLM服务，使用规则兜底: %s", e)
                self.llm_service = None
        if not self.use_llm:
            self.llm_service = None

        self.system_prompt = system_prompt or load_npc_director_prompt()

    def decide_actions(
        self,
        npc_ids: List[str],
        game_state: GameState,
        player_intent: Optional[DMAgentOutput] = None,
        trigger_source: str = "unified",
        recent_events: Optional[List[dict]] = None,
        narrative_context: str = "",
    ) -> NPCActionDecision:
        available_npc_ids = self._filter_actionable_npcs(npc_ids, game_state)
        if not available_npc_ids:
            return NPCActionDecision(actions={}, rationale="没有可行动NPC")

        if self.llm_service:
            llm_result = self._llm_decide(
                available_npc_ids,
                game_state,
                player_intent,
                trigger_source,
                recent_events or [],
                narrative_context,
            )
            if llm_result is not None and llm_result.actions:
                return llm_result

        return self._fallback_decision(
            available_npc_ids,
            game_state,
            player_intent,
            trigger_source,
            recent_events or [],
        )

    def _llm_decide(
        self,
        npc_ids: List[str],
        game_state: GameState,
        player_intent: Optional[DMAgentOutput],
        trigger_source: str,
        recent_events: List[dict],
        narrative_context: str,
    ) -> Optional[NPCActionDecision]:
        prompt = self._build_prompt(npc_ids, game_state, player_intent, trigger_source, recent_events, narrative_context)
        try:
            response = self.llm_service.call_llm_json(prompt=prompt, schema=NPC_DIRECTOR_OUTPUT_SCHEMA)
            if not response.get("success"):
                logger.warning("NPCDirector LLM调用失败: %s", response.get("error"))
                return None
            data = response.get("data") or {}
            return self._parse_decision(data, npc_ids)
        except Exception as e:
            logger.warning("NPCDirector LLM解析失败，回退规则兜底: %s", e)
            return None

    def _build_prompt(
        self,
        npc_ids: List[str],
        game_state: GameState,
        player_intent: Optional[DMAgentOutput],
        trigger_source: str,
        recent_events: List[dict],
        narrative_context: str,
    ) -> str:
        payload = {
            "turn_count": game_state.turn_count,
            "player_id": game_state.player_id,
            "npc_ids": npc_ids,
            "trigger_source": trigger_source,
            "player_intent": player_intent.model_dump() if player_intent else None,
            "recent_events": recent_events[-10:],
            "narrative_context": narrative_context,
            "npc_states": [self._serialize_npc_state(game_state, npc_id) for npc_id in npc_ids],
        }
        return (
            f"{self.system_prompt}\n\n"
            "## 决策输入(JSON)\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _serialize_npc_state(self, game_state: GameState, npc_id: str) -> Dict[str, Any]:
        npc = game_state.characters.get(npc_id)
        if not npc:
            return {"npc_id": npc_id}
        return {
            "npc_id": npc.id,
            "name": npc.name,
            "location": npc.location,
            "status": {
                "hp": npc.status.hp,
                "max_hp": npc.status.max_hp,
                "san": npc.status.san,
            },
            "attributes": {
                "dex": npc.attributes.dex,
                "int": npc.attributes.int,
                "pow": npc.attributes.pow,
            },
        }

    def _parse_decision(self, data: Dict[str, Any], allowed_npc_ids: List[str]) -> NPCActionDecision:
        raw_actions = data.get("actions") or {}
        actions: Dict[str, NPCActionForm] = {}
        for npc_id, raw_action in raw_actions.items():
            if npc_id not in allowed_npc_ids:
                continue
            if isinstance(raw_action, dict):
                raw_action.setdefault("npc_id", npc_id)
                actions[npc_id] = NPCActionForm(**raw_action)

        return NPCActionDecision(
            actions=actions,
            rationale=str(data.get("rationale", "")).strip(),
        )

    def _fallback_decision(
        self,
        npc_ids: List[str],
        game_state: GameState,
        player_intent: Optional[DMAgentOutput],
        trigger_source: str,
        recent_events: List[dict],
    ) -> NPCActionDecision:
        actions: Dict[str, NPCActionForm] = {}
        player_id = game_state.player_id or ""

        for npc_id in npc_ids:
            action_type = NPCActionType.WAIT
            target_id = None
            intent_description = "保持观察，等待局势变化"

            if player_intent and player_intent.npc_response_needed:
                action_type = NPCActionType.TALK
                target_id = player_id or None
                intent_description = player_intent.npc_intent or "对玩家刚刚的行动做出回应"

            actions[npc_id] = NPCActionForm(
                npc_id=npc_id,
                action_type=action_type,
                target_id=target_id,
                intent_description=intent_description,
                trigger_source=trigger_source,
                metadata={"recent_events_count": len(recent_events)},
            )

        return NPCActionDecision(
            actions=actions,
            rationale="LLM不可用，已使用规则兜底计划",
        )

    def _filter_actionable_npcs(self, npc_ids: List[str], game_state: GameState) -> List[str]:
        filtered: List[str] = []
        for npc_id in npc_ids:
            npc = game_state.characters.get(npc_id)
            if not npc or npc.is_player:
                continue
            if npc.status.hp <= 0 or npc.status.san <= 0:
                continue
            filtered.append(npc_id)
        return filtered


__all__ = ["NPCDirector"]
