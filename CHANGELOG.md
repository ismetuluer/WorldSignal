# Değişiklik günlüğü

Sürüm numaraları [Anlamsal Sürümleme](https://semver.org/lang/tr/) izler. 1.0'a kadar her faz bir ara sürümdür.
İngilizcesi (0.10.0'dan itibaren): [CHANGELOG.en.md](CHANGELOG.en.md).

## [0.12.0] — 2026-09-29 — Başka dillerde arama ve İstatistik

### Eklendi
- **İstatistik ekranı** (yeni "İstatistik" sayfası). Üstten dönem: 24 saat (saat saat), 7 ya da 30 gün (gün gün).
  - **Özet sayılar:** haber, hikâye ve bağımsız kaynak sayısı (aynı medya grubu tek kaynak), önceki eşit süreye göre
    değişimle.
  - **Konu trendi:** bir konu yazınca saat/gün başına kaç haberde ve kaç kaynakta geçtiği ve tüm haberler içindeki
    payı. Kaynaklarınızın dillerinde de aranır (aşağıdaki yeni arama gibi). Konu yokken tüm haberlerin dağılımı.
  - **Gündem payı:** kategorilere göre (yalnızca kategorisi bilinen haberler; oranı yazılır) ve haberi veren basının
    bölgesine göre; önceki döneme göre kaç puan değiştiği.
  - **Yükselenler:** son 6 saatte (7 günde son 24, 30 günde son 72 saatte) en hızlı büyüyen hikâyeler; tıklayınca açılır.
  - **Kaynaklar:** kaynak başına haber, hikâye, son haber zamanı; bu dönemde hiç haber vermeyenler de görünür.
  - **Haberlerde en çok geçen ülkeler** (yapay zekânın okuduğu haberler üzerinden; kaç haber olduğu yazılır).
  - Her grafik tablo olarak da gösterilebilir; üzerine gelince ya da klavyeyle seçince değerler çıkar. Toplama önceki
    dönemi kapsamıyorsa "karşılaştırma için yeterli geçmiş yok" yazar, yanıltıcı değişim gösterilmez.
- **Arama, kaynaklarınızın yayın dillerinde de yapılıyor.** Çoğu yabancı haberin Türkçe özeti olmadığından (yapay
  zekâ her habere yetişemiyor) Türkçe arama bu haberleri bulamıyordu; örneğin WSJ'nin "North Korea Is Testing Swarm
  Attacks Mixing Drones and Missiles" haberi "kuzey kore iha" ile çıkmıyordu. Artık yazdığınız kelimeler hemen aranıyor,
  ardından yapay zekâ onları etkin kaynakların dillerine çeviriyor ("North Korea drone", "Северная Корея беспилотник",
  "Nordkorea Drohne" …) ve bu haberler de listeye ekleniyor. Akış'ta ve Geçmiş'te çalışır; arama kutusunun altında
  hangi çevirilerle arandığı ya da neden çevrilemediği (yapay zekâ kapalı, ekran kartında başka model…) yazar.
  Bu bilgisayarda ölçülen: "kuzey kore" 14 yerine 140, "seçim" 118 yerine 574, "ateşkes" 60 yerine 178 haber buluyor.
- Çeviri, yazmayı bıraktıktan sonra istenir ve oturum boyunca hatırlanır. Ollama ile birkaç saniye sürer; ekran
  kartı özet işleriyle meşgulse 20 saniyeye kadar çıkabilir.
- Bulut yapay zekâ seçiliyse arama kelimeleri de o hizmete gönderilir; Ayarlar'daki uyarı buna göre güncellendi.

### Değişti
- **Abonelik siteleri Kaynaklar sayfasına taşındı** (olduğu gibi, ücretli kaynakların altında). Ayarlar → Tam metin'de
  oraya giden bir düğme var.
- **Abonelik sitelerinde insan gibi okuma, daha yavaş** (bot korumasına takılmamak için). Tarayıcıyla okunan sitelerde:
  aynı siteden iki sayfa arasında en az 20 dakika (sizin istediğiniz sayfalarda 3 dakika); site başına günde en çok
  15 sayfa; gece 00:00–07:00 arası kendiliğinden sayfa açılmaz (sizin istekleriniz yine alınır); her sayfa açılınca
  önce birkaç saniye bakılıyor, sonra düzensiz adımlarla aşağı kaydırılıyor (20–60 saniye) ve metin ondan sonra
  alınıyor; sayfalar arası bekleme 25–60 saniyeden 1–3 dakikaya çıktı. Ayarlar → Tam metin → **Abonelik sitelerinde
  okuma temposu** ve **Gece abonelik sitelerini okuma**'dan değiştirilebilir. CAPTCHA yine asla çözülmez.

### Denendi, kullanılmadı
- **Anlamsal arama** (hikâye birleştirmedeki bge-m3 ile): ölçümde kısa Türkçe aramalar yabancı haber bulmadı, en
  üste aynı dildeki başlıkları ve "United Nations", "Flaş" gibi bölüm adlarını getirdi. Yalnızca uzun, tarif eden
  aramalarda işe yarıyordu ve yalnızca son 7 günü kapsayabiliyordu.

## [0.11.2] — 2026-09-29 — İndirilen zip ve Yenilikler düzeltmesi

### Düzeltildi
- **İnternetten indirilen zip'ten çıkarılan program açılmıyordu** ("Failed to resolve Python.Runtime.Loader.Initialize").
  Windows, indirilen zip'ten çıkan her dosyayı "internetten geldi" diye işaretliyor; .NET de pencereyi çizen
  kitaplıkları (Python.Runtime, WebView2) bu işaret yüzünden yüklemiyordu. Paketteki yeni `WorldSignal.exe.config`
  bunlara yerel dosya gibi yüklenme izni veriyor; bu dosya olmadan paket hazırlanmıyor.
- **"Yenilikler" penceresinde cümleler yarıda alt satıra geçiyordu** ve `###`, `**` gibi işaretler görünüyordu. Sürüm
  notları artık başlık, madde ve kalın yazıyla düzgün gösteriliyor; satırlar pencere genişliğine göre akıyor.
- Başlığın **sonunda** "(Exclusive)" yazan haberler (Trend News Agency'nin yazımı) **Özel** rozeti almıyordu.

## [0.11.1] — 2026-09-28 — Güncelleme düzeltmesi

### Düzeltildi
- **Program içinden güncelleme "program klasörü kullanımda" hatasıyla başarısız oluyordu.** World Signal Dosya
  Gezgini'nden açıldığında program klasörü onun çalışma klasörü oluyor, güncelleyicinin başlattığı yeni program da
  bunu devralıyordu. Windows, çalışan bir programın çalışma klasörü olan bir klasörün adını değiştirmeye izin vermediği
  için güncelleme programı değiştiremiyor ve eski sürümü geri koyuyordu. Yeni program artık önce bu klasörden çıkıyor;
  çalışan program ve tarayıcı pencereleri de klasörü tutmuyor. Güncelleyici eski programın pencerelerinin kapanmasını
  20 saniye yerine bir dakikaya kadar bekliyor.
- Sürüm notları Türkçe ve İngilizce yayımlanıyor; "Yenilikler" arayüz dilindeki kısmı gösteriyor.

## [0.11.0] — 2026-09-28 — Özet dilleri ve bulut yapay zekâ

### Eklendi
- **Özet dillerini siz seçersiniz.** Ayarlar → Yapay zekâ → **Özet dilleri**: 31 dilden 1–4 tanesi (örneğin Portekizce
  ve Arapça). Başlık, özet, hikâye gerekçesi ve tam metin çevirisi bu dillerde yazılır; kartlardaki dil düğmesi
  aralarında gezer, çıktılar bu dillerden birinde alınır. Sağdan sola yazılan diller (Arapça, Farsça, İbranice) doğru
  yönde gösterilir. Sonradan eklenen dil eski haberler için arka planda tamamlanır. Varsayılan: arayüz dili + İngilizce.
- **Bulut yapay zekâ.** Ollama yerine kendi API anahtarınızla **Google Gemini**, **OpenAI uyumlu** bir hizmet
  (OpenAI, OpenRouter, Groq, Mistral, DeepSeek…, ya da bilgisayarınızdaki LM Studio) veya **Anthropic Claude**
  seçilebilir. Bağlantı testi hizmetin modellerini listeler; dakikadaki istek sayısı ayarlanabilir, sınır aşılınca
  program bekler. Anahtar yalnızca bu bilgisayarda, Windows'un kullanıcıya bağlı şifrelemesiyle (DPAPI) saklanır;
  ekrana, günlüklere ve yedeklere girmez. Ayarlarda açık uyarı: haber metinleri (abonelikle okunan tam metinler dahil)
  seçilen hizmete gönderilir; kullanım koşulları, ücret ve telif sorumluluğu kullanıcıdadır. Hikâye birleştirme yine
  bilgisayardaki Ollama (`bge-m3`) ile yapılır.
- **Ülkem → Konular** listeden eklenip çıkarılabiliyor; kendi konunuzu da yazabilirsiniz (en çok 20). Yapay zekâ haberin
  bu konuları anlatıp anlatmadığını söyler.

### Değişti
- İstemler artık bir Türk haber merkezini varsaymıyor; "Türkiye geçiyor mu?" sorusu yalnızca ülkesi Türkiye olan
  kullanıcılar için sorulur. Değerlendirme yöntemi aynı (yapay zekâ okur, kural karar verir).
- Arayüz metinleri sadeleşti: belge yolları ve iç notlar ("Karşılaştırma: docs/…") kaldırıldı; ülke ve dil metinleri
  her ülkeden kullanıcıya uyacak biçimde yazıldı. Zaman çizelgesindeki "ilk Türkçe kaynak", arayüz dilindeki ilk kaynak
  oldu.
- YZ metinleri dile göre tek JSON sütununda saklanıyor (şema v9); eski Türkçe/İngilizce sonuçlar göçte aynen taşındı.

### Düzeltildi
- **Dil filtresi boş kalıyordu** ("Eşleşme yok"): ilk kurulumda seçenekler yalnızca açılışta yükleniyordu; artık
  yeni haber geldikçe yenileniyor.
- Ollama adresine `http://localhost:11434` yazınca kutu yanlışlıkla "geçersiz" görünüyordu.

## [0.10.0] — 2026-09-28 — RSS'i olmayan siteler

### Eklendi
- **Haber site haritaları akış olarak okunur.** RSS vermeyen birçok haber sitesi arama motorları için başlık, saat ve
  dil içeren bir "haber site haritası" yayımlıyor. World Signal bunu RSS gibi okur; ama yalnızca sitenin robots.txt
  dosyası izin veriyorsa (her site için günde bir kez sorulur). robots.txt okunamazsa okumaz. Başlığı olmayan düz site
  haritaları kullanılmaz (sayfaları tek tek açmak gerekirdi).
- **Kaynak ekle, sitenin adresinden akış bulur.** RSS adresi yerine sitenin adresi yazılırsa sayfanın bildirdiği
  RSS/Atom bağlantıları ve robots.txt'nin izin verdiği haber site haritaları önerilir; **Dene** ile biri denenir.
- Katalogda CNN, Times of Israel, Kathimerini ve Bloomberg HT artık haberleri doğrudan yayıncının site haritasından da
  alıyor (Bing akışı özet için kalıyor; aynı haber tek kayıt olur).

### Denenip kullanılmayanlar
- AP ve Al Arabiya'nın haber site haritaları otomatik okuyucuları reddediyor (403). Reuters'ın robots.txt'si
  otomatik okumayı tümden kapatıyor. The Telegraph site haritasına robots.txt'de izin verse de otomatik okuyucuları
  başka yollarla engelliyor. Bu siteler Bing üzerinden izlenmeye devam ediyor.
- RSS-Bridge (PHP sunucusu gerektirir; Reuters köprüsü de engelleniyor) eklenmedi; site haritası yaklaşımı onun işe
  yarayan kısmını kurulum gerektirmeden karşılıyor.

## [0.9.0] — 2026-09-28 — Ülkem, ajanslar, rozetler

### Eklendi
- **Ülkem.** "Türkiye bağlantılı" artık programa sabit değil: Ayarlar → **Ülkem**'den ülke seçilir ("Sistem" =
  Windows'un bölge ayarı). Filtre, kart etiketleri, skor payı ve zaman çizelgesi seçilen ülkenin adıyla çıkar
  ("Güney Afrika bağlantılı"). Yöntem değişmedi: yapay zekâ haberi okuduktan sonra, bulduğu ülke ve konulara göre
  karar verilir. Doğrudan = ülkeniz listede ya da adı metinde; dolaylı = komşu ülke, sizin seçtiğiniz yakın ülkeler
  ya da konular. Yakın ülkeler, konular ve ek kelimeler ayarlanabilir. Türkiye için varsayılanlar eskisiyle
  birebir aynıdır. Ülke değişince kayıtlı haberler arka planda yeniden değerlendirilir.
  Ülke adları Wikidata'dan (CC0), kara komşuları GeoNames'ten (CC BY 4.0) alınır (`tools/make_countries.py`).
- **"Özel" ve "Son dakika" rozetleri.** Yayıncının "Exclusive / Özel / Эксклюзив…" diye işaretlediği haberler
  **Özel** rozeti taşır. **Son dakika**: 60 dakikada en az 3 bağımsız kaynağa yayılan hikâye ya da başlığında
  "Son dakika / Breaking" işareti olan yeni haber; rozette küçük bir sinyal animasyonu vardır (hareket azaltma
  ayarına uyar).
- Kaynaklar ekranında **Ücretli kaynaklar** ayrı bölümde.

### Değişti
- **Reuters, AP ve AFP'den çok daha fazla haber.** Bing tek aramada yalnızca en yeni ~12 haberi verdiği için
  Reuters 18, AP 16 bölüm aramasıyla izleniyor (bir ölçümde son 24 saatte Reuters'tan ~100 ayrı haber). Ajansların
  kendi siteleri otomatik okuyuculara kapalı (Reuters robots.txt, AP Cloudflare), bu yüzden doğrudan kullanılmıyor.
- Tema seçeneği "Windows'a uy" yerine **Sistem**.

### Düzeltildi
- **Bing Haberler'den gelen haberlerin saati 7 saat eskiydi.** Bing, ABD Pasifik saatini "GMT" diye yazıyor; artık
  yaz/kış saati dahil düzeltiliyor.
- 0.7.3'ten önce toplanmış eski Google News bağlantıları için tam metin artık hiç denenmiyor; "sayfada haber metni
  bulunamadı" yerine nedeni yazıyor.

### Doğrulandı
- Katalog yeniden doğrulandı: 139 kaynaktan 138'i çalışıyor; Reuters'ın 18, AP'nin 16, AFP'nin 2 akışı dahil.
- Abonelik siteleri (28 Eylül denemeleri): NYT, Washington Post, FT, Le Monde, Le Figaro, Spiegel, FAZ, El País,
  Corriere, Haaretz, Foreign Policy, SCMP, Nikkei Asia, Straits Times, The Hindu, EUobserver, The Athletic tam metin
  verdi. Economist, WSJ ve Japan Times otomatik okumayı reddediyor (403/401); bu engeller aşılmaz.

## [0.8.0] — 2026-09-28 — GitHub'dan güncelleme, e-posta

### Eklendi
- **Otomatik güncelleme.** Program yeni sürümleri GitHub'dan kendisi bulur (açılıştan kısa süre sonra ve 6 saatte bir),
  arka planda indirir, SHA-256 ile doğrular. Her ekranın üstünde "World Signal x.y.z hazır — Yeniden başlat ve
  güncelle" şeridi ve **Yenilikler** düğmesi çıkar. Güncelleme programın kendi klasörünü yeniler; bir sorun çıkarsa
  eski sürüm geri konur ve bu size söylenir. Verileriniz güncellemeden etkilenmez.
  Ayarlar → **Güncellemeler**: bu bilgisayardaki sürüm, son denetim, **Şimdi denetle**, otomatik denetim ve otomatik
  indirme anahtarları. Ağ klasöründen ya da yazılamayan bir klasörden çalışan program kendini güncelleyemez; nedeni
  ve indirme sayfası gösterilir.
- **E-postayla gönder** (bütün çıktı pencerelerinde): masaüstü Outlook varsa biçimli bir taslak açılır; yoksa
  bilgisayarın varsayılan e-posta uygulamasında düz metin taslak açılır (uzun metin kısaltılır, tamamı panoya da
  kopyalanır). Program e-postayı kendisi göndermez.
- Herkese açık, ayrıntılı README (kurulum, güncelleme, yapay zekâ ve donanım, telif ve abonelikler, gizlilik, sorun
  giderme); Android uygulaması için plan (`docs/ANDROID_PLAN.md`, karar kararlı sürümden sonra).

### Değişti
- **Dağıtım GitHub Releases'e geçti.** Her kullanıcı zip'i kendi bilgisayarına ayıklar, tek `WorldSignal.exe`'yi
  çalıştırır. 0.7.2'deki ağ klasörü başlatıcısı ve ağdan kendini kopyalama kaldırıldı.
  - `scripts\clean-build-release.bat` artık `release\<sürüm>\` altında zip + `.sha256` + sürüm notu hazırlar.
  - `scripts\publish.bat` kaynak kodu kişisel ve şirket verisi için tarar, GitHub'a gönderir ve sürümü oluşturur.
    Kişisel veri listesi yalnızca bu bilgisayarda durur. Kişisel notlar ve yayıncı metni alıntılayan belgeler depoya
    girmez.
- Herkese açık belgelerden kişisel adlar ve şirket içi adresler çıkarıldı.

### Doğrulandı
- Güncelleyici: sahte bir GitHub ile 19 test (indirme, doğrulama, bozuk dosya, sağlama değeri eksik, zip dışına
  yazma girişimi, yanlış sürüm, ağ/salt okunur klasör, klasör kullanımda, kopyalama yarıda kalırsa eski sürüme dönüş).
- E-posta: Outlook ve varsayılan uygulama yolları testte; bu bilgisayarda Outlook'un otomasyona izin verdiği
  gösterilmeden denendi (taslak oluşturulup atıldı, hiçbir şey gönderilmedi).

## [0.7.3] — 2026-09-28 — Kaynaklar, spor, hatırlanan filtreler

### Düzeltildi
- **Google News üzerinden gelen haberler açılmıyordu** ("Ziyaret ettiğiniz sayfa sizi geçersiz bir web adresine
  yönlendirmeye çalışıyor"). Neden: Google, şirket ağından gelen yönlendirme isteğine robot doğrulaması çıkarıyor.
  Google News akışları (Reuters, AP, Telegraph, Al-Monitor, Times of Israel, Al Arabiya, Kathimerini) Bing Haberler
  akışlarıyla değiştirildi; bağlantılar artık doğrudan yayıncının sayfasına gider, üstelik kısa özet de gelir.
  Önceden toplanmış Google bağlantıları açılınca başlık Bing'de aranır.

### Eklendi
- **Doğrulanmamış kaynaklar yeniden denendi**: 21 kaynaktan 20'si çalışıyor.
  - Sitenin kendi akışı bulundu: Middle East Monitor, SANA, UNIAN, EUobserver, TRT World.
  - Bing Haberler üzerinden: Corriere della Sera, CNN, AFP, Xinhua, Kyodo, EFE, Rudaw, Ahram, China Daily, Global Times,
    Euractiv, T24, DHA, Bloomberg HT, Türkiye Today.
  - İHA'nın akışı bozuk, Bing'de de güncel haberi yok: "doğrulanmadı" olarak kaldı.
  Bu kaynaklar mevcut veritabanında kendiliğinden açılır; ölü eski adresler silinir.
- **Spor grubu** (15 kaynak): Fotomaç, A Spor, NTV Spor, Sporx, BBC Sport, The Guardian Sport, Sky Sports, ESPN,
  The Athletic, Marca, AS, L'Équipe, kicker, La Gazzetta dello Sport, UEFA; AA'ya Spor akışı. Katalog: 138/139 kaynak
  doğrulandı.
- **Akış filtreleri hatırlanır** (bölge, grup, dil, kategori, kaynak, "Türkiye bağlantılı"): program açılınca
  kaldığınız gibi gelir. Sonradan silinen bir kaynak filtreden kendiliğinden çıkar.
- Ağ klasöründe yalnızca `WorldSignal.exe` ve `BENİOKU.txt` görünür; program klasörleri ve `surum.json` gizlenir.

### Değişti
- "YZ" ifadeleri sadeleşti: "YZ sırada" → "Özet için kuyruğa alındı", "YZ işleyemedi" → "Özet hazırlanamadı",
  "YZ çalışıyor" → "Özetler hazırlanıyor", "YZ önerisi" → "Neden önemli", "Yapay zekâ çevirisi" → "Otomatik çeviri";
  uyarı başlıkları da aynı dille ("Özetler hazırlanamıyor: Ollama'ya ulaşılamıyor"). Kaynak durumu "Sırada" →
  "İlk tarama bekleniyor".

### Doğrulandı
- Gerçek veritabanının kopyasında: 7 Google akışı silindi, 18 kurtarılan kaynak açıldı, 15 spor kaynağı eklendi;
  Reuters/AP/CNN/T24 Bing akışlarından 44 haber toplandı, hepsi yayıncı adresiyle kaydedildi.

## [0.7.2] — 2026-09-28 — Ağ klasöründen dağıtım

### Eklendi
- `scripts\clean-build-release.bat`: temizle → kütüphaneler → arayüz ve arka uç testleri → kaynak yedeği
  (`backups\`, son 3) → derleme (3 deneme) → `release\WorldSignal_<sürüm>_<tarih>\` hazırlığı ve denetimi.
- `scripts\publish.bat`: en son paketi ağdaki ortak klasöre yayınlar. Paket sürümü projeden farklıysa sorar; aynı paket iki kez yayınlanmaz; yarım kopya kullanıcılara görünmez;
  ağda yeni ve bir önceki sürüm kalır.
- Ağdaki **başlatıcı** (`WorldSignal.exe`): `surum.json`'daki sürümü bilgisayara bir kez kopyalar, oradan açar; ağ
  yoksa son yerel kopyayı açar. İlk kopyada "World Signal hazırlanıyor" notu gösterir.

### Doğrulandı
- Geçici bir ağ yolunda (`\\localhost\C$`) gerçek yayın: 19 sn. Boş bir kullanıcı klasörüyle ilk açılış 18 sn,
  ikincisi 2 sn; program yerel kopyadan çalıştı. Başlatıcı ve yayın aracı için 12 yeni test.

## [0.7.1] — 2026-09-28 — Abonelik sitelerine giriş

Kullanıcı geri bildirimi: "Oturum aç" dendiğinde tarayıcı boş sayfayla açılıyordu, hangi siteye girileceği görünmüyordu.

### Değişti
- Ayarlar → Tam metin → **Abonelik siteleri** listesi (eski tek "Oturum aç" düğmesinin yerine). Her sitede:
  - **Siteyi aç**: sitenin sayfası World Signal'in tarayıcı profilinde açılır (pencere açıksa yeni sekme olarak);
  - **Dene**: sitenin en yeni haberinin tam metni hemen denenir;
  - son denemenin sonucu: "Tam metin alındı", "Abonelik duvarı: giriş gerekli", "Henüz denenmedi", "Sırada…".
  Adımlar ekranda yazıyor: siteyi aç → giriş yap → pencereyi kapat → dene.
- Giriş penceresi açıkken "World Signal tarayıcı penceresi açık; bitince kapatın" uyarısı görünür (açıkken tam metin
  bekler; önceden bu durum yalnızca "profil kullanımda" diye görünüyordu).
- Giriş için site açılırken arka plandaki gizli tam metin tarayıcısı önce kapatılır ve 30 sn yeniden açılmaz; böylece
  sayfa yanlışlıkla görünmez pencereye gitmez.

### Düzeltildi
- **Abonelik vitrini tam metin sanılıyordu**: oturumsuz Financial Times sayfası ("Subscribe to unlock this article",
  419 karakter) ve Le Monde'un yarım metni ("Il vous reste 81 % … réservée aux abonnés") kabul ediliyordu. Kısa metinde
  abonelik teklifi geçiyorsa ya da metin abonelik cümlesiyle bitiyorsa artık "abonelik duvarı" sayılıyor; Fransızca,
  İspanyolca, İtalyanca, Almanca kalıplar eklendi.
- Metinden sayfa kalıntıları temizleniyor ("YouTube içeriğini göstermek için…", "Become an Independent member…",
  tek başına "Abone ol" satırları).
- Daha önce kaydedilmiş tam metinler bakım işinde bu kurallarla bir kez daha kontrol ediliyor; reddedilenin YZ özeti RSS
  özetinden yeniden yazılıyor. (Veritabanınızda: 1 kayıt reddedilecek, 7 kayıt temizlenecek, 70 kayıt aynen kalacak.)
- Veri klasörü göreli verilirse (geliştirme) tarayıcıya giden profil yolu yanlış yere çıkıyordu; yollar artık tam yol.

### Testler
- 247 arka uç testi (2'si isteğe bağlı), 118 arayüz testi; hepsi geçiyor. Gerçek denemede: siteyi açma, açık pencerenin
  algılanması, kapatınca devam, "Dene" ile Le Monde, eski FT kaydının yeniden kontrolle reddedilmesi.

## [0.7.0] — 2026-09-27 — Faz 7: Arka plan ve dağıtım

### Eklendi
- **Sistem tepsisi**: pencereyi kapatınca World Signal arka planda haber toplamaya devam eder (ilk seferde bir bildirim
  bunu söyler). Simgeye tıklayınca pencere açılır; sağ tık: son tarama bilgisi, **Şimdi tara**, **Çıkış**.
  Ayarlar → Arka plan ve bildirimler'den kapatılabilir. Ek paket kullanılmadı (Windows'un kendi arayüzü).
- **Windows bildirimleri**: önemli bir hikâye son 3 saatte çok sayıda bağımsız kaynakta yayılınca (varsayılan 5 kaynak,
  skor 60+). Her hikâye bir kez; birden çok hikâye tek bildirimde; en fazla 10 dakikada bir; sessiz saatler
  (varsayılan 23:00–07:00). Tıklayınca hikâye açılır. Ayarlarda eşikler ve **Deneme bildirimi gönder**.
- **Günlük yedek** (son 14 gün, ayarlanabilir), **Şimdi yedekle** ve **Geri yükle**: yedek önce doğrulanır (bozuk ya da
  daha yeni sürümden olan reddedilir), program kendini yeniden başlatıp yedeği yerine koyar, önceki durumun kopyasını da
  saklar. Sonuç Ayarlar → Yedekler'de görünür.
- **Kurulumsuz paket** (`tools/build.py` → `dist\WorldSignal`, 221 MB): `WorldSignal.exe`'ye çift tıklamak yeterli.
  Ağ klasöründen açılınca kendini bu bilgisayara kopyalayıp oradan çalışır; yeni sürüm bir sonraki açılışta alınır.
  Ölçümler: yerel açılış 1,6 sn; ağ yolundan ilk açılış 13,9 sn, sonrakiler 2,5 sn.
- Uygulama simgesi (arayüzdeki logonun aynısı; exe, tepsi ve bildirimlerde).
- Şema v7 (`stories.notified_at`).

### Düzeltildi
- Yeniden başlatmada yeni süreç, eski süreç veritabanını bırakmadan dosyayı değiştirmeye çalışıyordu (paketli sürümde
  görüldü: geri yükleme "dosya kullanımda" hatası verdi). Artık eski süreç bitene kadar beklenir, kilitli dosyada birkaç
  saniye yeniden denenir, yarım kalan geçici dosya silinir.
- İlk açılışta binlerce haber eşleştirilirken aynı hikâyeler dakikada bir yeniden özetleniyordu (GPU boşa gidiyordu).
  Eşleştirme sürerken otomatik hikâye özetleri bekler; sizin istedikleriniz beklemez.
- Geri yükleme sonucu mesajı yalnızca 3 gün gösterilir.

### Bilinen durumlar
- Bu bilgisayarda Python ara ara "erişim ihlali" ile çöküyor (proje dışı araçlarda da; Cinegy, nvcontainer gibi başka
  programlar da aynı günlerde çökmüş). World Signal verisi işlem bütünlüğü sayesinde bundan zarar görmez, ama program
  kapanırsa yeniden açmak gerekir. Bilgi işlem biriminin bakması önerilir.
- Bildirimin ekranda görünmesi Windows'un Odak / Rahatsız etme ayarına bağlıdır; Windows bildirimi kabul etti,
  ekranda göründüğü gözle doğrulanmadı.
- Gerçek bir ağ sunucusu yerine `\\localhost\C$` yoluyla denendi; gerçek ağda ilk kopyalama ağ hızına bağlıdır
  (221 MB; 1 Gbit'te birkaç saniye, 100 Mbit'te ~20 sn).

### Testler
- 241 arka uç testi (2 tanesi isteğe bağlı ve varsayılan olarak atlanır: internet ve ekranda bildirim; gerçek tarayıcıda uçtan uca 2 test ve
  gerçek Windows tepsisiyle 5 test dahil), 114 arayüz testi. Hepsi geçiyor.

## [0.6.0] — 2026-09-27 — Faz 6: Geçmiş

### Eklendi
- **Geçmiş** ekranı (yeni menü öğesi): takvimde haber toplanmış günler işaretli (ekran okuyucuda "45 hikâye · 120 haber").
  Bir gün seçince hikâyeler **o sabahki önem sırasıyla** (varsayılan 09:00, önceki 24 saat) ya da **günün tamamı**
  (o gün yayımlananlar, gün sonundaki sırayla) gösterilir. Skorlar ve etiketler o ana göre hesaplanır ("14 saat önce",
  "19 kaynak"). J/K, Enter ve T kısayolları burada da çalışır.
- Hikâye oluşturma başlamadan önce toplanmış günler için açıklama ve **Haberleri göster** (günün tek tek haberleri).
- **Tüm günlerde arama**: hikâyeler ve tek tek haberler; Türkçe karakter ve büyük/küçük harf ayırt edilmez.
- **Dönüm noktaları**: hikâye ayrıntısındaki zaman çizelgesinin altında ilk haber, 3/5/10/20/40 bağımsız kaynağa ulaşma,
  Türkiye bağlantısının ortaya çıkışı, ilk Türkçe kaynak ve son haber (zaman ve kaynak adıyla).
- **Saklama politikası** (Ayarlar → Geçmiş ve saklama): tam metinler 7 / 30 / 90 gün ya da hiç silinmeden saklanır
  (varsayılan 30). Hikâye eşleştirme verisi yalnızca son 7 gün tutulur (haber başına ~4 KB; tutulsaydı yılda birkaç GB
  ederdi). Başlık, özet, YZ metinleri, hikâyeler ve notlar hiç silinmez. Temizlik açılıştan 1 dk sonra ve 6 saatte bir;
  veritabanı boyutu ve son temizliğin sonucu ayarlarda görünür.
- Sabah görünümünün saati ayarlanabilir (06:00–12:00).
- Ayarlar → Klavye kısayolları listesine **T** (toplantıya ekle/çıkar) eklendi.
- Takvim, not defteri ve geçmiş için ortak bileşen oldu.
- Ölçüm (gerçek veritabanı, 7.980 haber, 2.182 hikâye): bir günün sıralaması 0,05–0,11 sn, ay takvimi 0,01 sn.
- **Testler**: 211 arka uç testi (isteğe bağlı 1 internet testi hariç; gerçek tarayıcıda uçtan uca 2 test dahil — geçmişte
  arama ve hikâye açma eklendi), 103 arayüz testi. Hepsi geçiyor.

### Veri
- Şema değişmedi (v6). Geçmiş sıralaması saklanmıyor, istek anında yeniden hesaplanıyor (bkz. ARCHITECTURE.md).

## [0.5.0] — 2026-09-27 — Faz 5: Tam metin ve İngilizce

### Eklendi
- **Türkçe + İngilizce**: yapay zekâ artık her haber ve hikâye için başlık, özet ve "neden toplantıda" cümlesini Türkçe
  ve İngilizce birlikte yazar (proje sahibinin kararı, 2026-09-27). Ekranda arayüz dili gösterilir; kartlarda ve hikâye
  ayrıntısında **EN / TR** düğmesiyle öbür dile geçilir. Çıktı penceresinde **Türkçe / English** seçimi var; şablon
  başlıkları ve tarih de seçilen dilde yazılır. Arama İngilizce yapay zekâ metninde de çalışır.
- İngilizcesi olmayan eski yapay zekâ sonuçları, yeni işler bittikten sonra arka planda tamamlanır; bu sırada Türkçe
  metin görünmeye devam eder, deneme başarısız olursa Türkçe sonuç korunur.
- Uydurma denetimi İngilizce metne de uygulanır.
- Ölçüm: gemma4-26b-a4b ile iki dilli çıktı haber başına ~4 sn (önce ~3 sn); 7 dilde (en, tr, ar, ru, de, fr, es)
  gerçek haberlerle kontrol edildi.
- Veritabanı şeması v5 (İngilizce sütunlar).
- **Tam metin**: hikâye ayrıntısında her haberin altında durumu ve düğmesi: **Tam metni getir**, "sırada", "alınamadı:
  neden" / "site engelledi: neden" (+ **Yeniden dene**), **Tam metni oku (N karakter)**.
- **Okuma penceresi**: orijinal metin; **Türkçe / English** sekmeleri ve **Çevir** düğmesi. Çeviri bu bilgisayardaki
  yapay zekâyla, paragraf paragraf yapılır, bitince pencerede kendiliğinden görünür ve "yapay zekâ çevirisi" diye
  işaretlenir. Haberin kendi diline çeviri yapılmaz.
- **Kaynak başına yöntem** (Kaynaklar → kaynak ayarları → Tam metin): Kapalı / Doğrudan indir (ücretsiz siteler) /
  Tarayıcı ile (abonelik siteleri). Ücretli kaynaklar "Kapalı" başlar.
- **Tarayıcı ile tam metin** (proje sahibinin açık izniyle gizlenmiş otomasyon): kendi Brave'iniz (yoksa Chrome/Edge),
  World Signal'e özel profil; Ayarlar → **Oturum aç** ile abonelik sitelerine bir kez girilir. İsteğe bağlı "kendi
  profilim" modu (tarayıcınız kapalıyken). Pencere ekran dışında açılır; boşta kalınca kapanır.
- **İnsan temposu**: tek sekme, site başına saatte sınır (varsayılan 4), sayfalar arası rastgele bekleme (tarayıcı
  25–60 sn, doğrudan indirme 6–15 sn).
- **Engeller**: robot doğrulaması asla çözülmez; haber "site engelledi" olur ve site 12 saat bekletilir (403/429'da 6 saat,
  abonelik duvarında 3 saat). Bekletilen siteler Ayarlar'da görünür, **Devam ettir** ile açılır.
- **Otomatik tam metin**: skoru 60 ve üzeri hikâyelerin en fazla 2 haberi ile not defterindeki/toplantıdaki hikâyeler;
  sizin istekleriniz her zaman önce. Tam metin gelince haberin YZ özeti tam metinle yeniden yazılır.
- **Ayarlar → Tam metin** bölümü: aç/kapat, tarayıcı, profil, oturum açma, ücretli kaynakların hepsinde tarayıcıyı açma,
  site başına sınır, otomatik seçim, pencereyi gösterme, kuyruk durumu.
- Veritabanı şeması v6 (`article_fulltext`, `sources.fulltext_mode`, `sources.fulltext_paused_until`).
- Yeni bağımlılıklar: **trafilatura** (sayfadan haber metni), **patchright** (tarayıcı otomasyonu).
- **Gerçek denemeler**: doğrudan indirme Guardian, BBC Türkçe, Times of India, Cumhuriyet, Sabah, APA ve Middle East
  Eye'da çalıştı; Brave ile tarayıcı yolu Washington Post'ta çalıştı (15 sn, ekran dışında). Guardian haberinin
  6.786 karakterlik metni gemma4-26b-a4b ile 30 saniyede Türkçeye çevrildi.
- **Testler**: 199 arka uç testi (isteğe bağlı 1 internet testi hariç; gerçek tarayıcıda uçtan uca 2 test dahil),
  93 arayüz testi. Hepsi geçiyor.

### Düzeltildi
- Oturum açmamış profilde Washington Post, haberin yalnızca ücretsiz ilk paragraflarını gösterdi ve bu kesik metin tam
  metin sanıldı. Sayfa kendi kelime sayısını bildiriyorsa (schema.org `wordCount`) ve alınan metin bunun yarısından
  azsa sonuç artık "abonelik duvarı" sayılıyor.
- Bazı sitelerde (Sabah) çıkarılan metnin satır aralarındaki boşluk yığınları temizleniyor.
- Seçim düğmelerindeki uzun yazılar artık iki satıra kırılmıyor.

### Bilinen sınırlamalar / elle doğrulanacaklar
- Abonelik sitelerinde **oturum açılmış** profil ile tam metin henüz denenmedi: kullanıcının Ayarlar → **Oturum aç** ile bir
  kez giriş yapması gerekiyor. NYT, WSJ ve Economist, 27 Eylül'deki ilk denemelerde otomasyonu fark ettiği için
  28 Eylül'den önce bu sitelere istek gönderilmedi.
- Kendi profilim modu yalnızca tarayıcınız tamamen kapalıyken çalışır (Brave arka planda çalışmaya devam ediyorsa da
  profil kilitli sayılır).
- Faz 4'ten: **Yazdır / PDF** ve Word'e biçimli yapıştırma gerçek program penceresinde elle denenecek.

## [0.4.0] — 2026-09-27 — Faz 4: Not defteri ve çıktılar

### Eklendi
- **Toplantı listesi** (yeni ekran): hikâyeyi kartındaki **Toplantıya ekle** düğmesiyle ya da seçip **T** tuşuyla bugünün
  listesine ekleyin (tekrar T ile çıkar). Sürükle-bırak veya ok düğmeleriyle sıralama, her öneriye kısa gerekçe. Liste
  hikâyeleri canlı izler: YZ özeti gelince kendiliğinden güncellenir.
- **Hikâye notları**: hikâye ayrıntısında **Notlarım** alanı.
- **Not Defteri** (yeni ekran): takvim; her günde serbest "günün notu", o günün toplantı listesi ve o gün başlanan hikâye
  notları. Geçmiş günlerin toplantı listesi o sabahki haliyle kalır.
- **Kayıpsız otomatik kayıt**: yazmayı bırakınca, alandan çıkınca ve pencere kapanırken kaydedilir; kayıt başarısız olursa
  metin ekranda kalır, "Kaydedilemedi, yeniden deneniyor" yazar ve kendiliğinden yeniden dener. Program sunucuya ulaşamadan
  kapanırsa yazdığınız bir sonraki açılışta geri gelir.
- **Dört çıktı şablonu**: toplantı öneri listesi, haber detayı, kategori başlıklı sabah bülteni (Akış → **Sabah bülteni**;
  12/24/48 saat, 10/20/30 hikâye), not defterinden seçtikleriniz. Her birinde önizleme, **Biçimli kopyala** (Word, Outlook),
  **Düz metin kopyala** (WhatsApp) ve **Yazdır / PDF**.
- **Telif koruması**: çıktılarda yalnızca Türkçe YZ özetleri, başlıklar, kaynak adları ve bağlantılar bulunur; yayıncıların
  kendi metinleri hiçbir zaman çıktıya girmez.
- Hikâyeler birleştirilirse notlar ve toplantı öğeleri birleşen hikâyeye taşınır; bir hikâye ortadan kalkarsa notunuz ve
  kayıtlı başlığı defterde kalır.
- Veritabanı şeması v4 (`story_notes`, `meeting_items`, `day_notes`); göç öncesi otomatik yedek.
- **Testler**: 166 arka uç testi (isteğe bağlı 1 internet testi hariç; gerçek tarayıcıda uçtan uca 2 test dahil; toplantıya ekleme, gerekçe, çıktı önizlemesi,
  günün notunun yeniden yüklemede korunması), 74 arayüz testi. Hepsi geçiyor.

### Düzeltildi
- İç içe açılan pencerelerde (hikâye ayrıntısı → çıktı) Esc artık yalnızca en üstteki pencereyi kapatıyor.

### Bilinen sınırlamalar / elle doğrulanacaklar
- **Yazdır / PDF** ve **Word/Outlook'a biçimli yapıştırma** gerçek program penceresinde (WebView2) henüz denenmedi;
  tarayıcıda önizleme, kopyalama komutu ve yedek kopyalama yolu doğrulandı.
- Hikâye ayrıntısını kapatır kapatmaz Not Defteri yenilenirse, son saniyede yazılan not bir sonraki yenilemede görünür.

## [0.3.0] — 2026-09-27 — Faz 3: Hikâyeler ve önem skoru

### Eklendi
- **Hikâyeler**: aynı olayı anlatan haberler, dilden bağımsız olarak tek kartta toplanır ("47 kaynak · 68 haber").
  Örnek: İngiltere'deki hava üssü olayı İngilizce, Rusça, Fransızca, Türkçe ve Urduca kaynaklardan tek hikâyede.
  Olay günlerce sürerse aynı hikâye büyümeye devam eder (hikâye zinciri).
- **Gömme modeli karşılaştırması**: bge-m3, qwen3-embedding:0.6b ve embeddinggemma, veritabanınızdaki gerçek haberlerden
  elle hazırlanan 95 haberlik cevap anahtarıyla (12 olay, 7 dil) karşılaştırıldı (`docs/GOMME_KARSILASTIRMA.md`).
  Seçilen: **bge-m3, yalnızca başlık**. Model işlemcide çalışır; ekran kartını YZ modeline bırakır.
- **Zincirlenme koruması**: gerçek akışta (6.919 haber) yalnızca "en yakın habere benziyor mu" kuralının alakasız
  olayları tek hikâyede topladığı ölçüldü (494 haberlik karışık hikâye). Yeni kural, hikâyenin geneline de benzemeyi şart
  koşar; en büyük hikâye 146 habere indi, doğruluk arttı (`docs/BIRLESTIRME_KARSILASTIRMA.md`).
- **Açıklanabilir önem skoru** (0–100): bağımsız kaynak sayısı (aynı medya grubu tek sayılır), tazelik ve yayılma hızı,
  Türkiye bağlantısı, ilgi profiliniz. Her kartta nedeni gösteren etiketler ("12 kaynak", "3 saatte 7 kaynak",
  "Türkiye bağlantısı", "İlgi alanınız: enerji"); ayrıntıda bileşen × ağırlık dökümü.
- **Hikâye özeti (YZ)**: çok kaynaklı hikâyeler için Türkçe başlık, 3–5 cümle özet, kategori ve "Neden toplantıda" cümlesi;
  önemli hikâyeler önce. Aynı uydurma denetimi uygulanır. "Özeti yeniden yaz" düğmesi.
- **Hikâye ayrıntısı**: özet, skor dökümü, günlere göre gelişim (zaman çizelgesi), tüm haberler ve orijinal bağlantıları.
- **Elle düzeltme**: "Bu hikâyeden ayır" ve "Başka hikâyeyle birleştir". Program sizin kararınızı bir daha bozmaz.
- **Akış**: "Hikâyeler / Haberler" görünüm seçimi (hatırlanır), önem veya yenilik sıralaması, "Yalnızca çok kaynaklı"
  filtresi; J/K + Enter hikâyeyi açar. Arka planda sıralama değişince liste altınızda kaymaz, "yeni sırayı göster" önerilir.
- **Ayarlar → Hikâyeler ve önem skoru**: birleştirme modeli (yalnızca gömme modelleri listelenir), birleştirme hassasiyeti,
  skor ağırlıkları, ilgi profili (anahtar kelimeler, kategoriler, bölgeler). Model değişince o modelin ölçülmüş eşiği
  kendiliğinden gelir.
- Veritabanı şeması v3 (`article_embeddings`, `stories`, `story_articles`); göç öncesi otomatik yedek.
- **Testler**: 158 arka uç testi (gerçek tarayıcıda uçtan uca 2 test dahil, pytest) ve 54 arayüz testi (Vitest), hepsi geçiyor.

### Düzeltildi
- YZ çalışanı, işlemcide çalışan bge-m3'ü "ekran kartı başka modelle meşgul" sanıp duruyordu.
- Arka plan çalışanları, çalışırken gelen "uyan" sinyalini kaybedebiliyordu (yeni haberler 15–30 sn gecikebiliyordu).
  Artık toplayıcı yeni haber bulunca hikâye ve YZ çalışanları hemen uyanıyor.
- Model listesi Ollama'dan gelene kadar seçili model yanlışlıkla "yüklü değil" görünüyordu.
- Uçtan uca testin sahte haber tarihleri sabitti; test ertesi gün kendiliğinden bozulacaktı.

### Bilinen sınırlamalar
- Birleştirme ayarı değişince eski hikâyeler yeniden kurulmaz; yeni gelen haberlere uygulanır.
- Uzun süren genel konular (ör. Rusya-Ukrayna saldırıları) tek, büyük bir hikâyede toplanabilir; gerekirse "ayır" ile bölün.
- Hikâyenin Türkiye bağlantısı, haberlerin YZ işlemesinden gelir; YZ henüz işlemediyse "0" görünür.
- Windows bildirimi (hızla yayılan hikâye) Faz 7'de (sistem tepsisi ile birlikte) gelecek.

## [0.2.0] — 2026-09-27 — Faz 2: Yapay zekâ

### Eklendi
- **Yerel yapay zekâ (Ollama)**: her haber için Türkçe başlık, 1–4 cümlelik Türkçe özet, kategori ve Türkiye bağlantısı.
  Hiçbir veri bilgisayardan çıkmaz.
- **Model karşılaştırması**: 6 model sizin veritabanınızdaki aynı 11 gerçek haberle (7 dil) karşılaştırıldı
  (`docs/MODEL_KARSILASTIRMA.md`). Seçilen model: **gemma4-26b-a4b** (haber başına ~3 sn).
- **Uydurma koruması**: model yalnızca kaynak metne dayanır; çıktıdaki her sayı kaynakta da olmalıdır, olmayan sayı kartta
  uyarı olarak gösterilir (karşılaştırmada bir modelin uydurduğu tarihleri yakaladı). Orijinal
  başlık hep altında, orijinal metin tek tık uzakta.
- **Açıklanabilir Türkiye bağlantısı**: "doğrudan / dolaylı" kararını kod verir; etiketin üzerine gelince neden
  ("Komşu ülke: Yunanistan", "Konu: NATO") görünür.
- **İş kuyruğu**: son 24 saatin haberleri otomatik işlenir (yeniler önce); "Türkçeleştir" ile istenen haber sıranın başına
  geçer; sonuçlar önbellekte, aynı iş tekrar yapılmaz; başarısızlar 3 denemeden sonra durur, "Yeniden dene" ile döner.
- **Kibar ekran kartı kullanımı**: Ollama'da başka bir model yüklüyse (sizin başka işiniz) World Signal onu bellekten atmaz,
  bekler. Ayarlardan kapatılabilir.
- **Akış**: Kategori ve "Türkiye bağlantılı" filtreleri; arama Türkçe YZ başlık/özetlerinde de çalışır; YZ tamamladıkça kartlar
  kendiliğinden güncellenir.
- **Ayarlar → Yapay zekâ**: aç/kapat, Ollama adresi + bağlantı testi, yüklü modellerden seçim, otomatik işleme süresi,
  kuyruk durumu, yeniden dene.
- **Tasarlanmış durumlar**: Ollama kapalı, model yüklü değil, model seçilmedi, ekran kartı meşgul (zaman aşımı), ekran kartı
  başka modelle meşgul. Hiçbirinde program çökmez; haberler orijinal dilde gösterilmeye devam eder.
- Veritabanı şeması v2 (`article_ai`, `article_ai_fts`); göç öncesi otomatik yedek alınır (gerçek veritabanınızın bir
  kopyasında denendi: 7.628 haberin tamamı korundu).
- **Testler**: 131 arka uç testi ve gerçek tarayıcıda 2 uçtan uca test (pytest), 40 arayüz testi (Vitest). Ollama kapalı,
  model yok, zaman aşımı, ekran kartı meşgul, bozuk model çıktısı ve uydurma sayı senaryoları sahte Ollama ile test edildi.

### Düzeltildi
- Kenar çubuğundaki "son tarama" zamanı program yeniden başlayınca kayboluyordu.
- Ayarlar art arda hızlı değiştirilince önceki değişiklik ekranda geri alınabiliyordu.

### Bilinen sınırlamalar
- Uydurma denetimi yalnızca sayılara bakar; isim uydurmasını mekanik olarak yakalayamaz (istem bunu yasaklar, orijinal
  her zaman görünür). Kaynakta yazıyla geçen sayı ("altı") çıktıda rakamla yazılırsa yanlış alarm verebilir.
- Özetler yalnızca RSS özetine dayandığı için kısa olabilir; tam metin Faz 5'te gelecek.
- gemma4-26b-a4b ekran kartı belleğinin neredeyse tamamını (14,7 GB) kullanır. Faz 3'teki gömme (embedding) modeli ile
  birlikte nasıl çalışacağı Faz 3'te ölçülecek.

## [0.1.0] — 2026-09-27 — Faz 1: Temel

### Eklendi
- **Proje iskeleti**: Python 3.12 arka uç (FastAPI, yalnızca 127.0.0.1) + React/TypeScript arayüz, pywebview
  (WebView2) masaüstü penceresi. Tek kopya kilidi: program ikinci kez açılırsa var olan pencere öne gelir.
- **Veritabanı**: SQLite (WAL), sürümlü şema göçleri, göç öncesi otomatik yedek, işlem bütünlüğü.
  Veriler `%LOCALAPPDATA%\WorldSignal\` altında; ağ klasöründe asla tutulmaz.
- **Türkçe duyarlı arama**: `ırak`, `Irak`, `IRAK`, `irak` ve `İstanbul`/`ISTANBUL` birbirini bulur
  (SQLite'ın hazır aramasının bu konudaki hatası test edilerek düzeltildi).
- **RSS toplama**: arka planda sürekli, akış başına ayarlanabilir aralık, ETag/Last-Modified ile gereksiz indirme
  yok, siteye aynı anda tek istek, hatalı akışlarda artan bekleme, çevrimdışı algılama.
- **Kaynak kataloğu**: 124 aday kaynak gerçekten test edildi. 103'ü (120 akış) doğrulandı. Çalışmayan 21 kaynak
  "doğrulanmadı" olarak kapalı ve ayrı listede. Reuters, AP ve doğrudan erişimi engelleyen 5 sitenin başlıkları
  Google News'in herkese açık RSS'i üzerinden alınıyor. Ayrıntılı rapor: `docs/KAYNAK_DOGRULAMA.md`.
- **Akış ekranı**: zaman aralığı (6 sa / 24 sa / 3 gün / 7 gün), arama, bölge/grup/dil/kaynak filtreleri, günlere
  göre gruplama, "yeni haber geldi" bildirimi, sonsuz kaydırma, J/K/Enter/`/` kısayolları, sağdan sola diller
  (Arapça vb.) için doğru yön, ücretli kaynak ve dil etiketleri.
- **Kaynaklar ekranı**: gruplara göre liste, durum (çalışıyor / hatalı / sırada / kapalı), hata nedeni Türkçe,
  son başarılı çekim, 24 saatlik haber sayısı, aç/kapa, düzenleme (ad, grup, medya grubu, bölge, dil,
  güvenilirlik ağırlığı, ücretli), akış ekleme/silme/aralık, test ederek yeni kaynak ekleme, silme.
- **Ayarlar ekranı**: tema (Windows'a uy / açık / koyu), arayüz dili, veri klasörü, kısayollar, sürüm.
- **Çok dilli arayüz**: Türkçe (varsayılan) ve İngilizce. Eksik çeviri derleme hatası verir.
- **Tasarlanmış durumlar**: yükleniyor, boş (ilk çalıştırma / filtre / arama), hata + yeniden dene, çevrimdışı,
  arka plana ulaşılamıyor, kaynak engelli.
- **Testler**: 94 arka uç testi (pytest), 25 arayüz testi (Vitest), gerçek tarayıcıda (Edge) 2 uçtan uca test ve isteğe bağlı 1 gerçek internet testi.
- `WorldSignal.cmd`: çift tıkla başlatıcı (ilk çalıştırmada ortamı kendisi hazırlar).
- **Saat dilimi düzeltmesi**: yerel saati UTC diye bildiren akışlar (CNN Türk, Jerusalem Post) otomatik algılanıp
  doğru sıraya konuyor.

### Bilinen sınırlamalar
- **Nikkei Asia** akışı haberlere tarih koymuyor. İlk kurulumdaki ilk taramada bu kaynağın mevcut 50 haberi
  "az önce" olarak görünür; sonraki haberleri bulunduğu anın saatiyle (15 dk hassasiyetle) gelir. Kalıcı çözüm
  Faz 5'te: tam metin alınırken haber sayfasındaki gerçek yayın tarihi okunacak.
- Pencere kapatılınca program tamamen kapanır; sistem tepsisinde arka planda çalışma Faz 7'de gelecek.
- Program şimdilik bu bilgisayardaki geliştirme ortamıyla (`WorldSignal.cmd`) çalışır; kurulumsuz paket Faz 7'de.
- Veri klasörü şimdilik Ayarlar'dan değiştirilemez, yalnızca görüntülenip açılabilir (Faz 7: dağıtımla birlikte).
