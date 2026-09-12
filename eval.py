"""Eval — paketin KENDI retrieval hattini olcer (Gun 3-4'ten tasindi, aynen degil).

Neden aynen degil: eski `degerlendir` kendi `ara()`'sini cagiriyordu (duz bi-encoder,
anime-only index). Burada `retrieval.getir()` cagriliyor -> HyDE + opsiyonel rerank +
medya filtresi dahil, yani OLCTUGUN SEY URUNUN KENDISI. Eval urunle ayni yoldan
gecmiyorsa olctugu sey urun degil.

UYARI — SAYILAR GUN 10-11 ILE DOGRUDAN KIYASLANAMAZ:
  Gun 10-11 index'i anime-only (4880). Bu paket birlesik (12104: +2430 film +4794 kitap).
  Ayni anime gold'u artik 7224 fazla belgeyle yarisiyor -> recall dusebilir ve bu
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
import math

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
# anime -> idMal (AniList id DEGIL) · film -> TMDB id · kitap -> Open Library ESER
# anahtari ("OL262454W"; kaynak 2026-09-10'da Google Books'tan tasindi).
# Her gold serinin KANONIK BAZ girdisi (Haikyuu 1. sezon, Rocky 1976, Godfather 1972).
ALTIN_SET = [
    #  ANİME 20 ADET
    ("ölüm ve yas üzerine sakin fantastik yolculuk", [("anime", 52991)]),                                                                                                                                               # 1) Frieren
    ("büyülü kızların savaştığı karanlık psikolojik hikaye", [("anime", 9756)]),                                                                                                                                        # 2) Madoka
    ("gizemli bir şekilde kaybolan kızın ardındaki sırları araştıran bir grup arkadaş", [("anime", 934)]),                                                                                                              # 3) Higurashi
    ("aniden başka bir dünyaya ışınlanan ergenin, yeni dünyada hayatta kalmak için verdiği mücadele", [("anime", 31240)]),                                                                                              # 4) Re:Zero
    ("zaman yolculuğu ve paralel evrenler arasında geçen, karmaşık ilişkiler ve duygusal bağları konu alan bir anime", [("anime", 9253)]),                                                                              # 5) Steins;Gate
    ("gizemli bir ışın tarafından tüm dünyadaki insanların taşlaştığı bir felaket sonrasında zeki ana karakterin uygarlığı yeniden inşa etme çabalarını konu alan bir anime", [("anime", 38691)]),                      # 6) Dr. STONE
    ("çin sarayında geçen, anakarakterin zehirlere ilgi duyduğu ve saraydaki gizemleri çözemeye çalıştığı bir anime", [("anime", 54492)]),                                                                              # 7) Kusuriya
    ("bir grup arkadaşın, kulüp odasında kek yapıp çay içtiği bazen de müzik yaptıkları, sakin ve huzurlu Kyoto yapımı bir anime", [("anime", 5680)]),                                                                  # 8) K-ON!
    ("tatlı ejderhaların bulunduğu slice of life tarzı bir anime", [("anime", 33206)]),                                                                                                                                 # 9) Kobayashi
    ("simya ve felsefe temalarını işleyen, iki kardeşin simya yolculuğunu konu alan bir anime", [("anime", 5114)]),                                                                                                     # 10) FMA:B
    ("yüzyıllar boyu üzerlerinde bulunan lanetler ile savaşan bir soyun başından geçen garip maceraları konu alan köklü bir serinin anime uyarlaması", [("anime", 14719)]),                                             # 11) JoJo
    ("spora ilgi duyan ama spordan anlamayan bir gencin lisede voleybol takımına katılmasını ve takım arkadaşlarıyla yaşadığı dostluğu konu alan bir anime", [("anime", 20583)]),                                       # 12) Haikyuu!! (1. sezon)
    ("lisedeki bir ders yüzünden zorla evlendirilen bir çiftin zamanla birbirlerine aşık olmasını konu alan romantik bir anime", [("anime", 50425)]),                                                                   # 13) Fuufu Ijou, Koibito Miman.
    ("iki düşman lisenin liderlerinin birbirlerine aşık olmasını ve kimseye fark ettirmeden ilişkilerini sürdürmeye çalışmalarını konu alan bir romantik komedi anime", [("anime", 37475)]),                            # 14) Kishuku Gakkou no Juliet
    ("hayatı çok kötü giden bir adamın tanımadığı bir şirket tarafından denek olarak kullanılması ve bu süreçte hayata yeniden bağlanmasını konu alan bir anime", [("anime", 30015)]),                                  # 15) ReLIFE
    ("iki farklı samuray ve bir kızın yollarının kesişmesinin ardından yaşadıkları maceraları ve gelişen arkadaşlıklarını konu alan bir anime", [("anime", 205)]),                                                      # 16) Samurai Champloo
    ("engelli bir kızın bir adama aşık olmasını ve ilişkilerini konu alan bir romantik anime", [("anime", 55866)]),                                                                                                     # 17) Yubisaki to Renren
    ("tanrıya inanmayan bir adamın öldükten sonra tatlı bir kız olarak yeniden doğmasını ve tanrıya savaş açmasını konu alan bir anime", [("anime", 32615)]),                                                           # 18) Youjo Senki
    ("insanları kişiliklerine ve suç işleme potansiyeline göre bir sistemde sınıflandıran bir dünyada geçen, ana karakterin bu sistemle mücadelesini konu alan bir anime", [("anime", 13601)]),                         # 19) Psycho-Pass
    ("galaksiler arasında iki farklı gücün savaşını ve iki taraftaki dahilerin akıl oyunlarını konu alan bir anime", [("anime", 820)]),                                                                                 # 20) Ginga Eiyuu Densetsu

    #  FILM 20 ADET
    ("italyan mafyasını konu alan, intikam ve suç temalarını işleyen bir yapım", [("film", 238)]),                                                                                                                      # 21) The Godfather (1972)
    ("spagetti western tarzında, zengin olmayı amaçlayan üç farklı adamın birbirleri arkasından iş çevirmelerini konu alan bir film", [("film", 429)]),                                                                 # 22) The Good, the Bad and the Ugly
    ("uzayda geçen, yalnızlık ve psikolojik gerilim barındıran bilimkurgu", [("film", 157336)]),                                                                                                                        # 23) Interstellar
    ("insanların rüyalarına girip fikir çalmayı konu alan soygun ve aksiyon filmi", [("film", 27205)]),                                                                                                                 # 24) Inception
    ("bir boksörün dipten zirveye yükselişini anlatan kült spor draması", [("film", 1366)]),                                                                                                                            # 25) Rocky (1976)
    ("haksız yere hapse atılan bir bankacının umut, dostluk ve sabırla örülü uzun yıllara yayılan kaçış hikayesi", [("film", 278)]),                                                                                    # 26) The Shawshank Redemption (1994)
    ("tek bir odada geçen, bir cinayet davasında sanığın suçluluğunu tartışan 12 jüri üyesinin psikolojik ve hukuki çatışması", [("film", 389)]),                                                                       # 27) 12 Angry Men (1957)
    ("modern tüketim kültürünü eleştiren, şizofrenik bir alt kültür ve yeraltı dövüş organizasyonu etrafında dönen psikolojik gerilim", [("film", 550)]),                                                               # 28) Fight Club (1999)
    ("bir televizyon programında doğup büyüyen ve tüm hayatının gizli kameralarla dünyaya naklen yayınlandığını fark eden bir adamın trajikomik varoluş mücadelesi", [("film", 37165)]),                                # 29) The Truman Show (1998)
    ("ikinci dünya savaşı sırasında yahudileri fabrikasında çalıştırarak soykırımdan kurtarmaya çalışan bir iş insanının gerçek hikayesi", [("film", 424)]),                                                            # 30) Schindler's List (1993)
    ("insanlığın ve evrenin kökenini araştırmak için gizemli bir siyah taşın izini süren bir uzay gemisi mürettebatının, yapay zekanın isyanıyla karşılaşmasını konu alan bir film", [("film", 62)]),                   # 31) 2001: A Space Odyssey (1968)
    ("bir dedektifin ve ortağının, yedi ölümcül günahı temel alarak cinayetler işleyen gizemli bir seri katilin peşine düşmesini konu alan polisiye", [("film", 807)]),                                                 # 32) Se7en (1995)
    ("akıl hastanesine yatırılan özgür ruhlu bir adamın, otoriter sisteme ve baskıcı hemşireye karşı başlattığı kurumsal isyan", [("film", 510)]),                                                                      # 33) One Flew Over the Cuckoo's Nest (1975)
    ("hafızasından eski sevgilisini sildirmeye çalışan bir adamın, zihninin derinliklerindeki anıları ve pişmanlıkları arasında geçen gerçeküstü drama", [("film", 38)]),                                               # 34) Eternal Sunshine of the Spotless Mind (2004)
    ("farklı hikaye çizgilerinin, absürt diyalogların ve suç dünyasındaki gangsterlerin yollarının kesiştiği doğrusal olmayan kült yapım", [("film", 680)]),                                                            # 35) Pulp Fiction (1994)
    ("japon feodal döneminde yağmacılara karşı köylerini korumak için yedi samurayı kiralayan köylülerin epik ve felsefi mücadelesi", [("film", 346)]),                                                                 # 36) Seven Samurai (1954)
    ("gizemli bir cinayeti çözmek için yerel polislerin ve bir dedektifin kırsal bir bölgede hafıza tazeleyerek katilin peşine düşmesini işleyen güney kore yapımı gerilim", [("film", 11423)]),                        # 37) Memories of Murder (2003)
    ("bir illüzyonistin, rakibiyle girdiği amansız rekabeti, takıntıyı ve fedakarlığı konu alan sihirbazlık temalı gizem filmi", [("film", 1124)]),                                                                     # 38) The Prestige (2006)
    ("insanlığın çocuk sahibi olma yetisini kaybettiği distopik bir gelecekte, mucizevi bir şekilde hamile kalan son kadını koruma mücadelesi", [("film", 9693)]),                                                      # 39) Children of Men (2006)
    ("vietnam savaşı'nın karanlığını, askerlerin deliliğe sürüklenişini ve insan doğasının vahşetini nehir boyunca yapılan bir yolculukla anlatan askeri drama", [("film", 28)]),                                       # 40) Apocalypse Now (1979)
    
    # KITAP 20 ADET
    ("yapay uzuvlar ve simya kullanarak ölümsüz bir varlık yaratmaya çalışan bir bilim insanının felsefi ve gotik hikayesi", [("kitap", "OL450063W")]),                                                                 # 41) Frankenstein — Mary Shelley
    ("transilvanya'dan ingiltere'ye uzanan, mektup ve günlük formunda yazılmış tekinsiz bir gotik korku ve vampir klasiği", [("kitap", "OL85892W")]),                                                                   # 42) Dracula — Bram Stoker
    ("rüzgarlı ingiliz kırlarında geçen, nesiller boyu süren saplantılı bir aşkı, nefreti ve intikamı konu alan dramatik roman", [("kitap", "OL21177W")]),                                                              # 43) Wuthering Heights — E. Brontë
    ("bir kaptanın okyanusun ortasında devasa bir beyaz balinayı takıntılı bir şekilde avlama mücadelesini anlatan felsefi epik", [("kitap", "OL102749W")]),                                                            # 44) Moby Dick — Melville
    ("1920'lerin Amerika'sında zenginlik, lüks ve gösterişin arkasındaki boşluğu ve imkansız bir aşkın trajedisini işleyen kült yapıt", [("kitap", "OL468431W")]),                                                      # 45) The Great Gatsby — Fitzgerald
    ("bir bilim insanının geleceğe giderek insanlığın evrimleştiği iki farklı sınıfın karanlık ilişkisini keşfetmesini anlatan bilimkurgu", [("kitap", "OL52267W")]),                                                   # 46) The Time Machine — H.G. Wells
    ("yoksul bir öğrencinin işlediği cinayetin ardından yaşadığı yoğun vicdan azabını ve ahlaki çöküşü ele alan psikolojik gerilim", [("kitap", "OL166894W")]),                                                         # 47) Crime and Punishment — Fyodor Dostoevsky
    ("üst sınıf rus toplumunda yaşanan yasak bir aşkı, evlilik normlarını ve bireysel trajedileri konu alan devasa gerçekçi drama", [("kitap", "OL267096W")]),                                                          # 48) Anna Karenina — Leo Tolstoy
    ("gizemli bir sisli arazide geçen, lanetli bir köpek efsanesini ve zekice işlenmiş bir cinayeti çözen dedektiflik hikayesi", [("kitap", "OL262454W")]),                                                             # 49) The Hound of the Baskervilles — Arthur Conan Doyle
    ("genç bir kızın bir tavşan deliğinden düşerek mantığın sınırlarını zorlayan gerçeküstü ve büyülü bir dünyaya adım atmasını anlatan klasik", [("kitap", "OL138052W")]),                                             # 50) Alice's Adventures in Wonderland — Lewis Carroll
    ("yetimhanede büyüyen bir çocuğun londra'nın yeraltı suç dünyasına çekilmesini ve hayatta kalma mücadelesini anlatan toplumsal eleştiri", [("kitap", "OL8193478W")]),                                               # 51) Oliver Twist — Charles Dickens
    ("ıssız bir adaya düşen bir denizcinin, doğaya karşı verdiği amansız hayatta kalma ve kendi uygarlığını inşa etme mücadelesi", [("kitap", "OL45089W")]),                                                            # 52) Robinson Crusoe — Daniel Defoe
    ("püriten bir toplumda zina ile suçlanan bir kadının, göğsünde taşımaya mahkum edildiği simge üzerinden ilerleyen toplumsal drama", [("kitap", "OL455305W")]),                                                      # 53) The Scarlet Letter — Nathaniel Hawthorne
    ("iktidarı elde etme, koruma ve devlet yönetimi üzerine acımasız ve rasyonalist stratejiler barındıran felsefi el kitabı", [("kitap", "OL1089297W")]),                                                              # 54) The Prince — Niccolò Machiavelli
    ("bir taşra kasabasında büyüyen bir yetimin, gizemli bir hayırsever sayesinde sınıf atlama ve aşkı bulma yolculuğunu anlatan roman", [("kitap", "OL8721462W")]),                                                    # 55) Great Expectations — Charles Dickens
    ("amerikan iç savaşı döneminde büyüyen dört kız kardeşin hayata tutunma, büyüme ve bireysellik mücadelesini işleyen sıcak drama", [("kitap", "OL29983W")]),                                                         # 56) Little Women — Louisa May Alcott
    ("iki gencin doğanın kalbindeki vahşi yaşamda yollarının kesişmesini, hayatta kalma mücadelelerini ve arka plandaki karmaşık aile dramalarını konu alan bir kitap", [("kitap", "OL17874351W")]),                    # 57) Wildlife — Fiona Wood
    ("küçük bir adanın izole atmosferinde geçen, yerel efsaneler, monarşik yapılar ve sırlarla örülü tarihi bir gizem romanı", [("kitap", "OL17871733W")]),                                                             # 58) The Last Kings of Sark — Ben Le Touzel Faccini
    ("yatılı bir lisedeki gençlerin güç mücadelelerini, gençlik travmalarını ve yozlaşmış bir eğitim sistemine karşı isyanlarını anlatan sert bir drama", [("kitap", "OL19986116W")]),                                  # 59) Brutal Youth — Anthony Breznican
    ("bir evin tavan arasında saklanan gizemleri, geçmişten gelen aile sırlarını ve klostrofobik bir atmosferde gelişen gerilim dolu bir hikayeyi işleyen roman", [("kitap", "OL4286638W")])                            # 60) Attic — Katherine S. Applegate
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


def isabet_at_k(altin_set=ALTIN_SET, k_listesi=(5, 10), hyde_cache=True,
                kota=True, tekillestir=True, franchise=True, **getir_ayar):
    """URUN yolundan isabet: her k icin getir(k=k) CAGIRIR, gold o listede mi?

    NEDEN AYRI BIR OLCU (A13, 2026-09-10 — Faz 4'un A1 dersinin kacan yarisi):
        degerlendir() tek bir getir(k=50) cagirip o listenin ilk 5'ine bakiyor ve
        buna "recall@5" diyor. Ama KOTA k ile OLCEKLENIYOR:
            kota_olcekle(KOTA, k=5)  -> {anime:3,  film:1,  kitap:1}
            kota_olcekle(KOTA, k=50) -> {anime:30, film:10, kitap:10}
        Yani k=50 listesinin ilk 5'i 30/10/10 kotasi altinda seciliyor; besi de
        kitap olabilir. Urun k=5'te 3/1/1'e ZORLUYOR. Olculen liste, urunun
        dondurdugu liste DEGIL.

        Olculdu (12104'luk corpus, 23 gold):
            eval yolu ilk-5 bilesimi : 69 kitap · 38 anime ·  8 film
            urun yolu k=5 bilesimi   : 69 anime · 23 film  · 23 kitap
            eval "recall@5" 0.478  vs  URUN isabet@5 0.478 (eski corpus'ta 0.565 vs 0.478)

        A1'de kota/tekillestirme bayraklarini urune esitlemistik ama `k`'nin kendisinin
        bir kota parametresi oldugunu gormemistik. Ayni ders, kacan yarisi.

    Isbolumu:  recall@50 = HAVUZ kalitesi (retrieval)   |   isabet@k = URUNUN verdigi
    """
    n = len(altin_set)
    sonuclar = {}
    for k in k_listesi:
        isabet = 0
        for sorgu, beklenen_ham in altin_set:
            sonuc = retrieval.getir(sorgu, k=k, hyde_cache=hyde_cache, profil_paketi=None,
                                    kota=kota, tekillestir=tekillestir, **getir_ayar)
            gelen = [_kimlik(r, franchise) for r in sonuc]
            hedef = {_kimlik(_gold_kayit(g), franchise) for g in beklenen_ham}
            isabet += any(h in gelen for h in hedef)
        sonuclar[f"isabet@{k}"] = isabet / n
        print(f"  isabet@{k:<2} = {isabet / n:.3f}   ({isabet}/{n} sorgu, URUN yolu)")
    return sonuclar


def degerlendir(altin_set=ALTIN_SET, k_listesi=(5, 10, 50), hyde_cache=True,
                kota=True, tekillestir=True, franchise=True, urun=None, **getir_ayar):
    """altin_set uzerinde retrieval.getir()'i kos, recall@k + MRR (+ isabet@k) bas.

    getir_ayar dogrudan retrieval.getir()'e gecer (medya, rerank, hyde_n...).
    Konfigurasyon ciktiya BASILIR — konfigini kaydetmeyen eval kiyaslanamaz sayi uretir.

    urun: [URUN] yolunu (isabet_at_k) kos. None = OTOMATIK, yani `hyde_cache` ne ise o.
        Iki sebep, ikisi de A13'un kendi mantigi:
          1) TEKRARLANABILIRLIK. isabet_at_k her k icin AYRI bir getir() cagiriyor.
             hyde_cache=False iken bu UC AYRI HyDE cekilisi demek: isabet@5, isabet@10
             ve yukaridaki recall@k farkli pusulalardan gelir, isabet@5 <= isabet@10
             sarti bozulabilir ve hepsi tek bir olcum gibi basilir. siralar()'in
             asagida uyardigi hatanin tek rapor icindeki hali.
          2) MALIYET. Urun yolu sorgu basina 2 getir() daha ekliyor (23 -> 69): her biri
             e5 encode + tam corpus matmul. Sayilari kullanmayan cagiran (deney_a11
             gibi) urun=False verip 3x bedeli odemesin.
    """
    en_buyuk = max(k_listesi)
    toplam_recall = {k: 0.0 for k in k_listesi}
    toplam_mrr = 0.0

    print(f"konfig: hyde={config.HYDE_AKTIF} hyde_n={getir_ayar.get('hyde_n', config.HYDE_N_ORNEK)} "
          f"cipa={getir_ayar.get('cipa', config.HYDE_CIPA)} "
          f"cache={hyde_cache} kota={kota} tekil={tekillestir} eslesme={'franchise' if franchise else 'kati'} "
          f"rerank={getir_ayar.get('rerank', config.RERANK_AKTIF)} "
          f"medya={getir_ayar.get('medya')} aday={config.ADAY} "
          f"kaynak={config.ANIME_KAYNAK} cihaz={retrieval.CIHAZ}")

    for sorgu, beklenen_ham in altin_set:
        # profil_paketi=None: altin set "sorgu -> su anime" olcuyor; kisisellestirme hedeften
        # uzaklastirir, recall@k onu degerlendiremez (yanlis seyi olcer, bkz. B4).
        # AMA kota/tekillestirme SUNUM kurallari ve URUNDE hep aktif -> eval de onlardan
        # gecmeli, yoksa olctugumuz hat urunun hatti degil (A1 dersi).
        sonuc = retrieval.getir(sorgu, k=en_buyuk, hyde_cache=hyde_cache,
                                profil_paketi=None, kota=kota, tekillestir=tekillestir,
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
    print("  [HAVUZ] k=%d listesinden — retrieval kalitesi, urunun listesi DEGIL" % en_buyuk)
    for k in k_listesi:
        print(f"  recall@{k:>2} = {toplam_recall[k] / n:.3f}")
    print(f"  MRR      = {toplam_mrr / n:.3f}")

    if urun is None:
        urun = hyde_cache                    # gerekce yukarida (docstring, urun)
    urun_olcu = {}
    if urun:
        print()
        print("  [URUN] getir(k=k) cagrilarindan — kullanicinin gordugu liste")
        urun_olcu = isabet_at_k(altin_set, k_listesi=tuple(k for k in k_listesi if k <= 10),
                                hyde_cache=hyde_cache, kota=kota, tekillestir=tekillestir,
                                franchise=franchise, **getir_ayar)
    elif not hyde_cache:
        print()
        print("  [URUN] ATLANDI: hyde_cache=False — her k AYRI cekilis olurdu, uc farkli"
              " pusula tek olcum gibi basilirdi. Urun yolu icin cache'li kos.")

    return {**{f"recall@{k}": toplam_recall[k] / n for k in k_listesi},
            "MRR": toplam_mrr / n, **urun_olcu}


# ---------------------------------------------------------------------------
# A14 — SIRA TABANLI KARSILASTIRMA (2026-09-05)
#
# Neden: recall@k ESIKLI bir olcu. Yalnizca "5. sira cizgisini gecti mi" diye
# soruyor; 22->3 ile 21->11'i ayni torbaya koyuyor ve ikincisini SIFIR sayiyor.
# 09-05'te olculdu: cipa 8 sorguyu oynatti, recall@5 bunlardan 2'sini gordu.
#
# TASARIM KARARI (mentor, 09-05): KARAR olcusu ISARET TESTI, Delta-sira sadece
# BETIMLEYICI. Gerekce: bir olcuden istenen ilk sey "gercek mi, gurultu mu" ve
# isaret testi bunu KENDI gurultu modeliyle cevapliyor (binom) — recall@k icin
# gurultu tabanini ayrica olcmek zorunda kalmistik (09-03, ayri kosu).
# Delta-sira'nin ilkeli bir esigi YOK ve '-' kayitlari icin sira uydurmak
# gerekiyor (51? 100?) -> karar veremez, betimler.
# Bir olcu karar verir, digerleri betimler. Iki olcuyu esit yetkiyle masaya
# koyarsan celistiklerinde hangisinin kazandigi belirsiz kalir. (bkz. B4)
# ---------------------------------------------------------------------------

def siralar(altin_set=ALTIN_SET, k=50, franchise=True, hyde_cache=True, **getir_ayar):
    """Her sorgu icin gold'un kacinci sirada geldigi (top-k icinde yoksa None).

    hyde_cache VARSAYILAN True — degerlendir() ile ayni gerekce: getir()'in kendi
    varsayilani False (URUN modu), o yuzden burada ACIKCA verilmezse iki konfig iki
    AYRI HyDE cekilisiyle kosar ve isaret testi LLM gurultusunu degisiklige yazar."""
    cikti = []
    for sorgu, beklenen_ham in altin_set:
        sonuc = retrieval.getir(sorgu, k=k, profil_paketi=None,
                                hyde_cache=hyde_cache, **getir_ayar)
        gelen = [_kimlik(r, franchise) for r in sonuc]
        # TUM gold'lar, en iyi (en kucuk) sira. Sadece beklenen_ham[0]'a bakmak,
        # degerlendir()'in tamamini puanlamasiyla celisiyordu: cok-gold'lu bir girdi
        # eklendiginde (kitap gold'lari karar bekliyor) ikinci gold'un 40 -> 2 hareketi
        # sessizce "berabere" sayilip isaret testinden DUSERDI. Karar olcusunun kendisi
        # gormedigini gorunmez sanar — fazin sessiz hata sinifi.
        bulunan = [gelen.index(h) + 1
                   for h in (_kimlik(_gold_kayit(g), franchise) for g in beklenen_ham)
                   if h in gelen]
        cikti.append(min(bulunan) if bulunan else None)
    return cikti


def isaret_testi(once, sonra):
    """Iki sira listesini karsilastir: kac yukari, kac asagi, iki yonlu binom p.

    '-' (None) ele alinisi: ikisi de None -> BERABERE (disarida). Biri None ise
    o taraf digerinden kotu sayilir. Beraberlikler testten DUSER — isaret
    testinin tanimi budur ve None'lar icin sayi uydurmak gerekmez.

    Null hipotez: degisiklik notrse, YER DEGISTIREN her sorgunun yukari ya da
    asagi gitmesi esit olasilikli (p=0.5). Iki yonlu p = sansin bu kadar veya
    daha uc bir dagilim uretme olasiligi. recall@k'nin aksine bu esik AMPIRIK
    DEGIL — ayri bir gurultu tabani kosusu gerektirmiyor."""
    yukari = asagi = berabere = 0
    for a, b in zip(once, sonra):
        if a == b:
            berabere += 1
        elif a is None:
            yukari += 1               # havuza girdi
        elif b is None:
            asagi += 1                # havuzdan dustu
        elif b < a:
            yukari += 1               # sira kucuk = daha iyi
        else:
            asagi += 1
    n = yukari + asagi
    if n == 0:
        return {"yukari": 0, "asagi": 0, "berabere": berabere, "n": 0, "p": 1.0}
    uc = max(yukari, asagi)
    kuyruk = sum(math.comb(n, i) for i in range(uc, n + 1)) / 2 ** n
    return {"yukari": yukari, "asagi": asagi, "berabere": berabere, "n": n,
            "p": min(1.0, 2 * kuyruk)}


def delta_sira(once, sonra):
    """BETIMLEYICI (karar vermez): iki tarafta da sirasi bilinen sorgularda
    ortalama sira kazanci. '-' iceren ciftler DISARIDA — sira uydurmuyoruz."""
    ciftler = [(a, b) for a, b in zip(once, sonra) if a is not None and b is not None]
    if not ciftler:
        return None, 0
    return sum(a - b for a, b in ciftler) / len(ciftler), len(ciftler)


def karsilastir(ad_a, ayar_a, ad_b, ayar_b, altin_set=ALTIN_SET, k=50, franchise=True):
    """Iki konfigi sorgu bazinda karsilastir, isaret testi + Delta-sira bas."""
    a, b = (siralar(altin_set, k, franchise, **ayar_a),
            siralar(altin_set, k, franchise, **ayar_b))
    print()
    print(f"{ad_a}  ->  {ad_b}")
    print(f"{'sorgu':<50} {'once':>6} {'sonra':>6}   ne oldu")
    print("-" * 82)
    for (sorgu, _), sa, sb in zip(altin_set, a, b):
        if sa == sb:
            not_ = ""
        else:
            iyi = (sa is None) or (sb is not None and sb < sa)
            gecti = ""
            if (sa is not None and sa <= 5) != (sb is not None and sb <= 5):
                gecti = "  >>> TOP-5'E GIRDI" if (sb is not None and sb <= 5) else "  <<< TOP-5'TEN CIKTI"
            not_ = ("yukari" if iyi else "asagi") + gecti
        print(f"{sorgu[:48]:<50} {str(sa or '-'):>6} {str(sb or '-'):>6}   {not_}")

    t = isaret_testi(a, b)
    d, kac = delta_sira(a, b)
    print("-" * 82)
    print(f"  KARAR  isaret testi: {t['yukari']} yukari / {t['asagi']} asagi / "
          f"{t['berabere']} berabere  ->  p = {t['p']:.3f}"
          f"   {'ORUNTU (p<0.05)' if t['p'] < 0.05 else 'gurultudan ayirt edilemiyor'}")
    print(f"  betim  ortalama Delta-sira: {d:+.2f} ({kac} sorguda, '-' iceren ciftler harictir)"
          if d is not None else "  betim  Delta-sira: hesaplanamadi")
    return t, d


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Retrieval eval (11 sorgu altin set)")
    p.add_argument("--rerank", action="store_true", help="cross-encoder rerank ac")
    p.add_argument("--medya", default=None, choices=["anime", "film", "kitap"],
                   help="medya filtresi (Gun 10-11 ile kiyas icin: anime)")
    p.add_argument("--hyde-n", type=int, default=config.HYDE_N_ORNEK)
    p.add_argument("--cipa", type=float, default=config.HYDE_CIPA,
                   help="A11: pusula ortalamasinda ham sorgunun payi (0=cipa yok, 1/(n+1)=makale)")
    p.add_argument("--kati", action="store_true",
                   help="eski KATI eslestirme (kanonik idMal); varsayilan franchise duzeyi")
    p.add_argument("--kotasiz", action="store_true", help="medya kotasini kapat (eski baseline)")
    p.add_argument("--tekilsiz", action="store_true", help="seri tekillestirmeyi kapat")
    p.add_argument("--no-cache", action="store_true",
                   help="sahte belgeyi her kosuda yeniden uret -> GURULTU TABANI olcumu icin")
    p.add_argument("--urunsuz", action="store_true",
                   help="[URUN] yolunu (isabet@k) atla — eval 3x hizlanir, sadece havuz olculur")
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
    # Havuzu buyutmek bi-encoder'a ~bedava: 12104 skor zaten hesaplaniyor, sadece kesme noktasi kayiyor.
    # Reranker icin AYNI SEY DEGIL — cross-encoder cift basina bir forward pass, maliyet dogrusal.
    k_listesi = (5, 10, 50) if a.aday <= 50 else (5, 10, 50, a.aday)
    config.ADAY = a.aday
    if a.kaynak is not None:
        config.ANIME_KAYNAK = a.kaynak  # belge() ve dolayisiyla index hash'i buna bagli

    gold_dogrula()
    degerlendir(k_listesi=k_listesi, rerank=a.rerank, medya=a.medya,
                hyde_n=a.hyde_n, cipa=a.cipa, hyde_cache=not a.no_cache,
                kota=not a.kotasiz, tekillestir=not a.tekilsiz,
                franchise=not a.kati, urun=False if a.urunsuz else None)
