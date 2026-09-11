# Kod incelemesi — Faz 5 Gün 0-2 dalı (`ajan`)

**Tarih:** 2026-09-11 · **Kapsam:** `main...ajan` (12 dosya, 1083 satır ekleme)
**Yöntem:** 10 bağımsız tarama açısı (satır satır diff, kaldırılan davranış, çağrı izleme,
dil tuzakları, sarmalayıcı doğruluğu, tekrar/basitleştirme/verimlilik, irtifa, CLAUDE.md
uyumu) + boşluk taraması. 15 bulgu, hepsi uygulandı.

**Sonuç:** 16 dosya, +350 / −132 satır. 50 davranış kontrolü, 50'si geçti.

---

## Neden bu belge var

Bu dalda üç şey aynı anda oldu: kitap corpus'u Open Library'ye taşındı, retrieval bir
araca dönüştü, çıplak bir ReAct döngüsü yazıldı. İncelemenin bulduğu hataların çoğu tek
tek küçük ama **hepsi aynı aileden**: fazın 1 numaralı teması olan *sessiz hata*. Hiçbiri
patlamıyor, hepsi yanlış bir sayı ya da eksik bir kayıt üretip susuyor. Aşağıdaki kayıt
"ne düzeldi"den çok **"hangi sessizlik kapandı"** listesi olarak okunmalı.

---

## 1. Sessiz veri kaybı — `scripts/cek_openlibrary.py`

### 1a. Resume dedup'ı hiç çalışmıyordu

`mevcut_idler` dosyadan **çıplak** id okuyor (`OL262454W`, çünkü kayda öyle yazılıyor),
üyelik testi ise OL'un verdiği **tam anahtarla** yapılıyordu (`/works/OL262454W`). İkisi
asla eşit olmuyor.

Sonucu: docstring'in açıkça vaat ettiği şey (`kesilebilir: dosyadaki work id'leri
atlanir`) hiç işlemiyordu. İkinci bir koşu 4794 eserin **tamamını yeniden çekip dosyaya
yeniden eklerdi** → corpus'ta çift kayıt, `kota_sec` sadece anime franchise'ını
tekilleştirdiği için aynı kitap 5 slotun birkaçını kapar, ayrıca belge içerik hash'i
değiştiği için 12104 vektörün tamamı çöpe giderdi.

Şu an dosyada çift kayıt **yok** — çünkü onu üreten koşu hiç yeniden başlatılmamış.
Hata, birisi kesilen bir koşuyu devam ettirene kadar tamamen görünmez.

> Karşılaştırma çıplak id'ye eşitlendi. Doğrulandı: dosyadaki 4794 eser artık atlanıyor
> (0 aday), yeni bir eser hâlâ aday olarak geçiyor.

### 1b. Ağ hatası "açıklaması yok" ile aynı torbaya giriyordu

`_liste` dört kez yeniden deniyordu ama `_detay` **hiç** denemiyordu: bir
`RequestException` ya da 200 olmayan herhangi bir yanıt `None` dönüyor, çağıran da onu
`atlanan_bos` sayıp "N açıklamasız atlandı" diye loglıyordu. 12 eşzamanlı istekle koşan
bir betikte geçici bir 429/503 dalgası böylece **kaynağın özelliği gibi** raporlanıyordu.

Aynı karıştırma `_liste`'de de vardı: dört deneme de tutmazsa `[]` dönüyor, `main` bunu
"konu tükendi" okuyup `break` ediyordu — geçici bir kesinti konuyu yarıda bırakıp
"havuz bitti" diye loglanıyordu.

> `CEKILEMEDI` sentinel'i eklendi, `_detay` artık `_liste` gibi 4 kez deniyor, `_liste`
> kalıcı hatada `None` dönüyor. Üç durum artık üç ayrı şey: **veri yok** / **biz
> alamadık** / **havuz bitti**. Bitiş logu kayıp sayısını ayrı basıyor.

### 1c. Resume kotayı baştan dolduruyordu

`kota` konu başına **toplam** hedef (varsayılan 334), ama `konu_yeni` her koşuda 0'dan
başlıyordu. 300'de kesilen bir konu, yeniden başlatınca 334 tane daha çekip 634'e
çıkardı; tamamlanmış bir koşunun üstüne basmak ~5000 kayıt daha eklerdi.

> Sayaç dosyadaki `_arandigi_konu` sayımından tohumlanıyor; kotası dolu konu hiç ağa
> çıkmadan atlanıyor.

### 1d. Tek `requests.Session` 12 iş parçacığında

`requests.Session` thread-safe değil (cookie jar, redirect/adapter durumu paylaşılır).
Belirtisi izsiz: bozulan istek `_detay`'dan `None` olarak döner, o da (1b sayesinde)
"açıklaması yok" diye sayılırdı — iki hata birbirini gizliyordu.

> Oturum `threading.local` ile iş parçacığı başına. Ayrıca havuz konu döngüsünün dışına
> alındı: sayfa başına havuz kurmak ~750 kez 12 iş parçacığı açıp kapatmak demekti.

---

## 2. Ajan döngüsü — `dongu.py`

### 2a. Model sözlük dışına çıkınca bütün koşu ölüyordu

`_arac_calistir` sadece `TypeError` yakalıyordu. Model `medya="Anime"` (ya da "books",
"kitaplar") yazdığında değer araca değil `retrieval.getir`'e gidiyor ve
`_medya_maskeleri(corpus)["Anime"]` **KeyError** fırlatıyordu. Bu istisna `dongu()`'den
kaçıyor, üstelik aracın içindeki HyDE çağrısı **zaten ödenmişken** koşuyu öldürüyordu.

Docstring'in verdiği söz şuydu: *"bozuk argumanlar HATA MESAJI olarak doner, exception
firlatmaz — ajan bunu gozlem olarak okuyup kendini duzeltebilsin diye."* O söz tek bir
istisna tipiyle tutulamaz.

> Geniş yakalama eklendi; mesaja istisna tipi ve geçerli medya değerleri yazılıyor ki
> ajan neyi düzelteceğini bilsin.

### 2b. Ölçülmüş kural sadece prompt'ta duruyordu

Gün 0 ölçümü net: 8 sorgu, beş çekilişin beşinde de başarısız — **aynı sorguyla tekrar
aramak faydasız**. Ama bu kuralın tek uygulayıcısı sistem prompt'undaki bir cümleydi,
yani modelden bir *rica*. Model tekrarladığında döngü bir tam tur harcıyordu: bir ajan
LLM çağrısı, bir HyDE çağrısı, bir corpus matmul'ü ve ~2.5k karakter bağlam — geçmişte
zaten duran bir sonuç için.

Dosya bu argümanı HARD_CAP için kendisi yapıyor: *"Hard cap modelin kararina bagli
OLMAYAN tek fren."* Aynı gerekçe buraya da uygulandı.

> Döngü artık görülen `(arac, args)` çiftlerini tutuyor; tekrar gelen çağrı
> **çalıştırılmıyor**, yerine sebebi gözlem olarak dönüyor ("sorguyu DEĞİŞTİR"). Tur
> kaydına `tekrar: True` düşüyor.

### 2c. Tur kaydı faturayı göstermiyordu

`sure_sn`, `_llm_turu` **döndükten sonra** başlatılıyordu — yani turun kendi model
çağrısı, gecikmenin ve faturanın büyük kısmı, ölçümün dışındaydı. Token/çağrı sayısı hiç
yoktu. `_llm_turu` bozuk JSON'da `MAX_ONARIM=3` çağrı yakabildiği için 6 turluk bir koşu
**18 ajan çağrısı** ödeyip `turlar`'da 6 satır gösterebiliyordu.

Dosya bu riski iki yerde kendisi yazıyor: *"fatura tur basina odenir"* ve *"bu fazin
sessiz hatasi '14 tur dondu ama kimse fark etmedi'"*.

> Ölçüm turun başında başlıyor; kayda `llm_cagri`, `girdi_tok`, `cikti_tok` eklendi
> (`llm.sayac` farkından). Onarım denemeleri ve aracın içindeki HyDE çağrısı artık tur
> kaydında görünüyor. `__main__` koşu başında `llm.sayac.sifirla()` çağırıyor (app.py'nin
> deseni).

---

## 3. Ölçüm hizası — `eval.py`, `deney_a12.py`

### 3a. `--no-cache` üç ayrı pusulayı tek ölçüm gibi basıyordu

`isabet_at_k` her `k` için **ayrı** bir `getir()` çağırıyor. `hyde_cache=True` iken üçü de
aynı cache anahtarını vurduğu için pusula paylaşılıyor — ama `--no-cache` (belgelenmiş
gürültü tabanı modu) her çağrıda farklı bir sahte belge üretiyor. O zaman isabet@5 ile
isabet@10 farklı pusulalardan geliyor, `isabet@5 <= isabet@10` şartı bozulabiliyor ve
hiçbiri üstündeki recall@k satırıyla aynı çekilişi paylaşmıyor.

Bu tam olarak `siralar()`'ın 12 satır aşağıda uyardığı hata: *"iki konfig iki AYRI HyDE
cekilisiyle kosar ve isaret testi LLM gurultusunu degisiklige yazar."*

> `degerlendir`'e `urun` parametresi eklendi, varsayılanı `hyde_cache`. Çekiliş donmuş
> değilse ürün yolu **atlanıyor** ve sebebi basılıyor.

### 3b. Ürün yolu her çağırana 3x bedel yazıyordu

`degerlendir` sorgu başına 1 değil 3 `getir()` çağırmaya başlamıştı (23 → 69). Her fazladan
çağrı e5 ile sahte belgeyi yeniden gömüyor ve 12104×1024 matmul'ü tekrarlıyor.
`deney_a11.py` 10 satırlık bir ızgarada `degerlendir` çağırıyor — 230 çağrı 690 olmuş,
üstelik özet tablosu yalnızca recall/MRR bastığı için **fazladan 460 çağrının tamamı
çöpe** gidiyordu.

> `urun=False` seçeneği, CLI'da `--urunsuz` bayrağı; `deney_a11` artık `urun=False`
> veriyor. **69 → 23 çağrı.**

### 3c. A12 havuz sayısını ürün adıyla raporluyordu

`deney_a12.kos()` tek bir `getir(k=50)` listesinden sıra alıp ilk 5'i sayıyor ve buna
"recall@5" diyordu — yani **aynı commit'te `isabet_at_k`'nın düzeltmek için eklendiği
karıştırmanın** kendisi. Kota `k` ile ölçekleniyor (k=50 → 30/10/10, k=5 → 3/1/1), o yüzden
iki listenin bileşimi farklı: eval yolu ilk-5'i 69 kitap/38 anime/8 film, ürün yolu
69 anime/23 film/23 kitap. A12'nin konusu tam da kitap corpus'unun tür metni, yani iki
bileşimin en çok ayrıştığı eksen.

> Anahtar `recall@k` → **`havuz@k`**. A/B için havuz ölçüsü daha hassas, ama adı ürün
> ölçüsünü ima etmemeli. ⚠️ Eski `data/a12_*.json` dosyaları eski anahtarlı —
> `--karsilastir` için iki dosya aynı sürümle üretilmiş olmalı.

---

## 4. Çöken kenar durumlar — `sinyaller.py`, `deney_gun0.py`

`getir` **k'dan az** kayıt dönebiliyor (aday havuzu tekilleştirmeden sonra tükenirse) ve
`araclar.ara` `k`'yi modele bırakıyor. Tek sonuçta `benzerlik` `n*(n-1) = 0`'a bölüp
ZeroDivisionError, sıfır sonuçta `skor_bandi` ValueError veriyordu — ikisinde de
`deney_gun0.auc`'un titizlikle koyduğu `if not ...` guard'ı yoktu.

Aynı delik rapor yolunda: `sum(iyi)/len(iyi)`, `auc` iki satır yukarıda boş grup için nan
dönerken korumasız duruyordu. Bütün sorguların başarılı (ya da hepsinin başarısız) olduğu
bir konfig, **ölçüm tamamen ödendikten sonra** raporu basarken çökerdi.

> `nan` guard'ları eklendi. `nan` seçildi, `0.0` değil: sıfır "bant yok, model bilmiyor"
> diye okunur ve sinyali sessizce bozar. `auc()`'un zaten yaptığının aynısı.

---

## 5. Bağlam bütçesi — `araclar.py`, `veri.py`, `config.py`

`_getir_kirp` ajana `veri.belge()` veriyordu; belge `"baslik. turler. ozet"` üretiyor ve
`_metin` başlığı **zaten kendi satırında** yazıyordu. Yani her sonuçta başlık iki kez
geçiyor, üstelik başlık+tür öneki 512 karakterlik bütçenin bir kısmını yiyordu — ajan
bütçenin ima ettiğinden **daha az sinopsis** görüyordu.

`config.AJAN_OZET_KRK` yorumu da yanlıştı: "%47'si kirpilir, %53'u dokunulmadan gecer"
diyordu, ölçüm tam tersini veriyordu.

> `veri.ozet()` ayrıldı (`belge()` artık onu çağırıyor), ajan sinopsisi okuyor.
>
> **`belge()`'nin ürettiği string bit bazında aynı kaldı** — imza `751ac70e29`, mevcut
> `cache/V_multilingual-e5-large_751ac70e29.npy` ile eşleşiyor. O string index cache
> anahtarı olduğu için bir karakter oynasa 12104 vektör boşa giderdi.
>
> Yorum **yeniden ölçülerek** düzeltildi. Ajan artık `belge()` değil `ozet()` okuduğu için
> eski sayı zaten yanlış tabandaydı:
>
> | | 512'de kırpılan | Dokunulmayan | Ortalama |
> |---|---|---|---|
> | eski yorum (`belge()`, ters yazılmış) | %47 | %53 | — |
> | `belge()` gerçek | %53.2 | %46.8 | 655 krk |
> | **`ozet()` — ajanın okuduğu** | **%49.8** | **%50.2** | **606 krk** |

---

## 6. Bayatlamış gerçekler (kaynak değişiminin arkada bıraktığı)

Corpus bu dalda 7807 → **12104** oldu (4880 anime / 4794 kitap / 2430 film) ve kitap
kaynağı Google Books → Open Library'ye taşındı, ama bunu söyleyen her yorum eski hâlde
kaldı. `config.py`'de değişen `LINK["kitap"]` satırının **hemen üstü** bile "kitap google
books id kullanir" diyordu — ve o dosyanın kendi yorumu sessiz link hatasının yeni
yakalandığını anlatıyor.

> Güncellendi: `config.py`, `eval.py` (modül başlığı, gold ad-alanı notu, kitap gold
> kararı), `sinyaller.py` (`V: (12104, 1024)`), `profil.py` (3 yer), `app.py`, `izle.py`,
> `demo_hazirla.py`, `README.md`.
>
> **Demo paketine ait 7807 referansları doğru** (paket 2026-09-06'da, taşınmadan önceki
> corpus'tan üretildi, `provenance.json` hash `e5f0dd87fb`) — bunlar değiştirilmedi,
> yalnızca "hangi corpus'tan" notu eklendi.

---

## Doğrulama

Ağ yok, model yüklenmedi (`llm.cagir` ve `retrieval.getir` stub'landı). **50 kontrol,
50 geçti.** Öne çıkanlar:

| Ne | Kanıt |
|---|---|
| Resume artık atlıyor | dosyadaki 4794 eser → **0 aday**; yeni eser hâlâ aday |
| `belge()` bozulmadı | imza `751ac70e29` = mevcut cache dosyası → **vektör kaybı yok** |
| `permutasyon` aynı sonucu veriyor | AUC tuple'ları ve p değerleri birebir (1.0 / 0.39375), **4–5× hızlı** |
| Ürün yolu opsiyonel | 69 → 23 çağrı; `hyde_cache=False` iken `isabet@` anahtarı hiç üretilmiyor |
| KeyError gözleme dönüyor | `HATA: 'ara' calistirilamadi (KeyError: 'Anime')...` |
| Tekrar freni | 1. tur çalıştı, 2–3. turlar açıklayıcı gözlem döndü (`tekrar: True`) |
| Onarım çağrısı görünür | bozuk JSON'lu turda `llm_cagri=2` |
| 19 modül derleniyor | `py_compile`; `eval.py --help` ve `cek_openlibrary.py --help` çalışıyor |

Doğrulama betiği tek kullanımlıktı ve depoya **girmedi** — bu depoda test altyapısı yok,
kurmak ayrı bir karar (bkz. aşağı).

---

## Yapılmayanlar

- **`araclar.py:117-121`**: ölü `# TODO(sen):` yorumu ve sonundaki boşluk duruyor. 15
  bulgunun içinde değildi, kapsam dışı bırakıldı.
- **`_turleri_esle` bağlam yanlış-pozitifleri**: kelime sınırı `"war" ⊂ "Warsaw"` sorununu
  çözüyor ama `"English Civil War"` gibi **özel ad/dönem başlıklarını** çözmüyor —
  Baskerville Tazısı bu yüzden `War` etiketi alıyor. Ölçüldü: `War`ın 695 kaydının büyük
  kısmı meşru ("War stories" 154, "World War, 1939-1945" 75), o yüzden rapora girmedi.
  Tür metni üzerine bir A/B (A12'nin devamı) bunu ölçmenin doğru yeri.
- **Test altyapısı**: yok. Yukarıdaki 50 kontrolün kalıcı bir `tests/` altına taşınması
  ayrı bir karar; bu incelemenin kapsamı değildi.
