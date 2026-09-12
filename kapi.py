"""Karar kapisi — getirilen liste sorguyu karsiliyor mu? (Faz 5 Gun 5-6)

NE OLDUGUNU BILEREK YAZIYORUM: Gun 0'da tam bu is icin iki YAPISAL sinyal
olculdu (skor_bandi, benzerlik) ve ikisi de gurultuden ayirt edilemedi —
sorgu-ici AUC 0.500 ve 0.389, p = 1.000 ve 0.394. Kapi fikri o olcumle DUSTU.

Buradaki kapi farkli bir malzeme kullaniyor: skor dagilimi degil, sorgunun
KELIMELERININ getirilen kayitlarda gecip gecmedigi. Ama "farkli malzeme"
otomatik olarak "bu sefer calisir" demek degil. Bu yuzden dongu.py bu yargiyi
KAYDEDIYOR, akisi YONETTIRMIYOR — once olcum, sonra terfi.

Deterministik: LLM yok. Gun 3-4'te durum.iz() icin verilen kararin aynisi —
budamayi LLM'e yaptirmak belirsizlik katiyordu, yargiyi da katardi.
"""


def yargila(sorgu: str, sonuclar: list[dict]) -> dict:
    """Bu sonuç listesi kullanıcının sorgusunu karşılıyor mu?

    sorgu     : kullanıcının orijinal isteği
    sonuclar  : araclar._getir_kirp çıktısı — her dict'te 'baslik', 'tur', 'aciklama'

    dönüş : {"yeterli": bool, "gerekce": str}

    KURAL SIKI: her sonuçta her anahtar kelime geçmeli. Tek bir kayıtta tek bir
    kelime eksikse liste yetersiz sayılıyor. Bu bilinçli olarak katı ve pratikte
    neredeyse hep "yetersiz" diyecek — ölçüm bunu gösterirse gevşetilecek yer
    aşağıdaki iç döngü.
    """
    # BOSLUKLARI SILMEDEN ONCE BOL. Once replace(" ","") yapip sonra split()
    # cagirmak butun sorguyu TEK kelimeye yapistiriyordu ("monster gibi
    # psikolojik" -> ["monstergibipsikolojik"]) ve kapi hicbir seyi eslestiremiyordu.
    anahtar_kelimeler = sorgu.lower().split()

    yeterli = True
    eksikler = []               # sirasi korunan, tekrarsiz eksik kelime listesi

    for sonuc in sonuclar:
        # Alan tarafinda bosluk silmek KALIYOR: kayitlarda "bilim kurgu" gibi
        # ayri yazilan turler var, sorgudaki "bilimkurgu" onu yakalayabilsin.
        baslik = sonuc["baslik"].lower().replace(" ", "")
        tur = sonuc["tur"].lower().replace(" ", "")
        aciklama = sonuc["aciklama"].lower().replace(" ", "")

        for kelime in anahtar_kelimeler:
            if kelime not in baslik and kelime not in tur and kelime not in aciklama:
                yeterli = False
                # Ayni kelime 5 kayitta da eksik olabilir; gerekceyi 5 kez
                # yazmak baglama bedava yuk. Bir kez yaziliyor.
                if kelime not in eksikler:
                    eksikler.append(kelime)

    if yeterli:
        return {"yeterli": True,
                "gerekce": "Sorgunun tüm anahtar kelimeleri sonuçlarda bulundu."}

    kelimeler = ", ".join(f'"{k}"' for k in eksikler)
    return {"yeterli": False,
            "gerekce": f"Şu anahtar kelimeler sonuçların hepsinde bulunamadı: {kelimeler}."}


if __name__ == "__main__":
    # elle deneme: python kapi.py   — araclar/retrieval yuklemeden, sentetik kayitla
    ornek = [
        {"baslik": "Monster", "tur": "anime",
         "aciklama": "Psikolojik gerilim, ahlaki ikilem, seri katil takibi."},
        {"baslik": "Death Note", "tur": "anime",
         "aciklama": "Bir dedektif ve katil arasinda psikolojik satranc."},
    ]
    for s in ["psikolojik", "psikolojik anime", "uzay gemisi"]:
        print(f"{s!r:28} -> {yargila(s, ornek)}")
