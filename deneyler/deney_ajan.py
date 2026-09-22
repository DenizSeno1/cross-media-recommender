"""Faz 5'in asil olcumu: AJANLI vs AJANSIZ, ayni gold set. (2026-09-18)

SPEC (Deniz'in kararlariyla):
  soru      : dongu icinde cagirmak, getir-i bir kez cagirmaktan iyi mi?
  gold      : 60 vaka (20/20/20), donmus HyDE pusulasi, kota 3/1/1, e5-large
  kollar    : rerank KAPALI ve rerank ACIK — ayni kod, tek degisken config.RERANK_AKTIF
  ajanin listesi : dongu()["oneriler"] — modelin 'secilen' ile bildirdigi kayitlar
  slot      : model "en fazla 5, zayifi koyma" ile secer; liste uzunlugu da OLCULUR
              (5-e doldurmaya zorlamak isabet@5-i lehte sisirir, serbest birakip
               olcmemek esitsizligi gizler)

NEDEN IZ KAYDI (trace): ajan kosusu tekrarlanabilir DEGIL — model her turda sorguyu
yeniden yaziyor ve o sorgularin HyDE pusulasi cache-te yok, taze uyduruluyor. Sayinin
nereden geldigi ancak butun turlar diske yazilirsa denetlenebilir. Ayrica "ajanin
listesi" tanimi degisirse ayni iz yeniden puanlanir, 60 sorgu yeniden kosulmaz.

OLCULENLER (uc sayi, iki degil):
  isabet@5        : hedef ajanin NIHAI listesinde mi          <- urunun verdigi
  herhangi_tur    : hedef ajanin gordugu kayitlarin BIRINDE mi <- dongu yuzeye cikardi mi
  erken_durma     : gordu ama secmedi                          <- ajanin SECME kaybi
Taban (ajansiz) ayni gold-da olculu: rerank kapali 23/60, rerank acik 33/60.

HIZ SINIRI: Gemini free tier 15 RPM. Sorgu basina ~4-6 cagri (her tur 1 LLM + her
arama 1 HyDE). Kosu, sorgu basina yapilan cagri sayisina gore bekliyor; 14 Eylul-un
429-u bu yuzden geldi (eval sorgular ARASI hic beklemiyordu).

Kosum:
    python deneyler/deney_ajan.py --rerank-kapali
    python deneyler/deney_ajan.py --rerank-acik
    ... --devam   (yarida kalan kosuyu surdurur, biten sorgulari atlar)
"""

import argparse
import inspect
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config          # YALNIZCA config — agir modulleri main() ICINDE import ediyoruz

# NEDEN GEC IMPORT (2026-09-18, kosmadan once yakalandi):
#   retrieval.getir imzasi  ->  rerank: bool = config.RERANK_AKTIF
# Varsayilan argumanlar IMPORT ANINDA baglanir. retrieval bir kez import edildikten
# sonra config.RERANK_AKTIF'i degistirmek getir()'i etkilemez. Ajanin araci rerank
# parametresi gecmiyor (araclar._getir_kirp), yani tek kolu bu varsayilan — bayragi
# import'tan SONRA cevirseydik "rerank acik" kolu sessizce rerank KAPALI kosar ve
# tamamen makul bir sayi basardi. Gomme deneyi bu tuzaga dusmuyor cunku rerank'i
# acikca parametre olarak geciyor (deney_gomme_modeli.py:199); burada o yol yok.

CIKTI = Path(__file__).resolve().parents[1] / "data"
CAGRI_BASINA_SN = 4.5          # 15 RPM = 4 sn; 4.5 marjli (retrieval.py:203 ile ayni gerekce)


def rerank_dogrula(beklenen: bool) -> None:
    """getir()'in GERCEKTEN kullanacagi rerank degeri beklenen mi?

    Kimlik fonksiyonun KENDISINDEN okunuyor (baglanmis varsayilan arguman),
    config'ten degil: config'i config'le karsilastiran denetim hep yesil yanar.
    retrieval.model_dogrula ile ayni gerekce."""
    import retrieval
    gercek = inspect.signature(retrieval.getir).parameters["rerank"].default
    if gercek != beklenen:
        raise RuntimeError(
            f"getir()'in rerank varsayilani {gercek!r}, istenen {beklenen!r}. "
            f"config.RERANK_AKTIF retrieval import EDILMEDEN once ayarlanmali.")
    print(f"rerank dogrulandi: getir() varsayilani = {gercek}")


def _kimlikler(idxler, corpus, franchise=True):
    """corpus satir numaralarini gold ile kiyaslanabilir kimliklere cevirir.

    dongu 'oneriler'-i _getir_kirp bicimli kayit donduruyor (baslik/tur/aciklama);
    eval._kimlik ise HAM corpus kaydi istiyor (media/id/idMal). Koprü _idx: kaydin
    corpus icindeki satir numarasi. Kimligi _getir_kirp ciktisindan yeniden kurmak
    yerine ham kayda donuyoruz — ayni bilgiyi iki yerde tutmak sessizce desenkronize
    olur (retrieval.py'nin _idx'i tasima gerekcesiyle ayni)."""
    return {E._kimlik(corpus[i], franchise) for i in idxler}


def bir_sorgu(sorgu, hedefler, corpus):
    """Tek gold vakasi kosar, olculeri ve tam izi dondurur."""
    import dongu

    sayac0 = llm.sayac.cagri
    basla = time.perf_counter()
    try:
        sonuc = dongu.dongu(sorgu)
        hata = None
    except Exception as h:                       # kosu 60 vakanin 1'i yuzunden olmesin
        traceback.print_exc()
        sonuc = {"cevap": None, "oneriler": [], "turlar": [], "durma_sebebi": f"HATA: {type(h).__name__}"}
        hata = f"{type(h).__name__}: {h}"
    gecen = time.perf_counter() - basla
    cagri = llm.sayac.cagri - sayac0

    hedef_kimlik = {E._kimlik(E._gold_kayit(g), True) for g in hedefler}
    nihai_idx = [r["_idx"] for r in sonuc["oneriler"]]
    gorulen_idx = [i for t in sonuc["turlar"] for i in t.get("getirilen_idx", [])]

    nihai = _kimlikler(nihai_idx, corpus)
    gorulen = _kimlikler(gorulen_idx, corpus)
    isabet = bool(hedef_kimlik & nihai)
    herhangi = bool(hedef_kimlik & gorulen)

    return {
        "sorgu": sorgu,
        "hedef": [list(h) for h in hedefler],
        "medya": hedefler[0][0],
        "isabet@5": int(isabet),
        "herhangi_tur": int(herhangi),
        "erken_durma": int(herhangi and not isabet),
        "liste_uzunlugu": len(nihai_idx),
        "tur_sayisi": len(sonuc["turlar"]),
        "llm_cagri": cagri,
        "sure_sn": round(gecen, 2),
        "durma_sebebi": sonuc["durma_sebebi"],
        "uydurma_id": sum(t.get("uydurma_id", 0) for t in sonuc["turlar"]),
        "hata": hata,
        # --- iz: sayinin nereden geldigini gosteren ham kayit ---
        "cevap": sonuc["cevap"],
        "nihai_idx": nihai_idx,
        "turlar": [{k: t.get(k) for k in
                    ("no", "dusunce", "arac", "args", "secilen", "getirilen_idx",
                     "tekrar", "kapi_yeterli", "gonderilen_tok", "girdi_tok",
                     "cikti_tok", "sure_sn")}
                   for t in sonuc["turlar"]],
    }


def ozet(kayitlar):
    n = len(kayitlar)
    if not n:
        return
    top = lambda a: sum(k[a] for k in kayitlar)
    print(f"\n{'=' * 70}")
    print(f"AJANLI KOL — {n} sorgu · rerank {'ACIK' if config.RERANK_AKTIF else 'KAPALI'}")
    print(f"{'=' * 70}")
    print(f"  isabet@5        {top('isabet@5') / n:.3f}   ({top('isabet@5')}/{n})   <- ajanin NIHAI listesi")
    print(f"  herhangi turda  {top('herhangi_tur') / n:.3f}   ({top('herhangi_tur')}/{n})   <- dongu yuzeye cikardi mi")
    print(f"  erken durma     {top('erken_durma')}/{n}   <- gordu ama secmedi")
    print(f"  ortalama tur         {top('tur_sayisi') / n:.2f}")
    print(f"  ortalama liste uzunl {top('liste_uzunlugu') / n:.2f}   (taban her zaman 5)")
    print(f"  ortalama llm cagri   {top('llm_cagri') / n:.2f}")
    print(f"  ortalama sure        {top('sure_sn') / n:.1f} sn")
    hard = sum(1 for k in kayitlar if k["durma_sebebi"] == "hard_cap")
    hata = sum(1 for k in kayitlar if k["hata"])
    print(f"  hard cap {hard}/{n} · uydurma id {top('uydurma_id')} · hata {hata}/{n}")
    for m in ("anime", "film", "kitap"):
        alt = [k for k in kayitlar if k["medya"] == m]
        if alt:
            print(f"    {m:<6} isabet {sum(k['isabet@5'] for k in alt)}/{len(alt)}"
                  f" · herhangi {sum(k['herhangi_tur'] for k in alt)}/{len(alt)}")


def main():
    p = argparse.ArgumentParser(description="Faz 5: ajanli kol")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--rerank-acik", action="store_true")
    g.add_argument("--rerank-kapali", action="store_true")
    p.add_argument("--devam", action="store_true", help="yarida kalan kosuyu surdur")
    p.add_argument("--sinir", type=int, default=None, help="ilk N sorgu (deneme icin)")
    a = p.parse_args()

    # SIRA ONEMLI: once bayrak, SONRA agir import'lar (yukaridaki gec-import notu).
    config.RERANK_AKTIF = a.rerank_acik
    global E, llm, veri
    import eval as E
    import llm
    import veri
    rerank_dogrula(a.rerank_acik)

    ad = "acik" if a.rerank_acik else "kapali"
    yol = CIKTI / f"ajan_kolu_rerank_{ad}.json"

    E.gold_dogrula()                       # bozuk gold-da kosmanin anlami yok
    corpus = veri.corpus_yukle()

    kayitlar = []
    if a.devam and yol.exists():
        kayitlar = json.loads(yol.read_text(encoding="utf-8"))["sorgular"]
        # HATA ile dusen kayit "bitmis" degildir: 18 Eylul'de 429 alan 20 kitap sorgusu diskte
        # duruyordu, eski hali onlari atlayip eksik ozeti tamamlanmis gibi basacakti.
        hatali = [k for k in kayitlar if k["hata"]]
        kayitlar = [k for k in kayitlar if not k["hata"]]
        print(f"devam: {len(kayitlar)} sorgu diskte, atlanacak · {len(hatali)} hatali, yeniden kosacak")
    bitmis = {k["sorgu"] for k in kayitlar}

    gold = E.ALTIN_SET[:a.sinir] if a.sinir else E.ALTIN_SET
    for no, (sorgu, hedefler) in enumerate(gold, 1):
        if sorgu in bitmis:
            continue
        basla = time.perf_counter()
        llm.sayac.sifirla()                # kosu basi degil SORGU basi fatura
        k = bir_sorgu(sorgu, hedefler, corpus)
        kayitlar.append(k)
        sira = {s: i for i, (s, _) in enumerate(gold)}
        kayitlar.sort(key=lambda r: sira.get(r["sorgu"], len(sira)))   # dosya gold sirasinda kalsin
        print(f"  {no}/{len(gold)} {'✓' if k['isabet@5'] else ('~' if k['herhangi_tur'] else '·')}"
              f" tur={k['tur_sayisi']} liste={k['liste_uzunlugu']} cagri={k['llm_cagri']}"
              f" {k['durma_sebebi']:<8} {sorgu[:44]}", flush=True)

        yol.write_text(json.dumps({"rerank": a.rerank_acik, "kayit_sayisi": len(kayitlar),
                                   "sorgular": kayitlar}, ensure_ascii=False, indent=1),
                       encoding="utf-8")    # her sorgudan sonra: kesinti kayip demek olmasin

        # HIZ FRENI: bu sorgunun yaptigi cagri kadar bekle, gecen sureyi dus.
        borc = k["llm_cagri"] * CAGRI_BASINA_SN - (time.perf_counter() - basla)
        if borc > 0 and no < len(gold):
            time.sleep(borc)

    ozet(kayitlar)
    print(f"\niz: {yol}")


if __name__ == "__main__":
    main()
