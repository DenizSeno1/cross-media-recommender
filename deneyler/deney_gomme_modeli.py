"""Gomme modeli degisince URUNUN getirdigi liste ne kadar degisiyor? — 2026-09-16.

SPEC (Deniz): uc model (e5-large, e5-base, bge-m3) x HyDE acik/kapali x rerank acik/kapali
= 12 hucre. Kolonlar: isabet@5, recall@50, MRR, skor bandi (BETIMLEYICI), sure; kirilim
toplam + anime/film/kitap. Hepsi urunun kendi getir() yolundan (A13).

NEDEN HER MODEL AYRI SUREC: retrieval modeli, index'i ve onekleri modul duzeyinde
singleton'da tutuyor. Ayni surecte model degistirmek vektorleri bir modelden, sorgu
vektorunu digerinden alir — patlamaz, yanlis olcer. retrieval.model_dogrula bunu
yakalayip raise ediyor; bu dosya ona gore kurulu.

KABUL KAPISI: e5-large surecinde IKI HUCRE once kosar ve kayitli sayilari BIREBIR uretmek
zorunda. Uretmezse kosu hatali sayilir, diger hucreler kosmaz ve karsilastirma yapilmaz.
    HyDE acik   + rerank kapali -> isabet@5 0.383 (23/60) · recall@50 0.700 · MRR 0.321  (09-14)
    HyDE kapali + rerank kapali -> isabet@5 0.250         · recall@50 0.567              (09-15)
Bu ayni zamanda onek degisikliginin (config.ONEKLER) e5'in davranisini bozmadiginin kanitidir.

AJAN DONGUSU BU DENEYE GIRMEZ: ajanin yazdigi sorgularin HyDE ciktisi cache'te yok, girdi
donmus olmaz.

Kosum:
    python deneyler/deney_gomme_modeli.py --hepsi         # uc model ayri sureclerde + karsilastirma
    python deneyler/deney_gomme_modeli.py --model BAAI/bge-m3
    python deneyler/deney_gomme_modeli.py --karsilastir   # diskteki sonuclardan
    python deneyler/deney_gomme_modeli.py --hepsi --devam # kesintiden sonra: bitenleri atla
"""

import argparse
import contextlib
import hashlib
import io
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))  # deneyler/ -> repo koku

import numpy as np  # noqa: E402

import config  # noqa: E402
import eval as ev  # noqa: E402
import retrieval  # noqa: E402

MODELLER = ["intfloat/multilingual-e5-large", "intfloat/multilingual-e5-base", "BAAI/bge-m3"]
TABAN_MODEL = MODELLER[0]
MEDYALAR = ("anime", "film", "kitap")
SONUC = config.VERI / "gomme_modeli.json"

# Sabit kalanlar (urun varsayilanlari). config'e guvenilmiyor, ACIK veriliyor: config'in
# varsayilani bir gun degisirse deney sessizce baska bir konfigu olcmesin.
ORTAK = dict(hyde_cache=True, kota=True, tekillestir=True, franchise=True)
PUSULA = dict(hyde_n=1, cipa=0.0)

# (hyde, rerank). Sira bilincli: kabul hucreleri ONCE (kapi erken kapansin); rerank'li
# hucreler EN SON (reranker ~2.3GB VRAM'e bir kez girince index gommesiyle yarismasin).
KABUL_HUCRELERI = [(True, False), (False, False)]
RERANK_HUCRELERI = [(True, True), (False, True)]

# Kayitli sayilar. Karsilastirma 3 ondalikta — kayit o hassasiyette tutulmus.
KABUL = {
    (True, False): {"isabet@5_sayi": 23, "isabet@5": 0.383, "recall@50": 0.700, "MRR": 0.321},
    (False, False): {"isabet@5": 0.250, "recall@50": 0.567},
}

# Sayilarin HANGI koddan ciktigi. Commit tek basina yetmez: calisma agaci kirliyken hash
# olculen kodu gostermez.
KAYNAKLAR = ["config.py", "retrieval.py", "eval.py", "veri.py", "profil.py",
             "deneyler/deney_gomme_modeli.py"]


# ------------------------------------------------------------------ saf yardimcilar
# (testler/test_gomme_modeli.py bunlari numpy'siz, modelsiz kosturuyor)

def bant_ozeti(skorlar) -> dict:
    """min / medyan / maks. Saf Python: testler numpy'yi sahteliyor. Bos dizi -> ValueError."""
    degerler = [float(x) for x in skorlar]
    if not degerler:
        raise ValueError("bos skor dizisi: bant tanimsiz")
    return {"min": min(degerler), "medyan": statistics.median(degerler), "maks": max(degerler)}


def hukum(p: float) -> str:
    return "gercek fark (p<0.05)" if p < 0.05 else "gurultuden ayirt edilemiyor"


def isabet_isaret_testi(isabet_a: list, isabet_b: list) -> dict:
    """isabet@5 icin isaret testi: YALNIZ BIRINDE isabet olan sorgular sayilir.

    eval.isaret_testi'ne sira listesi gibi verilir — isabet -> 1, iska -> None. Ikisi de
    isabet (1 == 1) ya da ikisi de iska (None == None) BERABERE sayilir ve testten duser;
    istatistik ikinci kez yazilmiyor."""
    if len(isabet_a) != len(isabet_b):
        raise ValueError(f"uzunluklar farkli: {len(isabet_a)} != {len(isabet_b)}")
    return ev.isaret_testi([1 if h else None for h in isabet_a],
                           [1 if h else None for h in isabet_b])


def anahtar(model_adi: str, hyde: bool, rerank: bool | None = None) -> str:
    kisa = model_adi.split("/")[-1]
    return f"{kisa}|hyde={int(hyde)}" + ("" if rerank is None else f"|rerank={int(rerank)}")


# ------------------------------------------------------------------ kayit
def _git(*argumanlar) -> str:
    # rstrip, strip DEGIL: porcelain satiri " M config.py" boslukla basliyor. strip() ilk satirin
    # boslugunu da yiyordu -> s[3:] "onfig.py" veriyordu (09-16 kosusunun ilk 3 hucresinde kayitli).
    return subprocess.run(["git", *argumanlar], cwd=KOK, capture_output=True,
                          text=True).stdout.rstrip()


def kaynak_izi() -> dict:
    return {
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "kirli_kaynaklar": [s[3:] for s in
                            _git("status", "--porcelain", "--", *KAYNAKLAR).splitlines()],
        "kaynak_imzalari": {k: hashlib.sha1((KOK / k).read_bytes()).hexdigest()[:10]
                            for k in KAYNAKLAR},
    }


def _yukle() -> dict:
    if SONUC.exists():
        return json.loads(SONUC.read_text(encoding="utf-8"))
    return {"hucreler": {}, "bantlar": {}, "index_gomme": {}, "karsilastirmalar": []}


def _yaz(sonuc: dict) -> None:
    SONUC.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ on kontrol
def on_kontrol() -> None:
    """Kosu baslamadan: cihaz + donmus pusula + gold. Hepsi DURDURUR, uyarip devam etmez.

    pusula_dogrula HyDE KAPALIYKEN hicbir seyi kontrol etmeden 0 doner ("pusula yok ki donmus
    olsun"). O yuzden burada HYDE_AKTIF=True iken cagriliyor — HyDE-kapali bir hucrenin
    ortasinda cagrilsaydi yesil yanar, yanlis seyi kontrol ederdi."""
    if retrieval.CIHAZ != "cuda":
        raise SystemExit(f"CIHAZ={retrieval.CIHAZ!r}, 'cuda' degil — spec GPU istiyor. Kosu durdu.")
    n = len(ev.ALTIN_SET)
    onceki = config.HYDE_AKTIF
    config.HYDE_AKTIF = True
    try:
        eksik = ev.pusula_dogrula(ev.ALTIN_SET, hyde_n=PUSULA["hyde_n"],
                                  hyde_cache=ORTAK["hyde_cache"])
    finally:
        config.HYDE_AKTIF = onceki
    if eksik:
        raise SystemExit(f"donmus pusula {n - eksik}/{n}, {n}/{n} degil — kosu DURDU. "
                         f"Girdi donmus degilse iki kosu ayni sonucu vermez.")
    ev.gold_dogrula()


def model_kimligi(model, belgeler) -> dict:
    """Her hucrenin basinda basilan kimlik. Degerler MODELIN KENDISINDEN okunur."""
    retrieval.model_dogrula(model)                  # uyusmazsa RAISE
    return {
        "model": model.model_card_data.base_model,
        "index_dosyasi": retrieval._index_yolu(belgeler).name,
        "onek": list(config.onekler(config.BI_MODEL)),
        "max_seq_length": model.max_seq_length,
        "cihaz": retrieval.CIHAZ,
    }


# ------------------------------------------------------------------ olcumler
def _sira_topla(sorgular: list) -> dict:
    n = len(sorgular)
    return {
        "n": n,
        "isabet@5_sayi": int(sum(x["isabet@5"] for x in sorgular)),
        "isabet@5": sum(x["isabet@5"] for x in sorgular) / n,
        "recall@50": sum(x["recall@50"] for x in sorgular) / n,
        "MRR": sum(x["MRR"] for x in sorgular) / n,
        "getir_sn_medyan": statistics.median(x["getir_sn"] for x in sorgular),
    }


def hucre_kos(model, hyde: bool, rerank: bool) -> dict:
    """Bir hucre: 60 sorgunun her biri icin urun yolundan isabet@5, recall@50, MRR, sira.

    Hazir araclar SORGU BASINA cagriliyor (tek elemanli altin set): toplamlari zaten
    veriyorlar, ama isaret testi sorgu basina sonuc istiyor. Toplamlar ayni sirayla
    toplanip bolundugu icin eval.degerlendir'in tek seferde bastigi sayiyla birebir ayni."""
    config.HYDE_AKTIF = hyde
    _, _, corpus, belgeler = retrieval._hazirla()
    kimlik = model_kimligi(model, belgeler)
    print(f"\n=== {anahtar(config.BI_MODEL, hyde, rerank)} ===")
    print("  " + "  ".join(f"{k}={v}" for k, v in kimlik.items()))

    getir_ayar = dict(rerank=rerank, **PUSULA)

    # Isitma: ilk cagri tembel yuklemeleri (reranker, franchise tablosu) tetikliyor, sure
    # olcumune binmesin. Donmus pusulali bir gold sorgusu -> LLM cagrisi yok.
    with contextlib.redirect_stdout(io.StringIO()):
        ev.isabet_at_k([ev.ALTIN_SET[0]], k_listesi=(5,), **ORTAK, **getir_ayar)

    sorgular, konfig_satiri = [], None
    for no, girdi in enumerate(ev.ALTIN_SET):
        tek = [girdi]
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            t0 = time.perf_counter()
            isabet = ev.isabet_at_k(tek, k_listesi=(5,), **ORTAK, **getir_ayar)["isabet@5"]
            sure = time.perf_counter() - t0
            havuz = ev.degerlendir(tek, k_listesi=(50,), urun=False, **ORTAK, **getir_ayar)
            sira = ev.siralar(tek, k=50, franchise=ORTAK["franchise"],
                              hyde_cache=ORTAK["hyde_cache"], kota=ORTAK["kota"],
                              tekillestir=ORTAK["tekillestir"], **getir_ayar)[0]
        if konfig_satiri is None:
            konfig_satiri = next(s for s in tampon.getvalue().splitlines()
                                 if s.startswith("konfig:"))
        # Ayni girdi iki cagrida ayni sirayi vermeli (tek gold: MRR = 1/sira). Vermiyorsa
        # "donmus girdi" varsayimi bozuk demektir ve kabul kapisi anlamsizlasir.
        if havuz["MRR"] != (1.0 / sira if sira else 0.0):
            raise RuntimeError(f"sorgu {no}: degerlendir MRR={havuz['MRR']} ama siralar "
                               f"sira={sira} — ayni girdi iki cagrida farkli sonuc verdi")
        (medya, _), = girdi[1]              # her sorguda TEK gold (60/60, 2026-09-16)
        sorgular.append({"no": no, "medya": medya, "isabet@5": isabet,
                         "recall@50": havuz["recall@50"], "MRR": havuz["MRR"],
                         "sira": sira, "getir_sn": sure})

    ozet = {"toplam": _sira_topla(sorgular),
            **{m: _sira_topla([x for x in sorgular if x["medya"] == m]) for m in MEDYALAR}}
    print(f"  {konfig_satiri}")
    print(f"  {'':<7} {'isabet@5':>14} {'recall@50':>10} {'MRR':>7} {'getir sn (medyan)':>18}")
    for ad in ("toplam", *MEDYALAR):
        o = ozet[ad]
        print(f"  {ad:<7} {o['isabet@5']:>6.3f} ({o['isabet@5_sayi']:>2}/{o['n']}) "
              f"{o['recall@50']:>10.3f} {o['MRR']:>7.3f} {o['getir_sn_medyan']:>18.3f}")

    return {"model": config.BI_MODEL, "hyde": hyde, "rerank": rerank, "kimlik": kimlik,
            "konfig": konfig_satiri, **ozet, "sorgular": sorgular, **kaynak_izi()}


def kabul_denetle(hucre: dict) -> dict:
    beklenen = KABUL[(hucre["hyde"], hucre["rerank"])]
    satirlar, tamam = {}, True
    for olcu, deger in beklenen.items():
        gercek = hucre["toplam"][olcu]
        esit = gercek == deger if isinstance(deger, int) else round(gercek, 3) == deger
        tamam &= esit
        satirlar[olcu] = {"beklenen": deger, "gercek": gercek, "esit": esit}
    print("  KABUL: " + "  ".join(
        f"{o} {s['gercek'] if isinstance(s['beklenen'], int) else round(s['gercek'], 3)}"
        f"{'✓' if s['esit'] else '✗ (beklenen ' + str(s['beklenen']) + ')'}"
        for o, s in satirlar.items()) + f"  -> {'GECTI' if tamam else 'GECMEDI'}")
    return {"tamam": tamam, "olculer": satirlar}


def index_gomme_suresi(model, belgeler) -> dict:
    """12104 kaydi TAZE gom, sureyi olc. Urun cache'ine YAZMAZ: vektorler gecici dizine gider.

    Olculen cagri urunun kendisi (retrieval._gom). Isitma: once kucuk bir parca gomulur ki
    CUDA cekirdek hazirligi ilk modelin olcumune binmesin — modeller arasi adil olsun.
    Kirilim YOK: urun 12104 kaydi TEK cagrida gomuyor; medya basina bolmek baska bir
    cagriyi olcmek olurdu."""
    retrieval._gom(belgeler[:64], model)
    t0 = time.perf_counter()
    V = retrieval._gom(belgeler, model)
    sure = time.perf_counter() - t0
    with tempfile.TemporaryDirectory(prefix="gomme-modeli-") as dizin:
        yol = Path(dizin) / f"V_taze_{config.BI_MODEL.split('/')[-1]}.npy"
        np.save(yol, V)
        print(f"  index gomme: {len(belgeler)} kayit, {sure:.1f} sn -> {yol} (gecici)")
    return {"model": config.BI_MODEL, "kayit": len(belgeler), "sure_sn": sure,
            "sekil": list(V.shape), **kaynak_izi()}


def _gold_satirlari(corpus) -> dict:
    """(medya, id) -> corpus satiri. Ad-alani eval._gold_kayit'in ayni: anime idMal, digerleri id."""
    return {(m["media"], m["idMal"] if m["media"] == "anime" else m["id"]): i
            for i, m in enumerate(corpus)}


def _bant_topla(sorgular: list) -> dict:
    return {k: statistics.median(x[k] for x in sorgular)
            for k in ("min", "medyan", "maks", "hedef_skor", "hedef_ham_sira")}


def skor_bandi(model, V, corpus, hyde: bool) -> dict:
    """BETIMLEYICI — kazanani SECMEZ. Yalniz bi-encoder skorlari, rerank'tan bagimsiz.

    (a) her sorgunun 12104 skorunun min / medyan / maksi -> 60 sorgunun medyani
    (b) hedefin kendi skoru ve MASKESIZ ham sirasi (12104 icinde, 1 = en yuksek skor;
        esitlikte hedef lehine)
    Pusula urunun kendisinden: retrieval._pusula."""
    config.HYDE_AKTIF = hyde
    satir = _gold_satirlari(corpus)
    sorgular = []
    for no, (sorgu, beklenen) in enumerate(ev.ALTIN_SET):
        q, _ = retrieval._pusula(sorgu, model, PUSULA["hyde_n"], ORTAK["hyde_cache"],
                                 PUSULA["cipa"])
        s = V @ q
        (medya, gid), = beklenen
        i = satir[(medya, gid)]
        sorgular.append({"no": no, "medya": medya, **bant_ozeti(s),
                         "hedef_skor": float(s[i]),
                         "hedef_ham_sira": int((s > s[i]).sum()) + 1})
    return {"model": config.BI_MODEL, "hyde": hyde, "toplam": _bant_topla(sorgular),
            **{m: _bant_topla([x for x in sorgular if x["medya"] == m]) for m in MEDYALAR},
            "sorgular": sorgular, **kaynak_izi()}


# ------------------------------------------------------------------ surec: tek model
def model_kos(model_adi: str, devam: bool = False) -> None:
    """devam=True: JSON'da ZATEN olan index/bant/rerank hucresi atlanir (kesintiden sonra).
    Kabul hucreleri HER ZAMAN yeniden kosar: ucuzlar (~1 dk) ve kod degistiyse kapinin
    yeni kodla da gectigini gosteren tek kanit onlar."""
    if model_adi not in MODELLER:
        raise SystemExit(f"bilinmeyen model {model_adi!r}; bu deneyin modelleri: {MODELLER}")
    config.BI_MODEL = model_adi                 # retrieval._hazirla'dan ONCE; surecte bir daha degismez
    config.onekler(model_adi)                   # tabloda yoksa model YUKLENMEDEN raise
    on_kontrol()

    model, V, corpus, belgeler = retrieval._hazirla()
    sonuc = _yukle()

    for hyde, rerank in KABUL_HUCRELERI:
        hucre = hucre_kos(model, hyde, rerank)
        if model_adi == TABAN_MODEL:
            hucre["kabul"] = kabul_denetle(hucre)
        sonuc["hucreler"][anahtar(model_adi, hyde, rerank)] = hucre
        _yaz(sonuc)
        if model_adi == TABAN_MODEL and not hucre["kabul"]["tamam"]:
            raise SystemExit(f"KABUL GECMEDI ({anahtar(model_adi, hyde, rerank)}): kayitli sayilar "
                             f"uretilmedi. Kosu hatali, diger hucreler KOSMADI. Bkz. {SONUC}")

    # Bir kayit JSON'a yalnizca TAMAMLANINCA yaziliyor (_yaz her adimin sonunda) -> varsa bitmistir.
    def atla(bolum, anah):
        if devam and anah in sonuc[bolum]:
            print(f"devam: {bolum}/{anah} JSON'da var ({sonuc[bolum][anah]['tarih']}), atlandi")
            return True
        return False

    if not atla("index_gomme", model_adi):
        sonuc["index_gomme"][model_adi] = index_gomme_suresi(model, belgeler)
        _yaz(sonuc)

    for hyde in (True, False):
        if atla("bantlar", anahtar(model_adi, hyde)):
            continue
        bant = skor_bandi(model, V, corpus, hyde)
        sonuc["bantlar"][anahtar(model_adi, hyde)] = bant
        _yaz(sonuc)

    for hyde, rerank in RERANK_HUCRELERI:
        if atla("hucreler", anahtar(model_adi, hyde, rerank)):
            continue
        sonuc["hucreler"][anahtar(model_adi, hyde, rerank)] = hucre_kos(model, hyde, rerank)
        _yaz(sonuc)

    print(f"\n{model_adi}: 4 hucre + 2 bant + index gomme -> {SONUC}")


# ------------------------------------------------------------------ karsilastirma
def karsilastir_hepsi() -> None:
    sonuc = _yukle()
    hucreler = sonuc["hucreler"]

    # Kabul gecmediyse diger hucreler YORUMLANMAZ (spec).
    kabul = [hucreler.get(anahtar(TABAN_MODEL, h, r), {}).get("kabul", {}).get("tamam")
             for h, r in KABUL_HUCRELERI]
    if not all(kabul):
        raise SystemExit(f"kabul hucreleri gecmemis ya da yok ({kabul}) — hucreler yorumlanmaz.")

    print("\n" + "=" * 100)
    print("SIRA (urun yolu) — kirilim: toplam | anime | film | kitap")
    print(f"{'hucre':<42} {'isabet@5':>13} {'recall@50':>10} {'MRR':>7} {'getir sn':>9}   "
          f"{'isabet@5  A / F / K':>22}")
    for hyde, rerank in KABUL_HUCRELERI + RERANK_HUCRELERI:
        for model_adi in MODELLER:
            h = hucreler.get(anahtar(model_adi, hyde, rerank))
            if not h:
                continue
            t = h["toplam"]
            print(f"{anahtar(model_adi, hyde, rerank):<42} {t['isabet@5']:.3f} ({t['isabet@5_sayi']:>2}/60)"
                  f" {t['recall@50']:>10.3f} {t['MRR']:>7.3f} {t['getir_sn_medyan']:>9.3f}   "
                  + " / ".join(f"{h[m]['isabet@5']:.2f}" for m in MEDYALAR))

    print("\nSKOR BANDI — BETIMLEYICI, KAZANANI SECMEZ (yalniz bi-encoder, rerank'tan bagimsiz;"
          " 60 sorgunun medyani)")
    print(f"{'model|hyde':<34} {'min':>7} {'medyan':>7} {'maks':>7} {'hedef skor':>11} {'hedef ham sira':>15}")
    for anah, b in sonuc["bantlar"].items():
        t = b["toplam"]
        print(f"{anah:<34} {t['min']:>7.4f} {t['medyan']:>7.4f} {t['maks']:>7.4f} "
              f"{t['hedef_skor']:>11.4f} {t['hedef_ham_sira']:>15.1f}")

    print("\nINDEX GOMME (12104 kayit, taze, tek cagri)")
    for model_adi, g in sonuc["index_gomme"].items():
        print(f"  {model_adi:<34} {g['sure_sn']:>8.1f} sn   sekil {g['sekil']}")

    print("\nGERCEK FARK KURALI — isabet@5: yalniz birinde isabet olan sorgular · sira: "
          "karsilastir (k=50) · iki yonlu p < 0.05")
    karsilastirmalar = []
    for hyde, rerank in KABUL_HUCRELERI + RERANK_HUCRELERI:
        for ma, mb in combinations(MODELLER, 2):
            ha, hb = hucreler.get(anahtar(ma, hyde, rerank)), hucreler.get(anahtar(mb, hyde, rerank))
            if not (ha and hb):
                continue
            ti = isabet_isaret_testi([x["isabet@5"] == 1.0 for x in ha["sorgular"]],
                                     [x["isabet@5"] == 1.0 for x in hb["sorgular"]])
            rapor = io.StringIO()
            with contextlib.redirect_stdout(rapor):
                ts, delta = ev.karsilastir_siralar(ma, [x["sira"] for x in ha["sorgular"]],
                                                   mb, [x["sira"] for x in hb["sorgular"]],
                                                   ev.ALTIN_SET)
            ad = f"hyde={int(hyde)} rerank={int(rerank)}  {ma.split('/')[-1]} -> {mb.split('/')[-1]}"
            print(f"  {ad:<60} isabet@5: {ti['yukari']}v{ti['asagi']} p={ti['p']:.3f} {hukum(ti['p']):<27}"
                  f" | sira: {ts['yukari']}v{ts['asagi']} p={ts['p']:.3f} {hukum(ts['p'])}")
            karsilastirmalar.append({"hyde": hyde, "rerank": rerank, "a": ma, "b": mb,
                                     "isabet@5": {**ti, "hukum": hukum(ti["p"])},
                                     "sira": {**ts, "hukum": hukum(ts["p"]), "delta_sira": delta},
                                     "rapor": rapor.getvalue()})
    sonuc["karsilastirmalar"] = karsilastirmalar
    _yaz(sonuc)
    print(f"\n-> {SONUC}")


def hepsi(devam: bool = False) -> None:
    if SONUC.exists() and not devam:            # eski sonuc SILINMEZ, yedeklenir
        yedek = SONUC.with_suffix(f".{datetime.now():%Y%m%d-%H%M%S}.json")
        SONUC.rename(yedek)
        print(f"onceki sonuc yedeklendi: {yedek.name}")
    for model_adi in MODELLER:
        # -u: alt surecin ciktisi dosyaya tamponlanmadan dussun (yoksa log saatlerce geride kaliyor)
        kod = subprocess.call([sys.executable, "-u", __file__, "--model", model_adi]
                              + (["--devam"] if devam else []))
        if kod != 0:
            raise SystemExit(f"{model_adi} sureci {kod} ile cikti — sonraki modeller KOSMADI.")
    karsilastir_hepsi()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="gomme modeli karsilastirmasi (12 hucre)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hepsi", action="store_true", help="uc model ayri sureclerde + karsilastirma")
    g.add_argument("--model", choices=MODELLER, help="tek model, bu surecte")
    g.add_argument("--karsilastir", action="store_true", help="diskteki sonuclardan karsilastir")
    ap.add_argument("--devam", action="store_true",
                    help="kesintiden sonra: JSON'da biten index/bant/rerank hucresini atla")
    a = ap.parse_args()
    if a.devam and a.karsilastir:
        ap.error("--devam yalnizca --hepsi ve --model ile anlamli")
    if a.hepsi:
        hepsi(a.devam)
    elif a.model:
        model_kos(a.model, a.devam)
    else:
        karsilastir_hepsi()
