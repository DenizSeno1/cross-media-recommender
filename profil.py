"""Kullanici zevk profili — MAL XML export'undan tercih vektoru.

Gun 5-7'de kanitlandi: tek ortalama profil cesitliligi yutuyor (oneriler hep romcom
cikti), K-means ile zevk adalari ayrisinca duzeldi. Bu dosya once TEK ortalamayi
kuruyor (basit hal); K-means stretch olarak duruyor.

TASARIM KARARLARI (Deniz, 2026-09-04):
  - Profil sorguyla HARMANLANIR, ayri bir mod degil. Agirlik `profil_agirligi`
    (0=sadece sorgu, 1=sadece profil). Varsayilan 0.6 -> profil biraz baskin.
  - Isim `alpha` DEGIL `profil_agirligi`: yonu isminden anlasilmayan parametre hata
    fabrikasidir (ilk yazimda tam bu karistirildi).
  - Harman HyDE PUSULASIYLA yapilir, ham sorgu vektoruyle degil — ham sorgu tek
    basina recall 0 veriyordu (Gun 3-4), zayif vektorle ortaklik kurulmaz.
  - Profil yoksa (kullanici listesini yuklemediyse) sistem duz sorgu aramasina duser.
    Kisisellestirme opsiyonel bir KATMAN, urunun onsuz da calismasi gerekiyor.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

import config

# Kullanicinin GORDUGU animeler: bunlar aday havuzundan CIKARILIR (izledigini yeniden
# onermeyiz). "Plan to Watch" haric — o daha izlenmemis, onerilebilir.
IZLENEN_DURUMLAR = {"Completed", "Watching", "Dropped"}


def liste_yukle(xml_yolu: Path | str | None = None) -> list[dict]:
    """MAL XML export -> [{idMal, baslik, puan, durum}, ...]  (BOILERPLATE, Gun 5-7'den)

    series_animedb_id = MAL id -> corpus'un idMal'iyle birebir eslesir.
    my_score 0-10 (0 = puanlanmamis). my_status = Completed/Watching/Dropped/Plan to Watch.
    """
    if xml_yolu is not None and not isinstance(xml_yolu, (str, Path)):
        kaynak = xml_yolu                           # dosya-benzeri (Streamlit uploader)
    else:
        yol = Path(xml_yolu) if xml_yolu else config.XML_LISTE
        if not yol.exists():
            return []                               # profil yok -> duz sorgu aramasi
        kaynak = yol
    kok = ET.parse(kaynak).getroot()
    return [{
        "idMal": int(a.findtext("series_animedb_id")),
        "baslik": a.findtext("series_title"),
        "puan": int(a.findtext("my_score", "0")),
        "durum": a.findtext("my_status"),
    } for a in kok.findall("anime")]


def izlenen_idler(liste: list[dict]) -> set[int]:
    """Izlenen (Completed/Watching/Dropped) idMal kumesi -> aday havuzu filtresi."""
    return {a["idMal"] for a in liste if a["durum"] in IZLENEN_DURUMLAR}


def cekirdek_idler(liste: list[dict], corpus_idmal: set[int], min_puan: int = 8) -> list[int]:
    """Profil malzemesi: corpus'ta olan + min_puan+ puanli animelerin idMal'leri.

    Neden 8+: profil "begendiklerin"den kurulmali, izlediklerinden degil. Esik dusurulurse
    profil ortalamaya kayar (herkesin izledigi seyler), yukseltilirse cekirdek cok kucuk kalir.
    """
    return [a["idMal"] for a in liste
            if a["puan"] >= min_puan and a["idMal"] in corpus_idmal]


# ---------------------------------------------------------------------------
# SENIN YAZACAGIN KISIM — asagidaki iki fonksiyon
# ---------------------------------------------------------------------------


def profil_vektoru(V: np.ndarray, satirlar: list[int]) -> np.ndarray:
    """Zevk vektoru: cekirdek animelerin embedding'lerinin ortalamasi, normalize edilmis.

    V        : (12104, 1024) birlesik index — V[i] corpus[i]'nin vektoru
    satirlar : cekirdek animelerin V'deki satir numaralari, orn. [12, 480, 3301, ...]
    Donus    : (1024,) birim vektor  (|v| = 1)

    Gun 5-7'de yazdin, retest. Mean pooling'in bir ust katmani: token->vektor yerine
    anime->zevk.
    """
    vektor = np.mean(V[satirlar], axis=0)  
    vektor = vektor / np.linalg.norm(vektor)
    return vektor 


def harmanla(pusula: np.ndarray, profil: np.ndarray, profil_agirligi: float) -> np.ndarray:
    """HyDE pusulasi ile zevk vektorunu agirlikli harmanla, normalize et.

    pusula          : (1024,) birim vektor — HyDE'nin urettigi arama vektoru
    profil          : (1024,) birim vektor — profil_vektoru() ciktisi
    profil_agirligi : 0.0 = sadece pusula (kisisellestirme yok)
                      1.0 = sadece profil (sorgu yok sayilir)
                      0.6 = varsayilan, profil biraz baskin
    Donus           : (1024,) birim vektor

    NOT: iki birim vektorun agirlikli toplami birim DEGILDIR -> normalize sart
    (kosinus benzerligi birim vektor varsayiyor). _hyde_vektor'daki ile ayni adim.
    """
    vektor = (1 - profil_agirligi) * pusula + profil_agirligi * profil
    vektor = vektor / np.linalg.norm(vektor)
    return vektor

def zevk_adalari(V: np.ndarray, satirlar: list[int], k: int = 10) -> np.ndarray:
    """Cekirdek vektorleri K kumeye ayir, merkezleri NORMALIZE edip dondur.

    Donus: (k, 1024) — her satir bir zevk adasi, birim vektor.
    random_state=42 (tekrarlanabilirlik). K-means Oklid ortalamasi verir,
    birim degildir -> satir bazinda normalize sart.
    """
    if len(satirlar) < k:
        # 3 cekirdekten 3 "zevk adasi" cikarmak olcum gibi gorunen bir uydurma olurdu.
        # Cagiran taraf bunu yakalayip profili tamamen kapatir (bkz. MIN_CEKIRDEK).
        raise ValueError(f"cekirdek ({len(satirlar)}) < ada sayisi ({k})")
    kmeans = KMeans(n_clusters=k, random_state=42).fit(V[satirlar])
    merkezler = kmeans.cluster_centers_
    merkezler = merkezler / np.linalg.norm(merkezler, axis=1, keepdims=True)
    return merkezler


def en_yakin_ada(merkezler: np.ndarray, pusula: np.ndarray) -> np.ndarray:
    """Pusulaya en cok hizalanan adayi dondur.

    merkezler: (k, 1024) birim vektorler
    pusula   : (1024,) birim vektor
    Donus    : (1024,) — secilen adanin kendisi (indeks degil, vektor)
    """
    benzerlikler = np.dot(merkezler, pusula)
    en_yakin_indeks = np.argmax(benzerlikler)
    return merkezler[en_yakin_indeks]

# "Ayni seri" sayilan kenar tipleri (Deniz'in karari: CHARACTER ve OTHER haric).
# CHARACTER/OTHER disarida cunku gruplama GECISLI: A-B, B-C, C-D baglantilari tek gruba
# toplanir. "Ortak karakter" gevsek bir kenar; bir crossover corpus'un yarisini tek
# franchise sanmaniza yol acabilir.
SERI_ILISKILERI = {
    "SEQUEL", "PREQUEL", "PARENT", "SIDE_STORY",
    "ALTERNATIVE", "SPIN_OFF", "SUMMARY", "COMPILATION", "CONTAINS",
}


def seri_gruplari(relations: list[dict]) -> dict[int, int]:
    """Bagli bilesenleri bul: her AniList id'sine bir grup numarasi ata.

    relations : cek_anilist_relations.py ciktisi
                [{"id": 154587, "idMal": 52991, "relations": [{"tip","id","idMal"}, ...]}, ...]
    Donus     : {anilist_id: grup_no}  — ayni seride olanlar ayni numarayi alir

    Iki asama: once komsuluk tablosu (kim kimle bagli), sonra gezme (bagli olan her seyi topla).
    """
    # --- 1) komsuluk tablosu, CIFT YONLU ---
    # AniList kenarlari tek yonlu verebiliyor: A'nin kaydinda "SEQUEL -> B" yazarken
    # B'nin kaydinda "PREQUEL -> A" olmayabilir. Iki yonu de yazarsak zincir kopmaz.
    komsu: dict[int, set[int]] = {}
    for kayit in relations:
        a = kayit["id"]
        komsu.setdefault(a, set())                  # iliskisi olmayan da tabloda dursun
        for r in kayit.get("relations", []):
            if r["tip"] not in SERI_ILISKILERI:
                continue
            b = r["id"]
            komsu.setdefault(b, set())
            komsu[a].add(b)
            komsu[b].add(a)

    # --- 2) gezme: her baslangictan ulasilabilen HER SEYI ayni gruba koy ---
    # `grup` ayni zamanda "ziyaret edildi" kaydi — ayri bir set tutmaya gerek yok.
    grup: dict[int, int] = {}
    grup_no = 0
    for baslangic in komsu:
        if baslangic in grup:                       # zaten bir gruba dahil edilmis
            continue
        grup_no += 1
        yigin = [baslangic]
        while yigin:                                # kuyruk/yigin bosalana kadar ac
            d = yigin.pop()
            if d in grup:
                continue
            grup[d] = grup_no
            yigin.extend(komsu[d] - grup.keys())    # HENUZ atanmamis komsulari sıraya ekle
    return grup


def iliskiler_yukle() -> list[dict]:
    """Dondurulmus relations dosyasi. Yoksa bos liste -> seri filtresi devre disi."""
    yol = config.VERI / "anime_relations.jsonl"
    if not yol.exists():
        return []
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").split(chr(10)) if s.strip()]


def izlenen_seri_maskesi(corpus: list[dict], izlenen: set[int],
                         grup: dict[int, int]) -> np.ndarray:
    """(12104,) bool dizi — True = bu kayit, izledigin bir seriyle AYNI grupta.

    corpus  : veri.corpus_yukle() ciktisi (uc medya karisik)
    izlenen : izlenen_idler() ciktisi — MAL id'leri (idMal)
    grup    : seri_gruplari() ciktisi — {AniList id: grup_no}
    Donus   : skorlara -inf yazmak icin maske (dunku medya filtresiyle ayni desen)
    """
    # grup.get: relations dosyasi yoksa `grup` bos gelir -> KeyError yerine zarif dusus.
    # (Cagiran taraf uyari basar; sessizce devre disi kalmasi fazin 1 numarali temasi olurdu.)
    izlenen_gruplar = {grup.get(m["id"]) for m in corpus
                       if m["media"] == "anime" and m["idMal"] in izlenen} - {None}
    return np.array([m["media"] == "anime" and grup.get(m["id"]) in izlenen_gruplar for m in corpus], dtype=bool)

# Profil kurmak icin gereken en az cekirdek. Altinda kisisellestirme KAPANIR:
# 5 animeden "zevk profili" cikarmak, olcum gibi gorunen bir uydurmadir.
MIN_CEKIRDEK = 20


def kota_olcekle(kota: dict[str, int], k: int) -> dict[str, int]:
    '''Kotayi k+ya orantili olcekle. KOTA bir ORAN tanimi, mutlak sayi degil.

    {"anime":3,"film":1,"kitap":1} + k=5  -> {"anime":3,"film":1,"kitap":1}
    ayni kota                     + k=10 -> {"anime":6,"film":2,"kitap":2}

    Neden oran: k arayuzden degisiyor (app.py slider 1-10). Mutlak kota k=10+da ilk 5
    slotu sekillendirip gerisini serbest birakiyordu — kota k buyudukce etkisizlesiyordu.
    Yuvarlamadan artan/eksilen slot en buyuk paya (anime) gider.
    '''
    toplam = sum(kota.values())
    olcekli = {m: max(1, round(k * n / toplam)) for m, n in kota.items()}
    fark = k - sum(olcekli.values())
    if fark:
        en_buyuk = max(olcekli, key=olcekli.get)
        olcekli[en_buyuk] = max(1, olcekli[en_buyuk] + fark)
    return olcekli


def kota_sec(sirali_idx: list[int], corpus: list[dict], grup: dict[int, int],
             k: int, kota: dict[str, int] | None = None) -> list[int]:
    """Sirali adaylardan sec: her seriden EN IYI olani + medya basina kota.

    sirali_idx : skora gore azalan siralanmis corpus indeksleri
    kota       : {"anime": 3, "film": 1, "kitap": 1} — None ise sadece seri tekillestirme
                 (medya filtresi seciliyken kota anlamsiz, hepsi ayni medyadan)
    Donus      : en fazla k indeks, hicbiri ayni seri grubunda degil

    Film/kitap `grup`ta yok -> her biri benzersiz sayilir.

    IKI TUR: 1. turda kotaya uyulur; k dolmadiysa 2. turda kalanlar sirayla eklenir.
    Neden doldurma: k kullaniciya verilen bir soz. Kitap corpus'u INCEYDI (Google Books,
    497, fantastik dilimine sikismis); Open Library'ye gecisle 4794'e cikti ama kural ayni
    kaliyor — bir VERI sinirini kullanicinin eksik sonuc gormesine cevirmemeli.
    Kota bir HEDEF, garanti degil. (Deniz'in `seri_tekillestir`inin genisletilmis hali.)
    """
    if k <= 0:
        return []

    secilen: list[int] = []
    secilen_kume: set[int] = set()          # `in` kontrolu O(1) olsun
    secilen_gruplar: set[int] = set()
    sayac: dict[str, int] = {}

    for kotaya_uy in (True, False):         # 1. tur: kota · 2. tur: bosluk doldurma
        if len(secilen) == k:
            break
        for idx in sirali_idx:
            if len(secilen) == k:
                break
            if idx in secilen_kume:
                continue
            kayit = corpus[idx]
            medya = kayit.get("media")

            grup_no = grup.get(kayit["id"]) if medya == "anime" else None
            if grup_no is not None and grup_no in secilen_gruplar:
                continue                    # bu seriden zaten bir temsilci var

            if kotaya_uy and kota is not None and sayac.get(medya, 0) >= kota.get(medya, 0):
                continue                    # bu medyanin kotasi dolu (2. turda bakilmaz)

            if grup_no is not None:
                secilen_gruplar.add(grup_no)
            sayac[medya] = sayac.get(medya, 0) + 1
            secilen.append(idx)
            secilen_kume.add(idx)

    return secilen


if __name__ == "__main__":
    import veri

    liste = liste_yukle()
    corpus = veri.corpus_yukle()
    idmal_satir = {m["idMal"]: i for i, m in enumerate(corpus) if m["media"] == "anime"}

    izlenen = izlenen_idler(liste)
    cekirdek = cekirdek_idler(liste, set(idmal_satir))
    print(f"liste: {len(liste)} anime | izlenen (havuzdan cikacak): {len(izlenen)}")
    print(f"profil cekirdegi (8+ puan, corpus'ta): {len(cekirdek)}")
    print("ornek:", [veri.baslik(corpus[idmal_satir[i]]) for i in cekirdek[:5]])
