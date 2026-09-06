"""Birlesik corpus yukleme + gosterim yardimcilari (konsolide).

Uc medya (anime/film/kitap) tek listede, her kayitta 'media' etiketi.
belge()  -> gomulecek metin (medyaya gore alan adlari farkli)
baslik() -> gosterim basligi (medyadan bagimsiz)
link()   -> id'den URL (yapisal ciktida kullaniciya link)
"""

import json
import re
from pathlib import Path

import config


def _yukle(yol: Path) -> list[dict]:
    # .split("\n") — .splitlines() U+2028 gibi unicode satir-sonlarina da boluyor,
    # json.dumps onlari kacirmaz -> kayit boluner (Gun 8-9 sessiz veri hatasi).
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").split("\n") if s.strip()]


_mal_synopsis = None


def _mal() -> dict[int, str]:
    """idMal -> MAL synopsis. Tembel yuklenir, sadece ANIME_KAYNAK='mal' iken kullanilir."""
    global _mal_synopsis
    if _mal_synopsis is None:
        _mal_synopsis = {m["idMal"]: m["synopsis"]
                         for m in _yukle(config.MAL_SYNOPSIS_JSONL) if m.get("synopsis")}
    return _mal_synopsis


def _temizle(h: str) -> str:
    """AniList description HTML iceriyor -> etiketleri soy."""
    return re.sub(r"<[^>]+>", "", h or "").strip()


def belge(m: dict) -> str:
    """Kayit -> gomulecek tek string. Anime ic ice title + description;
    film/kitap duz title + overview. Format uc medyada AYNI (hizali uzay)."""
    if m["media"] == "anime":
        bas = m["title"]["romaji"] or m["title"]["english"] or ""
        ozet = _temizle(m.get("description"))
        if config.ANIME_KAYNAK == "mal":                    # A7: tek degisken = aciklama kaynagi
            ozet = _mal().get(m.get("idMal")) or ozet       # MAL'da yoksa AniList'e dus (bosluk birakma)
    else:                                                   # film / kitap
        bas = m["title"] or ""
        ozet = m.get("overview") or ""
    turler = ", ".join(m.get("genres") or [])
    return f"{bas}. {turler}. {ozet}"


def baslik(m: dict) -> str:
    """Gosterim basligi — medyadan bagimsiz tek arayuz."""
    t = m["title"]
    if isinstance(t, dict):                    # tam corpus: AniList ic ice title
        return t.get("romaji") or t.get("english") or "?"
    return t or "?"                            # demo paketi: duz string


def link(m: dict) -> str:
    """id'den URL. anime idMal, film/kitap id kullanir."""
    mid = m["idMal"] if m["media"] == "anime" else m["id"]
    return config.LINK[m["media"]].format(id=mid)


def corpus_yukle() -> list[dict]:
    """Uc corpus'u yukle, media etiketle, tek liste dondur (index sirasi = liste sirasi).

    Demo modunda tek bir slim dosya okunur (sinopsis YOK) — sira demo/V.npy ile ayni."""
    if config.DEMO:
        return _yukle(config.DEMO_DIZIN / "kayitlar.jsonl")
    anime = _yukle(config.ANIME_JSONL)
    for a in anime:
        a["media"] = "anime"                       # AniList kaydinda 'media' yok, ekle
    film = _yukle(config.FILM_JSONL)               # media="film" zaten var
    kitap = _yukle(config.KITAP_JSONL)             # media="kitap" zaten var
    return anime + film + kitap


if __name__ == "__main__":
    corpus = corpus_yukle()
    from collections import Counter
    print(f"toplam {len(corpus)} kayit:", Counter(m["media"] for m in corpus))
    ornek = corpus[0]
    print("ornek belge:", belge(ornek)[:120])
    print("ornek baslik:", baslik(ornek))
    print("ornek link:", link(ornek))
