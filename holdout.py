"""B4 — "iyi oneri" olcutu: TUT-BIRAK (holdout). Fazin acik problemi.

recall@k RETRIEVAL'i olcuyor: "su sorguya su anime gelmeli". Oneri kalitesini
olcmuyor — kisisellestirme tanimi geregi hedeften uzaklastirdigi icin altin setle
ayarlanamiyor bile. Bu dosya farkli bir soru soruyor:

    Sevdigin N seyi profilden GIZLERSEM, sistem onlari geri bulabiliyor mu?

TASARIM KARARLARI (Deniz, 2026-09-05) — savunulmasi gereken kisim bu:
 1) Gizlenenler 10 verilenler. En guclu tercih sinyali; 8'leri gizlemek "az sevdigini
    bulabiliyor musun" diye sorardi, o baska bir soru.
 2) Gizleme FRANCHISE BAZINDA. Ilk surum tek tek idMal gizliyordu ve OLCTUGU SEYI
    IMKANSIZ KILIYORDU: maske franchise duzeyinde calisiyor, yani "K-On!!" gizlense
    bile "K-On!" izlenenlerde kaldigi icin butun seri maskeli kaliyordu. Olculdu
    (09-05): gizlenen 20 kaydin yalnizca 7'si gercekten ulasilabilirdi.
    Kural, 09-04'un kuralinin bu yoldaki hali: ESLESTIRME franchise duzeyindeyse
    GIZLEME de franchise duzeyinde olmali. Olcunun her adimi ayni semantigi tasimali.
 3) Esleme FRANCHISE duzeyinde (eval.py ile ayni semantik, A12). Urun franchise basina
    tek temsilci donduruyorsa, olcu belirli bir temsilciyi sart kosamaz.
 4) RASTGELE TABAN sart. hit@50 = 0.10 tek basina hicbir sey soylemiyor; corpus 4880
    iken rastgele bir sistemin ne bulacagini bilmeden "iyi" denemez. Rapor edilen sayi
    KAT (lift): gercek isabet / rastgele beklenti.
 5) Birden fazla tekrar, farkli gizlenen kumeleriyle (tohum sabit). Tek cekilis
    varyansi olcuyu gurultuye baglar — 09-05'in dersi.

Kullanim:  python holdout.py [gizlenen_sayisi] [tekrar]
"""
import random
import sys

import config
import profil
import retrieval

N_GIZLI = int(sys.argv[1]) if len(sys.argv) > 1 else 8
TEKRAR = int(sys.argv[2]) if len(sys.argv) > 2 else 5
K_LISTESI = (5, 10, 20, 50)


def _franchise(idmal, grup, idmal_anilist):
    """idMal -> franchise kimligi (grup no varsa o, yoksa kendisi)."""
    al = idmal_anilist.get(idmal)
    g = grup.get(al) if al is not None else None
    return ("f", g) if g is not None else ("tek", idmal)


def kos(n_gizli=N_GIZLI, tekrar=TEKRAR):
    model, V, corpus, _ = retrieval._hazirla()
    liste = profil.liste_yukle()
    grup = retrieval._seri_gruplari()

    idmal_satir = {m["idMal"]: i for i, m in enumerate(corpus) if m["media"] == "anime"}
    idmal_anilist = {m["idMal"]: m.get("id") for m in corpus if m["media"] == "anime"}
    cekirdek = profil.cekirdek_idler(liste, set(idmal_satir))          # 8+ puan
    onlar = [a["idMal"] for a in liste
             if a["puan"] == 10 and a["idMal"] in idmal_satir]
    izlenen_hepsi = profil.izlenen_idler(liste)

    # gizlenebilir havuz = 10 verilenlerin FRANCHISE'lari (tek tek baslik degil)
    f_uyeler = {}
    for i in onlar:
        f_uyeler.setdefault(_franchise(i, grup, idmal_anilist), set()).add(i)
    # bir franchise gizleniyorsa TUM uyeleri gizlenir (izlenenler dahil)
    for i in izlenen_hepsi | set(cekirdek):
        f = _franchise(i, grup, idmal_anilist)
        if f in f_uyeler:
            f_uyeler[f].add(i)
    franchiseler = list(f_uyeler)

    print(f"cekirdek {len(cekirdek)} · 10 verilen {len(onlar)} · "
          f"bunlarin franchise'i {len(franchiseler)} · gizlenen {n_gizli} x {tekrar} tekrar")
    if len(franchiseler) < n_gizli:
        raise SystemExit(f"franchise sayisi ({len(franchiseler)}) < gizlenecek ({n_gizli})")

    # Rastgele taban FRANCHISE duzeyinde sayilir. getir_profilden franchise basina TEK
    # temsilci donduruyor -> top-k = k farkli FRANCHISE, k kayit degil. Kayit sayisiyla
    # bolmek paydayi ~2x buyutuyordu (4880 kayit vs 2366 franchise) ve KAT'i ~2x sisiriyordu:
    # olcu, tam da durust oldugunu iddia ettigi yerde kisisellestirmeyi abartiyordu.
    # 09-05'in kurali burada da gecerli: olcunun HER adimi ayni semantigi tasimali.
    tum_f = {_franchise(m["idMal"], grup, idmal_anilist)
             for m in corpus if m["media"] == "anime"}
    izlenen_f = {_franchise(i, grup, idmal_anilist) for i in izlenen_hepsi}
    toplam = {k: 0.0 for k in K_LISTESI}
    taban = {k: 0.0 for k in K_LISTESI}

    for t in range(tekrar):
        rnd = random.Random(1000 + t)
        gizli_f = set(rnd.sample(franchiseler, n_gizli))
        gizli = set().union(*(f_uyeler[f] for f in gizli_f))   # tum uyeler

        satirlar = [idmal_satir[i] for i in cekirdek if i not in gizli]
        adalar = profil.zevk_adalari(V, satirlar, config.K_ADA)
        maske = profil.izlenen_seri_maskesi(corpus, izlenen_hepsi - gizli, grup)

        sonuc = retrieval.getir_profilden((adalar, maske), k=max(K_LISTESI), medya="anime")
        gelen_f = [_franchise(m["idMal"], grup, idmal_anilist) for m in sonuc]

        # Bu tekrarda ulasilabilir franchise havuzu: gizlenenler maskeden CIKTI, geri gelir.
        havuz_n = len(tum_f - (izlenen_f - gizli_f))
        for k in K_LISTESI:
            isabet = len(gizli_f & set(gelen_f[:k]))
            toplam[k] += isabet / len(gizli_f)
            taban[k] += min(k, havuz_n) / havuz_n
        ulasilir = sum(1 for i in gizli if not maske[idmal_satir[i]])
        print(f"  tekrar {t}: ilk-50'de {len(gizli_f & set(gelen_f))}/{len(gizli_f)} gizli "
              f"franchise  (gizlenen {len(gizli)} kayit, ulasilabilir {ulasilir})")

    print(f"\n{'k':>4} {'isabet@k':>10} {'rastgele':>10} {'KAT':>8}")
    print("-" * 36)
    for k in K_LISTESI:
        g, r = toplam[k] / tekrar, taban[k] / tekrar
        print(f"{k:>4} {g:>10.3f} {r:>10.4f} {(g / r if r else 0):>8.1f}x")
    print("\nKAT = rastgele bir sistemin bulacaginin kac kati. 1.0x = kisisellestirme yok.")


if __name__ == "__main__":
    kos()
