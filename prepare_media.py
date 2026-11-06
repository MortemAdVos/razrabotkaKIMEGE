# -*- coding: utf-8 -*-
"""
prepare_media.py — офлайн-подготовка пакета КИМ.

Скачивает все внешние изображения из tasks.json в media/,
переписывает content.image на локальные пути и обновляет SHA-256 в manifest.json.

Работает из любой папки: если рядом со скриптом лежит tasks.json — берёт её
как корень пакета, иначе ищет подпапку package/.

Запуск:
    pip install requests
    python3 prepare_media.py
"""
import hashlib
import json
from pathlib import Path

import requests

HERE = Path(__file__).parent
# автоопределение корня пакета: своя папка или подпапка package/
PACKAGE_DIR = HERE if (HERE / "tasks.json").exists() else HERE / "package"
MEDIA_DIR = PACKAGE_DIR / "media"
TASKS = PACKAGE_DIR / "tasks.json"
MANIFEST = PACKAGE_DIR / "manifest.json"

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (KIM-package-builder)"}


def local_name(url: str) -> str:
    """Уникальное локальное имя файла: хеш URL + оригинальный basename."""
    base = url.rstrip("/").split("/")[-1] or "image.svg"
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{digest}_{base}"


def main():
    if not TASKS.exists():
        raise SystemExit(f"Не найден {TASKS} — положи скрипт рядом с tasks.json "
                         f"или в папку на уровень выше package/")
    MEDIA_DIR.mkdir(exist_ok=True)
    bank = json.loads(TASKS.read_text(encoding="utf-8"))

    urls = sorted({t["content"]["image"]
                   for v in bank["variants"] for t in v["tasks"]
                   if "image" in t["content"]})
    print(f"Корень пакета: {PACKAGE_DIR}")
    print(f"Найдено уникальных изображений: {len(urls)}")

    ok, failed = 0, []
    for url in urls:
        dest = MEDIA_DIR / local_name(url)
        if dest.exists() and dest.stat().st_size > 0:
            ok += 1
            continue
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            dest.write_bytes(r.content)
            ok += 1
            print(f"  [ok] {url} -> media/{dest.name} ({len(r.content)//1024} KB)")
        except Exception as e:
            failed.append(url)
            print(f"  [FAIL] {url}: {e}")

    for v in bank["variants"]:
        for t in v["tasks"]:
            img = t["content"].get("image")
            if img and img.startswith("http"):
                t["content"]["image"] = f"media/{local_name(img)}"
    TASKS.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")

    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        sha = hashlib.sha256(TASKS.read_bytes()).hexdigest()
        m.setdefault("components", {}).setdefault("tasks.json", {})
        m["components"]["tasks.json"]["sha256"] = sha
        m["components"]["media/"] = {
            "mandatory": False,
            "note": f"локальные копии изображений ({ok} файлов), пакет работает офлайн",
        }
        MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nГотово: {ok}/{len(urls)} изображений локально, {len(failed)} не скачалось.")
    if failed:
        print("Не скачались (остались внешние ссылки):")
        for u in failed:
            print("  -", u)
    print("Перезапусти: streamlit run app.py")


if __name__ == "__main__":
    main()
