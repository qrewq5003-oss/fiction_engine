

# ─── Глава уходит проверке целиком ───────────────────────────────────────────
#
# Здесь стояли первые 3000 символов с комментарием «достаточно для
# проверки фактов» — утверждение, которое никто не проверял. Для главы в
# 11 000 символов это 26 %.
#
# Проверено подсадкой 14.09: одно и то же противоречие ставилось на 5 % и
# на 85 % главы, с уникальной меткой «нефритовый секстант», чтобы
# совпадение нельзя было спутать с упоминанием Павла в самом тексте.
#
#     подсадка на 85 %:  обрезка 3000 — не найдено (её там и нет)
#                        полный текст — найдено, метка названа дословно
#
# Факты — имена, предметы, обещания — рассыпаны по всей главе, а не
# собраны в начале. Выборка здесь режет не лишнее, а искомое.

class TestWholeChapterReachesContinuity:
    MARK = "нефритовый секстант"

    def _run(self, chapter, monkeypatch):
        import engine.continuity_checker as cc
        seen = {}

        def fake_call(prompt):
            seen["prompt"] = prompt
            return '{"violations": []}'

        monkeypatch.setattr(cc, "_has_enough_data", lambda *a: True)
        monkeypatch.setattr(cc, "_build_series_facts", lambda *a: "Павел погиб в главе 2")
        cc.check_continuity(project_id=1, chapter_num=5,
                            chapter_text=chapter, api_call_fn=fake_call)
        return seen.get("prompt", "")

    def test_late_fact_reaches_the_checker(self, monkeypatch):
        chapter = "Обычный текст главы. " * 400 + f"\n\nОн протянул Павлу {self.MARK}.\n"
        assert len(chapter) > 3000, "проверка потеряла смысл: глава короче прежней обрезки"
        assert self.MARK in self._run(chapter, monkeypatch), \
            "конец главы не дошёл до проверки непрерывности"

    def test_early_fact_still_reaches(self, monkeypatch):
        chapter = f"Он протянул Павлу {self.MARK}.\n\n" + "Обычный текст главы. " * 400
        assert self.MARK in self._run(chapter, monkeypatch)

    def test_pathological_length_is_capped(self, monkeypatch):
        from engine.pipeline_config import CRITIC_TEXT_LIMIT
        huge = "А" * (CRITIC_TEXT_LIMIT * 3)
        prompt = self._run(huge, monkeypatch)
        assert len(prompt) < len(huge)
