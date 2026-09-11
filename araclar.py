"""Ajanin araclari — Faz 5 Gun 0.

sema_uret + tool: Faz 3 Gun 7-8'de elle yazildi (`faz3/faz3_gun9_10/tools.py`),
buraya oldugu gibi tasindi. Yeni arac eklemek icin: fonksiyonu yaz, @tool koy.

Faz 3'ten fark: orada araclar tek turluk yardimcilardi (hesap makinesi, tarih farki).
Burada arac SISTEMIN KENDISI — ajan kendi retrieval hattini cagiriyor ve
sonucunu yargilayacak.
"""

import inspect
import re
from typing import get_type_hints

import config
import retrieval
import veri

ARACLAR = {}

TIP_HARITASI = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def sema_uret(fonksiyon):
    """Fonksiyon imzasindan JSON Schema uretir."""
    imza = inspect.signature(fonksiyon)
    tipler = get_type_hints(fonksiyon)

    ozellikler = {}
    zorunlular = []

    for ad, param in imza.parameters.items():
        param_tipi = tipler.get(ad, str)
        json_tipi = TIP_HARITASI.get(param_tipi, "string")
        ozellikler[ad] = {"type": json_tipi}
        if param.default is inspect.Parameter.empty:
            zorunlular.append(ad)

    return {
        "name": fonksiyon.__name__,
        "description": inspect.getdoc(fonksiyon),
        "parameters": {
            "type": "object",
            "properties": ozellikler,
            "required": zorunlular,
        },
    }


def tool(fonksiyon):
    """Dekorator: fonksiyonu semasiyla birlikte ARACLAR'a kaydeder."""
    ARACLAR[fonksiyon.__name__] = {
        "fonksiyon": fonksiyon,
        "sema": sema_uret(fonksiyon),
    }
    return fonksiyon



def _kirp_metin(metin: str, limit: int = config.AJAN_OZET_KRK) -> str:
    """Ozeti ajanin baglami icin kisaltir. Arama zaten TAM METIN uzerinde yapildi;
    burada kirpilan sey yalnizca LLM'in OKUDUGU sey.

    Uc is yapiyor, sirasi onemli:
      1) artik etiketleri at  ("[Written by MAL Rewrite]" gibi kaynak imzalari)
      2) bosluklari tekille   (sinopsislerde satir sonu ve cift bosluk cok)
      3) limitten sonra CUMLE SONUNDA kes (kelime ortasindan kesmek metni bozar)
    """
    metin = re.sub(r"\[[^\]]*\]", "", metin)      # [Written by MAL Rewrite] vb.
    metin = re.sub(r"\s+", " ", metin).strip()    # satir sonu, cift bosluk -> tek bosluk

    if len(metin) <= limit:
        return metin

    kesik = metin[:limit]
    # limitten geriye dogru en yakin cumle sonunu ara; yoksa son bosluktan kes.
    son_nokta = max(kesik.rfind(". "), kesik.rfind("! "), kesik.rfind("? "))
    if son_nokta > limit * 0.6:                   # cok geriye gidip metni yok etme
        return kesik[:son_nokta + 1]
    return kesik[:kesik.rfind(" ")] + "..."


# ------------------------------------------------------------------ ARACLAR
#
# KARAR (senin): getir() tam kaydi donduruyor — sinopsis, tum metadata, '_skor'.
# Bunun tamami ajanin onune KONMAZ (baglam sisirir), ama tamami ATILAMAZ da:
#
#   - LLM okuyacak      -> metin lazim (baslik, tur, kisa aciklama)
#   - KAPI olcecek      -> ham sayi lazim ('_skor', 'media')  [Gun 0'in sinyalleri]
#
# Bu yuzden iki fonksiyon var: biri veriyi getirip KIRPIYOR, digeri onu
# LLM'in okuyacagi metne ceviriyor. Hangi alanlarin kaldigina sen karar ver.
#
# Isine yarayacak yardimcilar (veri.py, senin yazdigin):
#   veri.baslik(m) -> str    (anime'de title ic ice dict, film/kitapta duz)
#   veri.belge(m)  -> str    (gomulen metin: baslik + tur + aciklama)
#   veri.link(m)   -> str
# Ham alanlar: anime {title, description, genres, tags, averageScore, seasonYear,...}
#              film/kitap {title, overview, genres, ...}  + hepsinde 'media', '_skor'


@tool
def ara(sorgu: str, medya: str = "hepsi", k: int = 5) -> str:
    """Capraz-medya corpus'unda (anime/film/kitap) arama yapar.

    sorgu: Aranacak metin. Kullanicinin cumlesi degil, ARAMAYA UYGUN bir tarif
        yaz — icerik, tema, ton. Sonuc zayifsa turlar arasi degistir.
    medya: "anime" | "film" | "kitap" | "hepsi". Daraltmak sonuclari keskinlestirir,
        "hepsi" capraz medya onerisi verir.
    k: Kac sonuc dondurulecek.
    """
    # _getir_kirp cagir, sonra _metin ile LLM'e okunur hale getir
    getirilen = _getir_kirp(sorgu=sorgu, medya=medya, k=k)
    metin = _metin(getirilen)
    return metin
    


def _getir_kirp(sorgu: str, medya: str = "hepsi", k: int = 5) -> list[dict]:
    """retrieval.getir()'i cagirir, kayitlari ajanin ihtiyaci kadar kirpar.

    Donen her dict'te NE OLMALI? Iki musteri var (yukaridaki KARAR notu):
    LLM okuyacak, kapi olcecek. Ikisine de yetecek en kucuk alan kumesi.

    Dikkat: 'medya' burada "hepsi" -> None'a cevrilir. sema_uret'in tip
    haritasi str|None bilmiyor, o yuzden sentinel kullaniyoruz.
    """
    if medya == "hepsi":
        medya = None
    kayitlar = retrieval.getir(sorgu=sorgu, medya=medya, k=k)
    kirpilmis = []
    for kayit in kayitlar:
        kirpilmis.append(
            {
                "baslik": veri.baslik(kayit),
                "tur": kayit["media"],
                # veri.ozet, veri.belge DEGIL: belge() "baslik. turler. ozet" uretiyor,
                # basligi _metin zaten kendi satirinda yaziyor. belge()'yi vermek basligi
                # iki kez yazip AJAN_OZET_KRK butcesini de oneke harcamak olurdu.
                "aciklama": _kirp_metin(veri.ozet(kayit)),
                "link": veri.link(kayit),
                "_idx": kayit["_idx"],   # V icindeki satir no — sinyaller.benzerlik kullaniyor
                "_skor": kayit["_skor"],
            }
        )
    return kirpilmis


def _metin(sonuclar: list[dict]) -> str:
    """Kirpilmis kayitlari LLM'in okuyacagi tek metne cevirir.

    Bicim karari senin. Aklinda tut: bu metin HER TURDA baglama ekleniyor —
    5 sonuc x 10 tur = ajanin onunde 50 kayit. Kisa tut.
    """
    metin = ""
    for kayit in sonuclar:
        metin += f"{kayit['baslik']} ({kayit['tur']})\n"
        metin += f"{kayit['aciklama']}\n"
        metin += f"Skor: {kayit['_skor']:.2f}  Link: {kayit['link']}\n\n"
    return metin.strip()


if __name__ == "__main__":
    # elle deneme: python araclar.py
    print(ARACLAR["ara"]["sema"])
    print(ara("psikolojik gerilim, ahlaki ikilem, seri katil takibi"))
