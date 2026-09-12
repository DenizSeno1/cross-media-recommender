"""Ajanin ana dongusu — Faz 5 Gun 1-2. Framework YOK.

Faz 3'ten fark TEK KELIME: dongu. Orada arac cagirma TEK TURLUYDU (arac sec ->
cagir -> cevapla, bitti). Burada BITIS KARARINI AJAN VERIYOR: kac tur donecegini,
ne zaman duracagini, tekrar arayip aramayacagini kendisi seciyor.

Bugunku durma kosulu bilerek EN APTAL hali: `cevap` doldu ya da tur sayisi
HARD_CAP'e dayandi. Zeka Gun 5-6'da gelecek — once dongunun kendisi calissin.

HARD_CAP NEDEN PAZARLIKSIZ: durma kosulu LLM'in kararina bagli, ve LLM her turda
"bir daha arayayim" diyebilir. Hard cap modelin kararina bagli OLMAYAN tek fren.
Durma kosulu bozulursa fatura tur basina odenir.

GUN 0'IN BULGUSU BURAYA GIRIYOR (olculdu, 23 sorgu x 5 cekilis):
    8 sorgu, bes cekilisin BESINDE de basarisiz. HyDE her seferinde farkli sahte
    belge uretmesine ragmen sonuc degismedi.
    -> AYNI SORGUYLA TEKRAR ARAMAK FAYDASIZ. Ajan tekrar arayacaksa sorguyu
       DEGISTIRMEK zorunda. Sistem prompt'unda acikca yaziyor AMA prompt bir RICA:
       dongu ayni (arac, args) ciftini ikinci kez CALISTIRMIYOR da. Olculmus bir
       kurali modelin keyfine birakmiyoruz — HARD_CAP'in gerekcesiyle ayni gerekce.
"""

import json
import logging
import sys
import time

from pydantic import BaseModel

import araclar
import durum
import kapi
import llm

log = logging.getLogger("dongu")

HARD_CAP = 6          # pazarliksiz ust sinir (yukarida gerekce)
MAX_ONARIM = 3        # bozuk JSON gelince kac kez duzeltme istenecek


SISTEM_PROMPT = """Sen bir capraz-medya oneri ajanisin. Kullanicinin tarifine uyan
anime, film ve kitaplari buluyorsun.

Elinde su arac(lar) var:
{semalar}

HER TURDA SADECE su JSON'u dondur, baska hicbir sey yazma:
{{"dusunce": "<neden bu hamle>", "arac": "<ad>", "args": {{...}}}}
Is bittiyse:
{{"dusunce": "<neden yeterli>", "cevap": "<kullaniciya nihai metin>"}}

KURALLAR:
- "dusunce" her turda ZORUNLU. Neden o hamleyi yaptigini tek cumleyle yaz.
- Sonuclar zayifsa tekrar arayabilirsin. AMA AYNI SORGUYLA TEKRAR ARAMA — olculdu,
  ise yaramiyor. Sorguyu degistir: baska kelimeler, baska tema vurgusu, ya da
  medya kisitini gevset.
- Elindeki sonuclar yeterliyse VAKIT KAYBETME, "cevap" dondur.
- Cevabinda SADECE aracin getirdigi yapitlardan bahset. Baslik uydurma.

Kullanicinin istegi: {sorgu}"""


def _json_ayikla(metin: str) -> dict:
    """Modelin metninden JSON'u cikarir (```json cercevesini soyar)."""
    temiz = metin.replace("```json", "").replace("```", "").strip()
    return json.loads(temiz)


def _llm_turu(gecmis: list[dict]) -> "Tur":
    """Bir tur icin modelden gecerli bir Tur al. Bozuk JSON gelirse onarim ister.

    gecmis : llm.cagir formatinda mesaj listesi
             [{"role": "user"|"model", "parts": [{"text": ...}]}, ...]
    donus  : Tur

    Onarim dongusu Faz 3'ten aynen geliyor: bozuk cikti gelince modele NE'nin
    bozuk oldugu soylenip tekrar isteniyor. Hata yutulmuyor, MAX_ONARIM sonunda
    firlatiliyor — sessizce yarim bir Tur donmek bu fazin sessiz hata sinifi.
    """
    for deneme in range(1, MAX_ONARIM + 1):
        ham = llm.cagir(gecmis)
        try:
            tur = Tur(**_json_ayikla(ham))
            if tur.arac or tur.cevap:
                return tur
            hata = "ya 'arac' ya 'cevap' alani dolu olmali"
        except json.JSONDecodeError:
            hata = "cikti gecerli JSON degil"
        except Exception as h:                      # pydantic ValidationError dahil
            hata = str(h)

        log.warning("tur ayristirma deneme %d basarisiz: %s", deneme, hata)
        gecmis.append({"role": "model", "parts": [{"text": ham}]})
        gecmis.append({"role": "user", "parts": [{"text": f"Hatali cikti: {hata}. SADECE istenen JSON'u dondur."}]})

    raise ValueError(f"{MAX_ONARIM} denemede gecerli tur alinamadi")


def _arac_calistir(ad: str, args: dict) -> tuple[str, list[dict] | None]:
    """Dispatcher: adi verilen araci cagirir.

    donus : (gozlem_metni, yapisal_kayitlar)
        gozlem_metni     -> modelin baglamina giren sey
        yapisal_kayitlar -> durum.iz()'in okudugu kayitlar; HATA YOLUNDA None

    None'in anlami "sonuc bos" degil, "bu tur normal bir arama degildi". Ayrim
    onemli: bos sonuc budanir (iz'e iner), hata mesaji BUDANMAZ — zaten bir iki
    satir ve ajanin kendini duzeltmesi ona bagli.

    Bilinmeyen arac adi ya da bozuk argumanlar HATA MESAJI olarak doner, exception
    firlatmaz — ajan bunu gozlem olarak okuyup kendini duzeltebilsin diye.
    """
    kayit = araclar.ARACLAR.get(ad)
    if kayit is None:
        return f"HATA: '{ad}' diye bir arac yok. Mevcut: {list(araclar.ARACLAR)}", None
    try:
        return kayit["fonksiyon"](**args)
    except TypeError as h:
        return f"HATA: '{ad}' argumanlari uymadi: {h}", None
    except Exception as h:
        # TypeError YETMIYOR. Model semadaki sozlugun DISINA cikan bir deger
        # uretebiliyor ("Anime", "books", "kitaplar") ve o deger araci degil
        # retrieval'i vuruyor: getir() bilinmeyen medya icin KeyError firlatiyor.
        # Genis yakalama olmadan bu istisna dongu()'den kacar ve — aracin icindeki
        # HyDE cagrisi zaten odenmisken — butun kosuyu oldururdu. Docstring'in
        # verdigi soz "bozuk argumanlar GOZLEM olarak doner"; o sozu tek bir
        # istisna tipiyle tutamayiz. Tip adi mesaja giriyor ki ajan neyi
        # duzeltecegini bilsin.
        log.warning("arac '%s' hata verdi: %s: %s", ad, type(h).__name__, h)
        return (f"HATA: '{ad}' calistirilamadi ({type(h).__name__}: {h}). "
                f"Argumanlari semaya gore duzelt; 'medya' yalnizca "
                f"anime/film/kitap/hepsi olabilir."), None


# ---------------------------------------------------------------------------
# BURADAN ASAGISI SENIN
# ---------------------------------------------------------------------------


class Tur(BaseModel):
    """Modelin HER TURDA donduracegi yapi.

    Dort alan (Faz 3'un AracCagrisi'na 'dusunce' eklenmis hali):

        dusunce : str          — neden bu hamle. ZORUNLU.
                                 Neden zorunlu: bu fazin sessiz hatasi "14 tur dondu
                                 ama kimse fark etmedi". dusunce, o turlarin
                                 gerekcesini goruebilecegin TEK yer.
        arac    : str | None   — cagrilacak arac adi ("ara")
        args    : dict         — o aracin argumanlari; arac yoksa bos
        cevap   : str | None   — is bitti, nihai metin bu

    'arac' ve 'cevap' birbirinin alternatifi: biri doluysa digeri bos.
    """
    dusunce: str
    arac: str | None = None
    args: dict = {}
    cevap: str | None = None


def _olcum_yaz(kayit: dict, basla: float, sayac0: tuple) -> None:
    """Turun olcum alanlarini doldur — sure ve token TURUN TAMAMI icin.

    llm.sayac surec genelinde kumulatif; burada turun BASINDAKI degerden fark
    aliniyor. Boylece onarim denemeleri ve aracin icindeki HyDE cagrisi da tur
    kaydina giriyor — kumulatif ozet bunlari tur basina ayirmiyor."""
    kayit["sure_sn"] = round(time.perf_counter() - basla, 2)
    kayit["llm_cagri"] = llm.sayac.cagri - sayac0[0]
    kayit["girdi_tok"] = llm.sayac.girdi - sayac0[1]
    kayit["cikti_tok"] = llm.sayac.cikti - sayac0[2]


def dongu(sorgu: str, hard_cap: int = HARD_CAP, pencere: int = durum.PENCERE) -> dict:
    """Ajani calistirir: model karar verir, arac cagrilir, sonuc geri beslenir.

    girdi : sorgu (str) — kullanicinin dogal dildeki istegi
    cikti : {
        "cevap": str | None,        # nihai metin (hard cap'e dayandiysa None olabilir)
        "turlar": list[dict],       # her turun kaydi — asagida
        "durma_sebebi": str,        # "cevap" | "hard_cap"
    }

    Her turun kaydi (Gun 9-10 bunlari olcecek):
        {"no": 1, "dusunce": ..., "arac": "ara", "args": {...},
         "gozlem_krk": 1840, "sure_sn": 2.3,
         "llm_cagri": 2, "girdi_tok": 3120, "cikti_tok": 88,
         "kapi_yeterli": False, "kapi_gerekce": "..."}

    kapi_* alanlari YALNIZCA normal arama turlarinda var (hata/tekrar yolunda
    yargilanacak liste yok). Kapinin kararini bu dongu KULLANMIYOR, sadece
    kaydediyor — gerekcesi kapi.py'nin basinda.

    sure_sn ve token alanlari TURUN TAMAMINI kapsar: modele sorma (_llm_turu'nun
    onarim denemeleri dahil) + arac calistirma (aracin icindeki HyDE cagrisi dahil).
    Eskiden sure yalnizca arac cagrisini olcuyordu ve token hic yoktu: "fatura tur
    basina odenir" diyen bir dosyada faturayi GOSTERMEYEN kayit, olcmedigi seyi
    yok sanar. 6 turluk bir kosu 18 LLM cagrisi odemis olabilir.

    Govde dort adim, sirayla:
        1) modele sor          -> _llm_turu(gecmis)
        2) 'cevap' geldiyse    -> dongu biter, durma_sebebi="cevap"
        3) arac cagir          -> _arac_calistir(tur.arac, tur.args)
        4) gozlemi gecmise ek  -> bir sonraki tur bunu gorsun

    Gecmis artik elle tutulan bir liste DEGIL, durum.Durum nesnesi (Gun 3-4).
    Fark: kayitlar hep TAM tutuluyor, modele GONDERILEN gecmis her turda sifirdan
    derleniyor ve `pencere` disinda kalan turlarin gozlemi tek satirlik IZ'e iniyor.

    pencere : kac turun gozlemi TAM gonderilecek
        1                     -> varsayilan, budamali
        hard_cap (ya da ustu) -> hicbir sey budanmaz; budamasiz taban olcum bu
    """
    d = durum.Durum(SISTEM_PROMPT.format(
        semalar=json.dumps([a["sema"] for a in araclar.ARACLAR.values()],
                           ensure_ascii=False, indent=2),
        sorgu=sorgu))
    turlar = []
    gorulen_cagri = set()          # (arac, args) — ayni hamle ikinci kez CALISTIRILMAZ
    for tur_no in range(1, hard_cap + 1):
        # Olcum TURUN BASINDA basliyor: modelin kendi cagrisi (ve _llm_turu'nun
        # onarim denemeleri) turun hem gecikmesinin hem faturasinin buyuk kismi.
        basla = time.perf_counter()
        sayac0 = (llm.sayac.cagri, llm.sayac.girdi, llm.sayac.cikti)
        # Gecmis HER TURDA SIFIRDAN kuruluyor (durum.Durum'un docstring'i):
        # budama yerinde yapilmadigi icin "hangi mesaji silmistim" takibi yok.
        # _llm_turu bu listeye onarim mesajlari ekleyebilir; o eklemeler TUR ICI
        # kalir, bir sonraki turda kaybolur — dogru olan da bu, bozuk JSON'un
        # duzeltmesi kalici gecmise girmemeli.
        tur = _llm_turu(d.gecmis(pencere))
        # Kayit ONCE olusturulup listeye konuyor, olcum alanlari asagida doldurulacak.
        # Boylece cevapla biten turda da kayit var.
        kayit = {"no": tur_no, "dusunce": tur.dusunce, "arac": tur.arac,
                 "args": tur.args, "gozlem_krk": 0, "sure_sn": 0.0,
                 "llm_cagri": 0, "girdi_tok": 0, "cikti_tok": 0,
                 "gonderilen_tok": d.token_tahmini(pencere),
                 "budamasiz_tok": d.token_tahmini(hard_cap)}
        turlar.append(kayit)
        if tur.cevap:
            _olcum_yaz(kayit, basla, sayac0)
            return {"cevap": tur.cevap, "turlar": turlar, "durma_sebebi": "cevap"}

        # Gun 0'in bulgusu BURADA uygulaniyor (dosya basina bak): ayni cagri ikinci
        # kez calistirilmaz. Sebep gozlem olarak donuyor ki ajan hamlesini degistirsin.
        imza = (tur.arac, json.dumps(tur.args, ensure_ascii=False, sort_keys=True))
        if imza in gorulen_cagri:
            log.warning("tur %d: ayni arac cagrisi tekrarlandi, CALISTIRILMADI", tur_no)
            kayit["tekrar"] = True
            sonuc = ("HATA: bu arac cagrisini AYNI argumanlarla daha once yaptin, "
                     "sonucu yukarida. Olculdu: ayni sorguyla tekrar aramak sonucu "
                     "degistirmiyor. Sorguyu DEGISTIR (baska kelimeler, baska tema "
                     "vurgusu, medya kisitini gevset) ya da elindekiyle cevap ver.")
            yapisal = None
        else:
            gorulen_cagri.add(imza)
            sonuc, yapisal = _arac_calistir(tur.arac, tur.args)
        kayit["gozlem_krk"] = len(sonuc)        # gozlemin baglama getirdigi yuk

        # IZ: normal aramada durum.iz() kurar (tepe skor + basliklar oradan gelir).
        # Hata/tekrar yolunda yapisal kayit YOK ve gozlemin kendisi zaten bir iki
        # satir — iz olarak onu birakiyoruz, budanacak bir sey yok.
        iz_satiri = (durum.iz(tur_no, tur.arac, tur.args, yapisal)
                     if yapisal is not None else sonuc)
        kayit["iz_krk"] = len(iz_satiri)        # budamanin kazandirdigi yer: gozlem_krk - iz_krk

        # KAPI (Gun 5-6): getirilen liste sorguyu karsiliyor mu?
        #
        # SADECE KAYDEDILIYOR — dongulyu YONETMIYOR, baglama DA GIRMIYOR. Bilerek.
        # Gun 0'da tam bu is icin iki yapisal sinyal olculdu ve gurultuden ayirt
        # edilemedi (AUC 0.500 / 0.389); kapi fikri o olcumle dustu. Olculmemis bir
        # yargiyi akisa sokmak — hatta gerekceyi gozleme eklemek bile — ayni hatayi
        # tekrarlamak olurdu: gerekce baglama girdigi anda modelin hamlesini
        # etkiler ve kapi olculmeden karar vermeye baslar.
        # Once kayit, Gun 9-10'da olcum, gecerse terfi.
        #
        # Hata/tekrar yolunda yapisal kayit yok: yargilanacak liste de yok.
        if yapisal is not None:
            karar = kapi.yargila(sorgu, yapisal)
            kayit["kapi_yeterli"] = karar["yeterli"]
            kayit["kapi_gerekce"] = karar["gerekce"]

        _olcum_yaz(kayit, basla, sayac0)

        d.tur_ekle(tur.model_dump(), sonuc, iz_satiri)

    return {"cevap": None, "turlar": turlar, "durma_sebebi": "hard_cap"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    varsayilan = "Monster gibi psikolojik gerilim, ahlaki ikilem barindiran bir sey"
    # python dongu.py "sorgu"              -> budamali (durum.PENCERE)
    # python dongu.py --pencere 99 "sorgu" -> budamasiz taban olcum
    argv = sys.argv[1:]
    pencere = durum.PENCERE
    if "--pencere" in argv:
        i = argv.index("--pencere")
        pencere = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    sorgu = " ".join(argv) or varsayilan
    budama = "budamasiz" if pencere >= HARD_CAP else "budamali"
    print(f"SORGU: {sorgu}\nPENCERE: {pencere}  ({budama})\n")
    llm.sayac.sifirla()          # app.py ile ayni: kosu basi maliyet, kumulatif degil
    sonuc = dongu(sorgu, pencere=pencere)
    print(f"\ndurma sebebi: {sonuc['durma_sebebi']} | tur sayisi: {len(sonuc['turlar'])}")
    for t in sonuc["turlar"]:
        print(f"  {t['no']}. {t['dusunce'][:70]}")
        print(f"     arac={t['arac']} args={t['args']}"
              f"{'  [TEKRAR - calistirilmadi]' if t.get('tekrar') else ''}")
        print(f"     gozlem={t['gozlem_krk']} krk -> iz={t.get('iz_krk', 0)} krk | "
              f"{t['sure_sn']} sn | {t['llm_cagri']} llm cagrisi | "
              f"{t['girdi_tok']}+{t['cikti_tok']} tok")
        print(f"     baglam: {t['gonderilen_tok']} tok "
              f"(budamasiz {t['budamasiz_tok']})")
        if "kapi_yeterli" in t:
            # Kapi akisi yonetmiyor; burada SADECE gorunur olsun diye basiliyor.
            print(f"     kapi: {'yeterli' if t['kapi_yeterli'] else 'YETERSIZ'}"
                  f" — {t['kapi_gerekce']}  [kayit; akisi etkilemiyor]")
    print(f"\nCEVAP:\n{sonuc['cevap']}")
    print(f"\n{llm.sayac.ozet()}")
