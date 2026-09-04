"""Oneri katmani — retrieval'in listesini al, LLM'e TEK aciklama paragrafi yazdir.

MIMARI KURAL ((ii) karari, Deniz): liste retrieval'dan gelir; LLM sadece tek bir
serbest aciklama yazar (oge basina degil). LLM listeyi yeniden TANIMLAMAZ, sadece
verilen yapitlar hakkinda konusur -> oge-parse/id-esleme YOK (dunku id cehennemi).

(ii) secildi cunku oge-basina baglama tesisati yok -> daha az kirilgan. Yetmezse
(i)'ye (oge basina aciklama) cikilir.
"""

import config
import llm
import retrieval
import veri


def _baglam(oneriler: list[dict]) -> str:
    """Getirilen yapitlari numarali bloga diz — LLM ne gordugunu bilsin.

    Numara (1..k) BIZIM etiketimiz; veri.belge() = 'baslik. turler. ozet'.
    "\\n\\n".join: her yapit arasi bos satir, LLM ayirt etsin.
    """
    return "\n\n".join(
        f"[{i + 1}] ({r['media']}) {veri.belge(r)}"
        for i, r in enumerate(oneriler)
    )


def _prompt(sorgu: str, baglam: str) -> str:
    """LLM aciklama prompt'u. TARZ KARARLARI (Deniz onayina sunuldu):
      - Turkce, sicak ama satici degil, 3-5 cumle, tek paragraf
      - SADECE verilen yapitlardan bahset (listede olmayani onerme/uydurma)
      - dururst: bir yapit istegin bir kismini karsilamiyorsa soyle
      - liste birden fazla medya iceriyorsa capraz-medya bagini vurgula
    """
    return f"""<ROL: Anime, film ve kitap önerileri veren bir kültür uzmanısın.>
<GOREV: Aşağıda bir arama motorunun kullanıcının isteğine göre getirdiği yapıtlar var.
Senin görevin ise bu LİSTENİN kullanıcının isteğine neden uyduğunu, ne gibi benzerlikler veya farklılıklar taşıdığını,
 tek bir kısa paragrafta açıklamak.>
<KURALLAR:
- Sadece aşağıda verilen yapıtlardan bahset. Listede olmayan bir yapıt önerme, başlık uydurma.
- 3-5 cümle tek paragraf, Kullanıcının hedef dilinde, sıcak ama abartısız.
- Paragrafın içinde, şu maddelerden bahsedebilirsin: (1) Yapıtların kullanıcının isteğiyle olan benzerlikleri ve farklılıkları, (2) Yapıtların türleri ve temaları, (3) Yapıtların öne çıkan özellikleri.
- Bir yapıt isteğinin bir kısmını karşılamıyorsa dürüstçe belirt.
- Liste birden fazla medya (anime/film/kitap) içeriyorsa aralarındaki tematik bağı vurgula.>
<GETIRILEN YAPITLAR:
{baglam}>
<KULLANICI ISTEGI: {sorgu}>"""


def oneri(sorgu: str, k: int = config.TOP_K, medya: str | None = None,
          rerank: bool = config.RERANK_AKTIF) -> dict:
    """Sorguya oneri uret. Liste retrieval'dan, aciklama LLM'den.

    Donus: {"sorgu": str, "oneriler": list[dict], "aciklama": str}
      oneriler: retrieval.getir ciktisi, DOKUNULMADI (baslik/link/medya/_skor elde)
      aciklama: LLM'in liste hakkinda yazdigi tek paragraf
    """
    sonuc = retrieval.getir(sorgu, k, medya, rerank)
    baglam = _baglam(sonuc)
    metin = llm.cagir(
        [{"role": "user", "parts": [{"text": _prompt(sorgu, baglam)}]}]
    ).strip()
    return {"sorgu": sorgu, "oneriler": sonuc, "aciklama": metin}


if __name__ == "__main__":
    r = oneri("ölüm ve yas üzerine sakin fantastik yolculuk")
    print(f"sorgu: {r['sorgu']}\n")
    print("=== ONERILER (retrieval) ===")
    for o in r["oneriler"]:
        print(f"  {o['_skor']:.3f}  [{o['media']}]  {veri.baslik(o)}")
        print(f"         {veri.link(o)}")
    print("\n=== ACIKLAMA (LLM) ===")
    print(r["aciklama"])
    print(f"\nLLM maliyeti: {llm.sayac.ozet()}")
