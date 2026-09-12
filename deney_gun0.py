"""Gun 0 olcumu: yapisal sinyaller basarili/basarisiz sorgulari ayiriyor mu?

Kurulum kurallari (ucu de Faz 4'un dersleri):
  1) SORGU BASINA TEK getir CAGRISI. Sinyali bir kosudan, basariyi baska kosudan
     alirsan HyDE varyansi ikisini ayirir ve korelasyon coker.
  2) hyde_cache=True. Olcum dondurulur, urun rastgele kalir.
  3) BASARI TANIMI URUNLE AYNI: kullanici k=TOP_K sonuc goruyor, sinyal de o
     listeye bakiyor, basari da o listede olculuyor. ("olcuyu urune esitle")

Kor tahmin (2026-09-07, olcumden ONCE):
  skor_bandi -> "ise yaramaz, e5'te bant zaten dar"
  benzerlik  -> "en iyisi bu"
"""

import config
import eval as ev
import retrieval
import sinyaller

K = config.TOP_K


def olc(k: int = K):
    """Her gold sorgu icin: (sorgu, basari, skor_bandi, benzerlik)."""
    satirlar = []
    for sorgu, beklenen_ham in ev.ALTIN_SET:
        sonuc = retrieval.getir(sorgu, k=k, profil_paketi=None, hyde_cache=True)

        # basari: gold'lardan HERHANGI BIRI listede mi (franchise kimligiyle)
        gelen = [ev._kimlik(r, True) for r in sonuc]
        hedef = {ev._kimlik(ev._gold_kayit(g), True) for g in beklenen_ham}
        basari = any(h in gelen for h in hedef)

        satirlar.append({
            "sorgu": sorgu,
            "basari": basari,
            "skor_bandi": sinyaller.skor_bandi(sonuc),
            "benzerlik": sinyaller.benzerlik(sonuc),
        })
    return satirlar


def auc(basarili: list[float], basarisiz: list[float]) -> float:
    """Ayrisma olcusu: rastgele bir BASARILI ve bir BASARISIZ sorgu secsen,
    basarilinin sinyali daha buyuk olma olasiligi. (Mann-Whitney U / AUC)

        0.5 = hic ayirmiyor (yazi-tura)
        1.0 = kusursuz ayiriyor, basarililar hep ustte
        0.0 = kusursuz ayiriyor ama TERS yonde (sinyalin isaretini cevir)

    Ortalama karsilastirmasindan iyi: tek bir uc deger sonucu suruklemiyor.
    """
    if not basarili or not basarisiz:
        return float("nan")
    kazanc = sum((a > b) + 0.5 * (a == b) for a in basarili for b in basarisiz)
    return kazanc / (len(basarili) * len(basarisiz))


def _ort(degerler):
    """Bos grupta nan — auc()'un bos grupta yaptiginin aynisi.

    Neden gerekli: butun sorgular basarili (ya da butun sorgular basarisiz) bir konfigda
    iyi/kotu gruplarindan biri bos kalir ve ortalama ZeroDivisionError verirdi — olcum
    kosusu tamamen odendikten SONRA, raporu basarken."""
    return sum(degerler) / len(degerler) if degerler else float("nan")


def rapor(satirlar):
    n_basari = sum(r["basari"] for r in satirlar)
    print(f"\n{len(satirlar)} sorgu — basarili {n_basari}, basarisiz {len(satirlar) - n_basari}"
          f"  (basari = gold ilk {K} icinde)\n")

    print(f"{'B':<2} {'skor_bandi':>11} {'benzerlik':>10}  sorgu")
    for r in sorted(satirlar, key=lambda r: -r["skor_bandi"]):
        isaret = "OK" if r["basari"] else "--"
        print(f"{isaret:<2} {r['skor_bandi']:>11.4f} {r['benzerlik']:>10.4f}  {r['sorgu'][:58]}")

    print()
    for ad in ("skor_bandi", "benzerlik"):
        iyi = [r[ad] for r in satirlar if r["basari"]]
        kotu = [r[ad] for r in satirlar if not r["basari"]]
        a = auc(iyi, kotu)
        print(f"{ad:<11} basarili ort {_ort(iyi):.4f} | "
              f"basarisiz ort {_ort(kotu):.4f} | AUC {a:.3f}")

    print("\nNOT: sorgu basina TEK cekilis. AUC 0.5'e yakinsa sinyal bilgi tasimiyor;"
          "\n0.5'ten uzaksa (iki yone de) tasiyor. Tek kosu, guven araligi YOK.")


if __name__ == "__main__":
    rapor(olc())
