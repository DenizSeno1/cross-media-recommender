"""Budamanin maliyet egrisi — Faz 5 Gun 3-4. AJANDAN BAGIMSIZ olcum.

NEDEN BOYLE BIR DENEY: durum.py'in basindaki iddia su —
    "budamasiz toplam maliyet tur sayisinin KARESI gibi buyuyor, tur sayisi gibi degil"
Bu cumle Gun 2'nin 4 turluk TEK kosusundan genellenmisti; olculmemisti.

Ve ajani kosarak olculemiyor: iki gercek kosu da 2 turda bitti, budama ise
`pencere=1` icin 3. turdan once tanim geregi hicbir sey yapmiyor. Yani olcmek
istedigimiz yere ajan hic gitmiyor. Sorgu secerek zorlamak da guvenilmez —
ajanin tur sayisi kosudan kosuya degisiyor, ilk karsilastirma tam bu yuzden
cokmustu (2 tur vs 3 tur, toplamlar karsilastirilamaz).

AYRIM, ve bu deneyin sinirini bu ciziyor:
    SORU 1 — davranis SABITKEN budama ne kazandiriyor?   -> bu dosya, deterministik
    SORU 2 — budama ajanin KARARINI bozuyor mu?          -> gold set isi, burada DEGIL
Burada ajanin kac tur donecegi girdi degil, PARAMETRE. "6 tur donseydi ne oderdi"
sorusunu soruyoruz; "6 tur doner mi" sorusunu degil.

YONTEM: Durum kayitlari tam tuttugu icin ayni gecmisi iki kez derleyebiliyoruz —
budamali ve budamasiz. Tek degisen derleme. Gozlem gercek: araclar.ara() bir kez
gercekten cagriliyor, sonra o gozlem N tur boyunca tekrarlaniyor (soru boyut
sorusu, icerik sorusu degil).
"""

import json

import araclar
import durum
import llm
from dongu import SISTEM_PROMPT

MAX_TUR = 8          # HARD_CAP 6; egrinin devamini gormek icin 8'e kadar
ORNEK_SORGU = "Monster gibi psikolojik gerilim, ahlaki ikilem barindiran bir sey"


def _sistem_mesaji(sorgu: str) -> str:
    """dongu()'nun kurdugu sistem mesajinin AYNISI — taban dogru olsun diye."""
    return SISTEM_PROMPT.format(
        semalar=json.dumps([a["sema"] for a in araclar.ARACLAR.values()],
                           ensure_ascii=False, indent=2),
        sorgu=sorgu)


def _ornek_tur(sorgu: str) -> tuple[dict, str, str]:
    """Bir kez GERCEKTEN arama yapar; (hamle, gozlem, iz) uclusunu doner.

    Uydurma metin yerine gercek gozlem kullanmanin sebebi: gozlem boyutu
    AJAN_OZET_KRK'ya, k'ya ve _metin()'in bicimine bagli. Elle 2000 karakter
    yazsaydik olctugumuz sey kendi tahminimiz olurdu.
    """
    args = {"sorgu": "psikolojik gerilim ahlaki ikilem seri katil", "medya": "hepsi", "k": 5}
    gozlem, yapisal = araclar.ara(**args)
    hamle = {"dusunce": "ornek hamle", "arac": "ara", "args": args, "cevap": None}
    return hamle, gozlem, durum.iz(1, "ara", args, yapisal)


def egri(max_tur: int = MAX_TUR, sorgu: str = ORNEK_SORGU) -> list[dict]:
    """Her tur sayisi icin budamali/budamasiz baglam boyutunu olcer.

    Tur N'de modele giden gecmis, o ana kadar KAYITLI N-1 turu iceriyor
    (dongu.py'da olcum de tam orada aliniyor). Onun icin: once olc, sonra turu ekle.

    donus : her tur icin bir dict — tur bazinda ve KUMULATIF sayilar
    """
    hamle, gozlem, iz_satiri = _ornek_tur(sorgu)
    print(f"ornek gozlem: {len(gozlem)} krk · iz: {len(iz_satiri)} krk\n")

    d = durum.Durum(_sistem_mesaji(sorgu))
    satirlar = []
    kum_budamali = kum_budamasiz = 0

    for tur_no in range(1, max_tur + 1):
        # pencere=1 -> son turun gozlemi tam, oncekiler iz
        # pencere=max_tur -> hicbiri budanmaz (budamasiz taban)
        budamali = d.token_tahmini(1)
        budamasiz = d.token_tahmini(max_tur)
        # Girdi HER TURDA BASTAN odeniyor: fatura tur bazinda degil, kumulatif.
        kum_budamali += budamali
        kum_budamasiz += budamasiz
        satirlar.append({"tur": tur_no, "budamali": budamali, "budamasiz": budamasiz,
                         "kum_budamali": kum_budamali, "kum_budamasiz": kum_budamasiz})
        d.tur_ekle(hamle, gozlem, iz_satiri)

    return satirlar


def bas(satirlar: list[dict]) -> None:
    print(f"{'tur':>4} | {'budamali':>9} {'budamasiz':>10} | "
          f"{'KUM budamali':>13} {'KUM budamasiz':>14} | {'tasarruf':>8}")
    print("-" * 72)
    for s in satirlar:
        tasarruf = 1 - s["kum_budamali"] / s["kum_budamasiz"]
        print(f"{s['tur']:>4} | {s['budamali']:>9} {s['budamasiz']:>10} | "
              f"{s['kum_budamali']:>13} {s['kum_budamasiz']:>14} | {tasarruf:>7.0%}")

    # Iddianin kendisi: budamasiz KUMULATIF kare gibi mi buyuyor?
    # Kare buyume, tur sayisi iki katina cikinca maliyetin ~4 katina cikmasi demek.
    print("\ntur sayisi iki katina cikinca kumulatif maliyet kac katina cikiyor:")
    for n in (2, 3, 4):
        if 2 * n <= len(satirlar):
            a, b = satirlar[n - 1], satirlar[2 * n - 1]
            print(f"  {n} tur -> {2*n} tur | budamasiz {b['kum_budamasiz']/a['kum_budamasiz']:.2f}x"
                  f" · budamali {b['kum_budamali']/a['kum_budamali']:.2f}x")
    print("  (kare buyume ~4.00x, dogrusal buyume ~2.00x beklenir)")


if __name__ == "__main__":
    llm.sayac.sifirla()
    bas(egri())
    print(f"\nNOT: token_tahmini 4 krk = 1 token sayiyor. Turkce metinde bu SAPIYOR —"
          f"\ngercek kosuda 2. turun tahmini 995 tok'ken API 1179 tok fatura etti."
          f"\nOran olarak okuyun, mutlak deger olarak degil.")
    print(f"\n{llm.sayac.ozet()}")
