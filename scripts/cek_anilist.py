"""AniList GraphQL'den anime metadata cekip diske DONDURUR.

Neden AniList (Jikan degil): Jikan MAL'i kaziyor ve 2026-08-23'te coktu.
AniList kendi veritabanindan servis ediyor, resmi GraphQL API'si var,
ve her kayitta `idMal` alani var -> MAL XML export'uyla birebir eslesiyor.

Kural (faz4_todo.md): corpus bir kere cekilir, diske yazilir, bir daha cekilmez.

Cikti : faz4/data/anime_anilist.jsonl   (satir basina bir anime)
Devam : dosyadaki idMal'ler atlanir; yarida kesilirse kaldigi yerden devam.

Kullanim:
    python faz4/faz4_gun1_2/cek_anilist.py --sayfa 120
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests

URL = "https://graphql.anilist.co"
CIKTI = Path(__file__).resolve().parents[1] / "data" / "anime_anilist.jsonl"
BEKLEME = 2.0          # AniList degraded state'te ~30 istek/dk -> 2 sn guvenli
ZAMAN_ASIMI = 30

# Ne istedigimizi biz belirtiyoruz (GraphQL). Fazlasi gelmez.
QUERY = """
query ($sayfa: Int, $adet: Int) {
  Page(page: $sayfa, perPage: $adet) {
    pageInfo { hasNextPage }
    media(type: ANIME, sort: SCORE_DESC) {
      idMal
      id
      title { romaji english native }
      description(asHtml: false)
      genres
      tags { name rank }
      averageScore
      meanScore
      popularity
      format
      episodes
      duration
      seasonYear
      studios(isMain: true) { nodes { name } }
    }
  }
}
"""

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s - %(message)s", stream=sys.stdout)
log = logging.getLogger("anilist")


def mevcut_idler(yol: Path) -> set[int]:
    """Dosyada zaten yazili idMal'leri okur (devam edebilmek icin)."""
    if not yol.exists():
        return set()
    idler = set()
    with yol.open(encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if not satir:
                continue
            try:
                mid = json.loads(satir).get("idMal")
                if mid is not None:
                    idler.add(mid)
            except json.JSONDecodeError:
                continue
    return idler


def sayfa_getir(sayfa: int, adet: int = 50, deneme: int = 8):
    """Tek sayfayi getirir. 429'da Retry-After'a saygi duyar, 5xx'te ustel bekler.

    Donus: (media_listesi, devam_var_mi)  ya da  (None, False) kalici hatada.
    """
    for i in range(deneme):
        try:
            r = requests.post(URL, json={"query": QUERY,
                                         "variables": {"sayfa": sayfa, "adet": adet}},
                              timeout=ZAMAN_ASIMI)
        except requests.RequestException as e:
            log.warning("sayfa %d ag hatasi (%s), yeniden", sayfa, e)
            time.sleep(2 ** i)
            continue

        if r.status_code == 200:
            veri = r.json()
            if "errors" in veri:                      # GraphQL hatasi 200 ile de gelebilir
                log.error("sayfa %d GraphQL hata: %s", sayfa, veri["errors"])
                return None, False
            sayfa_veri = veri["data"]["Page"]
            return sayfa_veri["media"], sayfa_veri["pageInfo"]["hasNextPage"]

        if r.status_code == 429:
            bekle = int(r.headers.get("Retry-After", 60))
            log.warning("sayfa %d rate limit (429), %d sn bekleniyor", sayfa, bekle)
            time.sleep(bekle + 1)
            continue
        if 500 <= r.status_code < 600:
            log.warning("sayfa %d sunucu hatasi %d, yeniden", sayfa, r.status_code)
            time.sleep(2 ** i)
            continue

        log.error("sayfa %d beklenmeyen durum %d", sayfa, r.status_code)
        return None, False
    return None, False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sayfa", type=int, default=120, help="cekilecek azami sayfa (50 anime/sayfa)")
    args = ap.parse_args()

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    gorulen = mevcut_idler(CIKTI)
    log.info("dosyada zaten %d kayit var -> %s", len(gorulen), CIKTI)

    yeni = 0
    with CIKTI.open("a", encoding="utf-8") as f:
        for sayfa in range(1, args.sayfa + 1):
            media, devam = sayfa_getir(sayfa)
            if media is None:
                log.error("sayfa %d alinamadi, durduruluyor. Tekrar calistir, kayitlar korunur.", sayfa)
                break

            for m in media:
                mid = m.get("idMal")
                if mid is None or mid in gorulen:      # idMal'i olmayani atla (MAL'da yok, eslesemez)
                    continue
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
                gorulen.add(mid)
                yeni += 1
            f.flush()

            if sayfa % 10 == 0:
                log.info("sayfa %d/%d, toplam %d kayit", sayfa, args.sayfa, len(gorulen))
            if not devam:
                log.info("son sayfa (hasNextPage=false), bitti")
                break
            time.sleep(BEKLEME)

    log.info("BITTI. bu kosuda %d yeni, dosyada toplam %d", yeni, len(gorulen))


if __name__ == "__main__":
    main()
