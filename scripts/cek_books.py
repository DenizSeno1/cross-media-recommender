"""Google Books'tan kitap metadata cekip diske DONDURUR (cross-media corpus).

Neden anahtarsiz: public 'volumes' arama ucu key istemez, gunluk kota tek
seferlik cekim icin fazlasiyla yeter (~birkac bin kitap ≈ ~80 istek). 403/429
gelirse backoff; israrci olursa key eklenir.

TMDB'den farki: Google Books "tumunu listele" demiyor, ARAMA tabanli.
O yuzden KONU konu cekeriz (q=subject:mystery ...), her konuda sayfalama.

Kural (faz4_todo.md): corpus bir kere cekilir, diske yazilir, bir daha cekilmez.
Tasarim: description'i BOS olan kitap YAZILMAZ (gomulemez = gurultu, Gun 3-4).

Cikti : faz4/data/books_google.jsonl
Devam : dosyadaki id'ler atlanir; ayni kitap birden cok konuda cikabilir -> tekil.

Kullanim:
    python faz4/faz4_gun8_9/cek_books.py
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

URL = "https://www.googleapis.com/books/v1/volumes"
CIKTI = Path(__file__).resolve().parents[1] / "data" / "books_google.jsonl"
KONULAR = [
    "fantasy", "science fiction", "mystery", "thriller", "horror",
    "romance", "drama", "historical fiction", "adventure", "psychological fiction",
]
SAYFA_BOYU = 40        # Google Books tavani
BEKLEME = 1.0          # anahtarsiz -> nazik ol
ZAMAN_ASIMI = 30

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s - %(message)s", stream=sys.stdout)
log = logging.getLogger("books")

# Anahtar opsiyonel AMA 2026-08-30 itibariyla pratikte zorunlu: anahtarsiz
# cagrilarda Google'in ortak projesinde "Queries per day" limiti 0 -> her
# istek 429. Anahtar https://console.cloud.google.com/apis/credentials
# uzerinden ucretsiz (Books API'yi etkinlestir), varsayilan 1000 istek/gun.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")


class KotaBitti(RuntimeError):
    """Kalici kota hatasi. Beklemek COZMEZ -> anahtar ekle ya da kaynagi degistir."""


def _hata_ayrinti(r) -> tuple[str, str]:
    """429/403 govdesinden (sebep, mesaj) cikarir. JSON degilse ham metin doner."""
    try:
        h = r.json().get("error", {})
        return (h.get("errors") or [{}])[0].get("reason", "?"), h.get("message", "")
    except ValueError:
        return "?", r.text[:200]


def istek(params: dict, deneme: int = 8):
    """Tek GET. 429/403(rateLimit)'te ustel bekleme, 5xx'te yeniden. Donus: json | None."""
    if _KEY:
        params = {**params, "key": _KEY}

    for i in range(deneme):
        try:
            r = requests.get(URL, params=params, timeout=ZAMAN_ASIMI)
        except requests.RequestException as e:
            log.warning("ag hatasi (%s), yeniden", e)
            time.sleep(2 ** i)
            continue

        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 403):        # 403 genelde rateLimitExceeded
            sebep, mesaj = _hata_ayrinti(r)
            # Anahtar YOKKEN gunluk kota sifir -> gecici degil, kalici. Bekleme
            # kuyrugunda 8 kez donmek hatayi gizler; hemen ve sebebiyle dur.
            if not _KEY:
                raise KotaBitti(
                    f"{r.status_code} {sebep}: {mesaj}. "
                    "Anahtarsiz Google Books kotasi 0. GOOGLE_BOOKS_API_KEY'i "
                    "faz4/.env icine ekle, ya da kaynagi Open Library'ye cevir."
                )
            bekle = 2 ** (i + 1)
            log.warning("rate limit (%d) %s: %s | %d sn bekleniyor",
                        r.status_code, sebep, mesaj[:160], bekle)
            time.sleep(bekle)
            continue
        if 500 <= r.status_code < 600:
            # 2026-08-30 olcumu: Books backend'i isteklerin ~yarisina 503
            # "backendFailed" donuyor, parametreden bagimsiz ve anlik.
            # Hemen yeniden denemek ise yariyor -> bekleme kisa tutuluyor
            # (2**i burada 128 sn'ye kadar cikiyordu, bosuna).
            sebep, mesaj = _hata_ayrinti(r)
            bekle = min(2 ** i, 5)
            log.warning("sunucu hatasi %d %s (%s), %d sn sonra yeniden",
                        r.status_code, sebep, mesaj[:80], bekle)
            time.sleep(bekle)
            continue

        log.error("beklenmeyen durum %d: %s", r.status_code, r.text[:200])
        return None
    return None


def mevcut_idler(yol: Path) -> set[str]:
    """Dosyada zaten yazili kitap id'leri (devam + konular arasi tekilleme)."""
    if not yol.exists():
        return set()
    idler = set()
    with yol.open(encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                try:
                    idler.add(json.loads(satir)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return idler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--konu-basi", type=int, default=240, help="konu basina hedef kitap sayisi")
    args = ap.parse_args()

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    gorulen = mevcut_idler(CIKTI)
    log.info("dosyada zaten %d kitap var -> %s", len(gorulen), CIKTI)

    yeni = atlanan_bos = 0
    with CIKTI.open("a", encoding="utf-8") as f:
        for konu in KONULAR:
            konu_yeni = 0
            for baslangic in range(0, args.konu_basi, SAYFA_BOYU):
                veri = istek({
                    "q": f"subject:{konu}",
                    "startIndex": baslangic,
                    "maxResults": SAYFA_BOYU,
                    "printType": "books",
                    "langRestrict": "en",
                    # orderBy YOK: varsayilani zaten "relevance", ama acikca
                    # gonderildiginde olcumde 6/6 503 verdi (2026-08-30).
                })
                if veri is None:
                    log.error("'%s' baslangic %d alinamadi, sonraki konuya geciliyor", konu, baslangic)
                    break
                ogeler = veri.get("items", [])
                if not ogeler:                       # bu konuda daha fazla sonuc yok
                    break

                for o in ogeler:
                    kid = o.get("id")
                    if not kid or kid in gorulen:    # konular arasi tekrar -> atla
                        continue
                    vi = o.get("volumeInfo", {})
                    aciklama = (vi.get("description") or "").strip()
                    if not aciklama:                 # sinopsissiz kitap gomulemez -> atla
                        atlanan_bos += 1
                        continue
                    kategoriler = vi.get("categories") or [konu.title()]  # yoksa arandigi konu
                    kayit = {
                        "id": kid,
                        "media": "kitap",            # birlesik corpus'ta kaynak etiketi
                        "title": vi.get("title") or "",
                        "overview": aciklama,
                        "genres": kategoriler,
                        "authors": vi.get("authors") or [],
                        "published_date": vi.get("publishedDate"),
                        "average_rating": vi.get("averageRating"),
                    }
                    f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
                    gorulen.add(kid)
                    yeni += 1
                    konu_yeni += 1
                f.flush()
                time.sleep(BEKLEME)

            log.info("'%s' bitti: bu konuda %d yeni | toplam %d (bos: %d)",
                     konu, konu_yeni, len(gorulen), atlanan_bos)

    log.info("BITTI. bu kosuda %d yeni, dosyada toplam %d (bos description atlanan: %d)",
             yeni, len(gorulen), atlanan_bos)


if __name__ == "__main__":
    main()
