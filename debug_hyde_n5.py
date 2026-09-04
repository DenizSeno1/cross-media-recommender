"""PILOT: cok-orneklemli HyDE (N=5, ortalama vektor) - flash-lite baseline (N=1) ile
karsilastir. Ayni ALTIN_SET, ayni corpus, TEK degisken: hyde_n.

Baseline (N=1, bu oturumda olculdu): top-50'de bulunan 6/11
(KACTI: Frieren, Higurashi, Re:Zero, Kusuriya, JoJo)
"""
import sys
from pathlib import Path

import retrieval  # once gun12_15'in kendi config/llm'i cache'e girsin

sys.path.append(str(Path(__file__).resolve().parents[1] / "faz4_gun3_4"))
from gun3_4_rag import ALTIN_SET

model, V, corpus, belgeler = retrieval._hazirla()

bulunan_sayisi = 0
for sorgu, beklenen in ALTIN_SET:
    sonuc = retrieval.getir(sorgu, k=50, medya=None, rerank=False, hyde_n=5)
    gelen_idler = [r["idMal"] for r in sonuc if r["media"] == "anime"]
    bulundu = any(b in gelen_idler for b in beklenen)
    bulunan_sayisi += bulundu

    durum = "BULUNDU" if bulundu else "KACTI  "
    print(f"[{durum}] sorgu: {sorgu}")

print(f"\ntop-50'de bulunan: {bulunan_sayisi}/{len(ALTIN_SET)}  (N=1 baseline: 6/11)")
print(f"\nLLM maliyeti: {retrieval.llm.sayac.ozet()}")
