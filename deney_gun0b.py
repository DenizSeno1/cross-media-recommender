"""Gun 0, ikinci kurulum: analiz birimi SORGU degil CEKILIS.

Neden degisti: kapi calisma aninda sorgulari siniflandirmiyor. Onune gelen sey
tek bir sonuc listesi — belirli bir HyDE cekilisinin urunu. Ayni sorgu iki
cekiliste tamamen farkli liste veriyor (canli gozlendi). Dogru soru:

    "AYNI sorgunun kotu cekilisinde bant, iyi cekilisindekinden dusuk mu?"

Bu kurulum iki sey kazandiriyor:
  1) sorgu-seviyesi karistiricilari (zorluk, uzunluk, medya) TAMAMEN yok eder —
     karsilastirma her sorgunun KENDI icinde yapiliyor
  2) gozlem sayisi 23 -> 23*TEKRAR

hyde_cache=False, bilerek: olculen sey cekilis varyansinin kendisi; dondurursak
olcecek bir sey kalmaz. Tekrarlanabilirlik icin ham satirlar diske yaziliyor.
"""

import json
import random
import time
from collections import Counter

import config
import eval as ev
import retrieval
import sinyaller

K = config.TOP_K
TEKRAR = 5
# config.VERI uzerinden: bare "data/..." cwd'ye gore cozuluyordu, yani kosuyu repo
# kokunun disindan baslatmak checkpoint'i gormemek (9 dk + 115 cagri bastan) ve ilk
# yazmada FileNotFoundError demekti — isi kaybetmemek icin yazilmis dosyada.
KAYIT = config.VERI / "gun0_cekilisler.json"
# Ucretsiz katman dakikada ~15 istek veriyor; 115 cagriyi ard arda atinca 429.
# 4.5 sn ara ~13 RPM -> kota altinda kalir. Toplam ~9 dk.
BEKLEME = 4.5


def olc(tekrar: int = TEKRAR, k: int = K):
    """Olcum KESILEBILIR: her sorgudan sonra diske yazilir, tekrar kosunca
    tamamlanmis sorgular atlanir. 429 kota hatasi 115 cagrilik bir kosuda
    kacinilmaz; is kaybolmasin diye boyle."""
    satirlar = json.loads(KAYIT.read_text(encoding="utf-8")) if KAYIT.exists() else []
    sayim = Counter(r["sorgu_no"] for r in satirlar)      # satir basina tam tarama yerine
    bitmis = {no for no, kac in sayim.items() if kac >= tekrar}

    for s, (sorgu, beklenen_ham) in enumerate(ev.ALTIN_SET, 1):
        if s in bitmis:
            print(f"  {s:2d}/{len(ev.ALTIN_SET)}  (atlandi)")
            continue
        satirlar = [r for r in satirlar if r["sorgu_no"] != s]   # yarim kalmisi at
        hedef = {ev._kimlik(ev._gold_kayit(g), True) for g in beklenen_ham}
        for t in range(tekrar):
            sonuc = retrieval.getir(sorgu, k=k, profil_paketi=None, hyde_cache=False)
            gelen = [ev._kimlik(r, True) for r in sonuc]
            satirlar.append({
                "sorgu_no": s,
                "cekilis": t,
                "basari": any(h in gelen for h in hedef),
                "skor_bandi": float(sinyaller.skor_bandi(sonuc)),
                "benzerlik": float(sinyaller.benzerlik(sonuc)),
            })
            time.sleep(BEKLEME)
        KAYIT.write_text(json.dumps(satirlar, ensure_ascii=False), encoding="utf-8")
        print(f"  {s:2d}/{len(ev.ALTIN_SET)}  {sorgu[:50]}")
    return satirlar


def auc(iyi, kotu):
    if not iyi or not kotu:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in iyi for b in kotu) / (len(iyi) * len(kotu))


def _grupla(satirlar, ad):
    """{sorgu_no: ([deger, ...], [etiket, ...])} — satirlari BIR KEZ grupla.

    permutasyon bunu 5000 kez kullaniyor; her cagrida yeniden gruplamak (sorgu basina
    tum satirlari taramak) testi saniyeler yerine dakikalar suruyordu."""
    gruplar = {}
    for r in satirlar:
        degerler, etiketler = gruplar.setdefault(r["sorgu_no"], ([], []))
        degerler.append(r[ad])
        etiketler.append(r["basari"])
    return gruplar


def _auc_gruplu(gruplar):
    """Katmanli AUC, onceden gruplanmis veriden. Donus: (auc, karisik_sorgu, cift)."""
    kazanc = esit = toplam = 0
    karisik = 0
    for degerler, etiketler in gruplar.values():
        iyi = [d for d, e in zip(degerler, etiketler) if e]
        kotu = [d for d, e in zip(degerler, etiketler) if not e]
        if not iyi or not kotu:
            continue
        karisik += 1
        for a in iyi:
            for b in kotu:
                toplam += 1
                kazanc += a > b
                esit += a == b
    if not toplam:
        return None, 0, 0
    return (kazanc + 0.5 * esit) / toplam, karisik, toplam


def sorgu_ici_auc(satirlar, ad):
    """Katmanli AUC: her sorgunun KENDI icinde ikili karsilastirma, sonra havuzla.

    Sadece hem basarili hem basarisiz cekilisi olan ('karisik') sorgular katkida
    bulunur — digerlerinde karsilastirilacak cift yok.
    """
    return _auc_gruplu(_grupla(satirlar, ad))


def permutasyon(satirlar, ad, gozlem, N=5000):
    """Etiketleri HER SORGUNUN ICINDE karistir — sorgu yapisi korunur.

    Gruplama DONGU DISINDA bir kez yapiliyor; her tekrarda yalnizca etiket listesi
    karistiriliyor. Eskiden her tekrar 115 dict kopyalayip gruplamayi bastan kuruyordu
    (2 sinyal x 5000 tekrar = ~26M satir karsilastirmasi). Karistirma sirasi ayni
    kaldigi icin p degeri de ayni."""
    rnd = random.Random(0)
    gruplar = _grupla(satirlar, ad)
    sayac = 0
    for _ in range(N):
        sahte = {}
        for no, (degerler, etiketler) in gruplar.items():
            karisik_etiket = list(etiketler)
            rnd.shuffle(karisik_etiket)
            sahte[no] = (degerler, karisik_etiket)
        a, _, _ = _auc_gruplu(sahte)
        if a is not None and abs(a - 0.5) >= abs(gozlem - 0.5):
            sayac += 1
    return sayac / N


def rapor(satirlar):
    n = len(satirlar)
    b = sum(r["basari"] for r in satirlar)
    print(f"\n{n} cekilis ({len(ev.ALTIN_SET)} sorgu x {TEKRAR}) — basarili {b}, basarisiz {n-b}")

    # cekiliste ne kadar oynuyor: sorgu basina kac farkli sonuc
    kararsiz = sum(1 for no in {r['sorgu_no'] for r in satirlar}
                   if len({r['basari'] for r in satirlar if r['sorgu_no'] == no}) > 1)
    print(f"KARISIK sorgu (hem basarili hem basarisiz cekilisi olan): "
          f"{kararsiz}/{len(ev.ALTIN_SET)}  <- testin gucu buna bagli\n")

    for ad in ("skor_bandi", "benzerlik"):
        havuz = auc([r[ad] for r in satirlar if r["basari"]],
                    [r[ad] for r in satirlar if not r["basari"]])
        ici, karisik, cift = sorgu_ici_auc(satirlar, ad)
        if ici is None:
            print(f"{ad:<11} sorgu-ici test YAPILAMADI (karisik sorgu yok)")
            continue
        p = permutasyon(satirlar, ad, ici)
        print(f"{ad:<11} havuz AUC {havuz:.3f} | SORGU-ICI AUC {ici:.3f} "
              f"({karisik} sorgu, {cift} cift) | p = {p:.3f}")


if __name__ == "__main__":
    rapor(olc())     # tamamlanmis sorgular atlanir; hepsi bitmisse dogrudan rapor
