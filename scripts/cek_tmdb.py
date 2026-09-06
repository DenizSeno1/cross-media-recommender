"""TMDB'den populer filmleri cekip diske DONDURUR (cross-media corpus).

Neden TMDB (Jikan degil): TMDB resmi bir REST API, kendi verisini kendisi
servis ediyor -> "olcumu buna dayandirabilir miyim" testini geciyor (Gun 0 dersi).

Kural (faz4_todo.md): corpus bir kere cekilir, diske yazilir, bir daha cekilmez.

Tasarim karari: overview'i BOS olan film YAZILMAZ -- sinopsissiz film gomulemez,
indekste sadece gurultu olur (Gun 3-4: bos/yanlis veri = gurultu).

Cikti : faz4/data/movies_tmdb.jsonl   (satir basina bir film)
Devam : dosyadaki id'ler atlanir; yarida kesilirse kaldigi yerden devam.

Kullanim:
    python faz4/faz4_gun8_9/cek_tmdb.py --sayfa 125     # ~2500 film (20/sayfa)
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

BASE = "https://api.themoviedb.org/3"
CIKTI = Path(__file__).resolve().parents[1] / "data" / "movies_tmdb.jsonl"
BEKLEME = 0.25         # TMDB nazik kullanim; kota degil, saygi
ZAMAN_ASIMI = 30

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
_KEY = os.environ.get("TMDB_API_KEY")
if _KEY is None:
    raise RuntimeError("TMDB_API_KEY bulunamadi. faz4/.env icine yaz.")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s - %(message)s", stream=sys.stdout)
log = logging.getLogger("tmdb")


HEADERS = {"Authorization": f"Bearer {_KEY}", "accept": "application/json"}


def istek(yol: str, params: dict, deneme: int = 8):
    """Tek GET. 429'da Retry-After'a saygi, 5xx'te ustel bekleme. Donus: json | None."""
    for i in range(deneme):
        try:
            r = requests.get(f"{BASE}{yol}", params=params, headers=HEADERS, timeout=ZAMAN_ASIMI)
        except requests.RequestException as e:
            log.warning("%s ag hatasi (%s), yeniden", yol, e)
            time.sleep(2 ** i)
            continue

        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            bekle = int(r.headers.get("Retry-After", 10))
            log.warning("%s rate limit (429), %d sn bekleniyor", yol, bekle)
            time.sleep(bekle + 1)
            continue
        if 500 <= r.status_code < 600:
            log.warning("%s sunucu hatasi %d, yeniden", yol, r.status_code)
            time.sleep(2 ** i)
            continue

        log.error("%s beklenmeyen durum %d: %s", yol, r.status_code, r.text[:200])
        return None
    return None


def tur_haritasi() -> dict[int, str]:
    """genre_id -> tur adi. discover sadece sayisal id doner, isim burada eslenir."""
    veri = istek("/genre/movie/list", {"language": "en-US"})
    if veri is None:
        raise RuntimeError("tur listesi alinamadi")
    return {g["id"]: g["name"] for g in veri["genres"]}


def mevcut_idler(yol: Path) -> set[int]:
    """Dosyada zaten yazili film id'leri (devam edebilmek icin)."""
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
    ap.add_argument("--sayfa", type=int, default=125, help="cekilecek azami sayfa (20 film/sayfa)")
    args = ap.parse_args()

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    turler = tur_haritasi()
    log.info("%d tur yuklendi", len(turler))
    gorulen = mevcut_idler(CIKTI)
    log.info("dosyada zaten %d film var -> %s", len(gorulen), CIKTI)

    yeni = atlanan_bos = 0
    with CIKTI.open("a", encoding="utf-8") as f:
        for sayfa in range(1, args.sayfa + 1):
            veri = istek("/discover/movie", {
                "sort_by": "popularity.desc",
                "include_adult": "false",
                "language": "en-US",
                "page": sayfa,
            })
            if veri is None:
                log.error("sayfa %d alinamadi, durduruluyor. Tekrar calistir, kayitlar korunur.", sayfa)
                break

            for m in veri["results"]:
                if m["id"] in gorulen:
                    continue
                overview = (m.get("overview") or "").strip()
                if not overview:                        # sinopsissiz film gomulemez -> atla
                    atlanan_bos += 1
                    continue
                kayit = {
                    "id": m["id"],
                    "media": "film",                    # birlesik corpus'ta kaynak etiketi
                    "title": m.get("title") or m.get("original_title") or "",
                    "overview": overview,
                    "genres": [turler[g] for g in m.get("genre_ids", []) if g in turler],
                    "release_date": m.get("release_date"),
                    "vote_average": m.get("vote_average"),
                    "popularity": m.get("popularity"),
                }
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
                gorulen.add(m["id"])
                yeni += 1
            f.flush()

            if sayfa % 10 == 0:
                log.info("sayfa %d/%d, toplam %d film (bos atlanan: %d)",
                         sayfa, args.sayfa, len(gorulen), atlanan_bos)
            if sayfa >= veri.get("total_pages", sayfa):
                log.info("son sayfa (total_pages=%d), bitti", veri.get("total_pages"))
                break
            time.sleep(BEKLEME)

    log.info("BITTI. bu kosuda %d yeni, dosyada toplam %d (bos overview atlanan: %d)",
             yeni, len(gorulen), atlanan_bos)


if __name__ == "__main__":
    main()
