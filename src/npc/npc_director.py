"""NPC director module for phase-2 architecture refactor."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.data.models import DMAgentOutput, GameState
from src.data.npc_planning_models import NPCActionDecision, NPCActionForm, NPCActionType


class NPCDirector:
    """Centralized NPC planner that outputs structured action forms."""

    def decide_actions(
        self,
        npc_ids: List[str],
        game_state: GameState,
        player_intent: Optional[DMAgentOutput] = None,
        trigger_source: str = "queue",
        recent_events: Optional[List[dict]] = None,
    ) -> NPCActionDecision:
        actions: Dict[str, NPCActionForm] = {}
        player_id = game_state.player_id or ""

        for npc_id in npc_ids:
            npc = game_state.characters.get(npc_id)
            if not npc or npc.is_player:
                continue
            if npc.status.hp <= 0 or npc.status.san <= 0:
                continue

            action_type = NPCActionType.WAIT
            target_id = None
            intent_description = "保持观察，等待局势变化"

            if player_intent and player_intent.npc_response_needed:
                action_type = NPCActionType.TALK
                target_id = player_id or None
                intent_description = (
                    player_intent.npc_intent
                    or "对玩家刚刚的行动做出回应"
                )

            actions[npc_id] = NPCActionForm(
                npc_id=npc_id,
                action_type=action_type,
                target_id=target_id,
                intent_description=intent_description,
                trigger_source=trigger_source,
                metadata={
                    "recent_events_count": len(recent_events or []),
                },
            )

        return NPCActionDecision(
            actions=actions,
            rationale="Rule-based fallback planner for phase-2 NPCDirector integration.",
        )


__all__ = ["NPCDirector"]
