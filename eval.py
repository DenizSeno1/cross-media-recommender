"""Eval — paketin KENDI retrieval hattini olcer (Gun 3-4'ten tasindi, aynen degil).

Neden aynen degil: eski `degerlendir` kendi `ara()`'sini cagiriyordu (duz bi-encoder,
anime-only index). Burada `retrieval.getir()` cagriliyor -> HyDE + opsiyonel rerank +
medya filtresi dahil, yani OLCTUGUN SEY URUNUN KENDISI. Eval urunle ayni yoldan
gecmiyorsa olctugu sey urun degil.

UYARI — SAYILAR GUN 10-11 ILE DOGRUDAN KIYASLANAMAZ:
  Gun 10-11 index'i anime-only (4880). Bu paket birlesik (7807: +2430 film +497 kitap).
  Ayni anime gold'u artik 2927 fazla belgeyle yarisiyor -> recall dusebilir ve bu
  REGRESYON DEGIL, farkli bir olcum. Kiyaslama yapacaksan `medya="anime"` ile kos.

HyDE VARYANSI — iki ayri soru, iki ayri kurulum:
  1) "Bu degisiklik ise yaradi mi?" -> A/B. Rastgeleligi DONDUR (hyde_cache=True, varsayilan).
     Yoksa olctugun sey senin degisikligin degil, LLM'in o gunku keyfi olur.
     (Gun 5-7'deki K-means `random_state=42` ile ayni gerekce.)
  2) "Urun gercek kullanici icin ne kadar iyi?" -> GURULTU TABANI. `--no-cache` ile ayni
     konfigi 3 kez kos, yayilima bak. Kullanici cache gormuyor; o varyans urunun gercek
     bir ozelligi, dondurup rapor etmek kendine yalan olur.
Bir farkin gercek olmasi icin gurultu tabanindan BUYUK olmasi gerekir. 11 sorguda tek bir
sorgu = 0.091 -> bu setin cozunurlugu 0.091, bundan kucuk kazanc olculemez.
"""

import argparse

import config
import profil
import retrieval
import veri

# (sorgu, [beklenen_idMal]) — Gun 3-4'ten aynen. idMal, AniList id DEGIL.
# Her gold serinin baz TV girdisi (kanonik tek girdi).
# (sorgu, [(medya, id), ...])
# NEDEN AD-ALANLI: TMDB id'leri ile MAL id'leri CAKISIR (Godfather'in TMDB id'si 238, ayni
# sayi gecerli bir MAL id'si de). Cip lak int tutsaydik bir film gold'u yanlislikla bir anime'yi
# dogru sayabilirdi — sessiz eval hatasi, Gun 3-4'te bir kez yasandi (AniList id vs idMal).
# anime -> idMal (AniList id DEGIL) · film -> TMDB id · kitap -> Google Books id.
# Her gold serinin KANONIK BAZ girdisi (Haikyuu 1. sezon, Rocky 1976, Godfather 1972).
ALTIN_SET = [
    # --- anime (Gun 3-4'ten, degistirilmedi: eski sayilar yeniden uretilebilsin) ---
    ("ölüm ve yas üzerine sakin fantastik yolculuk", [("anime", 52991)]),                       # Frieren
    ("büyülü kızların savaştığı karanlık psikolojik hikaye", [("anime", 9756)]),                # Madoka
    ("gizemli bir şekilde kaybolan kızın ardındaki sırları araştıran bir grup arkadaş", [("anime", 934)]),   # Higurashi
    ("aniden başka bir dünyaya ışınlanan ergenin, yeni dünyada hayatta kalmak için verdiği mücadele", [("anime", 31240)]),  # Re:Zero
    ("zaman yolculuğu ve paralel evrenler arasında geçen, karmaşık ilişkiler ve duygusal bağları konu alan bir anime", [("anime", 9253)]),  # Steins;Gate
    ("gizemli bir ışın tarafından tüm dünyadaki insanların taşlaştığı bir felaket sonrasında zeki ana karakterin uygarlığı yeniden inşa etme çabalarını konu alan bir anime", [("anime", 38691)]),  # Dr. STONE
    ("çin sarayında geçen, anakarakterin zehirlere ilgi duyduğu ve saraydaki gizemleri çözemeye çalıştığı bir anime", [("anime", 54492)]),  # Kusuriya
    ("bir grup arkadaşın, kulüp odasında kek yapıp çay içtiği bazen de müzik yaptıkları, sakin ve huzurlu Kyoto yapımı bir anime", [("anime", 5680)]),  # K-ON!
    ("tatlı ejderhaların bulunduğu slice of life tarzı bir anime", [("anime", 33206)]),         # Kobayashi
    ("simya ve felsefe temalarını işleyen, iki kardeşin simya yolculuğunu konu alan bir anime", [("anime", 5114)]),  # FMA:B
    ("yüzyıllar boyu üzerlerinde bulunan lanetler ile savaşan bir soyun başından geçen garip maceraları konu alan köklü bir serinin anime uyarlaması", [("anime", 14719)]),  # JoJo

    # --- anime, 2026-09-03 eki (Deniz yazdi; nis + tur cesitliligi icin) ---
    ("spora ilgi duyan ama spordan anlamayan bir gencin lisede voleybol takımına katılmasını ve takım arkadaşlarıyla yaşadığı dostluğu konu alan bir anime", [("anime", 20583)]),  # Haikyuu!! (1. sezon)
    ("lisedeki bir ders yüzünden zorla evlendirilen bir çiftin zamanla birbirlerine aşık olmasını konu alan romantik bir anime", [("anime", 50425)]),  # Fuufu Ijou, Koibito Miman.
    ("iki düşman lisenin liderlerinin birbirlerine aşık olmasını ve kimseye fark ettirmeden ilişkilerini sürdürmeye çalışmalarını konu alan bir romantik komedi anime", [("anime", 37475)]),  # Kishuku Gakkou no Juliet
    ("hayatı çok kötü giden bir adamın tanımadığı bir şirket tarafından denek olarak kullanılması ve bu süreçte hayata yeniden bağlanmasını konu alan bir anime", [("anime", 30015)]),  # ReLIFE
    ("iki farklı samuray ve bir kızın yollarının kesişmesinin ardından yaşadıkları maceraları ve gelişen arkadaşlıklarını konu alan bir anime", [("anime", 205)]),  # Samurai Champloo
    ("engelli bir kızın bir adama aşık olmasını ve ilişkilerini konu alan bir romantik anime", [("anime", 55866)]),  # Yubisaki to Renren
    ("tanrıya inanmayan bir adamın öldükten sonra tatlı bir kız olarak yeniden doğmasını ve tanrıya savaş açmasını konu alan bir anime", [("anime", 32615)]),  # Youjo Senki

    # --- film, 2026-09-03 eki. DIKKAT: bunlar film->film, CAPRAZ MEDYA DEGIL.
    #     Film corpus'u (2430) daha once hic olculmemisti, o bosluğu kapatiyor. A6 ayri duruyor.
    ("italyan mafyasını konu alan, intikam ve suç temalarını işleyen bir yapım", [("film", 238)]),        # The Godfather (1972)
    ("spagetti western tarzında, zengin olmayı amaçlayan üç farklı adamın birbirleri arkasından iş çevirmelerini konu alan bir film", [("film", 429)]),  # The Good, the Bad and the Ugly
    # ⚠️ ZAYIF GOLD (mentor notu): bu tarif Solaris / Moon / Sunshine'a Interstellar'dan daha
    #    cok uyuyor. Sistem onlari getirirse HAKLI olur ama eval yanlis sayar. Sorgu yeniden
    #    yazilmali (zaman genlesmesi + baba-kiz cekirdegi) ya da hedef degismeli. Deniz karar verecek.
    ("uzayda geçen, yalnızlık ve psikolojik gerilim barındıran bilimkurgu", [("film", 157336)]),          # Interstellar
    ("insanların rüyalarına girip fikir çalmayı konu alan soygun ve aksiyon filmi", [("film", 27205)]),   # Inception
    ("bir boksörün dipten zirveye yükselişini anlatan kült spor draması", [("film", 1366)]),              # Rocky (1976)

    # --- kitap: HENUZ YOK. Kitap corpus'u (497) fantastik/cocuk klasikleri dilimine sikismis
    #     (Narnia, Moomin, Tolkien, Harry Potter) -> gold ancak o dilimde yazilabilir. Karar bekliyor.
]


def recall_at_k(gelen_idler, beklenen_idler, k):
    """Beklenenlerden kaci gelen top-k icinde? (Gun 3-4, Deniz yazdi.)"""
    bulunan = len(set(beklenen_idler) & set(gelen_idler[:k]))
    return bulunan / len(beklenen_idler)


def mrr_hesapla(gelen_idler, beklenen_idler):
    """Dogru cevabin ilk bulundugu siranin tersi. Bulunamazsa 0. (Gun 3-4, Deniz yazdi.)"""
    for sira, gid in enumerate(gelen_idler, start=1):
        if gid in beklenen_idler:
            return 1.0 / sira
    return 0.0


_gold_index = None
_franchise = None


def _gold_kayit(gold):
    """(medya, id) gold girdisini corpus kaydi gibi bir dict-e cevir."""
    medya, gid = gold
    return {"media": medya, "idMal": gid} if medya == "anime" else {"media": medya, "id": gid}


def _franchise_tablosu():
    '''idMal -> franchise grup no. Bir kez kurulur.

    Bos dict = relations dosyasi yok -> otomatik olarak KATI eslestirmeye duser.'''
    global _franchise
    if _franchise is None:
        grup = profil.seri_gruplari(profil.iliskiler_yukle())
        _franchise = {m["idMal"]: grup[m["id"]] for m in veri.corpus_yukle()
                      if m["media"] == "anime" and m["id"] in grup}
    return _franchise


def _kimlik(kayit, franchise=True):
    '''Kayit -> gold ile karsilastirilabilir kimlik.

    franchise=True (varsayilan): anime icin ("anime", "f<grup_no>") — AYNI SERININ her
    girdisi ayni kimligi alir. Neden: urun bilerek franchise basina TEK temsilci
    donduruyor ve hangi temsilcinin hayatta kalacagi 0.001lik skor farklarina bagli
    (olculdu 2026-09-04: Haikyuu gold 0.7969, kardesi 0.7979 -> gold elendi, recall 0).
    Eval-in eslestirme semantigi urunun cikti semantigiyle ayni olmali; yoksa urunun
    KASTEN yaptigi seyi hata sayarsin.

    franchise=False: eski KATI davranis (kanonik idMal). --kati bayragi ile secilir,
    bugune kadarki sayilar yeniden uretilebilsin diye korunuyor.

    Ad-alani sart: TMDB/Google id-leri MAL id-leriyle cakisabilir.'''
    m = kayit["media"]
    if m != "anime":
        return (m, kayit["id"])
    idmal = kayit["idMal"]
    if franchise:
        g = _franchise_tablosu().get(idmal)
        if g is not None:
            return ("anime", f"f{g}")
    return ("anime", idmal)


def gold_dogrula(altin_set=ALTIN_SET):
    """Her gold gercekten corpus'ta var mi? Yoksa recall o sorguda ASLA >0 olamaz.

    Bu bozuk gold, sistem hatasi degil — ve sessizdir: metrik duser, sen modeli suclarsin.
    Gun 3-4'te iki kez yasandi (AniList id vs idMal, music video'ya denk gelen id). Ucuz kontrol,
    her kosuda yapilir; model yuklenmeden, sadece corpus okunarak."""
    var = {_kimlik(m, franchise=False) for m in veri.corpus_yukle()}
    eksik = [(sorgu, g) for sorgu, bek in altin_set for g in bek if g not in var]
    for sorgu, g in eksik:
        print(f"  ⚠️  GOLD CORPUS'TA YOK: {g} — {sorgu[:60]}")
    if eksik:
        raise SystemExit(f"{len(eksik)} bozuk gold girdisi. Duzeltmeden olcme.")
    print(f"gold dogrulandi: {sum(len(b) for _, b in altin_set)} hedef, hepsi corpus'ta")


def degerlendir(altin_set=ALTIN_SET, k_listesi=(5, 10, 50), hyde_cache=True,
                kota=True, tekillestir=True, franchise=True, **getir_ayar):
    """altin_set uzerinde retrieval.getir()'i kos, recall@k + MRR bas.

    getir_ayar dogrudan retrieval.getir()'e gecer (medya, rerank, hyde_n...).
    Konfigurasyon ciktiya BASILIR — konfigini kaydetmeyen eval kiyaslanamaz sayi uretir.
    """
    en_buyuk = max(k_listesi)
    toplam_recall = {k: 0.0 for k in k_listesi}
    toplam_mrr = 0.0

    print(f"konfig: hyde={config.HYDE_AKTIF} hyde_n={getir_ayar.get('hyde_n', config.HYDE_N_ORNEK)} "
          f"cache={hyde_cache} kota={kota} tekil={tekillestir} eslesme={'franchise' if franchise else 'kati'} "
          f"rerank={getir_ayar.get('rerank', config.RERANK_AKTIF)} "
          f"medya={getir_ayar.get('medya')} aday={config.ADAY} "
          f"kaynak={config.ANIME_KAYNAK} cihaz={retrieval.CIHAZ}")

    for sorgu, beklenen_ham in altin_set:
        # kisisel=False: altin set "sorgu -> su anime" olcuyor; kisisellestirme hedeften
        # uzaklastirir, recall@k onu degerlendiremez (yanlis seyi olcer, bkz. B4).
        # AMA kota/tekillestirme SUNUM kurallari ve URUNDE hep aktif -> eval de onlardan
        # gecmeli, yoksa olctugumuz hat urunun hatti degil (A1 dersi).
        sonuc = retrieval.getir(sorgu, k=en_buyuk, hyde_cache=hyde_cache,
                                kisisel=False, kota=kota, tekillestir=tekillestir,
                                **getir_ayar)
        gelen = [_kimlik(r, franchise) for r in sonuc]
        beklenen = [_kimlik(_gold_kayit(g), franchise) for g in beklenen_ham]
        for k in k_listesi:
            toplam_recall[k] += recall_at_k(gelen, beklenen, k)
        mrr = mrr_hesapla(gelen, beklenen)
        toplam_mrr += mrr
        sira = gelen.index(beklenen[0]) + 1 if beklenen[0] in gelen else None
        print(f"  {'✓' if sira and sira <= 5 else '·'} sira={sira or '>' + str(en_buyuk):>4}  {sorgu[:52]}")

    n = len(altin_set)
    print()
    for k in k_listesi:
        print(f"  recall@{k:>2} = {toplam_recall[k] / n:.3f}")
    print(f"  MRR      = {toplam_mrr / n:.3f}")
    return {**{f"recall@{k}": toplam_recall[k] / n for k in k_listesi}, "MRR": toplam_mrr / n}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Retrieval eval (11 sorgu altin set)")
    p.add_argument("--rerank", action="store_true", help="cross-encoder rerank ac")
    p.add_argument("--medya", default=None, choices=["anime", "film", "kitap"],
                   help="medya filtresi (Gun 10-11 ile kiyas icin: anime)")
    p.add_argument("--hyde-n", type=int, default=config.HYDE_N_ORNEK)
    p.add_argument("--kati", action="store_true",
                   help="eski KATI eslestirme (kanonik idMal); varsayilan franchise duzeyi")
    p.add_argument("--kotasiz", action="store_true", help="medya kotasini kapat (eski baseline)")
    p.add_argument("--tekilsiz", action="store_true", help="seri tekillestirmeyi kapat")
    p.add_argument("--no-cache", action="store_true",
                   help="sahte belgeyi her kosuda yeniden uret -> GURULTU TABANI olcumu icin")
    # varsayilan None: verilmezse config.py'nin kendi degeri (su an "mal") EZILMEZ.
    # Onceki hali default="anilist" idi -> her eval.py cagrisi sessizce config'i eziyordu,
    # A7'nin sonucunu (mal secili) fiilen gecersiz kiliyordu. Fazin 1 numarali temasinin
    # eval script'inde cikan hali: bayrak "verilmedi" derken aslinda bir sey EMPOZE ediyordu.
    p.add_argument("--kaynak", default=None, choices=["anilist", "mal"],
                   help="A7: anime aciklamasinin kaynagi (verilmezse config.py'nin degeri kullanilir)")
    p.add_argument("--aday", type=int, default=config.ADAY,
                   help="aday havuzu buyuklugu (TAVAN olcumu: --aday 500, rerank KAPALI tut)")
    a = p.parse_args()

    # Tanisal kosu icin config'i yerinde degistiriyoruz (CLI'a ozel, kutuphane kodu boyle yapmaz).
    # Havuzu buyutmek bi-encoder'a ~bedava: 7807 skor zaten hesaplaniyor, sadece kesme noktasi kayiyor.
    # Reranker icin AYNI SEY DEGIL — cross-encoder cift basina bir forward pass, maliyet dogrusal.
    k_listesi = (5, 10, 50) if a.aday <= 50 else (5, 10, 50, a.aday)
    config.ADAY = a.aday
    if a.kaynak is not None:
        config.ANIME_KAYNAK = a.kaynak  # belge() ve dolayisiyla index hash'i buna bagli

    gold_dogrula()
    degerlendir(k_listesi=k_listesi, rerank=a.rerank, medya=a.medya,
                hyde_n=a.hyde_n, hyde_cache=not a.no_cache,
                kota=not a.kotasiz, tekillestir=not a.tekilsiz,
                franchise=not a.kati)
