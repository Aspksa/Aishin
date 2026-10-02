from __future__ import annotations

from ..personality import personality


class SelfModel:
    """Structured self-description derived from the canonical personality profile.

    It gives the cognitive layer stable identity, values, goals and boundaries
    without tying them to any one language model.
    """

    def snapshot(self) -> dict:
        p = personality.profile
        return {
            "identity": p["identity"],
            "core_identity": p["core_identity"],
            "values": p["runtime_personality_kernel"]["priority_rules"],
            "goals": p["aspiration"],
            "strengths": p["work_profile"]["strongest_task_types"],
            "boundaries": {
                "final_decision_owner": p["view_of_master"]["final_decision_owner"],
                "cannot": p["view_of_master"]["assistant_cannot"],
                "care": p["care"],
            },
            "error_policy": p["error_handling"],
            "memory_policy": p["memory"],
        }

    def prompt_block(self) -> str:
        p = personality.profile
        return (
            "Постоянная модель себя Айшин:\n"
            f"- Главный принцип: {p['core_identity']['main_principle']}\n"
            f"- Цель: {p['aspiration']['goal']}\n"
            f"- Решение остаётся за: {p['view_of_master']['final_decision_owner']}\n"
            f"- Ошибка: {p['error_handling']['view']}\n"
            f"- Память: {p['memory']['principle']}"
        )
