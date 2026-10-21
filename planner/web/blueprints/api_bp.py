from flask import Blueprint, request, jsonify

bp = Blueprint("api", __name__, url_prefix="/api")


from ..ownership import (owned_scene, owned_act, owned_link,  # noqa: E402
                          current_pid, deny)


# ─── Scenes ───────────────────────────────────────────────────────────────────

# ─── Адрес Fiction Engine ─────────────────────────────────────────────────────

def _fe_base_url() -> str:
    """
    Адрес Fiction Engine. Настраивается через FE_URL.

    Прибивать localhost:5000 в шести местах нельзя: хост и порт FE
    задаются переменными FE_HOST/FE_PORT, и по умолчанию он слушает
    127.0.0.1, а не localhost-как-придётся.
    """
    import os
    return os.environ.get("FE_URL", "http://127.0.0.1:5000").rstrip("/")


def _fe_headers() -> dict:
    """
    Заголовок X-FE-Token: Fiction Engine пускает программы с ним без сессии
    и токена CSRF (fiction_engine/web/security.py). Токен — sha256 от
    FE_PASSWORD, если задан, иначе файл, который создаёт сам FE: FE_API_TOKEN_FILE или
    ~/fiction_engine/api_token.
    """
    import hashlib
    import os
    from pathlib import Path
    pw = os.environ.get("FE_PASSWORD", "")
    # Не сам пароль — заголовок HTTP латиница-1; так же считает FE
    # (fiction_engine/web/security.py, token_from_password)
    token = hashlib.sha256(("fiction-engine-api:" + pw).encode()).hexdigest() if pw else ""
    if not token:
        path = Path(os.environ.get("FE_API_TOKEN_FILE")
                    or Path.home() / "fiction_engine" / "api_token")
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""      # FE ещё ни разу не запускался — он и не ответит
    return {"X-FE-Token": token} if token else {}


def _fe_get(path: str, timeout: float):
    import urllib.request
    return urllib.request.urlopen(
        urllib.request.Request(f"{_fe_base_url()}{path}", headers=_fe_headers()), timeout=timeout)


@bp.route("/scenes")
def scenes_list():
    pid = current_pid()
    if not pid: return jsonify({"scenes": []})
    from engine.db import get_scenes
    return jsonify({"scenes": get_scenes(pid)})


@bp.route("/scenes/new", methods=["POST"])
def scene_new():
    pid = current_pid()
    if not pid: return jsonify({"error": "Нет проекта"}), 400
    data   = request.json or {}
    act_id = data.get("act_id")
    if act_id is not None and not owned_act(act_id):
        return deny("Акт")
    from engine.db import create_scene, update_scene
    sid = create_scene(pid, act_id)
    # Карточка /scene/new сохраняется впервые — поля приходят сразу.
    # Снапшот пустой карточки не нужен: откатываться к пустоте незачем
    fields = {k: v for k, v in data.items() if k != "act_id"}
    if fields:
        update_scene(sid, fields, snapshot=False)
    return jsonify({"ok": True, "id": sid})


@bp.route("/scenes/move", methods=["POST"])
def scene_move():
    data     = request.json or {}
    sid      = data.get("scene_id")
    act_id   = data.get("act_id")
    position = data.get("position", 0)
    if not sid: return jsonify({"error": "Нет scene_id"}), 400
    # Двигать можно только свою сцену и только в свой акт:
    # оба номера приходят из запроса и раньше принимались как есть.
    if not owned_scene(sid):
        return deny("Сцена")
    if act_id is not None and not owned_act(act_id):
        return deny("Акт")
    from engine.db import move_scene
    move_scene(sid, act_id, position)
    return jsonify({"ok": True})


@bp.route("/scenes/reorder", methods=["POST"])
def scene_reorder():
    """Пересохранить позиции сцен в акте после drag & drop."""
    data   = request.json or {}
    order  = data.get("order", [])  # [{scene_id, position}]
    act_id = data.get("act_id")

    # Переставлять можно только свои сцены и только внутри своего акта.
    # Раньше номера брались из запроса как есть, и порядок чужого проекта
    # переписывался целиком.
    if act_id is not None and not owned_act(act_id):
        return deny("Акт")
    for item in order:
        if not owned_scene(item.get("scene_id")):
            return deny("Сцена")

    from engine.db import get_conn
    with get_conn() as conn:
        for item in order:
            conn.execute(
                "UPDATE scenes SET act_id=?, position=? WHERE id=?",
                (act_id, item["position"], item["scene_id"])
            )
    return jsonify({"ok": True})


# ─── Acts ─────────────────────────────────────────────────────────────────────

@bp.route("/acts")
def acts_list():
    pid = current_pid()
    if not pid: return jsonify({"acts": []})
    from engine.db import get_acts
    return jsonify({"acts": get_acts(pid)})


@bp.route("/acts/save", methods=["POST"])
def act_save():
    pid = current_pid()
    if not pid: return jsonify({"error": "Нет проекта"}), 400
    data  = request.json or {}
    # Номер правимого акта приходит под ключом "id" (не "act_id").
    # Без этой проверки чужой акт переписывался по одному лишь номеру.
    existing = data.get("id") or data.get("act_id")
    if existing and not owned_act(existing):
        return deny("Акт")
    from engine.db import save_act
    aid = save_act(pid, data.get("id"), data.get("number", 1),
                   data.get("title", "Акт"), data.get("color", "#6b7280"))
    return jsonify({"ok": True, "id": aid})


@bp.route("/acts/<int:act_id>/delete", methods=["POST"])
def act_delete(act_id):
    if not owned_act(act_id):
        return deny("Акт")
    from engine.db import delete_act
    delete_act(act_id)
    return jsonify({"ok": True})


# ─── Links ───────────────────────────────────────────────────────────────────

@bp.route("/links")
def links_list():
    pid = current_pid()
    if not pid: return jsonify({"links": []})
    from engine.db import get_links
    return jsonify({"links": get_links(pid)})


@bp.route("/links/save", methods=["POST"])
def link_save():
    data = request.json or {}
    # Связь вписывалась между любыми сценами по номерам из запроса —
    # в том числе в чужой проект.
    for key in ("from_id", "to_id"):
        if not owned_scene(data.get(key)):
            return deny("Сцена")
    from engine.db import save_link
    lid = save_link(data["from_id"], data["to_id"],
                    data.get("link_type", "cause"), data.get("label", ""))
    return jsonify({"ok": True, "id": lid})


@bp.route("/links/<int:link_id>/delete", methods=["POST"])
def link_delete(link_id):
    if not owned_link(link_id):
        return deny("Связь")
    from engine.db import delete_link
    delete_link(link_id)
    return jsonify({"ok": True})


# ─── AI Assistant ─────────────────────────────────────────────────────────────

BOOK_CONTEXT_MAX = 9000        # символов о книге в запросе AI-помощи
FE_UNREACHABLE = "Fiction Engine не ответил — помощь без контекста книги"


def _book_context() -> tuple[str, str]:
    """
    Что известно о связанной книге FE: что уже случилось (L3), сюжетные
    линии и состояние мира → (текст, предупреждение). Проекта нет — («», «»),
    FE молчит — («», FE_UNREACHABLE): раньше помощь шла без книги молча.
    Каждому блоку — своя треть бюджета: общий обрез с конца отбрасывал
    State героев целиком (разбор 21.10).
    """
    from engine.db import get_project
    fe_pid = (get_project(current_pid()) or {}).get("fe_project_id")
    if not fe_pid:
        return "", ""
    import json as _json
    try:
        with _fe_get(f"/api/project/context?pid={fe_pid}", timeout=5) as r:
            d = _json.loads(r.read())
    except Exception:
        return "", FE_UNREACHABLE
    share = BOOK_CONTEXT_MAX // 3
    parts = [(d.get("story_so_far") or "").strip()[-share:],
             "СЮЖЕТНЫЕ ЛИНИИ:\n" + d["plot_matrix"].strip()[:share] if d.get("plot_matrix") else "",
             "СОСТОЯНИЕ МИРА И ГЕРОЕВ:\n" + d["global_state"].strip()[:share] if d.get("global_state") else ""]
    text = "\n\n".join(p for p in parts if p)
    if not text:
        return "", ""
    last = d.get("last_chapter") or 0
    return f"=== КНИГА (написано глав: {last}) ===\n{text}\n\n", ""


def _neighbours(scene_id) -> str:
    """Сцена до и после этой на доске — только своего проекта."""
    me = owned_scene(scene_id) if scene_id else None
    if not me:
        return ""
    from engine.db import get_acts, get_scenes
    order = {a["id"]: i for i, a in enumerate(get_acts(me["project_id"]))}
    seq = sorted(get_scenes(me["project_id"]),
                 key=lambda s: (order.get(s["act_id"], len(order)), s["position"] or 0))
    i = next(k for k, s in enumerate(seq) if s["id"] == me["id"])
    out = []
    for label, s in (("ДО", seq[i - 1] if i > 0 else None),
                     ("ПОСЛЕ", seq[i + 1] if i + 1 < len(seq) else None)):
        if s and (s["title"] or s["what_happens"]):
            out.append(f"СЦЕНА {label}: {s['title'] or 'без названия'} — {s['what_happens'] or ''}".strip(" —"))
    return ("=== СОСЕДНИЕ СЦЕНЫ ===\n" + "\n".join(out) + "\n\n") if out else ""


@bp.route("/ai/assist", methods=["POST"])
def ai_assist():
    data   = request.json or {}
    action = data.get("action", "develop")
    scene  = data.get("scene", {})
    model  = data.get("model", "")

    ACTIONS = {
        "develop":  "Развей идею этой сцены — что можно добавить, углубить, сделать интереснее.",
        "conflict": "Предложи конфликт или напряжение для этой сцены. Что может пойти не так?",
        "subtext":  "Что персонажи не говорят вслух? Добавь подтекст — скрытые мотивы, недосказанность.",
        "next":     "Что логично происходит после этой сцены? Предложи 2-3 варианта следующей сцены.",
        "rewrite":  "Перепиши описание этой сцены — более конкретно, с деталями.",
    }

    instruction = ACTIONS.get(action, ACTIONS["develop"])
    scene_text  = (
        f"Сцена: {scene.get('title','')}\n"
        f"Локация: {scene.get('location','')} / {scene.get('time_of_day','')}\n"
        f"Персонажи: {scene.get('characters','')}\n"
        f"Что происходит: {scene.get('what_happens','')}\n"
        f"Эмоция: {scene.get('emotion','')}\n"
        f"Заметки: {scene.get('notes','')}"
    )
    # Книга и соседние сцены: без них «что дальше» и «конфликт» придумывались
    # с нуля и спорили с тем, что уже написано
    book, book_warning = _book_context()
    context = book + _neighbours(data.get("scene_id"))
    prompt = f"{instruction}\n\n{context}=== ЭТА СЦЕНА ===\n{scene_text}"
    if context:
        prompt += ("\n\nДержись того, что уже есть в книге и в соседних сценах: "
                   "не меняй факты, не воскрешай погибших, не переноси места и время.")

    # Вызов модели делает Fiction Engine: ключи живут там
    try:
        import requests as req
        resp = req.post(f"{_fe_base_url()}/api/inline_call", headers=_fe_headers(), json={
            "model": model,
            "system": "Ты помощник сценариста и писателя. Отвечаешь конкретно и по делу.",
            "prompt": prompt,
            "max_tokens": 900
        # Вызов по подписке идёт минутами (у FE предел 900 с): 90 с обрывали ответ
        }, timeout=900)
        if resp.ok:
            return jsonify({"ok": True, "result": resp.json().get("result", ""),
                            **({"warning": book_warning} if book_warning else {})})

        # Осмысленный отказ FE (нет ключа, пустой ответ модели) раньше
        # схлопывался в «FE недоступен» — автор видел не ту причину и не
        # понимал, что делать. Передаём сообщение как есть.
        try:
            detail = resp.json().get("error") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        return jsonify({"error": f"Fiction Engine ответил отказом: {detail}"}), resp.status_code

    except req.exceptions.RequestException as e:
        # Сетевая ошибка — это действительно «FE недоступен»
        return jsonify({
            "error": f"Fiction Engine недоступен ({_fe_base_url()}): {e}. "
                     "Запусти его или задай FE_URL."
        }), 503


# ─── Импорт главы на доску ────────────────────────────────────────────────────

@bp.route("/fe/chapters")
def fe_chapters():
    """Написанные главы связанного проекта FE — выбор в «Импорт главы»."""
    from engine.db import get_project
    fe_pid = (get_project(current_pid()) or {}).get("fe_project_id")
    if not fe_pid:
        return jsonify({"chapters": [], "linked": False})
    import json as _json
    try:
        with _fe_get(f"/api/chapters/list?pid={fe_pid}", timeout=5) as r:
            return jsonify({"chapters": _json.loads(r.read()).get("chapters", []), "linked": True})
    except Exception as e:
        return jsonify({"chapters": [], "linked": True, "error": f"FE недоступен: {e}"})


@bp.route("/chapter_import/split", methods=["POST"])
def chapter_import_split():
    """
    Разбить главу на сцены — только предложение, на доску ничего не пишется:
    автор смотрит, правит и снимает лишнее в окне, потом /chapter_import/save.
    Текст — вставленный автором или глава связанного проекта FE.
    """
    pid = current_pid()
    if not pid:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter, model = _chapter_num(data), (data.get("model") or "").strip()
    if not model:
        return jsonify({"error": "Выбери модель"}), 400
    text = (data.get("text") or "").strip()
    if not text:
        from engine.db import get_project
        fe_pid = (get_project(pid) or {}).get("fe_project_id")
        if not fe_pid:
            return jsonify({"error": "Проект не связан с Fiction Engine — вставь текст главы"}), 400
        import json as _json
        try:
            with _fe_get(f"/api/chapter/{chapter}/text?pid={fe_pid}", timeout=10) as r:
                text = (_json.loads(r.read()).get("text") or "").strip()
        except Exception as e:
            return jsonify({"error": f"FE недоступен: {e}"}), 503
        if not text:
            return jsonify({"error": f"Главы {chapter} в Fiction Engine нет"}), 404

    from engine.chapter_import import SYSTEM, build_prompt, parse
    from engine.db import get_scenes
    board = get_scenes(pid)
    import requests as req
    try:
        # Глава целиком и ответ на десяток сцен: подписке нужно время
        resp = req.post(f"{_fe_base_url()}/api/inline_call", headers=_fe_headers(), json={
            "model": model, "system": SYSTEM, "prompt": build_prompt(text, chapter, board),
            "max_tokens": 8000}, timeout=600)
    except req.exceptions.RequestException as e:
        return jsonify({"error": f"Fiction Engine недоступен ({_fe_base_url()}): {e}"}), 503
    if not resp.ok:
        try:
            detail = resp.json().get("error") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        return jsonify({"error": f"Fiction Engine ответил отказом: {detail}"}), resp.status_code
    try:
        got = parse(resp.json().get("result", ""), {s["id"] for s in board})
    except ValueError as e:
        return jsonify({"error": f"Не разобрать ответ модели: {e}. Попробуй ещё раз или другую модель"}), 502
    titles = {s["id"]: s["title"] or f"Сцена #{s['id']}" for s in board}
    for ln in got["links"]:
        for end in ("from", "to"):
            if ln[end][0] == "board":
                ln[end + "_title"] = titles[ln[end][1]]
    return jsonify({"ok": True, "chapter_num": chapter, "words": len(text.split()),
                    "already": sum(1 for s in board if s.get("chapter_num") == chapter), **got})


@bp.route("/chapter_import/save", methods=["POST"])
def chapter_import_save():
    """Сцены главы, которые автор оставил в окне, — на доску; связи — в граф."""
    pid = current_pid()
    if not pid:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    act_id = data.get("act_id") or None
    if act_id is not None and not owned_act(act_id):
        return deny("Акт")
    scenes = [s for s in data.get("scenes") or [] if isinstance(s, dict)]
    if not scenes:
        return jsonify({"error": "Нет сцен"}), 400
    links = []
    for ln in data.get("links") or []:
        try:
            ends = [(str(e[0]), int(e[1])) for e in (ln["from"], ln["to"])]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if all(k in ("new", "board") for k, _ in ends):
            links.append({"from": ends[0], "to": ends[1],
                          "type": ln.get("type") if ln.get("type") in ("cause", "parallel", "mirror", "contrast")
                          else "cause", "label": str(ln.get("label") or "")[:80]})
    from engine.db import import_chapter
    ids = import_chapter(pid, act_id, _chapter_num(data), scenes, links)
    return jsonify({"ok": True, "ids": ids})


# ─── Export to Fiction Engine ─────────────────────────────────────────────────

@bp.route("/timeline")
def timeline():
    """
    Подсказки по времени для сцен главы в порядке экспорта
    (engine/timeline.py). Чужие сцены отбрасываются, как в export_send.
    """
    from engine.timeline import check
    ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip().isdigit()]
    scenes = [sc for sc in (owned_scene(sid) for sid in ids) if sc]
    return jsonify({"warnings": check(scenes)})


def plan_text(scenes: list, chapter_num: int) -> str:
    """
    План главы из сцен. Один на превью и на отправку: раньше превью
    собиралось в браузере по-своему (с заметками сцены), а в FE уходил
    другой текст. Заметки сцены — черновик автора, в план не идут.
    """
    from engine.timeline import scene_when
    lines = [f"ПЛАН ГЛАВЫ {chapter_num}\n"]
    for i, s in enumerate(scenes, 1):
        lines.append(f"СЦЕНА {i}: {s['title'] or 'Без названия'}")
        if s["location"]:
            lines.append(f"  Локация: {s['location']}")
        if scene_when(s):
            lines.append(f"  Когда: {scene_when(s)}")
        if s["characters"]:  lines.append(f"  Персонажи: {s['characters']}")
        if s["what_happens"]:lines.append(f"  Что происходит: {s['what_happens']}")
        if s["emotion"]:     lines.append(f"  Эмоция: {s['emotion']}")
        lines.append("")
    # «Пока не раскрывать» — одним блоком после сцен: запрет на всю главу,
    # писатель его видит, разгадку — нет. Сверка с планом этот блок пунктом
    # не считает (engine/plan_check: HOLD_HEADER)
    holds = [(s.get("hold") or "").strip() for s in scenes]
    holds = [h for h in dict.fromkeys(holds) if h]
    if holds:
        lines.append(HOLD_HEADER)
        lines += [f"- {h}" for h in holds]
    return "\n".join(lines).strip() + "\n"


def future_text(pid: int, chapter_num: int, current: list) -> str:
    """
    Сцены доски после плана главы — что будет дальше. Идёт в FE только
    сторожу забеганий («глава раскрыла то, что по плану позже»), писателю —
    никогда. Сторож «Фона» (19.10) ловил забегания по планам следующих глав:
    по одному «пока не раскрывать» текущей главы из четырёх раскрытий
    видно одно. Дальше — сцены позже последней сцены главы на доске (акты
    по номеру) и сцены, уже размеченные под главы после этой. Заметки
    сцены — черновик автора, не идут.
    """
    from engine.db import get_acts, get_scenes
    act_no = {a["id"]: a["number"] for a in get_acts(pid)}
    board = sorted(get_scenes(pid), key=lambda s: (act_no.get(s["act_id"], 10**6), s["position"] or 0, s["id"]))
    here = {s["id"] for s in current}
    idx = [i for i, s in enumerate(board) if s["id"] in here]
    after = idx[-1] if idx else len(board)
    lines = []
    for i, s in enumerate(board):
        later = s.get("chapter_num") and s["chapter_num"] > chapter_num
        if s["id"] in here or not (later or (i > after and not s.get("chapter_num"))):
            continue
        what = (s.get("what_happens") or "").strip()
        if not what:
            continue
        where = f"гл.{s['chapter_num']}" if s.get("chapter_num") else "дальше"
        hold = (s.get("hold") or "").strip()
        lines.append(f"- {where} «{s['title'] or 'без названия'}»: {what}" + (f" (пока не раскрывать: {hold})" if hold else ""))
    return "\n".join(lines)


HOLD_HEADER = "ПОКА НЕ РАСКРЫВАТЬ (в этой главе читатель этого ещё не узнаёт — ни прямо, ни уликой, которая указывает однозначно):"


def _chapter_num(data: dict) -> int:
    try:
        return max(1, int(data.get("chapter_num") or 1))
    except (TypeError, ValueError):
        return 1


def _mark_chapter(chapter_num: int, scenes: list) -> None:
    """План ушёл в FE — сцены помнят главу (метка на доске, выбор в экспорте)."""
    from engine.db import set_chapter_scenes
    set_chapter_scenes(current_pid(), chapter_num, [s["id"] for s in scenes])


@bp.route("/export/preview", methods=["POST"])
def export_preview():
    data   = request.json or {}
    scenes = [sc for sc in (owned_scene(sid) for sid in data.get("scene_ids", [])) if sc]
    if not scenes:
        return jsonify({"error": "Выбери хотя бы одну сцену"}), 400
    return jsonify({"ok": True, "prompt": plan_text(scenes, _chapter_num(data))})


@bp.route("/export/send", methods=["POST"])
def export_send():
    data       = request.json or {}
    scene_ids  = data.get("scene_ids", [])
    # Без номера главы план уходил главой 1 (разбор 21.10)
    try:
        if int(data.get("chapter_num") or 0) < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Укажи номер главы"}), 400
    chapter_num = _chapter_num(data)

    # Номера сцен приходят из запроса. Без фильтра по проекту содержимое
    # чужой сцены уходило в промт — и дальше в Fiction Engine
    # режиссёрской заметкой к главе. Маршрут был выведен из-под проверок
    # ложным обоснованием «читает только сцены текущего проекта».
    scenes = [sc for sc in (owned_scene(sid) for sid in scene_ids) if sc]
    if scene_ids and not scenes:
        return deny("Сцена")

    # Текст плана автор мог поправить в окне перед отправкой — уходит его
    # текст; факты сцен для библии всё равно берутся из карточек
    prompt_text = ((data.get("text") or "").strip() or plan_text(scenes, chapter_num)).strip()

    # Проект связан с Fiction Engine (импорт) — план идёт в него вместе с
    # фактами сцен: место, время, кто — в библию серии до того, как глава
    # написана. Без связи — прежняя записка в активный проект FE.
    from engine.db import get_project
    fe_pid = (get_project(current_pid()) or {}).get("fe_project_id")
    if fe_pid:
        from engine.timeline import scene_when
        facts = []
        for i, s in enumerate(scenes, 1):
            ev = f"глава {chapter_num}, сцена {i}: {s['title'] or 'без названия'}"
            # «время» — день и время суток вместе: библия FE сверяет день
            # события с главой, а не только «утро»
            for attr, val in (("место", s["location"]), ("время", scene_when(s)), ("кто", s["characters"])):
                if val:
                    facts.append({"kind": "событие", "name": ev, "attr": attr, "value": val})
        import requests as req
        try:
            resp = req.post(f"{_fe_base_url()}/api/chapter_plan/{chapter_num}/save",
                            json={"pid": fe_pid, "note": prompt_text, "facts": facts,
                                  "future": future_text(current_pid(), chapter_num, scenes)},
                            headers=_fe_headers(), timeout=10)
            if resp.ok:
                _mark_chapter(chapter_num, scenes)
                return jsonify({"ok": True, "prompt": prompt_text, "sent": True,
                                "facts": resp.json().get("facts", 0)})
            return jsonify({"ok": False, "prompt": prompt_text, "sent": False,
                            "error": f"Fiction Engine ответил отказом: {resp.text[:200]}"}), 502
        except req.exceptions.RequestException:
            return jsonify({"ok": True, "prompt": prompt_text, "sent": False,
                            "message": "Fiction Engine недоступен — скопируй план вручную"})

    # Проект не связан с книгой FE — план не отправляется: раньше он уходил в
    # проект, открытый в FE сейчас, — то есть, возможно, в чужую книгу, без
    # фактов сцен и без плана вперёд (разбор 21.10)
    return jsonify({"ok": False, "prompt": prompt_text, "sent": False,
                    "error": "Проект планировщика не связан с книгой в Fiction Engine (связь создаёт "
                             "«Импорт из FE») — план не отправлен."})


# ─── Статус системы ───────────────────────────────────────────────────────────

@bp.route("/status")
def system_status():
    """
    Состояние связки планировщик ↔ Fiction Engine.

    Ключи спрашиваются у FE по HTTP, а не читаются из его projects.db.
    Прежний вариант лез в чужую базу напрямую: планировщик знал её путь,
    схему таблицы api_keys и держал собственных клиентов пяти провайдеров.
    Любое изменение в FE ломало бы планировщик молча.
    """
    import json as _json
    import urllib.request

    fe_server, keys = False, {}
    try:
        with _fe_get("/api/keys/status", timeout=2) as r:
            raw = _json.loads(r.read())
        fe_server = True
        # FE отдаёт {провайдер: маскированный ключ}; нам нужен сам факт наличия
        keys = {
            "anthropic": "anthropic_direct" in raw,
            "openai":    "openai_direct" in raw,
            "gemini":    "gemini_direct" in raw,
            "deepseek":  "deepseek_direct" in raw,
            "nano":      "nano_gpt" in raw,
        }
    except Exception:
        # FE не запущен — это штатное состояние, а не ошибка:
        # планировщиком можно пользоваться и без него
        pass

    return jsonify({
        "fe_server": fe_server,
        "keys":      keys,
        "has_keys":  any(keys.values()),
    })


@bp.route("/fe/projects")
def fe_projects():
    """Список проектов FE."""
    try:
        import json as _json
        with _fe_get("/api/projects/list", timeout=3) as r:
            return jsonify(_json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": str(e), "projects": []})


@bp.route("/fe/models")
def fe_models():
    """Модели Fiction Engine — для AI-помощи в сцене (раньше модель вводилась вручную)."""
    try:
        import json as _json
        with _fe_get("/api/models", timeout=5) as r:
            return jsonify({"models": _json.loads(r.read())})
    except Exception as e:
        return jsonify({"error": str(e), "models": []})


@bp.route("/fe/bible")
def fe_bible():
    """Библия серии связанного проекта Fiction Engine."""
    from engine.db import get_project
    fe_pid = (get_project(current_pid()) or {}).get("fe_project_id")
    if not fe_pid:
        return jsonify({"error": "Проект не связан с Fiction Engine — сначала импортируй его"}), 400
    try:
        import json as _json
        with _fe_get(f"/api/bible?pid={fe_pid}", timeout=10) as r:
            return jsonify(_json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": f"FE недоступен: {e}"}), 503


@bp.route("/fe/bible/set", methods=["POST"])
def fe_bible_set():
    """Правка автора — новая запись в библии FE, прошлое остаётся в истории."""
    from engine.db import get_project
    fe_pid = (get_project(current_pid()) or {}).get("fe_project_id")
    if not fe_pid:
        return jsonify({"error": "Проект не связан с Fiction Engine — сначала импортируй его"}), 400
    import requests as req
    body = {k: (request.json or {}).get(k) for k in ("kind", "name", "attr", "value", "chapter_num", "reason")}
    try:
        resp = req.post(f"{_fe_base_url()}/api/bible/set", json=dict(body, pid=fe_pid),
                        headers=_fe_headers(), timeout=10)
    except req.exceptions.RequestException as e:
        return jsonify({"error": f"FE недоступен: {e}"}), 503
    # Ответ не JSON (500 страницей) — сказать, а не упасть самим
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"error": f"Fiction Engine ответил {resp.status_code}: {resp.text[:200]}"}), 502


@bp.route("/fe/import/<int:fe_pid>", methods=["POST"])
def fe_import(fe_pid):
    """Импортировать контекст проекта из FE в планировщик."""
    pid = current_pid()
    if not pid:
        return jsonify({"error": "Нет проекта в планировщике"}), 400

    import json as _json
    import urllib.error
    try:
        with _fe_get(f"/api/project/context?pid={fe_pid}", timeout=10) as r:
            data = _json.loads(r.read())
    except urllib.error.HTTPError as e:
        # FE ответил — это не «недоступен»: нет проекта, нет входа (разбор 21.10)
        return jsonify({"error": f"Fiction Engine ответил {e.code}: проекта {fe_pid} нет или нет доступа"}), 502
    except Exception as e:
        return jsonify({"error": f"FE недоступен: {e}"}), 503

    # Обновляем описание проекта в планировщике
    # save_logline здесь не нужен — и его в engine.db нет: импорт
    # валил весь обработчик с ImportError, то есть импорт из FE
    # не работал вовсе
    from engine.db import update_project, get_project
    project = get_project(pid)
    if not project:
        return jsonify({"error": "Проект не найден"}), 404

    fe_proj = data.get("project", {})
    global_state = data.get("global_state", "")
    promises     = data.get("active_promises", [])

    # Копия State в описании проекта устаревала с первой же главы (у автора
    # 17.10 там были «выписан домой» и «музей алхимии» после отката State).
    # Книгу AI-помощь теперь берёт из FE при каждом вызове; описание —
    # авторское, а прежняя копия State из него убирается
    description = project.get("description", "") or ""
    if description.startswith("СОСТОЯНИЕ МИРА:"):
        description = ""

    update_project(pid,
        name=project["name"],
        genre=fe_proj.get("genre") or project.get("genre", ""),
        description=description
    )
    # Связь запоминается: план главы и библия дальше идут в этот проект FE
    from engine.db import set_fe_project
    set_fe_project(pid, fe_pid)

    return jsonify({
        "ok": True,
        "imported": {
            "genre":    fe_proj.get("genre", ""),
            "promises": len(promises),
            "has_state": bool(global_state),
        }
    })
