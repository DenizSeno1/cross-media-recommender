"""Tek API sarmalayici: retry + timeout + token/maliyet sayaci.

Neden ayri dosya: uygulamanin geri kalani HTTP bilmesin. oneri.py "model
cagir" der, burasi nasil cagrildigiyla ilgilenir. Saglayici degisirse sadece
bu dosya degisir — Gun 12-15'te bunu KANITLADIK: Gemini -> NVIDIA -> Gemini,
her seferinde yalnizca burasi degisti, retrieval.py/oneri.py ellenmedi.
(NVIDIA free tier is yukunu karsilayamadigi icin Gemini'de kalindi.)
"""

import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)

env_yolu = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_yolu)

_KEY = os.environ.get("GEMINI_API_KEY")
if _KEY is None:
    raise RuntimeError(f"GEMINI_API_KEY bulunamadi. Beklenen dosya: {env_yolu}")


class LLMHatasi(Exception):
    """Ag/kota/ayiklama hatalarinin tek catisi. Cagiran taraf tek sey yakalar."""


class Sayac:
    """Bu kosuda harcanan token ve tahmini ucret."""

    def __init__(self):
        self.girdi = 0
        self.cikti = 0
        self.cagri = 0

    def sifirla(self):
        """Sorgu BASI maliyet icin. Kumulatif sayac UI'da "bu sorgu ne tuttu"
        sorusunu cevaplayamiyordu (C3); app.py her kosudan once sifirliyor."""
        self.__init__()

    def ekle(self, kullanim):
        self.girdi += kullanim.get("promptTokenCount", 0)
        self.cikti += kullanim.get("candidatesTokenCount", 0)
        self.cagri += 1

    @property
    def ucret(self):
        return (
            self.girdi / 1_000_000 * config.FIYAT_GIRDI_1M
            + self.cikti / 1_000_000 * config.FIYAT_CIKTI_1M
        )

    def ozet(self):
        return (
            f"{self.cagri} cagri | girdi {self.girdi} tok | "
            f"cikti {self.cikti} tok | ~${self.ucret:.6f}"
        )


sayac = Sayac()


def cagir(gecmis, temperature=None):
    """Mesaj gecmisini gonderir, modelin metnini doner.

    gecmis: [{"role": "user"|"model", "parts": [{"text": ...}]}, ...]
    Hata durumunda LLMHatasi firlatir — sessizce None donmez.
    """
    govde = {
        "contents": gecmis,
        "generationConfig": {
            "temperature": config.TEMPERATURE if temperature is None else temperature
        },
    }
    headers = {"x-goog-api-key": _KEY}

    son_hata = None
    for deneme in range(config.MAX_RETRY):
        try:
            basla = time.perf_counter()
            cevap = requests.post(
                config.API_URL, headers=headers, json=govde, timeout=config.TIMEOUT
            )
            gecen = time.perf_counter() - basla

            if cevap.status_code == 429:
                bekleme = config.BACKOFF_TABAN ** (deneme + 1)
                logger.warning("429 kota asimi, %s sn bekleniyor", bekleme)
                time.sleep(bekleme)
                son_hata = "kota asimi (429)"
                continue

            # 5xx = sunucu tarafi, GECICI -> retry dogru (Gun 8-9 dersi: 503 tokezleme,
            # 429 sabit kosul). 4xx = istegin kendisi bozuk, tekrar denemek ayni sonucu
            # verir -> hemen firlat. Ayrimi yapmayan retry ya hatayi maskeler ya pes eder.
            if cevap.status_code >= 500:
                bekleme = config.BACKOFF_TABAN ** (deneme + 1)
                logger.warning("HTTP %s (gecici), %s sn bekleniyor", cevap.status_code, bekleme)
                son_hata = f"sunucu hatasi ({cevap.status_code})"
                time.sleep(bekleme)
                continue

            if cevap.status_code != 200:
                raise LLMHatasi(f"HTTP {cevap.status_code}: {cevap.text[:200]}")

            veri = cevap.json()
            sayac.ekle(veri.get("usageMetadata", {}))
            metin = veri["candidates"][0]["content"]["parts"][0]["text"]
            logger.info("cagri ok | %.2f sn | %s", gecen, sayac.ozet())
            return metin

        except requests.exceptions.Timeout:
            son_hata = f"zaman asimi ({config.TIMEOUT} sn)"
            logger.warning("timeout, deneme %s", deneme + 1)
        except requests.exceptions.ConnectionError:
            son_hata = "baglanti kurulamadi"
            logger.warning("baglanti hatasi, deneme %s", deneme + 1)
        except (KeyError, IndexError) as hata:
            raise LLMHatasi(f"beklenmeyen cevap bicimi: {hata}") from hata

        time.sleep(config.BACKOFF_TABAN ** (deneme + 1))

    raise LLMHatasi(f"{config.MAX_RETRY} denemede basarisiz: {son_hata}")
