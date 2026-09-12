"""Ajanin hafizasi ve baglam budamasi — Faz 5 Gun 3-4.

NEDEN BUDAMA (iki sebep, ve "baglam doluyor" bunlardan BIRI DEGIL):
  Kullanilan modelin penceresi genis; 6 turda doldurulamaz. Gercek sebepler:

  1) MALIYET — girdi her turda BASTAN odeniyor. Olculdu (Osmanli kosusu, 4 tur):
         tur 1: 556 tok · tur 2: 1228 · tur 3: 1678 · tur 4: 2165  -> toplam 5627
     1. turun gozlemi DORT KEZ faturalandi. Budamasiz toplam maliyet tur sayisinin
     KARESI gibi buyuyor, tur sayisi gibi degil.

     OLCULDU (deney_gun3.py, ajandan bagimsiz — ayni gecmis iki kez derleniyor):
         tur sayisi iki katina cikinca kumulatif maliyet
             budamasiz 3.8x  (kare ~4.0x)
             budamali  2.55x (dogrusal ~2.0x)
         HARD_CAP=6'da tasarruf %43.
     Yani budama egrinin SEKLINI degil KATSAYISINI degistiriyor: tur basina kalici
     yuk ~545 tok'tan ~91'e iniyor ama SIFIRA INMIYOR — iz de her turda birikiyor.
     Budamali egri de kareye caliyor, sadece alti kat daha yavas. Gun 5-6'da durma
     karari ajana gecip tur sayilari buyudugunde bu geri gelecek.

  2) SEYRELME — alakasiz metin arttikca modelin karari bozuluyor. 6. turda onunde
     5 tur oncesinin sinopsisleri duruyor ve hicbiri isine yaramiyor.

KARAR: IZ BIRAKMA (Deniz, 2026-09-11). Uc secenek tartisildi:
    a) pencere    — eski gozlemi tamamen at        -> "denedim" bilgisi de gider
    b) ozetleme   — LLM'e ozetlet                  -> BELIRSIZLIK: ozet kosudan kosuya
                                                      degisir, ajanin tur sayisi da degisir
                                                      ve Gun 9-10'da sistemi degil o gunku
                                                      modeli olcersin
    c) IZ         — eski gozlemi KODUN urettigi tek satirla degistir
Deniz'in gerekcesi: *"LLM'e ozetletmek belirsizlik katiyor"*. Gun 0'da yapisal
sinyalleri LLM yargicina tercih ederken kullanilan ilkenin aynisi: ucuz +
deterministik, pahali + belirsize tercih edilir.

AYRIM (gunun kavrami): gozlemin ICERIGI ile IZI ayri seylerdir.
    icerik : 2500 krk, 5 sinopsis, skorlar   -> 6. turda gereksiz
    iz     : "sunu aradim, soyle seyler geldi" -> 6. turda SART
Ajan sorgusunu onceki turlarin ustune kurarak gelistiriyor; "neyi denedim"
bilgisi gitmezse ayni yere geri doner.
"""

import json


PENCERE = 1     # <-- SENIN KARARIN: kac turun gozlemi TAM halinde tutulacak.
# 1 = sadece en son gozlem tam, digerleri iz. Buyutmenin bedeli her turda tekrar
# odenen ~600 token; kucultmenin bedeli modelin son sonuclari gormeden karar vermesi.


def iz(tur_no: int, arac: str, args: dict, sonuclar: list[dict]) -> str:
    """Bir turun gozlemini TEK SATIRA indirger. Deterministik — LLM yok.

    Icerik karari (Deniz, 2026-09-11): dort parca da girsin.
        cagri      -> "neyi denedim"; sorguyu gelistirmesi buna bagli
        kac sonuc  -> bos dondu mu
        tepe skor  -> "zayifti" bilgisi
        basliklar  -> ayni eseri TEKRAR ONERMESINI ve ayni bolgeyi tekrar
                      taramasini engeller (tekrar freni arac cagrisini engeller,
                      bu ayri bir koruma)

    Ornek cikti:
        tur 1: ara(sorgu="psikolojik gerilim ahlaki ikilem", medya=hepsi, k=5)
               -> 5 sonuc · tepe 0.79 · Heretic, ID: INVADED, Phi Brain, ...
    """
    arg_metni = ", ".join(f"{k}={v!r}" for k, v in args.items())
    if not sonuclar:
        return f"tur {tur_no}: {arac}({arg_metni}) -> SONUC YOK"
    tepe = max(s.get("_skor", 0) for s in sonuclar)
    basliklar = ", ".join(s.get("baslik", "?") for s in sonuclar)
    return (f"tur {tur_no}: {arac}({arg_metni})\n"
            f"       -> {len(sonuclar)} sonuc · tepe {tepe:.2f} · {basliklar}")


class Durum:
    """Ajanin hafizasi. Gecmisi DEGISTIRMEZ, her turda YENIDEN KURAR.

    Neden yeniden kurma: budamayi yerinde yapmak "hangi mesaji silmistim, indeksler
    kaydi mi" takibi gerektiriyor ve bir kez kaydiginda modele bozuk bir konusma
    gider — sessizce. Yeniden kurmada boyle bir durum yok: kayitlar hep tam,
    gonderilen gecmis her seferinde sifirdan derleniyor.
    """

    def __init__(self, sistem_mesaji: str):
        self.sistem = sistem_mesaji
        self.turlar = []        # [{"hamle": <model JSON>, "gozlem": <tam metin>, "iz": <tek satir>}]

    def tur_ekle(self, hamle: dict, gozlem: str, iz_satiri: str) -> None:
        """Bir turu kaydet. UCUNU DE saklar — budama gonderim aninda yapilir,
        kayitta kayip olmaz (log ve Gun 9-10 olcumu tam gecmisi gormeli)."""
        self.turlar.append({"hamle": hamle, "gozlem": gozlem, "iz": iz_satiri})

    # -----------------------------------------------------------------
    # BURASI SENIN
    # -----------------------------------------------------------------

    def gecmis(self, pencere: int = PENCERE) -> list[dict]:
        """Modele GONDERILECEK mesaj listesini kurar.

        cikti : [{"role": "user"|"model", "parts": [{"text": ...}]}, ...]

        Kural:
            - ilk mesaj her zaman sistem mesaji (role="user")
            - SON `pencere` tur          -> gozlem TAM haliyle
            - daha eski turlar           -> gozlem yerine IZ satiri
            - her turun "hamle"si model mesaji olarak korunur (role="model"),
              cunku ajan kendi hamlelerini gormeli

        Dikkat: rolleri karistirma. Modelin kendi JSON'u "model", aracin sonucu
        (ya da izi) "user". Karisirsa model kendi ciktisini kullanicinin yazdigi sanir.

        Ornek — 4 tur kayitli, pencere=1:
            [sistem] [hamle1] [iz1] [hamle2] [iz2] [hamle3] [iz3] [hamle4] [GOZLEM4]
        """
        mesajlar = [{"role": "user", "parts": [{"text": self.sistem}]}]
        toplam_tur = len(self.turlar)

        for i, tur in enumerate(self.turlar):
            mesajlar.append({"role": "model", "parts": [{"text": json.dumps(tur["hamle"])}]})
            if i >= toplam_tur - pencere:
                icerik = tur["gozlem"]
            else:
                icerik = tur["iz"]

            mesajlar.append({"role": "user", "parts": [{"text": icerik}]})
        return mesajlar

    def token_tahmini(self, pencere: int = PENCERE) -> int:
        """Gonderilecek gecmisin kaba token sayisi (4 krk ~ 1 token).

        Kesin degil, KARSILASTIRMA icin: budamali vs budamasiz farki gormek yeterli.
        """
        metin = "".join(p["text"] for m in self.gecmis(pencere) for p in m["parts"])
        return len(metin) // 4
