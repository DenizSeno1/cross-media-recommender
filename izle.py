"""IZ SURUCU — bir sorguyu boru hattinin HER asamasinda gorunur kilar.

Bu dosya hicbir sey olcmez ve hicbir sey degistirmez. Amaci tek: hattin
mimarisini okumak yerine KOSTURARAK gormek. Her asama "ne girdi / ne cikti /
bu asama neden var" uclusuyle basiliyor.

Kullanim:
    python izle.py                                  # varsayilan sorgu, profilli
    python izle.py "zaman yolculugu olan bir anime"
    python izle.py "..." --profilsiz                # profil katmani kapali
    python izle.py --sorgusuz                       # B5 yolu: sorgu yok, adalar
    python izle.py "..." --agirlik=0.2              # profil_agirligi'ni gecici degistir
"""
import sys

import numpy as np

import config
import oneri
import profil
import retrieval
import veri

VARSAYILAN = "ölüm ve yas üzerine sakin fantastik yolculuk"
CIZGI = "=" * 78


def baslik(no, ad, neden):
    print(f"\n{CIZGI}\n {no}. {ad}\n    ({neden})\n{CIZGI}")


def aci(a, b):
    """Iki birim vektor arasindaki aci — derece. Harmanin sorguyu NE KADAR
    oynattigini gormek icin; 09-04'te kisisellestirmenin 'cekme mi ince ayar mi'
    oldugu tam bu sayiyla karara baglanmisti (6 derece vs 30 derece)."""
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b), -1, 1))))


def izle(sorgu, kisisel=True, k=5, agirlik=None):
    model, V, corpus, belgeler = retrieval._hazirla()

    baslik(0, "CORPUS", "aranan sey: dondurulmus 7807 kayit, uc medya AYNI uzayda")
    from collections import Counter
    print(f"    {Counter(m['media'] for m in corpus)}  toplam {len(corpus)}")
    print(f"    index: V{V.shape}, satirlar birim vektor (norm={np.linalg.norm(V[0]):.3f})")
    print(f"    gomulen metin ornegi (veri.belge):\n      {belgeler[0][:150]}...")

    baslik(1, "HyDE — SAHTE BELGE", "sorgu Turkce+elestirmen dili, corpus Ingilizce+arka kapak; "
                                    "aradigimiz sey dogruluk degil BICIM benzerligi")
    q_ham = model.encode("query: " + sorgu, normalize_embeddings=True)
    q, sahte = retrieval._hyde_vektor(sorgu, model, config.HYDE_N_ORNEK, cache=True)
    print(f"    girdi : {sorgu}")
    print(f"    cikti : {sahte[:300]}...")
    print(f"    ham sorgu ile sahte belge arasindaki aci: {aci(q_ham, q):.1f}°")
    print(f"    (ham sorgu TEK BASINA recall@5 = 0 veriyor; HyDE bu acinin oteki ucu)")

    baslik(2, "PROFIL HARMANI", "profil CEKMEZ, ince ayar yapar — olculdu: en yakin ada 6°, "
                                "tek ortalama 30° (sorgu terk edilir)")
    izlenen_maske = None
    if kisisel:
        adalar, izlenen_maske = retrieval.profil_kur()
        if adalar is not None:
            ada = profil.en_yakin_ada(adalar, q)
            w = config.PROFIL_AGIRLIGI if agirlik is None else agirlik
            q_yeni = profil.harmanla(q, ada, w)
            print(f"    {len(adalar)} zevk adasi · secilen ada pusulaya en yakin olan")
            print(f"    harman oncesi/sonrasi aci: {aci(q, q_yeni):.1f}°  "
                  f"(profil_agirligi={w})")
            q = q_yeni
        else:
            print("    profil kurulamadi -> katman atlandi")
    else:
        print("    kisisellestirme KAPALI (--profilsiz)")

    baslik(3, "BI-ENCODER — 7807 SKOR", "tek matris carpimi; bu yuzden FAISS reddedildi, "
                                        "brute force zaten milisaniye")
    skorlar = V @ q
    ilk = np.argsort(-skorlar)[:5]
    print(f"    skor bandi: min {skorlar.min():.3f} · medyan {np.median(skorlar):.3f} · "
          f"max {skorlar.max():.3f}")
    print("    maskesiz ilk 5:")
    for i in ilk:
        print(f"      {skorlar[i]:.3f}  [{corpus[i]['media']:<5}] {veri.baslik(corpus[i])}")

    baslik(4, "MASKELER", "KIRPMADAN ONCE uygulanir — sonra uygulanirsa elenenlerin "
                          "yerini baskalari coktan doldurmus olur")
    n_once = int(np.isfinite(skorlar).sum())
    if izlenen_maske is not None:
        skorlar[izlenen_maske] = -np.inf
        print(f"    izlenen seri filtresi (franchise grafi): {int(izlenen_maske.sum())} kayit elendi")
        print(f"    (naif idMal filtresi 321 eliyordu, franchise grafi 617 — %92 daha fazla)")
    else:
        print("    maske yok")
    print(f"    aday havuzuna kalan: {int(np.isfinite(skorlar).sum())} / {n_once}")

    baslik(5, "ADAY HAVUZU (kaba suzgec)", "her kademe yalnizca KAYBEDEBILIR — buradan "
                                           "dusen kayit sonraki asamada geri gelmez")
    aday = list(np.argsort(-skorlar)[:config.ADAY])
    print(f"    {len(corpus)} -> {len(aday)} aday (config.ADAY)")
    print(f"    karnesi recall@50 = 0.739 -> altin setin %26'si BURAYA hic giremiyor.")
    print(f"    rerank {'ACIK' if config.RERANK_AKTIF else 'KAPALI'} "
          f"(+0.18 recall@5 ama CPU'da dk/sorgu -> varsayilan kapali)")

    baslik(6, "SECIM — tekillestirme + kota", "SUNUM kurallari, kisisellestirme DEGIL: "
                                              "profili olmayan da 3 One Piece gormemeli")
    gruplar = retrieval._seri_gruplari()
    kota = profil.kota_olcekle(config.KOTA, k)
    secilen = profil.kota_sec(aday, corpus, gruplar, k, kota)
    dusen = [i for i in aday[:k + 5] if i not in secilen][:5]
    print(f"    kota (k={k}'ya orantili): {kota}")
    print(f"    {len(aday)} aday -> {len(secilen)} oneri")
    if dusen:
        print("    ust siralardan DUSENLER (seri tekrari ya da kota doldu):")
        for i in dusen:
            print(f"      {skorlar[i]:.3f}  [{corpus[i]['media']:<5}] {veri.baslik(corpus[i])}")

    baslik(7, "SONUC", "kullaniciya giden liste")
    sonuc = [dict(corpus[i], _skor=float(skorlar[i])) for i in secilen]
    for r in sonuc:
        print(f"    {r['_skor']:.3f}  [{r['media']:<5}] {veri.baslik(r)}")

    baslik(8, "PROMPT'A GIDEN METIN", "gerekce GETIRILEN METNE dayanmali (grounding); "
                                      "model uydurursa bu bir bug, uslup tercihi degil")
    print(oneri._prompt(sorgu, oneri._baglam(sonuc))[:1200])
    print("    ...")
    print("\n    NOT: profil prompt'a GIRMIYOR -> gerekce 'Frieren'e 10 verdigin icin'")
    print("    diyemez, sadece getirilen metne dayanir. Bilinen eksik (B7).")


def izle_sorgusuz(k=5):
    """B5 yolu: sorgu yok. Icerik sorguda degil LISTEDE."""
    paket = retrieval.profil_kur()
    if paket[0] is None:
        raise SystemExit("profil kurulamadi")
    adalar, maske = paket
    baslik(1, "SORGU YOK — ADALAR PUSULA", "iceriksiz bir istegi HyDE'a vermek onu yoktan "
                                           "bir olay orgusu uydurmaya zorluyor")
    print(f"    {len(adalar)} zevk adasi, her biri birim vektor")
    print("    SIFIR LLM cagrisi: ada secimi bir MESAFE sorusu, uydurmaya gerek yok")
    baslik(2, "ADALAR ARASI ROUND-ROBIN", "tek ortalama AYRIMI oldurur, tek ada CESITLILIGI "
                                          "oldurur -> her adadan sirayla bir aday")
    for r in retrieval.getir_profilden(paket, k=k):
        print(f"    ada{r['_ada']:<2} {r['_skor']:.3f}  [{r['media']:<5}] {veri.baslik(r)}")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]]
    if "--sorgusuz" in argv:
        izle_sorgusuz()
    else:
        kisisel = "--profilsiz" not in argv
        metin = next((a for a in argv if not a.startswith("--")), VARSAYILAN)
        w = next((float(a.split("=")[1]) for a in argv if a.startswith("--agirlik=")), None)
        izle(metin, kisisel=kisisel, agirlik=w)
