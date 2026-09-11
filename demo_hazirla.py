"""Demo eserlerini uretir: hazir vektorler + TELIFSIZ meta (sinopsis YOK).

Neden boyle:
  1. HF Spaces ucretsiz CPU'da (2 vCPU) 12104 dokumani her soguk acilista gommek
     dakikalar surer. Hazir vektor gondermek demo'nun kullanilabilir olmasi icin ZORUNLU.
  2. Sinopsis metni ucuncu tarafa ait. Vektor turetilmis bir donusum, baslik/id/tur ise
     olgu -> demo pakette KORUNAN metin yok.

Provenance: _index'in icerik-hash guard'i burada BYPASS EDILMIYOR, yerine acik bir
provenance.json konuyor (model, kayit sayisi, kaynak belge hash'i, uretim tarihi).
Guard'in amaci "vektorler hangi metinden uretildi" sorusunu cevaplamakti; bu dosya
ayni soruyu daha acik cevapliyor.

Kosum:  python demo_hazirla.py
"""

import hashlib
import json
from datetime import date

import numpy as np
from sentence_transformers import SentenceTransformer

import config
import retrieval
import veri

CIKTI = config.KOK / "demo"

# Meta'ya SADECE bunlar giriyor. description/overview/synopsis BILEREK yok.
ALANLAR = ("id", "idMal", "media", "genres")


def slim(m: dict) -> dict:
    d = {k: m[k] for k in ALANLAR if k in m}
    d["title"] = veri.baslik(m)          # goruntulenen baslik (olgu)
    return d


def main() -> None:
    corpus = veri.corpus_yukle()
    belgeler = [veri.belge(m) for m in corpus]
    imza = hashlib.sha1(chr(10).join(belgeler).encode("utf-8")).hexdigest()[:10]

    model = SentenceTransformer(config.BI_MODEL)
    V = retrieval._index(belgeler, model)          # varsa cache'ten, yoksa kurar

    CIKTI.mkdir(exist_ok=True)
    np.save(CIKTI / "V.npy", V.astype(np.float16))  # 32 MB -> 16 MB; kosinus icin yeterli

    with (CIKTI / "kayitlar.jsonl").open("w", encoding="utf-8") as f:
        for m in corpus:
            f.write(json.dumps(slim(m), ensure_ascii=False) + "\n")

    (CIKTI / "provenance.json").write_text(json.dumps({
        "model": config.BI_MODEL,
        "anime_kaynak": config.ANIME_KAYNAK,
        "kayit": len(corpus),
        "boyut": list(V.shape),
        "dtype_diskte": "float16",
        "kaynak_belge_hash": imza,   # _index guard'inin ayni imzasi
        "uretim": str(date.today()),
        "not": "Vektorler tam corpus'tan uretildi; bu pakette sinopsis METNI yok.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"demo/ hazir: {len(corpus)} kayit, V{V.shape} float16, imza={imza}")


if __name__ == "__main__":
    main()
