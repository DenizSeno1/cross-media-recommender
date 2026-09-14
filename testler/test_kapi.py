"""dongu <-> kapi kablolamasi — LLM YOK, retrieval YOK, ag YOK.

Kosum:  python testler/test_kapi.py      (cikis kodu 0 = gecti)

NE OLCUYOR: kapi.yargila'nin dongu.py'ye dogru yerden baglandigini ve
--- en onemlisi --- kapinin akisi YONETMEDIGINI. Gun 5-6'da kapi bilerek
"sadece kayit" olarak baglandi; bu test o kararin kazara bozulmasini yakalar.
Kapinin KENDI dogrulugu burada olculmuyor (o Gun 9-10'un olcum isi), sadece
kablolama.

NEDEN SAHTE BAGIMLILIK: gercek hattı kosturmak model yuklemek + Gemini
faturasi demek. Test o yuzden agir modulleri import aninda sahteliyor;
boylece agsiz, GPU'suz, anahtarsiz makinede de kosuyor.
"""
import json, os, sys, types
from pathlib import Path

# llm.py import aninda anahtar ariyor. GERCEK ANAHTAR OKUNMUYOR: dotenv
# sahtelendigi icin .env yuklenmiyor, buraya kukla deger konuyor. Ag cagrisi
# da yok — llm.cagir asagida degistiriliyor.
os.environ["GEMINI_API_KEY"] = "test-anahtari-degil"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # testler/ -> repo koku


# --- agir bagimliliklari import ZAMANINDA sahtele ---
class Sahte:
    """Her niteligi ve her cagrisi yine kendisini doner; bool() -> False.

    Neden ozyinelemeli: retrieval.py import aninda torch.cuda.is_available()
    cagiriyor. Tek kademeli sahte tam orada kiriliyordu.
    """
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

# pydantic kurulu olmayabilir -> minimum stub. Tur'un DOGRULAMASI test edilmiyor;
# test edilen sey kapi kablolamasi.
if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kw):
            for a in type(self).__annotations__:
                setattr(self, a, kw.get(a, getattr(type(self), a, None)))

        def model_dump(self):
            return {a: getattr(self, a) for a in type(self).__annotations__}

    pd.BaseModel = BaseModel
    sys.modules["pydantic"] = pd

import dongu, llm, araclar        # noqa: E402  (sahtelemeden SONRA import sart)

# --- sahte model: 1. tur arama yapar, 2. tur cevap verir ---
CEVAPLAR = [
    json.dumps({"dusunce": "once arayayim", "arac": "ara",
                "args": {"sorgu": "psikolojik gerilim", "medya": "anime", "k": 2}}),
    json.dumps({"dusunce": "elimdekiler yeterli", "cevap": "Monster ve Death Note."}),
]
sirasi = iter(CEVAPLAR)
llm.cagir = lambda gecmis, temperature=None: next(sirasi)

# --- sahte arac: retrieval'i hic cagirmadan _getir_kirp bicimli kayit dondur ---
SAHTE = [
    {"baslik": "Monster", "tur": "anime", "link": "x", "_idx": 1, "_skor": 0.9,
     "aciklama": "Psikolojik gerilim, ahlaki ikilem, seri katil takibi."},
    {"baslik": "Death Note", "tur": "anime", "link": "y", "_idx": 2, "_skor": 0.8,
     "aciklama": "Dedektif ve katil arasinda psikolojik satranc."},
]
araclar.ARACLAR["ara"]["fonksiyon"] = lambda **kw: ("sahte gozlem metni", SAHTE)

sonuc = dongu.dongu("psikolojik gerilim", hard_cap=3)

print("durma sebebi :", sonuc["durma_sebebi"])
for t in sonuc["turlar"]:
    print(f"  tur {t['no']}: arac={t['arac']} "
          f"kapi_yeterli={t.get('kapi_yeterli', '- (alan yok)')}")
    if "kapi_gerekce" in t:
        print(f"          gerekce: {t['kapi_gerekce']}")

# --- beklentiler ---
t1, t2 = sonuc["turlar"][0], sonuc["turlar"][1]

# 1) Arama turunda kapi kaydi VAR.
assert "kapi_yeterli" in t1, "arama turunda kapi calismali"

# 2) Kati kural dogru isliyor: "gerilim" Death Note kaydinda gecmiyor -> yetersiz.
#    NOT: bu satiri yazarken once "yeterli olmali" diye assert etmistim, kod degil
#    BEKLENTI yanlisti. Kural "her kelime HER kayitta gecmeli" diyor.
assert t1["kapi_yeterli"] is False
assert "gerilim" in t1["kapi_gerekce"]

# 3) Cevap turunda yapisal kayit yok -> kapi alani da OLMAMALI.
assert "kapi_yeterli" not in t2, "cevap turunda kapi alani olmamali"

# 4) EN ONEMLISI: kapi "yetersiz" dedigi halde dongu AYNEN devam etti.
#    Bu assert duserse kapi sessizce akisi yonetmeye baslamis demektir.
assert sonuc["durma_sebebi"] == "cevap"
assert sonuc["cevap"] == "Monster ve Death Note."

print("")
print("GECTI:")
print("  - arama turunda kapi kaydi var, cevap turunda yok")
print("  - kapi YETERSIZ dedi AMA akis degismedi (durma_sebebi=cevap)")
