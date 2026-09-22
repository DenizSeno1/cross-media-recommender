"""Gomme modeli deneyi — kabul testleri. LLM YOK, model YOK, ag YOK.

Kosum:  python testler/test_gomme_modeli.py      (cikis kodu 0 = gecti)

VAKALARI DENIZ SECTI (spec 2026-09-16, bolum 5). Kod mentordan. Bu dosya kodun spec'e
UYDUGUNU dogrular; deneyin sayilarinin dogrulugunu degil — o, kabul kapisinin isi
(e5-large'in kayitli iki hucresini birebir uretmek).
"""
import os, sys, types
from pathlib import Path

os.environ["GEMINI_API_KEY"] = "test-anahtari-degil"     # gercek anahtar OKUNMUYOR
KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))                               # testler/ -> repo koku
sys.path.insert(0, str(KOK / "deneyler"))


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

import config, eval as ev, retrieval          # noqa: E402  (sahtelemeden SONRA)
import deney_gomme_modeli as dgm              # noqa: E402


def raise_eder(fonksiyon, *argumanlar, hata=Exception):
    try:
        fonksiyon(*argumanlar)
    except hata:
        return True
    return False


# --- 1) onek tablosu ---
assert config.onekler("intfloat/multilingual-e5-large") == ("query: ", "passage: ")
assert config.onekler("intfloat/multilingual-e5-base") == ("query: ", "passage: ")
assert config.onekler("BAAI/bge-m3") == ("", "")
#     sessizce e5 onekine DUSMEMELI
assert raise_eder(config.onekler, "sentence-transformers/all-MiniLM-L6-v2", hata=ValueError)


# --- 2) model uyusmazligi: yuklu model sahte nesneyle taklit ---
def sahte_model(ad):
    return types.SimpleNamespace(model_card_data=types.SimpleNamespace(base_model=ad))


config.BI_MODEL = "intfloat/multilingual-e5-large"
retrieval.model_dogrula(sahte_model("intfloat/multilingual-e5-large"))       # ayni -> sessiz
assert raise_eder(retrieval.model_dogrula, sahte_model("BAAI/bge-m3"), hata=RuntimeError)


# --- 3) pusula eksik -> kosu BASLAMAZ ---
retrieval.CIHAZ = "cuda"                        # cihaz kapisini gec, pusula kapisini olc
cagrilanlar = []
retrieval._hazirla = lambda: cagrilanlar.append("_hazirla")
ev.gold_dogrula = lambda *a, **k: cagrilanlar.append("gold_dogrula")
ev.pusula_dogrula = lambda *a, **k: 3           # 60'in 3'u eksik
try:
    dgm.model_kos("intfloat/multilingual-e5-large")
    raise AssertionError("pusula eksikken kosu basladi")
except SystemExit:
    pass
assert cagrilanlar == [], f"pusula eksikken bunlar cagrildi: {cagrilanlar}"


# --- 4) skor bandi ozeti ---
ozet = dgm.bant_ozeti([0.2, 0.5, 0.9])
assert ozet == {"min": 0.2, "medyan": 0.5, "maks": 0.9}, ozet
assert raise_eder(dgm.bant_ozeti, [], hata=ValueError)


# --- 5) isabet@5 isaret testi ---
def isabet_dizileri(yalniz_a, yalniz_b, ikisi=4, hicbiri=3):
    """Beraberlikler (ikisi / hicbiri) bilerek var: testten DUSMELILER."""
    a = [True] * yalniz_a + [False] * yalniz_b + [True] * ikisi + [False] * hicbiri
    b = [False] * yalniz_a + [True] * yalniz_b + [True] * ikisi + [False] * hicbiri
    return a, b


t = dgm.isabet_isaret_testi(*isabet_dizileri(8, 1))
assert (t["n"], t["berabere"]) == (9, 7), t
assert abs(t["p"] - 0.039) < 5e-4, t["p"]                  # 2 * 10/512 = 0.0390625
assert dgm.hukum(t["p"]) == "gercek fark (p<0.05)"

t = dgm.isabet_isaret_testi(*isabet_dizileri(13, 5))
assert (t["n"], t["berabere"]) == (18, 7), t
assert abs(t["p"] - 0.096) < 5e-4, t["p"]                  # 2 * 12616/262144 = 0.09625
assert dgm.hukum(t["p"]) == "gurultuden ayirt edilemiyor"

print("")
print("GECTI:")
print("  1 onek tablosu: e5-large/e5-base -> query/passage, bge-m3 -> bos, bilinmeyen -> raise")
print("  2 yuklu model config.BI_MODEL degilse raise, ayniysa sessiz")
print("  3 pusula eksikken kosu baslamiyor (_hazirla ve gold_dogrula cagrilmadi)")
print("  4 bant ozeti [0.2, 0.5, 0.9] -> 0.2 / 0.5 / 0.9, bos -> raise")
print(f"  5 isaret testi 8'e 1 -> p=0.039 fark var · 13'e 5 -> p=0.096 gurultu")
