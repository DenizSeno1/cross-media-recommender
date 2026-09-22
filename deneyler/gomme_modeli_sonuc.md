# Gömme modeli deneyi — sonuçlar

**Soru:** Gömme (bi-encoder) modeli değişince ürünün döndürdüğü liste ne kadar değişiyor?
**Tarih:** 2026-09-16 → 2026-09-17 · **Dal:** `gomme-modeli` (taban `a269f9c`, değişiklikler commit edilmedi)
**Koşu:** `python -u deneyler/deney_gomme_modeli.py --hepsi` + iki kesintiden sonra `--hepsi --devam` · çıkış kodu **0**

**Kısa sonuç:** Gömme modelini değiştirmek, ürünün verdiği ilk 5'i hiçbir ayarda gürültüden
ayırt edilebilir biçimde değiştirmedi. Anlamlı fark yalnızca hedefin ilk 50 içindeki sırasında,
3 yerde çıktı; ikisi HyDE kapalıyken e5-base'in geride kalması.

**Koşullar (bütün tablolarda aynı):** 60 gold sorgu (20 anime · 20 film · 20 kitap), 12104 kayıt,
dondurulmuş HyDE (n=1, çıpa 0), kota, tekilleştirme ve seri eşleştirme açık, `max_seq_length` 512,
RTX 3050 Laptop 4 GB (fp16 bi-encoder + fp32 reranker). Ajan döngüsü deneye girmedi.

Modeller: `intfloat/multilingual-e5-large` (L) · `intfloat/multilingual-e5-base` (B) · `BAAI/bge-m3` (M).

---

## 1. Sıra tablosu (ürün yolu)

isabet@5 = `getir(k=5)`; recall@50 ve MRR = ayrı bir `getir(k=50)` çağrısı. Medya sütunları 20 sorgu
üzerinden isabet sayısı.

| HyDE | rerank | model | isabet@5 | anime | film | kitap | recall@50 | MRR |
|---|---|---|---|---|---|---|---|---|
| açık | kapalı | e5-large | 0.383 (23) | 11 | 9 | 3 | 0.700 | 0.321 |
| | | e5-base | 0.433 (26) | 12 | 10 | 4 | 0.617 | 0.311 |
| | | bge-m3 | 0.367 (22) | 7 | 12 | 3 | 0.633 | 0.339 |
| kapalı | kapalı | e5-large | 0.250 (15) | 5 | 7 | 3 | 0.567 | 0.253 |
| | | e5-base | 0.150 (9) | 3 | 6 | 0 | 0.400 | 0.121 |
| | | bge-m3 | 0.267 (16) | 4 | 9 | 3 | 0.533 | 0.270 |
| açık | açık | e5-large | 0.550 (33) | 12 | 13 | 8 | 0.800 | 0.527 |
| | | e5-base | 0.500 (30) | 14 | 12 | 4 | 0.700 | 0.488 |
| | | bge-m3 | 0.517 (31) | 11 | 13 | 7 | 0.683 | 0.482 |
| kapalı | açık | e5-large | 0.450 (27) | 9 | 12 | 6 | 0.650 | 0.413 |
| | | e5-base | 0.350 (21) | 7 | 10 | 4 | 0.550 | 0.314 |
| | | bge-m3 | 0.383 (23) | 6 | 10 | 7 | 0.600 | 0.372 |

## 2. Modeller arası işaret testleri

İki yönlü, p<0.05 ise "gerçek fark". isabet@5 testinde yalnız bir modelin bulduğu sorgular sayılır
(ikisinin de bulduğu / ikisinin de kaçırdığı düşer). Sıra testi `eval.karsilastir_siralar` (k=50).

| HyDE / rerank | çift | isabet@5: yalnız biri buldu | p | sıra (k=50): kim önde | p |
|---|---|---|---|---|---|
| açık / kapalı | L – B | L 2 · B 5 | 0.453 | L 20 · B 15 | 0.500 |
| | L – M | L 6 · M 5 | 1.000 | L 19 · M 20 | 1.000 |
| | B – M | B 8 · M 4 | 0.388 | B 20 · M 17 | 0.743 |
| kapalı / kapalı | L – B | L 8 · B 2 | 0.109 | **L 26 · B 6** | **0.001 ✓** |
| | L – M | L 4 · M 5 | 1.000 | L 14 · M 16 | 0.856 |
| | B – M | B 2 · M 9 | 0.065 | **B 8 · M 26** | **0.003 ✓** |
| açık / açık | L – B | L 7 · B 4 | 0.549 | L 11 · B 10 | 1.000 |
| | L – M | L 4 · M 2 | 0.688 | **L 19 · M 6** | **0.015 ✓** |
| | B – M | B 6 · M 7 | 1.000 | B 16 · M 8 | 0.152 |
| kapalı / açık | L – B | L 9 · B 3 | 0.146 | L 12 · B 13 | 1.000 |
| | L – M | L 8 · M 4 | 0.388 | L 15 · M 10 | 0.424 |
| | B – M | B 6 · M 8 | 0.791 | B 17 · M 11 | 0.345 |

**Nasıl okunur:**

- **isabet@5 testlerinin 12'sinde de fark yok.** Bu "modeller aynı" demek değil. Yalnız bir modelin
  bulduğu sorgu sayısı her çiftte 6–14 arası. Bu büyüklükte p<0.05 çıkması için 10'a 2 gibi büyük bir
  ayrışma gerekir. Yani bu deney ilk 5'teki küçük farkları göremez.
- **Sıra testlerinde 3 gerçek fark var:**
  1. HyDE kapalı, rerank kapalı: e5-large, e5-base'den önde (26'ya 6).
  2. Aynı ayarda bge-m3, e5-base'den önde (26'ya 8).
  3. HyDE açık, rerank açık: e5-large, bge-m3'ten önde (19'a 6).

  İlk ikisi aynı şeyi söylüyor: HyDE kapalıyken e5-base geride kalıyor. HyDE açıkken bu fark görünmüyor.
- **Çoklu karşılaştırma notu:** 24 test yapıldı. Gerçekte hiç fark olmasa bile ~1 testin tesadüfen
  p<0.05 çıkması beklenir. Daha sıkı bir eşik (0.05/24 ≈ 0.002) uygulansaydı yalnız 1. fark kalırdı
  (p≈0.0005); 2. (p≈0.003) ve 3. (p=0.015) düşerdi. Hükümler spec'teki p<0.05 kuralına göre verildi,
  bu yalnızca okurken akılda tutulacak bir not.

## 3. Skor bandı (betimleyici, kazanan seçmez)

Yalnız bi-encoder, rerank'ten bağımsız. Her sorgunun 12104 skorunun min/medyan/maks'ı alındı,
60 sorgu üzerinden medyanı raporlandı. Hedefin ham sırası maskesiz, bütün corpus içindeki sıra.

| model | HyDE | min | medyan | maks | hedefin skoru | hedefin ham sırası |
|---|---|---|---|---|---|---|
| e5-large | açık | 0.662 | 0.728 | 0.808 | 0.786 | 25.5 |
| e5-large | kapalı | 0.670 | 0.737 | 0.814 | 0.792 | 42 |
| e5-base | açık | 0.667 | 0.738 | 0.819 | 0.794 | 30.5 |
| e5-base | kapalı | 0.688 | 0.757 | 0.828 | 0.802 | 144.5 |
| bge-m3 | açık | 0.231 | 0.476 | 0.683 | 0.639 | 11 |
| bge-m3 | kapalı | 0.221 | 0.443 | 0.640 | 0.582 | 24 |

- **e5 modelleri 12104 kaydı ~0.15 genişliğinde dar bir banda sıkıştırıyor, bge-m3 ~0.45'lik bir
  aralığa yayıyor.** Ölçekler farklı, ham skor modeller arasında karşılaştırılamaz.
- **Ham sıra ürünün sırası değil:** maskesiz, kotasız ve tekilleştirmesiz. Nitekim bge-m3 ham sırada
  en önde (11) ama ürünün ilk 5'inde öne geçmiyor (22/60).

## 4. Süreler

- **Index gömme (12104 belge, tek çağrı, reranker yüklenmeden):** e5-base 43.9 sn · bge-m3 130.1 sn ·
  e5-large 138.5 sn. e5-large 16 Eylül'de yeniden başlatmadan önceki oturumda ölçüldü, öbür ikisi
  sonrakinde. Oturumlar arası 2,5 katlık oynama görüldü, bu sayılar kaba.
- **getir sn, rerank kapalı (60 sorgunun medyanı):** üçü de 17 Eylül sabahı aynı oturumda ölçüldü,
  hepsi 0.1 sn'nin altında. e5-base 0.06–0.07, bge-m3 0.08–0.09, e5-large 0.09.
- **Rerank açık süreler (12.7–88.5 sn):** karşılaştırma dışı. Bi-encoder + reranker 4 GB VRAM'e
  sığmıyor, ~1.9 GB sistem RAM'ine taşıyor. Taşma miktarı modele göre değişiyor, ayrıca bu hücreler
  farklı oturumlarda koştu. Hücre süreleri: e5-large 100 / 81 dk, e5-base 89 / 137 dk,
  bge-m3 ~230 / ~224 dk (HyDE açık / kapalı).

## Geçerlilik

- **Kabul kapısı** üç oturumda da kayıtlı sayıları birebir üretti: e5-large, HyDE açık + rerank
  kapalı → 23/60 · 0.700 · 0.321; HyDE kapalı + rerank kapalı → 0.250 · 0.567. Bu aynı zamanda önek
  değişikliğinin (`config.ONEKLER`) e5'in davranışını bozmadığının kanıtı.
- **12 hücrenin kimlik satırları doğru:** model (`model_card_data.base_model`), önek (e5:
  `query:`/`passage:`, bge-m3: boş), `max_seq_length` 512, cihaz cuda.
- **Üç model aynı corpus'u gömdü:** index dosyalarının belge imzası aynı (`751ac70e29`).
- **Ürün kodunun sha1'i 21 kaydın hepsinde aynı:** `config.py` 0439940214 · `retrieval.py` 19ce9b149a ·
  `eval.py` 78961a8444.
- **Deney dosyasından 2 sürüm var:** 4 kayıt eski sürümle (`ffd9ec2718`: e5-large index süresi,
  iki bandı, HyDE açık rerank hücresi), 17 kayıt yeni sürümle (`3f1d2ae147`). Aradaki fark yalnızca
  devam etme (`--devam`), log (`-u`) ve kaynak izi (`onfig.py` hatası) kısımlarında; ölçüm yoluna
  dokunmuyor.
- **Tutarlılık denetimi hiç patlamadı:** `degerlendir`'in MRR'si ile `siralar`'ın sırası her sorguda
  aynı sonucu verdi (dondurulmuş girdi varsayımı tuttu).

## Açık kalanlar

- **Kör review:** kademe 2 kodunun teslimi bu. Yapılmazsa kayda "ölçülmemiş" diye düşer.
- **Sessizce yanlış gömebilecek iki yer:** `izle.py:50` ve `scripts/demo_hazirla.py` e5 önekini ve
  token sınırını hâlâ kendileri tutuyor. `BI_MODEL` değişirse yanlış gömerler.
- **Commit yok:** değişiklikler `gomme-modeli` dalında commit edilmemiş duruyor.
- **Kayıt ve borç:** 16–17 Eylül gün kaydı yazılmadı. Kademe 1 borcu da duruyor: `dongu()` ajanın
  listesini döndürsün.

---

**Ham veri:** `data/gomme_modeli.json` (hücre, bant, index süresi, sorgu bazında sonuçlar,
karşılaştırmalar, kaynak izi). `data/` `.gitignore`'da, dosya depoya girmiyor.
**Kod:** `deneyler/deney_gomme_modeli.py` · kabul testleri `testler/test_gomme_modeli.py`.
