"""Open Library'den kitap corpus'u ceker (Google Books'un yerine).

NEDEN KAYNAK DEGISTI (2026-09-10 olcumu):
    Google Books `subject:` sorgusu konu basina ~100 sonucta TUKENIYOR
    (startIndex 200'de bos donuyor). 10 konu x 240 hedef = 497 kitap; 5000 icin
    ~180 konu gerekirdi ve o noktada corpus rastgelesir. Ayrica GB birimi BASKI,
    ayni kitap onlarca id ile geliyor.
    Open Library ESER (work) seviyesinde: mystery 5837, fantasy 14661,
    science fiction 21208 eser. Aciklama kapsami 3000. sirada bile %88-95,
    ortalama ~600 karakter (mevcut corpus'un belge ortalamasi 583 — hizali).

TASARIM:
  - iki uc: /subjects/<konu>.json listeler, /works/<id>.json aciklamayi verir
  - aciklamasiz eser YAZILMAZ (gomulemez = gurultu)
  - tur alani SUZULUR: OL'in ham subjects'i katalog cop'u iceriyor
    ("Manners and customs", "British and irish fiction"). Anime/film tur
    sozlugune eslenenler tutulur -> uc medya AYNI tur kelimelerini konusur.
  - kesilebilir: dosyadaki work id'leri atlanir

Kullanim:
    python scripts/cek_openlibrary.py                # 5000 hedef
    python scripts/cek_openlibrary.py --hedef 10000
"""

import argparse
import collections
import json
import re
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

TABAN = "https://openlibrary.org"
CIKTI = config.VERI / "books_openlibrary.jsonl"
ISCI = 12          # es zamanli detay istegi. OL kar amaci gutmuyor — nazik ol.
SAYFA = 100        # /subjects listeleme sayfa boyu

# Kullanicinin sordugu TEMALAR — kutuphane rafi etiketleri degil.
KONULAR = [
    "mystery", "thriller", "fantasy", "science_fiction", "horror",
    "historical_fiction", "romance", "psychological_fiction", "detective_and_mystery_stories",
    "adventure", "war_stories", "dystopia", "coming_of_age", "magic", "crime",
]

# Anime (AniList) + film (TMDB) tur sozlugunun birlesimi. Kitaplar da BU
# kelimeleri konusacak — capraz medya eslesmesi ortak kelime dagarcigina dayaniyor.
TURLER = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama",
    "Family", "Fantasy", "History", "Horror", "Mecha", "Music", "Mystery",
    "Psychological", "Romance", "Sci-Fi", "Slice of Life", "Sports",
    "Supernatural", "Thriller", "War", "Western",
]
# Anime sozlugu TEMEL alindi (Deniz, 2026-09-10): corpus'un cogunlugu anime, film
# turleri zaten yakin. Bu yuzden "Sci-Fi", "Science Fiction" degil.

# OL etiketlerinde gecen bicimler -> kanonik TUR. Duz alt-dizi YETMIYOR, iki yonlu bozuk:
#   fazla eslesir : "war" ⊂ "Edward", "Warsaw", "warfare"
#   az eslesir    : "history" ⊄ "historical"  ('y' yok)
# Cozum: KELIME SINIRI ile ara + varyantlari burada topla.
TAKMA_AD = {
    "historical": "History", "history": "History",
    "detective": "Mystery", "mystery": "Mystery", "whodunit": "Mystery",
    "science fiction": "Sci-Fi", "sci-fi": "Sci-Fi", "scifi": "Sci-Fi",
    "dystopia": "Sci-Fi", "dystopian": "Sci-Fi", "space opera": "Sci-Fi",
    "fantasy": "Fantasy", "magic": "Fantasy", "fairy tale": "Fantasy",
    "psychological": "Psychological",
    "thriller": "Thriller", "suspense": "Thriller",
    "horror": "Horror", "ghost": "Horror", "vampire": "Supernatural",
    "supernatural": "Supernatural", "occult": "Supernatural",
    "romance": "Romance", "love stories": "Romance",
    "crime": "Crime", "criminal": "Crime",
    "war": "War", "wars": "War", "military": "War",
    "western": "Western", "cowboy": "Western",
    "adventure": "Adventure", "quest": "Adventure",
    "humor": "Comedy", "humorous": "Comedy", "comedy": "Comedy", "satire": "Comedy",
    "coming of age": "Drama", "bildungsromans": "Drama", "drama": "Drama",
    "domestic fiction": "Drama", "family": "Family",
    "sports": "Sports", "action": "Action", "music": "Music", "musicians": "Music",
    "biography": "Documentary", "true crime": "Crime",
    # biography->Documentary bir KOPRU eslemesi, birebir karsilik degil (Deniz, 09-10):
    # nis bir tur ve dystopia->Sci-Fi ile ayni turden bir yaklastirma. Tutarli olsun.
}

# Konu adi -> TUR (hicbir subject eslesmezse geriye dusus). Deniz'in ilkesi:
# corpus'ta karsiligi OLMAYAN yeni bir kelime (ornegin "Dystopia") ASLA yazilmaz.
KONU_TUR = {
    "mystery": "Mystery", "thriller": "Thriller", "fantasy": "Fantasy",
    "science_fiction": "Sci-Fi", "horror": "Horror", "historical_fiction": "History",
    "romance": "Romance", "psychological_fiction": "Psychological",
    "detective_and_mystery_stories": "Mystery", "adventure": "Adventure",
    "war_stories": "War", "dystopia": "Sci-Fi", "coming_of_age": "Drama",
    "magic": "Fantasy", "crime": "Crime",
}

TAVAN = 5          # kitaplar ortalama 2.3 etiket aliyor (olculdu), tavan nadiren bagliyor

# Takma adlari uzundan kisaya dene: "science fiction" once, "fiction" sonra caksin diye.
_DESENLER = sorted(TAKMA_AD.items(), key=lambda kv: -len(kv[0]))

log = logging.getLogger("cek_ol")


def _turleri_esle(ham_subjects: list[str], aranan_konu: str) -> list[str]:
    """OL'in ham `subjects` listesini TURLER sozlugune esler.

    Girdi : ['Fiction', 'Punic War, 3rd, 149-146 B.C.', 'Fiction, historical, general',
             'Detective and mystery stories', 'Manners and customs']
    Cikti : ['War', 'History', 'Mystery']      <- OL'in SIRASI korunur, en fazla TAVAN tane

    Kurallar:
      - kucuk harfe cevir, KELIME SINIRIYLA ara (duz alt-dizi "Edward"i War yapiyordu)
      - varyantlar TAKMA_AD'da toplanir (historical->History, detective->Mystery)
      - sira OL'in verdigi sira: olculdu, tematik etiketler basta cikiyor
      - hicbiri eslesmezse KONU_TUR'den geriye dusus — corpus'ta olmayan yeni bir
        kelime asla yazilmaz (aksi halde o kelime yonunde 'dik' bir bilesen olusur
        ve kitap, anime/film komsulugundan uzaklasir)
    """
    bulunan: list[str] = []
    for ham in ham_subjects:
        metin = ham.lower()
        for kalip, tur in _DESENLER:
            if tur in bulunan:
                continue
            if re.search(rf"\b{re.escape(kalip)}\b", metin):
                bulunan.append(tur)
                if len(bulunan) >= TAVAN:
                    return bulunan
    if not bulunan:
        geri = KONU_TUR.get(aranan_konu)
        if geri:
            bulunan.append(geri)
    return bulunan


_yerel = threading.local()

# _detay'in "cekilemedi" hali. "aciklama yok" ile AYNI SEY DEGIL: birincisi BIZIM
# hatamiz (ag/kota), ikincisi verinin ozelligi. Ayni torbaya konursa gecici bir 429
# dalgasi "bu kitaplarin aciklamasi yok" diye raporlanir ve kayip gorunmez olur.
CEKILEMEDI = object()


def _oturum() -> requests.Session:
    """Is parcacigi BASINA bir oturum. requests.Session thread-safe DEGIL (cookie jar,
    redirect ve adapter durumu paylasilir); tek oturumu ISCI tane isciye vermek dusuk
    siklikli ve izsiz hatalar uretir — bozulan istek _detay'dan None olarak doner, o da
    "aciklama yok" diye sayilirdi."""
    s = getattr(_yerel, "oturum", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = "cross-media-recommender/0.1 (ds.denizsenol@gmail.com)"
        _yerel.oturum = s
    return s


def _liste(konu: str, offset: int) -> list[dict] | None:
    """Bir konunun eser listesinden bir sayfa.

    Konu bittiyse [] · dort denemede de cekilemediyse None. Ikisi AYRI SEY: birincisi
    havuzun sonu, ikincisi gecici bir ag hatasi. Ayni sayilirsa bir 503 dalgasi
    "konu tukendi" diye loglanir ve konu sessizce yarim kalir."""
    for deneme in range(4):
        try:
            r = _oturum().get(f"{TABAN}/subjects/{konu}.json",
                              params={"limit": SAYFA, "offset": offset}, timeout=30)
        except requests.RequestException as e:
            log.warning("%s @ %d istek hatasi: %s", konu, offset, e)
            time.sleep(2 ** deneme)
            continue
        if r.status_code == 200:
            return r.json().get("works", [])
        log.warning("%s @ %d durum %d", konu, offset, r.status_code)
        time.sleep(2 ** deneme)
    return None


def _detay(anahtar: str):
    """Eser detayindan (aciklama, ham_subjects).

    Aciklama yoksa None · istek dort denemede de tutmadiysa CEKILEMEDI. _liste gibi
    yeniden dener: 12 es zamanli istek atiyoruz, tek bir 429/503 yuzunden eseri
    "aciklamasiz" sayip atmak veriyi sessizce kaybetmek olur."""
    for deneme in range(4):
        try:
            r = _oturum().get(f"{TABAN}{anahtar}.json", timeout=30)
        except requests.RequestException as e:
            log.warning("%s istek hatasi: %s", anahtar, e)
            time.sleep(2 ** deneme)
            continue
        if r.status_code == 200:
            d = r.json()
            ozet = d.get("description")
            if isinstance(ozet, dict):   # OL bazen {"type":..., "value": "..."} doner
                ozet = ozet.get("value")
            ozet = (ozet or "").strip()
            if not ozet:
                return None
            return ozet, (d.get("subjects") or [])
        if r.status_code in (403, 404):  # kalici: eser yok / erisim kapali
            return None
        log.warning("%s durum %d", anahtar, r.status_code)
        time.sleep(2 ** deneme)
    return CEKILEMEDI


def mevcut_idler(yol: Path) -> tuple[set[str], collections.Counter]:
    """Dosyadaki work id'leri + KONU BASINA kayit sayisi.

    Konu sayaci sart: `kota` konu basina TOPLAM hedef, "bu kosunun hedefi" degil.
    Sayilmazsa kesilmis bir kosu yeniden baslatildiginda her konu kotayi BASTAN
    doldurur (yarim kalmis 300'luk bir konu 634'e cikar) ve --hedef asilir.
    Donen id'ler CIPLAK ('OL262454W') — dosyaya yazilan bicimin aynisi."""
    if not yol.exists():
        return set(), collections.Counter()
    idler = set()
    konu_sayaci = collections.Counter()
    with yol.open(encoding="utf-8") as f:
        for satir in f:
            if satir.strip():
                try:
                    kayit = json.loads(satir)
                    idler.add(kayit["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
                konu_sayaci[kayit.get("_arandigi_konu")] += 1
    return idler, konu_sayaci


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedef", type=int, default=5000, help="toplam hedef kitap sayisi")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    gorulen, konu_sayaci = mevcut_idler(CIKTI)
    kota = -(-args.hedef // len(KONULAR))          # konu basina, yukari yuvarla
    log.info("dosyada %d kitap var | hedef %d | %d konu x %d kota",
             len(gorulen), args.hedef, len(KONULAR), kota)

    yeni_toplam = atlanan_bos = cekilemeyen = 0

    # Havuz konu dongusunun DISINDA: sayfa basina yeni havuz kurmak ~750 kez 12 is
    # parcacigi acip kapatmak demekti. Oturum zaten is parcacigi basina (_oturum).
    havuz = ThreadPoolExecutor(max_workers=ISCI)
    with CIKTI.open("a", encoding="utf-8") as f, havuz:
        for konu in KONULAR:
            # Kota TOPLAM hedef, "bu kosunun hedefi" degil: dosyada o konudan kac kayit
            # varsa sayaci ORADAN baslat. 0'dan baslamak, kesilmis bir kosuyu her yeniden
            # baslatista kotayi BASTAN doldurmaya cevirir ve --hedef asilir.
            konu_yeni, offset = konu_sayaci.get(konu, 0), 0
            if konu_yeni >= kota:
                log.info("%-28s kota dolu (%d/%d), atlandi", konu, konu_yeni, kota)
                continue
            while konu_yeni < kota:
                eserler = _liste(konu, offset)
                if eserler is None:               # cekilemedi != konu bitti
                    log.error("%s: liste %d CEKILEMEDI — konu YARIM kaldi, tekrar kos",
                              konu, offset)
                    break
                if not eserler:
                    log.info("%s: liste %d'de bitti", konu, offset)
                    break
                offset += SAYFA

                # Karsilastirma CIPLAK id ile: mevcut_idler dosyadan ciplak id okuyor,
                # w["key"] ise "/works/OL262454W". Ikisi esitlenmezse dosyadaki hicbir
                # kayit "gorulmus" sayilmaz ve resume her seyi yeniden yazar.
                adaylar = [w for w in eserler
                           if w.get("key") and w["key"].rsplit("/", 1)[-1] not in gorulen]
                if not adaylar:
                    continue

                t0 = time.time()
                detaylar = list(havuz.map(_detay, [w["key"] for w in adaylar]))

                yazilan = 0
                for w, det in zip(adaylar, detaylar):
                    if det is CEKILEMEDI:         # ag/kota hatasi: "aciklamasiz" DEGIL
                        cekilemeyen += 1
                        continue
                    if det is None:
                        atlanan_bos += 1
                        continue
                    ozet, ham_subjects = det
                    ol_id = w["key"].rsplit("/", 1)[-1]          # OL262458W
                    kayit = {
                        "id": ol_id,
                        "media": "kitap",
                        "title": w.get("title") or "",
                        "overview": ozet,
                        "genres": _turleri_esle(ham_subjects, konu),
                        # HAM veri saklanir: tur eslemesi degisince corpus YENIDEN
                        # CEKILMESIN, sadece yeniden hesaplansin. (~200 bayt/kayit)
                        "_ham_subjects": ham_subjects,
                        "_arandigi_konu": konu,
                        "authors": [a.get("name", "") for a in (w.get("authors") or [])],
                        "published_date": str(w.get("first_publish_year") or ""),
                        "edition_count": w.get("edition_count", 0),
                    }
                    f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
                    gorulen.add(ol_id)
                    konu_yeni += 1
                    yeni_toplam += 1
                    yazilan += 1
                    if konu_yeni >= kota:
                        break
                f.flush()
                log.info("%-28s +%-3d (konu %d/%d, toplam %d) %.1f eser/sn",
                         konu, yazilan, konu_yeni, kota, yeni_toplam,
                         len(adaylar) / max(time.time() - t0, 0.01))

    log.info("BITTI: %d yeni kitap | %d aciklamasiz atlandi | %d CEKILEMEDI | dosya %s",
             yeni_toplam, atlanan_bos, cekilemeyen, CIKTI)
    if cekilemeyen:
        log.warning("%d eser ag/kota hatasi yuzunden ALINAMADI — bunlar 'aciklamasiz' "
                    "degil, kayip. Tekrar kosmak onlari yeniden dener.", cekilemeyen)


if __name__ == "__main__":
    main()
