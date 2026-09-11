"""Yapisal sinyaller — Faz 5 Gun 0.

Amac: getirilen sonuc listesinden UCUZ ve DETERMINISTIK tek sayilar uretmek.
Karar kapisi (Gun 5-6) once bunlara bakacak, LLM yargicini yalnizca kararsiz
kaldigi ara bantta cagiracak. Bi-encoder -> cross-encoder kademesinin ayni deseni:
ucuz suzgec once, pahali yargic yalnizca gerektiginde.

ONCE OLC, SONRA KUR: bu sinyallerin ise yaradigi VARSAYILMIYOR. Gun 0'in isi,
23 sorguluk altin sette basarili ve basarisiz sorgulari ayirip ayirmadiklarini
olcmek. Ayirmiyorlarsa kapi fikri duser ve dogrudan LLM'e gidilir.

DUSURULEN UCUNCU SINYAL — medya cesitliligi (2026-09-08):
    Olculmedi, cunku olculecek bilgi yok. Medya dagilimi iki kademede birden
    sistem tarafindan belirleniyor: aday havuzu medya basina kuruluyor
    (retrieval.py, `kotali` dali) ve secim KOTA={"anime":3,"film":1,"kitap":1}
    ile bitiyor. Kota kapatilsa dagilim bu sefer ~%97 anime'ye cokuyor (senin
    Faz 4 olcumun, retrieval.py'daki yorumda). Iki durumda da sinyal SABIT —
    sorgunun iyiligi hakkinda bilgi tasimiyor.

KOR TAHMIN (olcumden once yazildi, 2026-09-07):
    skor_bandi -> "ise yaramaz, e5'te bant zaten dar"
    benzerlik  -> "en iyisi bu, hem sinyal hem urun acisindan dogru"
"""

import numpy as np

import retrieval


def skor_bandi(sonuclar: list[dict]) -> float:
    """Tepe skor ile medyan skor arasindaki fark.

    Neden MUTLAK esik degil de fark: kosinus skorlari kalibre degil. Ayni 0.55
    bir sorguda mukemmel eslesme, digerinde cop olabilir; model degisirse tum
    bant kayar. Fark ise ayni olcekten geliyor -> gaddar bir sorgulayici butun
    bandi asagi cekse bile korunur.

    Yorumu: BUYUK = model bir sey secebildi (tepede belirgin bir aday var).
            ~0   = hepsi ayni, model "bilmiyorum" diyor.

    girdi : araclar._getir_kirp ciktisi — her dict'te '_skor' var
    cikti : float
    """
    if not sonuclar:
        # Bos liste: olculecek bant yok. nan, auc()'un bos grupta yaptiginin aynisi —
        # 0.0 donmek "bant yok, model bilmiyor" diye OKUNUR ve sinyali sessizce bozar.
        return float("nan")
    skorlar = np.array([x["_skor"] for x in sonuclar])
    return float(skorlar.max() - np.median(skorlar))


def benzerlik(sonuclar: list[dict]) -> float:
    """Getirilen sonuclarin BIRBIRINE ortalama ikili kosinus benzerligi.

    Ne olcuyor: 5 sonuc birbirinin ayni sey mi? Franchise tekillestirme (kimlik)
    bunu yakalayamaz — bes FARKLI voleybol animesi ayri kayitlardir ama kullanici
    bakinca "hepsi ayni sey" der. Bu sinyal kimlige degil ANLAMA bakiyor.

    Yorumu: YUKSEK = liste dar bir bolgeye sikismis (cesitlilik yok).
            DUSUK  = sonuclar dagilmis (ya zengin bir liste, ya da model odaklanamamis).
            Iki okumasi da var — hangisinin dogru oldugu OLCUMDEN cikacak.

    Kullanacagin malzeme:
        _, V, _, _ = retrieval._hazirla()   # V: (12104, 1024), satirlar NORMALIZE
        V[kayit["_idx"]]                    # bir sonucun vektoru
        V normalize oldugu icin kosinus = nokta carpimi (np.dot), bolme YOK.

    n sonuc icin kac ikili var? Kendini kendisiyle ve ayni cifti iki kez sayma.

    girdi : araclar._getir_kirp ciktisi — her dict'te '_idx' var
    cikti : float
    """
    if len(sonuclar) < 2:
        # Tek (ya da sifir) sonucta ikili benzerlik TANIMSIZ: n*(n-1) = 0.
        # getir() k'dan AZ kayit donebiliyor (aday havuzu tekillestirmeden sonra
        # tukenirse) ve araclar.ara k'yi modele birakiyor — yani bu hal erisilebilir.
        return float("nan")
    _, V, _, _ = retrieval._hazirla()
    vektorler = np.array([V[x["_idx"]] for x in sonuclar])
    benzerlikler = np.dot(vektorler, vektorler.T)
    np.fill_diagonal(benzerlikler, 0)
    return float(benzerlikler.sum() / (len(sonuclar) * (len(sonuclar) - 1)))

if __name__ == "__main__":
    # elle deneme: python sinyaller.py
    import araclar

    for sorgu in [
        "psikolojik gerilim, ahlaki ikilem, seri katil takibi",
        "zzzz qwerty asdf",          # kasten anlamsiz — sinyaller farkli mi?
    ]:
        s = araclar._getir_kirp(sorgu, k=5)
        print(f"\n{sorgu!r}")
        for x in s:
            print(f"  {x['_skor']:.3f}  {x['baslik']}")
        print(f"  -> skor_bandi = {skor_bandi(s)}")
        print(f"  -> benzerlik  = {benzerlik(s)}")
