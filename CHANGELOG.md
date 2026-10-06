# Değişiklik günlüğü

Sürüm numaraları [Anlamsal Sürümleme](https://semver.org/lang/tr/) izler. 1.0'a kadar her faz bir ara sürümdür.
İngilizcesi (0.10.0'dan itibaren): [CHANGELOG.en.md](CHANGELOG.en.md).

## [0.17.2] — 2026-10-06 — Bildirime tıklayınca program donuyordu: düzeltildi

### Düzeltildi
- **Bildirime ya da tepsi simgesine tıklayınca bütün program donabiliyordu** (pencere "yanıt vermiyor", sunucu da yanıtsız, günlük duruyor). Neden, donmuş süreç incelenerek bulundu: tepsi iş parçacığı pencereyi öne getirmek için `window.on_top` ayarını yapıyordu; bu çağrı pywebview'ın penceresine başka bir iş parçacığından, Python'un yorumlayıcı kilidi (GIL) elindeyken dokunuyor, pencerenin kendi iş parçacığı da aynı anda kilidi bekliyorsa ikisi birbirini bekleyip program kilitleniyordu (çökme değil, kilitlenme; bu yüzden çökme koruması devreye girmiyordu). Pencere artık doğrudan Windows çağrılarıyla (ctypes, kilidi bırakır) öne getiriliyor; bildirime tıklayınca açılacak hikâye pencereye sayfanın kendi durum sorgusuyla (en geç 5 saniye, pencere odak alınca hemen) iletiliyor.
- Hâlâ pywebview üzerinden başka iş parçacığından yapılan tek çağrı Çıkış/yeniden başlatma sırasındaki pencere kapatması; aynı türden riski var ama yalnızca kapanırken. Çökme koruması **kilitlenmeleri** yakalamaz (program çalışıyor görünür); bunun için ayrı bir "yanıt vermiyorsa yeniden başlat" denetimi ileride eklenebilir.

## [0.17.1] — 2026-10-06 — Çökme koruması; toplantı listesinde özet ve not tam görünür

### Eklendi
- **Çökme koruması** (Ayarlar → Sistem → "Çökerse kendiliğinden yeniden aç"; varsayılan **kapalı**). Açıkken küçük bir izleyici işlem (aynı program, `--watch-pid`) World Signal'i bekler; program çalışırken `running.flag` dosyası bulunur, düzgün kapanınca (Çıkış, güncelleme, yeniden başlatma) silinir. Dosya kalmışsa program çökmüştür ve izleyici 5 saniye sonra programı yeniden açar. 10 dakikada 3'ten fazla çökerse denemeyi bırakır (açılamayan programı sonsuza dek açmaya çalışmaz); Görev Yöneticisi'nden elle kapatmak da çökme sayılır. Ayar kapatılırsa izleyici yeniden açmaz. Günlük: `logs\watchdog.log`. Sahada denenen: bu bilgisayarda program gece boyunca `c0000005` (erişim ihlali) ile çöktü; Windows olay günlüğünde 03:40, 07:08, 09:15 kayıtları var. Çökmenin kendisinin nedeni bulunamadı (kod hatası mı, ortam mı belli değil); bu koruma nedeni gidermez, yalnızca programı ayakta tutar. Birim testleri sahte işlemlerle yazıldı; gerçek WorldSignal.exe'nin çökmesi sonrası yeniden açılması otomatik testte denenmedi.

### Düzeltildi
- **Toplantı listesindeki özet yarım görünmüyor.** Özete basınca tamamı açılır, tekrar basınca kısalır (akıştaki kartlarla aynı).
- **Not kutusu uzun metni gösteriyor.** Tek satırlık kutu, yazdıkça büyüyen çok satırlı alana döndü; yapıştırılan uzun not tam görünür. Not sınırı 300 karakterden 3000'e çıktı. Enter yeni satır açar; kutudan çıkmak için Ctrl+Enter ya da kutunun dışına tıklamak yeterli (kayıt otomatik).

## [0.17.0] — 2026-10-05 — Son dakika: anında bildirim ve ayrı sayfa

### Eklendi
- **Son dakika bildirimi.** Bir yayıncı haberi "Son dakika", "BREAKING", "URGENT", "Flaş", "عاجل" gibi etiketlediyse ve **son bir saatte en az 3 bağımsız kaynak** (ayarlanabilir: 2–5) aynı olayı yazdıysa Windows bildirimi hemen gelir; diğer bildirimlerin arasındaki 10 dakikayı beklemez (yalnızca iki son dakika bildirimi arasında 2 dakika). Başlıktaki etiket çıkarılır; tıklayınca hikâye açılır. Aynı hikâye ikinci kez "hızla yayılıyor" diye bildirilmez. Sessiz saatler ve bildirimleri kapatma ayarı geçerlidir. Ayar: Ayarlar → Sistem → Windows bildirimleri → *Son dakika haberlerini hemen bildir*.
- **Son dakika sayfası** (kenar çubuğu): etiketli hikâyeler en yeniden eskiye, 3 / 12 / 24 saatlik pencerelerle. Son 3 saatte etiketli hikâye varsa kenar çubuğunda kırmızı bir sayı görünür.
- Ölçüm (gerçek veri, 72 saat): etiket + en az 3 kaynak koşulu yaklaşık günde 4 bildirim, 2 kaynak koşulu günde 7; yalnızca kaynak sayısına bakmak (etiketsiz) günde onlarca olacağı için kullanılmadı. (Veritabanı göçü 0013.)
- **Özel haber algısı genişledi.** Yayıncı etiketi artık başlığın başındaki "Scoop:" (Axios) ve özetin başındaki "Exclusive:" (The Guardian, The Independent: başlıkta etiket yok) ile de tanınır. Gerçek veride son 30 günde 71 → 90 özel haber. Çoğu kaynak (NYT, WSJ, FT, Bloomberg, Al Jazeera) RSS'inde özel haber etiketi hiç vermiyor; bunlar bu yöntemle görünmez.
- **Özel haber etiketi artık makalenin sayfasından da okunur.** Eklentinin (ve düz indirmenin) getirdiği sayfada yayıncının "Exclusive" / "Scoop" etiketi aranır: anahtar kelime ve etiket meta'ları, yapılandırılmış veri (`keywords`, `articleSection`), makalenin üstündeki küçük etiket öğesi (menü, altbilgi ve kenar çubuğu sayılmaz), sayfa başlığı ve sayfa açıklaması (The Guardian, The Independent). Paywall yüzünden yalnızca ilk paragraf okunabilse bile etiket sayfada olduğu için yakalanır. Makale metninde "exclusive" kelimesi **aranmaz**. Özetlerde "exclusive interview", "exclusively reported" gibi ifadeler de işaretlenir. Gerçek Guardian ve Fox News sayfalarında doğrulandı (6 etiketsiz sayfada yanlış alarm yok); **NYT, FT, WSJ, Bloomberg sayfalarında henüz denenmedi**: etiketleri sayfalarında farklı yerde olabilir. Yalnızca bundan sonra okunan sayfalar işaretlenir (eski sayfaların HTML'i saklanmıyor). (Göç 0014: `articles.page_exclusive`.)
- **Tanılama anahtarı** (Ayarlar → Tam metin → "Tanılama: okunan sayfaları sakla"). Açıkken okunan son 40 sayfanın HTML'i yalnızca bu bilgisayarda `debug-pages` klasörüne yazılır; bir yayıncının etiketi sayfada nerede duruyor, neden bulamadık diye bakmak içindir. Yedeklere ve paketlere girmez.
- **Reuters'ın özel haberleri artık kendi etiketiyle geliyor.** Reuters sitesini otomatik okuyuculara kapattığı için etiketi oradan okumuyoruz; ama Bing Haberler'in herkese açık RSS araması, Reuters'ın kendi "Exclusive-" başlığını taşıyan kopyaları (MSN, Yahoo, U.S. News vb.) döndürüyor. Yeni "Reuters (Exclusive)" kaynağı sekiz arama yapar ve yalnızca başlığı "Exclusive-…", "Exclusive - …" ya da "Reuters exclusive: …" olanları saklar (yeni feed özelliği: `keep_only`, göç 0015). Tahmin yok: başlıktaki etiket Reuters'ındır. Denemede bir seferde 39 başlık geldi; aynı haber Reuters kaynağında etiketsiz de bulunur, ikisi aynı hikâyede birleşir ve tek bağımsız kaynak sayılır. Tam metin istenince yayıncının kopyasından alınır (The Print, Yahoo, BNN Bloomberg, The Star okunur; MSN okunamaz, orada Kaynağa git ile tarayıcıda açılır). "CNN Exclusive: …" gibi kaynak adı önde olan etiketler de tanınır.
- **Her kaynak için "Exclusive" araması.** Ölçtük: 140 kaynağın her biri için Bing Haberler'de `"Exclusive" site:<alan adı>` aranınca **13 kaynak** kendi başlığında yayıncının etiketini taşıyan haberler döndürdü; bu 13 kaynağa (Axios, AP, Fox News, CNA, Al-Monitor, Kyiv Independent, Hindustan Times, Korea Herald, Middle East Eye, IRNA, Times of India, Global Times) gerçek kaynaklarının altında çalışan bir "Exclusive" araması eklendi (`keep_only: exclusive`: yalnızca yayıncının kendi etiketini taşıyanlar saklanır; kaynak adı, sahip ve bağlantı gerçek kaynaktan). Denemede bir seferde 34 yeni etiketli haber geldi (Axios 10, CNA 5, Fox 4, AP 2…). **Yapılamayanlar:** NYT, WSJ, FT, Bloomberg, Washington Post, Guardian, BBC gibi yayıncılar etiketi başlığa koymadığı için aramayla görünmez (Reuters'ın "Exclusive-" başlığı ajans üslubu olduğu için kopyalarda yaşıyor); onlar için tek yol sayfa okumasıdır (yukarıdaki sayfa etiketi, eklentiyle okunan haberlerde).

## [0.16.1] — 2026-10-05 — Özeti açmak için basın; eklenti yeniden yükleme istemez

### Eklendi
- **Haber ve hikâye kartlarında özetin üstüne basınca tamamı açılır**, tekrar basınca kısalır (fare ya da Enter/Boşluk).
  Altında Tam metni oku, Kaynağa git ve Orijinal metni göster bağlantıları durur.

### Değişti
- **Eklenti sürümü artık program sürümünü izlemez.** Program, beklediği eklenti sürümünü kendi bilir; yalnızca eklentinin
  kendisi değişince bu sayı yükselir. Bu sürümde eklenti değişmedi: **Yeniden yükle'ye basmanız gerekmez.**

## [0.16.0] — 2026-10-05 — Haberi toplantıya ekleme; eklenti için ayrı tarayıcı profili; otomasyon tarayıcısı kalktı

### Eklendi
- **Tek bir haber de toplantı listesine eklenebilir** (yalnızca hikâye değil). Akışta "Haberler" görünümündeki her kartta
  **Toplantıya ekle** düğmesi ve **T** tuşu var; listede haber, kaynağının bağlantısıyla görünür ("Hikâye artık yok"
  uyarısı yalnızca gerçekten kaybolmuş hikâyeler içindir). Yapay zekâ metni sonradan gelirse bugünün listesi onu izler.
  Çıktılarda hikâyeyle aynı biçim; telif kuralı aynı (yalnızca yapay zekâ metni ve bağlantı). Listeye eklenen haberin tam
  metni de kuyruğa girer. (Veritabanı göçü 0012: `meeting_items.article_id`.)
- **Eklenti için ayrı tarayıcı profili.** Ayarlar → Tam metin → "Eklenti hangi tarayıcı profilinde çalışsın?":
  *Ayrı profil (önerilen)* ya da *Kendi tarayıcım*. Ayrı profilde eklenti ve abonelik girişleri World Signal'e özel bir
  profilde durur; program onu pencere açmadan başlatır, günlük tarayıcınıza, sekmelerinize ve oturumunuza dokunulmaz.
  **Ayrı profili aç** düğmesi o profili eklentiler sayfasında açar (eklentiyi bir kez yüklersiniz). Varsayılan hâlâ *Kendi
  tarayıcım*; geçmek için eklentiyi o profile bir kez yüklemek gerekir.

### Kaldırıldı
- **Programın otomasyon tarayıcısı (patchright).** Hiç kullanılmıyordu (eklentiden beri tek bir tam metin onunla alınmadı),
  abonelik siteleri onu reddediyor ve tarayıcıyı çökertiyordu. Gitti: bu okuyucu, `fulltext.reader`, `fulltext.profile`,
  `fulltext.visible` ayarları, "Tarayıcı penceresini göster" ve profil satırları, patchright bağımlılığı. Paket yaklaşık 100 MB
  küçülür. `browser` yöntemli kaynakları artık yalnızca eklenti okur.

### Ölçüldü
- Aynı olayın isim değişik haberleri ("Erdoğan X'i kabul etti") gerçek veride bge-m3 ile 0,66–0,73 benzer; 0,8 eşiğinin
  üstündekiler aynı ziyaretteki iki kişi gibi gerçekten aynı olay. İsim farkına bakan ek bir birleştirme kuralı gerekmedi.

## [0.15.2] — 2026-10-02 — Eşiği yükselttikten sonra eski hikâyeleri düzenleme

### Eklendi
- **Ayarlar → Haber toplama → "Son 3 günün hikâyelerini bu eşiğe göre düzenle".** Birleştirme eşiği yalnızca yeni haberleri
  etkiler; daha düşük bir eşikle kurulmuş hikâyeler olduğu gibi kalıyordu (ör. bir belediye başkanının Cumhurbaşkanı ziyareti
  hikâyesine, ertesi gün başka bir başkanın ziyareti de katılmıştı). **Denetle** düğmesi kaç hikâyenin bölüneceğini söyler,
  **Uygula** böler. Büyük grup hikâyeyi (notlar, toplantı kayıtları) korur, ayrılanlar yeni hikâye olur. Elle düzelttiğiniz
  (ayırdığınız ya da birleştirdiğiniz) hikâyelere dokunulmaz. Hiçbir şey kendiliğinden bölünmez.

### Düzeltildi
- **Akışta ve hikâyelerde aşağı gezinirken liste son seçilen satıra geri zıplıyordu.** Liste her uzadığında (aşağıda yeni
  haberler yüklenince ya da yeni hikâye gelince) program seçili satırı ekrana getiriyordu. Artık yalnızca tuşla (J/K)
  seçimi hareket ettirince oraya kaydırır.

## [0.15.1] — 2026-10-02 — Arama kutusunda tek silme düğmesi

### Düzeltildi
- Arama kutularında metin yazınca iki "×" görünüyordu (tarayıcının kendi silme düğmesi bizimkinin yanındaydı); yalnızca bizimki kalıyor.
- Eklenti sürümü program sürümüyle eşleşir; bu sürümden sonra `brave://extensions` → Yeniden yükle gerekir.

## [0.15.0] — 2026-10-02 — Yapay zekâya giden talimatlar arayüzden değiştirilebiliyor

### Eklendi
- **Ayarlar → Yapay zekâ talimatları.** Yerel (Ollama) ya da bulut yapay zekâya her istekle giden talimat metinleri artık
  arayüzden değiştirilebilir: **Haber özeti** (başlık, özet, kategori; tek tek ve toplu), **Hikâye özeti** (hikâye başlığı,
  özet, toplantı notu, önemli noktalar), **Tam metin çevirisi** ve **Arama sözcükleri**. Her biri için varsayılan metin
  düzenleyicide görünür; üslubu, ayrıntı düzeyini ya da vurgulanacak konuları kendi yönergenize göre yazabilirsiniz.
  "Varsayılana dön" düğmesi programın kendi metnini geri getirir.
- **Yer tutucular:** `{input}` (gelen malzemenin tarifi), `{languages}` (çıktı dilleri), `{language}` (çevrilecek dil),
  `{fields}` (cevap alanlarının teknik açıklaması). Çeviri ve arama metni dil yer tutucusunu içermek zorundadır, yoksa
  kaydedilmez; `{fields}` ya da `{input}` yazılmazsa program eksiği kendisi ekler, çünkü model onsuz işi yapamaz.
- **Sabit kalanlar:** cevabın JSON yapısı (her istekle bir şema gider), rakamların kaynakta bulunup bulunmadığı denetimi ve
  uzunluk sınırları programdadır. Değişiklik yalnızca bundan sonra yapılacak işleri etkiler; yazılmış özetler değişmez.
- Varsayılan metinler bu sürümden önce gönderilenlerle **birebir aynıdır** (bir testle sabitlendi).
- **Modele gönderilen haberin düzeni ve miktarı da değiştirilebilir.** Haber özetinde her haberin istekteki kalıbı
  (`{source}`, `{language}`, `{title}`, `{text}`), hikâye özetinde giriş satırı (`{count}`) ve her haberin kalıbı
  (`{n}` ve öncekiler) yazılabilir. Ne kadarının gönderileceği sınırlarla ayarlanır: bir haberin metninden karakter sayısı
  (200–60.000), toplu okumada haber başına karakter ve tek istekte kaç haber (2–25), hikâye için kaç haber ve her birinden
  kaç karakter. Boş bırakılan alan varsayılanı kullanır. Daha çok metin daha iyi özet verebilir ama işi yavaşlatır, bulutta
  ücreti artırır. Başlık kalıpta bulunmak zorundadır.
- **Klavye kısayolları değiştirilebiliyor** (Ayarlar → Klavye kısayolları). Her işlem (aramaya git, sonraki / önceki haber,
  haberi aç, toplantı listesine ekle) için en çok dört tuş atanır: **+** ile tuşa basarak eklenir, **×** ile kaldırılır
  (son tuş kaldırılamaz), "Varsayılan" işlemi eski haline getirir. Tek harf, rakam, işaret ya da Enter, Boşluk, ok tuşları,
  Home, End, PgUp, PgDn, F1–F12 verilebilir; bir tuş iki işlemde kullanılamaz (hangi işlemde olduğu söylenir). Esc (pencere
  kapatma) ve Tab sabittir. Akıştaki ve geçmişteki ipucu satırı ile arama kutusundaki tuş etiketi seçilen tuşları gösterir.
- **Yazı tipi, yazı boyutu ve yazı rengi ayarlanabiliyor** (Ayarlar → Görünüm). Yazı tipi listeden seçilir ya da
  bilgisayarda yüklü herhangi bir yazı tipinin adı yazılır; boyut %80–%140 arasında arayüzün tamamını ölçekler; yazı rengi
  açık ve koyu tema için ayrı seçilir (soluk gri yazılar seçilen renge göre türetilir). Her biri "temanınki"ne
  döndürülebilir. Yazı tipi adında yalnızca harf, rakam, boşluk ve `, . - ' "` kabul edilir.
- **Ayarlar iki sütunlu.** Uzun tek sayfa yerine solda altı kategori (Genel, Haber toplama, Yapay zekâ, Tam metin, Arşiv ve
  yedek, Sistem), sağda seçili kategorinin ayarları. Üstteki **Ayar ara** kutusu tüm kategorilerde arar ve yalnızca
  eşleşen ayarları gösterir. Son açılan kategori hatırlanır; dar pencerede liste üstte yatay şeride döner.

## [0.14.3] — 2026-10-02 — Eklenti pencere açmıyor; eski eklenti uyarısı; yeni simgeler

### Düzeltildi
- **Eklenti okurken önünüze pencere çıkmıyor.** Tarayıcı penceresiz başlatıldığında (program onu kapalı bulup
  başlattığında) eklenti her sayfa için küçültülmüş yeni bir pencere açıyordu. Artık böyle bir durumda en fazla bir kez,
  boş sekmeli küçültülmüş bir pencere açılır ve sonraki sayfalar onun içinde arka plan sekmesi olarak okunur. Açık bir
  pencere varsa, küçültülmüş olmayan bir pencere seçilir.
- **Eski eklenti uyarısı.** Eklenti her istekte sürümünü bildiriyor. Tarayıcı, program klasöründekinden farklı (eski)
  bir kopya çalıştırıyorsa Ayarlar → Tam metin'de ve kenar çubuğunda "Eklentiyi yeniden yükleyin" yazar.
  Güncellemeden sonra tarayıcının eklentiler sayfasında bir kez **Yeniden yükle** demek yeterlidir.

### Değişti
- **Hikâye birleştirme daha sıkı:** bir haberin hikâyeye katılması için hikâyedeki haberlere ortalama benzerliği artık en az
  0,55 (eskiden 0,50). 7 güne yayılan bir hikâye, konudan konuya kayıp alakasız haberler topluyordu (ör. Gazze'deki uydu
  görüntüleri hikâyesine bir petrol sızıntısı haberi). Son 66 saatin 18.664 gerçek haberiyle ölçüldü: en büyük hikâye 525 →
  278 habere, 50+ haberli hikâyelerdeki haber payı %13,7 → %7,6'ya indi, hikâye içi tutarlılık 0,60 → 0,65'e çıktı, gerçek
  (3+ haberli) hikâye sayısı arttı. Bedeli: etiketli kümede aynı olayın bazı haberleri iki hikâyeye bölünebiliyor. Var olan
  hikâyeler değişmez; Ayarlar'dan 0,50'ye dönülebilir. Ayrıntı: docs/BIRLESTIRME_KARSILASTIRMA.md.
- README'de tanıtım animasyonu (GIF) ve yeni simgelerle yenilenmiş ekran görüntüleri.
- Kenar çubuğunda **Akış** (gazete) ve **Toplantı** (sunum tahtası) simgeleri birbirinden kolayca ayrılıyor.

## [0.14.2] — 2026-10-02 — The Independent akışı yeniden çekiliyor

### Düzeltildi
- **The Independent'ın RSS akışı 429 ("çok sık istek") veriyordu ve hiç çekilemiyordu.** Site, Python'un HTTP istemcisinin
  bağlantı kuruş biçimini tanıyıp geri çeviriyordu (başlıklar önemli değildi; aynı adres `curl` ile 200 veriyordu). Bu
  akış artık Windows'la gelen `curl.exe` ile çekiliyor: kimlik taklidi yok, herkese açık RSS adresi sıradan ve adıyla
  gelen bir araçla alınıyor. Site bunu da reddederse akış "başarısız" kalır, başka yol denenmez. `curl.exe` yoksa
  hata görünür. Gerçek akışla denendi (84 haber).

## [0.14.1] — 2026-10-02 — Eklenti arka planda okur; yabancı yazılı haberlerin dili doğru

### Değişti
- **Eklenti sayfaları artık arka plan sekmesinde açar** (eskiden her sayfa için küçültülmüş ayrı bir pencere açılıyor,
  bu da çoğu zaman öne geliyordu). Tarayıcıda açık bir pencere varsa sayfa onda, `active: false` ile arka planda
  yüklenir, okunur ve sekme kapanır; açık pencere yoksa (tarayıcı pencere açmadan başlatılmışsa) eskisi gibi küçültülmüş
  bir pencere kullanılır. Gerçek Chromium'da iki Guardian haberiyle denendi: çıkan metin aynı uzunlukta (2468 ve 5079
  karakter), hiçbir an ikinci bir pencere açılmadı, sekmeler kapandı. **Güncelleme sonrası tarayıcının eklentiler
  sayfasında eklentiye bir kez "Yeniden yükle" demek gerekir.**
- Eklenti açıklamaları ve kurulum adımları "Chromium tabanlı tarayıcı (Chrome, Brave, Edge, Opera)" diyor.

### Düzeltildi
- **Haberin dili metnin harflerinden anlaşılır.** İngilizce etiketli bir akışın Japonca, Arapça ya da Rusça bölümü
  (Reuters, CNN, UNIAN, SANA gibi) kartta "İngilizce" yazıyordu; son 3 günde 24.000 haberin 798'i böyleydi. Artık metin
  Latin harfli değilse dil harflerden bulunur (Japonca, Çince, Korece, Arapça, Farsça, Urduca, Rusça, Ukraynaca,
  İbranice, Yunanca, Tay). Latin harfli metinlerde akışın etiketi aynen kalır; doğru etiketli olan (ör. Ukraynaca)
  değiştirilmez. Var olan haberler bir kez düzeltilir (`repair.languages`).

### Eklendi
- Eklentinin okuduğu haberler tam metinden özetlenir ve yapay zekâ kuyruğunun başına geçer (0.14.0'da yayımlanmıştı;
  ayrıntı orada).

## [0.14.0] — 2026-10-01 — Tarayıcı eklentisi: abonelik siteleri kendi tarayıcınızda okunur

### Eklendi
- **Eklentinin okuduğu haberler tam metinden özetlenir ve sıranın başına geçer.** Yapay zekâ kuyruğu doluyken bile,
  eklentinin sizin tarayıcınızda okuduğu bir haber (özel haberler, abonelik siteleri) tam metniyle yeniden
  özetlenir; özeti daha önce yazılmışsa o kalır, yenisi hazır olunca değişir. Tam özet yazılır (yalnızca başlık
  değil). Yapay zekâ üç denemede başaramazsa bırakılır, eski özet kalır. Diğer yöntemlerle gelen tam metinler
  eskisi gibi sıra boşaldığında işlenir. Hikâye özeti hâlâ haberlerin özetlerinden yazılır (tam metinden değil).
- **World Signal tarayıcı eklentisi** (program klasöründeki `extension` klasörü; Chrome ve Brave için).
  Abonelik sitelerinin haberlerini, özellikle yalnızca orada çıkan özel haberleri, programın kendi otomasyon
  tarayıcısı yerine **sizin tarayıcınız** açar: gerçek profiliniz, gerçek oturumunuz. Hangi haberin
  ne zaman okunacağına program karar verir (aynı kuyruk, aynı insan temposu); eklenti yalnızca sayfayı küçültülmüş ayrı
  bir pencerede açar, 3–8 saniye bakıp insan gibi aşağı kaydırır, sayfanın HTML'ini programa verir ve pencereyi kapatır.
  Metni çıkarma, engel algılama ve bekletme programdadır. Her sayfa için ayrı pencere açılır ve sayfa bitince kapanır.
- **Bir kerelik kurulum, üç adım** (Ayarlar → Tam metin → Eklenti): (1) tarayıcının eklentiler sayfasında Geliştirici
  modunu açıp **Paketlenmemiş öğe yükle** ile eklenti klasörünü seçin (**Eklenti klasörünü aç** düğmesi klasörü
  gösterir), (2) eklentinin simgesine tıklayıp Ayarlar'daki **eşleşme kodunu** yapıştırın, (3) abonelik sitelerine o
  tarayıcıda giriş yapmış olun. Sonrası kendiliğinden: tarayıcı açıkken (kapalıysa program onu pencere açmadan
  başlatabilir, ayarla kapatılır) eklenti haberleri okur. Eklenti, programın ona söylediği bekleme süresini aşıp 10
  dakikadan uzun sessiz kalırsa kenar çubuğunda tek satırlık uyarı çıkar (program yeni açıldığında ya da siteye uzun
  bir mola verildiğinde boşuna uyarmaz); Ayarlar bağlı / bağlı değil durumunu gösterir.
- **Okuyucu seçimi** (`fulltext.reader`): *Eklenti (önerilen)* ya da *Programın kendi tarayıcısı* (eskisi gibi). Eklenti
  modunda "tarayıcı ile" kaynakların işlerini yalnızca eklenti alır; "doğrudan indir" kaynakları eskisi gibi program
  okur. Eklenti bağlı değilken otomasyon tarayıcısına dönülmez, iş sırada bekler.
- **Eklenti modunda ücretli kaynakların yeni haberleri sıraya girer**; yayıncının "Özel" dediği haberler önde, sonra
  öbürleri; sizin istedikleriniz ve not defterindekiler yine en önde. Site başına günlük sınır ve diğer tempo ayarları
  geçerlidir. Kendiliğinden sıraya girip 24 saat içinde okunamayan haberler sıradan çıkar (sizin istedikleriniz ve not
  defterindekiler kalır), böylece sıra şişmez.
- **Eklentinin açtığı sayfa bir deneme sayılır:** sayfa zamanında açılmaz, açılamaz, okunamaz ya da alınamayacak kadar
  büyükse (8 MB üstü) deneme sayılır, site bir süre dinlenir; üç denemeden sonra haber bırakılır. Yalnızca okuma
  penceresini sizin kapatmanız deneme sayılmaz. Sayfanın HTTP durumu (401/403/429 gibi) da programa iletilir; site,
  programın kendi tarayıcısında olduğu gibi bekletilir. Google News yönlendirmeleri ve web adresi olmayan bağlantılar
  eklentiye hiç verilmez. Tam metin kapatılır ya da okuyucu değiştirilirse eklentinin elindeki iş bırakılır.
- **Güvenlik:** eklenti programla yalnızca bu bilgisayarın içinde, sabit bir port aralığında (47821–47830) ve rastgele
  üretilen, yalnızca bu bilgisayarda (Windows kullanıcı şifrelemesiyle) saklanan bir eşleşme kodu ile konuşur. Başka bir
  bilgisayar, bir web sayfası ya da DNS yeniden bağlama ile gelen istek kodla bile kabul edilmez. Kod **Yeni kod** ile
  yenilenebilir (eski eklenti bağlantısı kopar). Eklenti kodu göndermeden önce, sorduğu portta aynı kodu taşıyan World
  Signal'in dinlediğini doğrular (her seferinde rastgele bir soru; yanıt kodla imzalanır ve programın dinlediği portu
  içerir): bu portlardan birini başka bir program tutsa da, soruyu asıl programa aktarsa bile kodu öğrenemez.
  (Kullanıcının belleğini ya da dosyalarını okuyabilen bir program bu korumanın dışındadır.) Eklenti programın verdiği adresler dışında hiçbir siteyi açmaz,
  yalnızca `http`/`https` adreslerini açar.

### Değişmeyen sınırlar ve riskler
- **Robot doğrulaması (CAPTCHA) ve benzeri korumalar asla çözülmez.** Böyle bir sayfa gelirse haber "engellendi" olur,
  site giderek uzayan aralıklarla bekletilir. Eklenti sayfada yalnızca kaydırır; tıklamaz, yazmaz, form göndermez.
- **Sitelerin kullanım şartları abonelere de otomatik okumayı yasaklayabilir.** Bunun riski (hesabın uyarılması ya da
  kapatılması dahil) sizindir; tempo sınırları Ayarlar → Tam metin'den görülür ve değiştirilir.
- Tarayıcı kapalıyken ya da eklenti duraklatılmışken hiçbir sayfa okunmaz; iş sırada bekler.
- Eklenti tarayıcı mağazalarında yayımlanmaz; program güncellenince eklenti klasörü de güncellenir, tarayıcıda eklentiler
  sayfasında bir kez **Yenile**'ye basmak gerekir.

### Kaldırıldı
- **Sayfa ekle**'nin (yer imi + yapıştırma) arka uç kodu (`clip.py`, `/api/clips`): eklenti yeni haber eklemiyor,
  var olan haberleri tamamlıyor. Daha önce eklenen haberler ve "Elle eklenenler" kaynağı yerinde duruyor.

### Denendi
- Gerçek bir tarayıcıda (Chromium, eklenti yüklü, deneme örneğiyle) eklenti eşleşti, iki Guardian haberini küçültülmüş
  pencerede okudu; çıkan metin düz indirmeyle aynı uzunluktaydı (3554 ve 4205 karakter), ikinci sayfa ilkinden yaklaşık
  3 dakika sonra açıldı, okuma penceresi sonra kapandı. **Abonelik siteleri, Brave ve pencere açmadan başlatma henüz
  denenmedi.**

## [0.13.4] — 2026-10-01 — Toplantı notunda önemli noktalar; tarayıcı çökmesi haberleri yakmıyor

### Değişti
- **Toplantı öneri listesi** (ekran ve çıktı): her öneride başlık, ne olduğunu anlatan kısa özet ve altında maddeler
  halinde **önemli noktalar** (isimler, rakamlar, kim ne dedi). "Birçok kaynakta geçtiği için…" türünden "neden
  toplantıda" cümleleri çıktıdan çıktı (hikâye kartlarında duruyor). Sizin notunuz "Notum:" olarak yazılır; kaynaklardan
  yalnızca hikâyeye en yakın üçü, bağlantılarıyla. Önemli noktaları yapay zekâ hikâye özetiyle birlikte, yalnızca
  haberlerdeki bilgilerle yazar; rakamlar özetteki gibi denetlenir. Toplantı listesine eklenen hikâyeler sıraya önce
  girer (daha önce özetlenmiş olsalar da, çalışma saatleri dışında da); ekran noktalar gelince kendiliğinden yenilenir.
  Özetler biraz uzadığı için hikâye başına yapay zekâ süresi bir miktar artar.
- Toplantı listesindeki not kutusunun adı "Kısa gerekçe" yerine "Kısa not".

### Kaldırıldı
- **Sayfa ekle** (yer imi + yapıştırma). Elle tek tek eklemek otonom çalışmaya uymuyordu; yerine kendi tarayıcınızda
  çalışacak bir World Signal eklentisi tasarlanıyor. Daha önce bu yolla eklenen haberler yerinde duruyor.

### Düzeltildi
- **Tarayıcı açılırken çöküyordu, haberler boşuna "alınamadı" oluyordu.** Tam metin için açılan Brave, özellikle
  kendini güncellerken açılışta çöküyordu (profilde 75 çökme raporu; her biri kayıttaki bir "tarayıcı başlatılamadı"ya
  denk geliyor). Her çökme sıradaki haberin deneme hakkından düşüyordu; site hiç sorulmadan haberler "alınamadı"
  oluyordu ve program dakikada bir yeniden deniyordu. Artık açılmayan tarayıcı habere ve sitenin temposuna dokunmuyor,
  yeniden deneme 1, 2, 4… en çok 30 dakika arayla yapılıyor ve hatanın ayrıntısı kayda yazılıyor.

## [0.13.3] — 2026-09-29 — Sayfa ekle, ilk veren ve kaynaklar arası çelişki

### Eklendi
- **Sayfa ekle** (Akış → Sayfa ekle): The Economist, WSJ gibi programları içeri almayan siteler için. Haberi kendi
  tarayıcınızda, aboneliğinizle okursunuz; bir kez yer imleri çubuğuna sürüklediğiniz **World Signal'e kopyala**
  düğmesine tıklarsınız (sayfa panoya kopyalanır), programa dönüp yapıştırır, **Ekle**'ye basarsınız. Haber, sitenin
  kaynağının altına (yoksa "Elle eklenenler"e) tam metniyle girer; özeti yapay zekâ yazar, hikâyelere karışır,
  aranabilir, not defterine eklenebilir. Siteye hiçbir istek gönderilmez, hiçbir koruma aşılmaz: sayfayı siz açmış
  olursunuz. Aynı sayfa yeniden eklenirse metni yenilenir. Sayfada haber ya da tam metin yoksa nedeni söylenir.
- **"İlk veren"**: birden çok kaynakta geçen hikâyenin kartında ve ayrıntısında, olayı ilk yayımlayan kaynak ve saati
  (yayın saatine göre). Birkaç güne yayılan hikâyelerde zincirin ilk haberini gösterir; saat açıkça yazıldığı için
  yanıltmaz.
- **"Kaynaklar çelişiyor"**: hikâye özetini yazarken yapay zekâ, kaynaklar bir olguda (rakam, kim ne yaptı, kim
  sorumlu) birbirini yalanlıyorsa bunu tek cümleyle ve kaynak adlarıyla yazar; kartta turuncu bir notla görünür. Kaynaklar
  uyuşuyorsa ya da model emin değilse boş bırakır. Bu bilgi yeni yazılan özetlerde çıkar; eski özetlerde görünmez.

## [0.13.2] — 2026-09-29 — Habere tıklayınca tam metin

### Değişti
- **Habere tıklayınca tam metin açılıyor:** akıştaki haber kartında ve hikâye ayrıntısında başlığa basınca kaynak site
  değil, program içindeki okuma penceresi açılır. Metin henüz yoksa pencere onu ister, beklerken özeti gösterir ve metin
  gelince kendiliğinden ona geçer; alınamazsa nedenini söyler. Çevirisi yoksa orijinal metin açılır, çeviri bir tık
  uzakta. Tam metin kapalıysa (Ayarlar → Tam metin) başlık eskisi gibi kaynağı açar.
- **Kaynağa git** düğmesi: kartlarda, hikâye ayrıntısındaki her haberde ve okuma penceresinde.

### Düzeltildi
- **Çalışma saatleri ve sessiz saatlerde saat kutuları daralıp "07" yerine "0" gösteriyordu.**
- **Akıştaki kartlardan açılan tam metin okuma penceresi diğer kartların arkasında kalıyor, okunamıyordu.** Açılır
  pencereler artık kartın içinde değil sayfanın kendisinde çizildiği için her zaman en üstte açılır (0.13.1'de eklenen
  akıştaki tam metin düğmesinin hatasıydı).

## [0.13.1] — 2026-09-29 — Ülkem gerçekten kapanıyor, çalışma saatleri, düzeltmeler

### Eklendi
- **Çalışma saatleri** (Ayarlar → Arka plan). Varsayılan: gece gündüz sürekli çalışır; programı hep açık
  bırakabilirsiniz. İsterseniz saat aralığı seçersiniz; dışında haber toplama, yapay zekâ ve tam metin dinlenir. Elle
  istedikleriniz (Özetle, tam metni getir, Şimdi tara) yine yapılır; pencere ve veriler her zaman kullanılabilir.
- **Ülke etiketleri ayrı bir seçenek** (Ayarlar → Ülkem → Ülke etiketleri, varsayılan açık). Kapatınca ülkeyi ya da
  konuları değiştirdiğinizde eski haberler yeniden derecelendirilmez ve kartlarda etiket görünmez.

- **Akışta tam metin:** hem hikâye kartlarında hem haber kartlarında **Tam metni getir** / **Tam metni oku** düğmesi.
  Getirince kart yenilenmeden durumu izler ("Tam metin sırada…"), gelince okuma penceresi açılır (yalnızca sizin
  okumanız için; çıktılara konmaz). Hikâye kartında düğme, hikâyenin temsilci haberi içindir; diğer haberler hikâye
  ayrıntısında.
- **Tam metni de çevir** (Ayarlar → Tam metin, varsayılan kapalı = yalnızca özet). Açıksa gelen her tam metin özet
  dillerinize de çevrilir (çok yapay zekâ işi gerektirir); kapalıyken okuma penceresinde **Çevir**'e basınca çevrilir.

### Değişti
- **Bölge filtresinde "Küresel" yerine "Yerel dışı":** yerel bölge (Türkiye) dışındaki tüm kaynakların haberleri.
  Ajansları (Reuters, AP, AFP, Bloomberg) ayırmak için Kaynak grubu → Ajanslar kullanılır. Seçenek yalnızca ülkesi
  Türkiye olanlarda görünür (başka ülkelerde "yerel bölge" tanımı yok).
- **"Ülkem" kapalıyken yapay zekâ o işleri hiç yapmıyor:** haber ve hikâye istemlerinden ülke/konu soruları çıkarıldı
  (istem ve cevap kısalır, iş hızlanır) ve "ülke bilgisi eksik" diye özetlerin yeniden yazılması durdu. Bedeli:
  kapalıyken işlenen haberlerde ülke bilgisi olmaz; sonradan açarsanız yalnızca yeni haberlerde çalışır.
- **Son dakika göstergesi** artık yanıp sönen kırmızı bir nokta (eskisi kablosuz ağ simgesine benziyordu).
- **Engellenen sitelere daha temkinli davranılıyor:** bot doğrulaması ya da 401/403/429 alan sitede bekleme süresi, aynı
  engel üç gün içinde tekrarlanırsa her seferinde ikiye katlanıyor (en fazla 72 saat); giriş isteyen (401) siteler de
  beklemeye alınıyor. Amaç aboneliklerin şüpheli işaretlenmemesi.

### Düzeltildi
- **TRT Haber gibi bazı akışlarda bozuk Türkçe karakterler** ("SoykÄ±rÄ±m"): UTF-8 yazının Windows-1252 sanılmasından
  doğan bozukluk yeni haberlerde okunurken düzeltiliyor; kayıtlı 69 haber bir kez onarıldı (arama dizini dahil).

## [0.13.0] — 2026-09-29 — Yapay zekâ yetişiyor, veritabanı küçülüyor

### Eklendi
- **Özetleme kapsamı** (Ayarlar → Yapay zekâ). Günde ~7.500 haber geliyor, program günde ~8 saat açık; haber başına
  ~8 saniyeyle yapay zekâ en fazla ~4.000 haber okuyabiliyordu ve kuyruk hiç yetişmiyordu. Üç seçenek:
  - **Her haber ayrı** (eskisi gibi) — güçlü bilgisayarlar ya da hızlı bir bulut hizmeti için.
  - **Hikâyeler birlikte** — birden çok kaynakta geçen olayın haberleri ayrıca işlenmez, hikâye özeti onları kapsar.
    Hikâye özeti artık ülke bilgisini de çıkarıyor (hangi ülkeler, Türkiye geçiyor mu, konularınız); hikâyenin ülke
    bağlantısı hem haberlerinden hem bu bilgiden, aynı kurallarla hesaplanıyor. Bu bilgi olmadan yazılmış son
    özetler bir kez yeniden yazılır.
  - **Hızlı** (varsayılan) — ayrıca tek kaynaklı haberler 10'arlı okunur: başlık, kategori ve ülke bağlantısı; özet,
    haberdeki **Özetle** düğmesiyle yazılır. Gerçek haberlerde ölçüldü: haber başına ~8 yerine ~3,3 saniye, 30
    haberin 30'u kullanılabilir. Hesap: günlük iş ~65.000 saniyeden ~12.000 saniyeye iniyor.
- **Akışta iki yeni kaynak grubu:** "Kaynak grubu" filtresinde **Özel haberler** (yayıncının "Özel haber",
  "Exclusive" … diye işaretlediği haberler) ve **Makaleler (görüş, analiz, köşe yazısı)**. Makale; sitenin kendi
  bölümünden (adreste `/opinion/`, `/yazarlar/`, `/commentisfree/` …) ya da başlıktaki etiketten ("Görüş:",
  "Analysis |", "… - opinion") tanınır. Her kaynaktan gelir; kaynak listesi değişmez. Gerçek akışta son 24 saat:
  7 özel haber, 76 makale.

### Değişti
- **Önem sırası dünyaya açıldı:** bir bölgeden en fazla 6 bağımsız kaynak sayılıyor ve kaynak puanı 12 yerine 40
  kaynakta doluyor. Önceden Türk basınında 12 kaynakta geçen bir iç haber, 57 yabancı kaynakta geçen bir dünya
  haberiyle aynı kaynak puanını alıyordu. Gerçek akışta ölçüldü (son 24 saat): ilk 20 hikâyede çoğunluğu Türk
  kaynaklı olanlar 11'den 4'e indi; en çok yabancı kaynakta geçen hikâyeler 28., 36. ve 53. sıradan 2., 4. ve 8. sıraya
  çıktı. Büyük Türkiye haberleri ilk sıralarda kalıyor. Kartta "N kaynak" etiketi yine tüm kaynakları sayar.
- **Ülkem artık isteğe bağlı** (Ayarlar → Ülkem → Ülkem özelliği). Kapatınca ülke bağlantısı önem skoruna katılmaz,
  akıştaki ülke filtresi ve kartlardaki ülke etiketi gizlenir. Yapay zekâ ülke bilgisini çıkarmayı sürdürür; yeniden
  açınca hemen geçerli olur.
- **Yedekler beş kat küçük:** yedek artık sıkıştırılmış bir `.zip` ve hikâye birleştirmenin vektörlerini içermiyor
  (geri yüklemeden sonra birkaç dakikada yeniden hesaplanırlar). Ölçülen: 80 MB → ~15 MB. Eski `.db` yedekler
  listelenir ve geri yüklenebilir.
- **Vektörler yarım boyutta ve 4 gün:** hikâye birleştirme son 72 saate baktığı için 7 yerine 4 gün tutuluyor; 16 bitlik
  sayılarla saklanıyor (ölçüm: 27.122 benzer çiftin yalnızca 4'ünde karar değişiyor). Veritabanının en büyük kalemi
  (~210 MB) ~60 MB'a iniyor.
- **Silinen verinin yeri diske geri veriliyor:** bakım, boş alan dosyanın %20'sini aşınca veritabanını sıkıştırıyor.

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
