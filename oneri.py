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


def _baglam(oneriler: list[dict], ada: bool = False) -> str:
    """Getirilen yapitlari numarali bloga diz — LLM ne gordugunu bilsin.

    Numara (1..k) BIZIM etiketimiz; veri.belge() = 'baslik. turler. ozet'.
    "\\n\\n".join: her yapit arasi bos satir, LLM ayirt etsin.

    ada=True (sorgusuz yol): kaydin geldigi zevk adasi da yazilir. PROFIL_PROMPT
    "ada numaralari verildi" diyor — VERMEZSEK LLM onlari uydurur ya da [1..k]
    etiketlerini ada sanir; ayni prompt'un bir ust satirinda yasakladigi sey.
    """
    satirlar = []
    for i, r in enumerate(oneriler):
        etiket = r["media"]
        if ada and "_ada" in r:
            etiket += f", zevk kumesi {r['_ada']}"
        satirlar.append(f"[{i + 1}] ({etiket}) {veri.belge(r)}")
    return "\n\n".join(satirlar)


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
          rerank: bool = config.RERANK_AKTIF, profil_paketi=None) -> dict:
    """Sorguya oneri uret. Liste retrieval'dan, aciklama LLM'den.

    Donus: {"sorgu": str, "oneriler": list[dict], "aciklama": str}
      oneriler: retrieval.getir ciktisi, DOKUNULMADI (baslik/link/medya/_skor elde)
      aciklama: LLM'in liste hakkinda yazdigi tek paragraf
    """
    # ISIMLI cagri: konumsal hali (getir(sorgu, k, medya, rerank)) getir'in imzasina
    # araya bir parametre eklendiginde SESSIZCE yanlis degeri gecirirdi.
    sonuc = retrieval.getir(sorgu, k=k, medya=medya, rerank=rerank,
                            profil_paketi=profil_paketi)
    baglam = _baglam(sonuc)
    metin = llm.cagir(
        [{"role": "user", "parts": [{"text": _prompt(sorgu, baglam)}]}]
    ).strip()
    return {"sorgu": sorgu, "oneriler": sonuc, "aciklama": metin}


PROFIL_PROMPT = """Aşağıda bir kullanıcının BEĞENDİĞİ yapıtlardan çıkarılmış zevk kümelerine
göre seçilmiş öneriler var. Kullanıcı serbest bir istek yazmadı; liste tamamen onun
geçmiş beğenilerinden üretildi.

Tek paragrafta, Türkçe, listeyi tanıt. Kurallar:
- SADECE aşağıdaki metinlere dayan. Metinde olmayan bir şey uydurma.
- Her öneri farklı bir zevk kümesinden geliyor (ada numaraları verildi) — bu ÇEŞİTLİLİK
  kasıtlı, onu vurgula.
- Kullanıcının hangi yapıta kaç puan verdiğini BİLMİYORSUN, öyleymiş gibi yazma.

<GETIRILEN YAPITLAR:
{baglam}>"""


def oneri_profilden(profil_paketi, k: int = config.TOP_K,
                    medya: str | None = None) -> dict:
    """Sorgusuz oneri: zevk adalarindan dogrudan. (B5, 2026-09-05)

    Aciklama prompt'u AYRI: "kullanicinin istegi" diye bir sey yok, uydurmamasi icin
    bunu acikca soyluyoruz. Ayrica profil ICERIGINI gormuyor (puanlar prompt'a
    girmiyor) -> "Frieren'e 10 verdigin icin" DIYEMEZ ve demesini yasakliyoruz.
    Gerekcenin profile dayanmasi ayri bir is (B7)."""
    if profil_paketi[0] is None:
        return {"sorgu": None, "oneriler": [], "aciklama": "Profil kurulamadı."}
    sonuc = retrieval.getir_profilden(profil_paketi, k=k, medya=medya)
    if not sonuc:
        # Profil KURULU ama secim bos: medya filtresi + tekillestirme havuzu kapatmis.
        # Bunu "profil kurulamadi" diye raporlamak calisan profili sucluyordu; iki ayri
        # teshis, iki ayri mesaj.
        return {"sorgu": None, "oneriler": [],
                "aciklama": "Bu filtrede zevk adalarindan oneri cikmadi — medya filtresini genislet."}
    metin = llm.cagir([{"role": "user", "parts": [{"text": PROFIL_PROMPT.format(
        baglam=_baglam(sonuc, ada=True))}]}]).strip()
    return {"sorgu": None, "oneriler": sonuc, "aciklama": metin}


DARALT_PROMPT = """Bir kullanici arama yapti, sonra sonucu daraltmak istedi.

Onceki istek: {onceki}
Daraltma: {daraltma}

Ikisini TEK bir yeni istege birlestir ve SADECE o istegi yaz (aciklama yok, tirnak yok).

Kural — bu isin can alici noktasi: OLUMSUZLAMAYI OLUMLUYA CEVIR.
Arama bir embedding uzayinda yapiliyor ve embedding'ler olumsuzlama yapamaz:
"romantik olmasin" cumlesinin vektoru "romantik"e YAKIN cikar, cunku iki cumle de
ayni kelimeden bahsediyor. Bu yuzden "X olmasin" gibi bir daraltmayi, X'in yerine
NE ISTENDIGINI soyleyen olumlu bir tarife cevir.
Ornek: "olum ve yas uzerine sakin fantastik yolculuk" + "romantik olmasin"
    -> "olum ve yas uzerine, arkadaslik ve yol arkadasligi temali sakin fantastik yolculuk"
Ornek: "zaman yolculugu" + "daha kisa olsun"
    -> "tek sezonluk, kisa ve tempolu zaman yolculugu hikayesi"
"""


def daralt(onceki: str, daraltma: str) -> str:
    """Onceki sorgu + daraltma -> TEK yeni sorgu. (B3, tek tur)

    `while` YOK — ajan dongusu Faz 5. Burada tek adim: yeniden yazilan sorgu tum
    hatti bastan kosturur (yeni HyDE pusulasi dahil), cunku daraltma pusulanin
    KENDISINI degistirmeli; sonuclari sonradan suzmek olumsuzlamayi cozmez."""
    return llm.cagir([{"role": "user", "parts": [{"text": DARALT_PROMPT.format(
        onceki=onceki, daraltma=daraltma)}]}]).strip().strip('"')


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
