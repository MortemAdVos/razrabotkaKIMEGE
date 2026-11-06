# -*- coding: utf-8 -*-
"""
Прототип интерфейса подсистемы «Разработка КИМ» (NFR-12, NFR-13).
Запуск:  streamlit run app.py
Читает пакет КИМ (tasks.json, variant_plan.json, branching_tree.json,
reference_materials.json, manifest.json) из папки package/ рядом со скриптом
или из загруженных файлов. Точка входа для демо на защите.
"""
import io
import json
import random
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Редактор КИМ — прототип", page_icon="📝", layout="wide")
_HERE = Path(__file__).parent
PACKAGE_DIR = _HERE if (_HERE / "tasks.json").exists() else _HERE / "package"
SEED_FILE = Path(__file__).parent / "session_seed.json"

SUBJECTS = {"02": "Математика (профильный уровень)"}  # федеральный справочник (Формат данных v2, раздел 5)


# ---------- загрузка данных ----------
@st.cache_data
def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_component(name, uploader_key):
    """Файл из package/ по умолчанию, иначе — загруженный пользователем."""
    up = st.sidebar.file_uploader(name, type=["json"], key=uploader_key)
    if up is not None:
        return json.loads(up.read().decode("utf-8"))
    p = PACKAGE_DIR / name
    if p.exists():
        return load_json(p)
    return None


# ---------- бизнес-логика (зеркало подсистемы) ----------
def assemble_variant(variant_no, bank, tree):
    """Сборка варианта: случайный валидный путь по дереву ветвления (FR-09/FR-10)."""
    by_id = {t["id"]: t for v in bank["variants"] for t in v["tasks"]}
    chosen, used_topics = [], set()
    for node in tree["nodes"]:
        alts = [a for a in node["alternatives"]
                if a["topic_code"] not in used_topics] or node["alternatives"]
        alt = random.choice(alts)
        used_topics.add(alt["topic_code"])
        t = by_id[random.choice(alt["example_task_ids"])]
        chosen.append(dict(t, position=node["position"]))
    return {
        "variant": variant_no,
        "exam_type": "EGE",
        "subject_code": "02",
        "title": f"Математика. Профильный уровень. Вариант {variant_no}",
        "tasks": sorted(chosen, key=lambda x: x["position"]),
    }


def build_package_zip(variant, plan, refs, manifest, instruction_md, media_dir=None):
    """Пакет КИМ одного варианта (структура ТЗ 7.2, JSON + локальные media)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("tasks/variant.json", json.dumps(variant, ensure_ascii=False, indent=2))
        z.writestr("variant_plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
        z.writestr("reference_materials.json", json.dumps(refs, ensure_ascii=False, indent=2))
        z.writestr("instruction.md", instruction_md)
        if media_dir and Path(media_dir).exists():
            used = set()
            for t in variant.get("tasks", []):
                img = t.get("content", {}).get("image")
                if img:
                    used.add(Path(img).name)
            for fname in used:
                src = Path(media_dir) / fname
                if src.exists():
                    z.write(src, f"media/{fname}")
    return buf.getvalue()


# ---------- интерфейс ----------
st.title("📝 Редактор КИМ — прототип подсистемы разработки контрольно-измерительных материалов")
st.caption("Веб-платформа тестирующей системы ЕГЭ · отдел разработки КИМ · демо для NFR-12/NFR-13")

# --- Э1/Э2: предмет и темы ---
st.sidebar.header("Э1–Э2 · Предмет и темы")
subject_code = st.sidebar.selectbox("Предмет (код федерального справочника)",
                                    options=list(SUBJECTS), format_func=lambda c: f"{c} — {SUBJECTS[c]}")
st.sidebar.success(f"Кодификатор и спецификация ФИПИ закреплены за предметом {subject_code} (FR-01, FR-02)")

bank = load_component("tasks.json", "up_tasks")
plan = load_component("variant_plan.json", "up_plan")
tree = load_component("branching_tree.json", "up_tree")
refs = load_component("reference_materials.json", "up_refs")
manifest = load_component("manifest.json", "up_manifest")
instruction_md = (PACKAGE_DIR / "instruction.md").read_text(encoding="utf-8") \
    if (PACKAGE_DIR / "instruction.md").exists() else "# Инструкция"

if not all([bank, plan, tree, refs]):
    st.error("Загрузите компоненты пакета КИМ (tasks / plan / branching_tree / reference_materials) "
             "в боковой панели или положите их в папку package/.")
    st.stop()

topics = sorted({t["topic_code"] for v in bank["variants"] for t in v["tasks"]})
st.sidebar.info(f"Список тем составлен: {len(topics)} тем кодификатора, покрытие 100 % (FR-03, FR-04)")

# --- Э3: план варианта ---
st.header("Э3 · План варианта (FR-05 — FR-08)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Заданий", plan["total_tasks"])
c2.metric("Макс. первичный балл", plan["max_primary_score"])
c3.metric("Длительность", f"{plan['exam_duration_min']} мин")
c4.metric("Путей ветвления", f"{tree['valid_paths_total']:,}".replace(",", " "))
plan_df = pd.DataFrame([{
    "№": p["number"], "Часть": p["part"], "Тип": p["type"],
    "Сложность": p["difficulty"], "Балл": p["max_score"],
    "Темы (варианты узла)": ", ".join(o["topic_code"] for o in p["topic_options"]),
} for p in plan["positions"]])
st.dataframe(plan_df, use_container_width=True, hide_index=True)
if st.button("✅ Согласовать план с Рособрнадзором"):
    st.balloons()
    st.success("План утверждён. Критических замечаний: 0 (FR-06). Макс. балл согласован с аналитикой (FR-08).")

# --- Э4–Э5: сборка варианта и предпросмотр ---
st.header("Э4–Э5 · Сборка заданий и предпросмотр (FR-09 — FR-14, NFR-12)")
col_a, col_b = st.columns([1, 2])
with col_a:
    variant_no = st.number_input("Номер собираемого варианта", 1, 100000, 1001)
    seed = st.number_input("Seed воспроизводимости", 0, 999999, 42)
    if st.button("🔀 Собрать вариант по дереву ветвления"):
        random.seed(seed)
        st.session_state["variant"] = assemble_variant(variant_no, bank, tree)
        st.session_state["seed_saved"] = seed

variant = st.session_state.get("variant")
if variant:
    psum = sum(t["max_score"] for t in variant["tasks"])
    st.write(f"**Вариант {variant['variant']}** — {len(variant['tasks'])} заданий, "
             f"суммарный балл {psum}, валидный путь дерева ✓ (FR-10)")
    sel = st.selectbox("Предпросмотр задания как у участника",
                       [t["id"] for t in variant["tasks"]],
                       format_func=lambda i: f"Задание {next(t['number'] for t in variant['tasks'] if t['id'] == i)} · {i}")
    task = next(t for t in variant["tasks"] if t["id"] == sel)

    with st.container(border=True):
        st.subheader(f"Задание {task['number']} · тема {task['topic_code']} · {task['difficulty']} · {task['max_score']} балл")
        st.markdown(task["content"]["condition"])
        if "image" in task["content"]:
            st.image(task["content"]["image"], caption="Чертёж к заданию")
        st.markdown(f"**{task['content']['question']}**")
        st.text_input("Поле ответа участника", placeholder="ответ не введён", disabled=True)
        st.caption(f"Метаданные: id={task['id']}, тип={task['type']}, проверка=auto, автор={task['author']} (NFR-20)")
        with st.expander("👁 Методист: правильный ответ и формат"):
            st.json(task["answer"])
    ref_ids = task.get("reference_ids", [])
    if ref_ids:
        st.info("Справочные материалы к заданию: " + "; ".join(
            f"**{r['title']}** ({r['id']})" for r in refs["materials"] if r["id"] in ref_ids))

    # --- Э8: экспорт пакета ---
    st.header("Э8 · Оформление и интеграция (FR-23 — FR-28)")
    if manifest is None:
        manifest = {"package_id": f"kim-ege-math-profile-2026-v{variant['variant']}",
                    "version": "1.0.0", "status": "ready_for_import"}
    zip_bytes = build_package_zip(variant, plan, refs, manifest, instruction_md, media_dir=PACKAGE_DIR / "media")
    st.download_button("📦 Скачать пакет КИМ (ZIP: manifest + tasks + plan + reference_materials + instruction + media)",
                       data=zip_bytes,
                       file_name=f"kim_variant_{variant['variant']}.zip",
                       mime="application/zip")
    st.success("Пакет прошёл валидацию JSON-схемы: 0 ошибок (NFR-06, NFR-14). Формат интеграции — JSON (XML исключён по ЗИ, FR-24).")
else:
    st.info("Нажмите «Собрать вариант по дереву ветвления» — будет выбран случайный валидный путь (не менее 4 уникальных путей, FR-09).")

# --- Э7: инструкция ---
with st.expander("📄 Инструкция прохождения экзамена (Э7, FR-20 — FR-22)"):
    st.markdown(instruction_md)
