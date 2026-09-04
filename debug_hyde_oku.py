"""Debug arac - HyDE sahte belgesini OKU. gormeden teshis konmaz (fazin kurucu cumlesi).

Gun3-4 ALTIN_SET'teki her sorgu icin: sahte belgeyi uret, embed et, top-50'yi
kontrol et, BULUNDU/KACTI etiketiyle sahte belgeyi yazdir. Ozellikle KACTI
olanlara bak - pusula jenerik mi, sorguya ozgu mu?
"""
import sys
from pathlib import Path

import retrieval  # once gun12_15'in kendi config.py'si ile

sys.path.append(str(Path(__file__).resolve().parents[1] / "faz4_gun3_4"))
from gun3_4_rag import ALTIN_SET

model, V, corpus, belgeler = retrieval._hazirla()

for sorgu, beklenen in ALTIN_SET:
    sahte = retrieval._hyde_belge(sorgu)
    q = model.encode("query: " + sahte, normalize_embeddings=True)
    skorlar = V @ q
    aday_idx = skorlar.argsort()[::-1][:50]
    gelen_idler = [corpus[i]["idMal"] for i in aday_idx if corpus[i]["media"] == "anime"]
    bulundu = any(b in gelen_idler for b in beklenen)

    durum = "BULUNDU" if bulundu else "KACTI  "
    print(f"\n[{durum}] sorgu: {sorgu}")
    print(f"          sahte belge: {sahte}")
