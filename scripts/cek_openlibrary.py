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
import json
import re
import logging
import sys
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


def _oturum() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "cross-media-recommender/0.1 (ds.denizsenol@gmail.com)"
    return s


def _liste(oturum, konu: str, offset: int) -> list[dict]:
    """Bir konunun eser listesinden bir sayfa. Hata/bos -> []."""
    for deneme in range(4):
        try:
            r = oturum.get(f"{TABAN}/subjects/{konu}.json",
                           params={"limit": SAYFA, "offset": offset}, timeout=30)
        except requests.RequestException as e:
            log.warning("%s @ %d istek hatasi: %s", konu, offset, e)
            time.sleep(2 ** deneme)
            continue
        if r.status_code == 200:
            return r.json().get("works", [])
        log.warning("%s @ %d durum %d", konu, offset, r.status_code)
        time.sleep(2 ** deneme)
    return []


def _detay(oturum, anahtar: str) -> tuple[str, list[str]] | None:
    """Eser detayindan (aciklama, ham_subjects). Aciklama yoksa None."""
    try:
        r = oturum.get(f"{TABAN}{anahtar}.json", timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    d = r.json()
    ozet = d.get("description")
    if isinstance(ozet, dict):           # OL bazen {"type":..., "value": "..."} doner
        ozet = ozet.get("value")
    ozet = (ozet or "").strip()
    if not ozet:
        return None
    return ozet, (d.get("subjects") or [])


def mevcut_idler(yol: Path) -> set[str]:
    if not yol.exists():
        return set()
    idler = set()
    with yol.open(encoding="utf-8") as f:
        for satir in f:
            if satir.strip():
                try:
                    idler.add(json.loads(satir)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return idler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedef", type=int, default=5000, help="toplam hedef kitap sayisi")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    gorulen = mevcut_idler(CIKTI)
    kota = -(-args.hedef // len(KONULAR))          # konu basina, yukari yuvarla
    log.info("dosyada %d kitap var | hedef %d | %d konu x %d kota",
             len(gorulen), args.hedef, len(KONULAR), kota)

    oturum = _oturum()
    yeni_toplam = atlanan_bos = 0

    with CIKTI.open("a", encoding="utf-8") as f:
        for konu in KONULAR:
            konu_yeni, offset = 0, 0
            while konu_yeni < kota:
                eserler = _liste(oturum, konu, offset)
                if not eserler:
                    log.info("%s: liste %d'de bitti", konu, offset)
                    break
                offset += SAYFA

                adaylar = [w for w in eserler if w.get("key") and w["key"] not in gorulen]
                if not adaylar:
                    continue

                t0 = time.time()
                with ThreadPoolExecutor(max_workers=ISCI) as havuz:
                    detaylar = list(havuz.map(lambda w: _detay(oturum, w["key"]), adaylar))

                for w, det in zip(adaylar, detaylar):
                    if det is None:
                        atlanan_bos += 1
                        continue
                    ozet, ham_subjects = det
                    kayit = {
                        "id": w["key"].rsplit("/", 1)[-1],       # OL262458W
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
                    gorulen.add(w["key"])
                    konu_yeni += 1
                    yeni_toplam += 1
                    if konu_yeni >= kota:
                        break
                f.flush()
                log.info("%-28s +%-3d (konu %d/%d, toplam %d) %.1f eser/sn",
                         konu, len(adaylar), konu_yeni, kota, yeni_toplam,
                         len(adaylar) / max(time.time() - t0, 0.01))

    log.info("BITTI: %d yeni kitap | %d aciklamasiz atlandi | dosya %s",
             yeni_toplam, atlanan_bos, CIKTI)


if __name__ == "__main__":
    main()
