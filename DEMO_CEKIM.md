# Demo GIF — çekim senaryosu

**Amaç:** 20-25 saniyede projenin *ayırt edici* tarafını göstermek. Uzun olmasın; işe alım
uzmanı GIF'i 10 saniye izler.

**Araç önerisi:** [ScreenToGif](https://www.screentogif.com) (ücretsiz, doğrudan GIF verir,
kırpma/hız ayarı içinde). Alternatif: Win+G (Xbox Game Bar) ile mp4 çek, sonra GIF'e çevir.

**Ayarlar:** tarayıcı penceresini ~1280×800 yap, zoom %100. Sadece uygulama görünsün —
sekme çubuğu, yer imleri, masaüstü görünmesin. 12-15 FPS yeter.

---

## Kayıt sırası

1. **Sayfa hazır haldeyken başla** — "Model + index ısıtılıyor" ekranı GIF'e girmesin.
   (Uygulama zaten açık ve ısınmış olmalı.)

2. **Sol panelden MAL XML'ini yükle.** "10 zevk adası kuruldu, 617 kayıt elendi" satırı
   görünsün — kişiselleştirmenin gerçek olduğunun kanıtı bu.

3. **Sorguyu yaz** (elle yaz, yapıştırma — yazılışı görünsün):

   > ölüm ve yas üzerine sakin fantastik yolculuk

4. **Enter.** Spinner dönerken kesme — bekleme süresi dürüstlüğün parçası, ~5-10 sn.

5. **Sonuçlar gelince 3-4 saniye bekle.** Kritik kare bu: listede **anime, film ve kitap
   bir arada** görünüyor. Projenin tek cümlelik iddiası orada.

6. **"Neden bu liste?" bölümüne kaydır**, gerekçe metni görünsün.

7. **Altta maliyet sayacını göster** (çağrı/token/USD), sonra bitir.

---

## Kırpma sonrası

- Baştaki boş kareleri ve sondaki fazlalığı at.
- Bekleme süresi uzun geldiyse **hızlandırma**, kes — sahte hız portföyde yalan olur.
- Dosya adı: `demo.gif`, `gorseller/` altına koy. 5 MB'ı geçerse ScreenToGif'ten renk sayısını
  düşür ya da boyutu %75'e indir.

## Çekmeyeceğin şeyler

- **Rerank'i açma.** CPU'da 1.5-3 dk/sorgu; GIF'te bekleyiş anlamsız görünür.
  README zaten +0.18 kazancını ve neden kapalı olduğunu yazıyor.
- **API anahtarı, .env, terminal** görünmesin.
- Boş/başarısız sorgu denemesi çekme — ayrı bir kare olarak değerli ama bu GIF'in işi değil.
