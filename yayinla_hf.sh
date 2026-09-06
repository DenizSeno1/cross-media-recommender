#!/usr/bin/env bash
# Hugging Face Space'e yayin. main'i kirletmeden calisir:
# HF, Space kartini README.md'nin YAML frontmatter'indan okuyor; o frontmatter GitHub'da
# cirkin bir tablo olarak render ediliyor. Bu yuzden frontmatter SADECE hf-space
# dalinda duruyor, main temiz kaliyor.
#
# Ilk kullanimdan once:
#   git remote add hf https://huggingface.co/spaces/<KULLANICI>/capraz-medya-onerici
set -e

git checkout -B hf-space main

python - <<'PY'
from pathlib import Path
fm = """---
title: Capraz Medya Onerici
emoji: 🎬
colorFrom: indigo
colorTo: pink
sdk: streamlit
app_file: app.py
pinned: false
short_description: Anime, film ve kitabi tek vektor uzayinda arayan capraz-medya onerici
---

"""
p = Path("README.md")
s = p.read_text(encoding="utf-8")
if not s.startswith("---\ntitle:"):
    p.write_text(fm + s, encoding="utf-8")
    print("frontmatter eklendi")
else:
    print("frontmatter zaten var")
PY

git add README.md
git commit -q -m "HF Space frontmatter (sadece bu dalda)" || echo "degisiklik yok"
git push -f hf hf-space:main
git checkout main
echo "yayinlandi. Space'te GEMINI_API_KEY secret'inin tanimli oldugundan emin ol."
