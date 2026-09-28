# Android uygulaması — plan (karar: kararlı sürümden sonra)

Durum: **yalnızca plan.** Hiçbir kod yazılmadı. Hedef: önce kişisel kullanım (APK'yı telefona elle kurmak);
Google Play'de yayın ilk adımda yok.

## Temel sorun

World Signal'in iki ağır parçası telefona doğrudan taşınamaz:

- **Özetler** 8–26 milyar parametreli dil modelleriyle yazılıyor; bunlar telefonda çalışmaz ya da çok yavaş ve
  zayıf Türkçeyle çalışır.
- **Arka planda sürekli tarama** Android'de pil ve arka plan kısıtlarına takılır (sistem uygulamayı uyutur).

Bu yüzden iki yol var:

## Yol A — Eşlik uygulaması (önerilen ilk adım)

Telefon, bilgisayarınızda çalışan World Signal'in **ekranı** olur. Toplama, hikâyeler ve özetler bilgisayarda
yapılmaya devam eder; telefon hazır sonucu gösterir, notları ve toplantı listesini düzenler.

- **Arayüz:** mevcut React arayüzü aynen kullanılır, [Capacitor](https://capacitorjs.com) ile Android uygulamasına
  sarılır. Dokunmatik ekran ve dar ekran için düzen uyarlanır (arayüzün ~%80'i aynen çalışır).
- **Bağlantı:** bilgisayardaki World Signal bugün yalnızca kendisine (`127.0.0.1`) açık. Telefon için:
  - Ayarlar'da "Telefonumu bağla" düğmesi → bilgisayarın yerel ağ adresi ve tek seferlik bir eşleştirme kodu içeren
    bir **QR kod**;
  - telefon bu kodla kalıcı ama iptal edilebilir bir anahtar alır; bilgisayar yalnızca eşleşmiş cihazlara cevap verir;
  - evden/dışarıdan erişim için ücretsiz [Tailscale](https://tailscale.com) (şifreli özel ağ; port açmak gerekmez).
- **Çevrimdışı okuma:** telefon son akışı, toplantı listesini ve notları kendi içinde saklar; bağlantı yokken de
  okunur, notlar bağlantı gelince bilgisayara yazılır.
- **Telif:** tam metinler telefona da yalnızca okuma için gelir; çıktı kuralları aynı.
- **Tahmini iş:** 2–3 hafta. Bilgisayar kapalıysa telefon yalnızca son kaydedileni gösterir.

Bu yol, rafa kaldırılan "ortak mod"un tek kullanıcılı küçük bir parçasıdır (bilgisayarın ağa açılması, cihaz
anahtarları); ileride ortak moda geçişi de kolaylaştırır.

## Yol B — Tek başına çalışan Android uygulaması

Telefon bilgisayarsız çalışır.

- Toplama telefonda: RSS okuma ve kaynak kataloğu Kotlin ya da TypeScript'e taşınır; Android'in `WorkManager`'ı ile
  15–30 dakikada bir tarama (Android daha sık izin vermez).
- Hikâye birleştirme: küçük bir çok dilli gömme modeli telefonda (ONNX, ~100–500 MB) ya da yalnızca başlık
  benzerliğiyle daha basit bir birleştirme.
- Özetler: telefonda yok ya da isteğe bağlı bir bulut hizmetiyle (maliyet ve "veri dışarı gönderilmez" kuralı yeniden
  konuşulmalı).
- **Tahmini iş:** 2–3 ay; iki kod tabanının (Windows + Android) bakımı.

## Dağıtım (iki yol için de)

- APK'yı kendi anahtarınızla imzalarız; GitHub Releases'e Windows zip'inin yanına konur.
- Telefona ilk kurulum: APK'yı indirip "bilinmeyen kaynaklardan yüklemeye" bir kez izin vermek.
- Güncelleme: masaüstündeki gibi uygulama GitHub'daki son sürüme bakar, yenisini indirip Android'in kurulum ekranını
  açar (Android sessiz kurulum izin vermez; "Güncelle"ye siz basarsınız).

## Karar zamanı sorulacaklar

1. Yol A mı, Yol B mi (ya da önce A, gerekirse sonra B)?
2. Telefon bilgisayara yalnızca aynı ağdayken mi bağlansın, yoksa dışarıdan da (Tailscale) mı?
3. Telefonda hangi ekranlar olsun: yalnızca akış + toplantı listesi + notlar mı, yoksa ayarlar ve kaynaklar da mı?
