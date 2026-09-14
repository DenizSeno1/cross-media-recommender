"""pusula_dogrula — donmus HyDE denetimi. LLM YOK, model YOK, ag YOK.

Kosum:  python testler/test_pusula.py      (cikis kodu 0 = gecti)

NE OLCUYOR: eval.pusula_dogrula'nin eksik cache'i SAYDIGINI ve dogru
durumlarda SUSTUGUNU. Gercek cache/hyde/ dizinine BAKMIYOR — gecici bir
dizin kurup config.HYDE_CACHE'i oraya cevirerek olcuyor, yoksa test
deponun o anki cache durumuna gore geciyor/kaliyor olurdu.

Neden gerekli: denetimin kendisi "sessiz hata" yakalamak icin yazildi.
Denetim sessizce bozulursa yakalayacak sey kalmaz.
"""
import os, sys, tempfile, types
from pathlib import Path

os.environ["GEMINI_API_KEY"] = "test-anahtari-degil"     # gercek anahtar OKUNMUYOR
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # testler/ -> repo koku


class Sahte:
    """Her niteligi ve her cagrisi yine kendisini doner; bool() -> False."""
    def __getattr__(self, ad): return Sahte()
    def __call__(self, *a, **k): return Sahte()
    def __bool__(self): return False


def _sahte_modul(ad):
    m = types.ModuleType(ad)
    m.__getattr__ = lambda a: Sahte()
    return m


for ad in ["sentence_transformers", "torch", "numpy", "sklearn", "sklearn.cluster",
           "dotenv", "requests", "google", "google.genai"]:
    sys.modules.setdefault(ad, _sahte_modul(ad))

import config, eval, retrieval        # noqa: E402  (sahtelemeden SONRA)

N = 1
SORGULAR = [("birinci sorgu", [("anime", 1)]),
            ("ikinci sorgu", [("anime", 2)]),
            ("ucuncu sorgu", [("anime", 3)])]

gecici = tempfile.mkdtemp(prefix="pusula-testi-")
config.HYDE_CACHE = Path(gecici)          # _hyde_cache_yolu bunu CAGRI ANINDA okuyor
config.HYDE_AKTIF = True


def _cache_yaz(sorgu):
    yol = retrieval._hyde_cache_yolu(sorgu, N)
    yol.write_text('["sahte sinopsis"]', encoding="utf-8")


# --- 1) hicbiri donmus degil -> hepsi eksik sayilmali ---
eksik = eval.pusula_dogrula(SORGULAR, hyde_n=N)
assert eksik == 3, eksik

# --- 2) biri donunca eksik 2'ye dusmeli ---
_cache_yaz("birinci sorgu")
eksik = eval.pusula_dogrula(SORGULAR, hyde_n=N)
assert eksik == 2, eksik

# --- 3) hepsi donunca 0 ve "dogrulandi" satiri ---
_cache_yaz("ikinci sorgu")
_cache_yaz("ucuncu sorgu")
eksik = eval.pusula_dogrula(SORGULAR, hyde_n=N)
assert eksik == 0, eksik

# --- 4) n DEGISINCE cache anahtari da degisir -> hepsi yeniden eksik ---
#     Bu sessiz hatanin ta kendisi: --hyde-n 5 ile kosan biri n=1 cache'ini
#     kullandigini sanabilir. Anahtar (prompt, n, sorgu) uclusu; n degisti, pusula degisti.
assert eval.pusula_dogrula(SORGULAR, hyde_n=5) == 3

# --- 5) --no-cache BILEREK taze cekilis -> uyarilmamali ---
assert eval.pusula_dogrula(SORGULAR, hyde_n=5, hyde_cache=False) == 0

# --- 6) HyDE kapaliysa ortada pusula yok -> uyarilmamali ---
config.HYDE_AKTIF = False
assert eval.pusula_dogrula(SORGULAR, hyde_n=5) == 0
config.HYDE_AKTIF = True

print("")
print("GECTI:")
print("  - eksik donmus pusula dogru sayiliyor (3 / 2 / 0)")
print("  - hyde_n degisince anahtar da degisiyor (n=5 -> 3 eksik)")
print("  - --no-cache ve HYDE_AKTIF=False durumlarinda susuyor")
