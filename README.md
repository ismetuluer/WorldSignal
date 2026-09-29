# World Signal

**Türkçe · [English](README.en.md)**

**Dünya gündemini tek ekranda toplayan, aynı olayı anlatan haberleri birleştiren, önem sırasına dizen ve seçtiğiniz
dillerde özetleyen bir Windows masaüstü programı.**

Haber merkezlerinde sabah toplantısına hazırlanmak için yapıldı: yüzlerce kaynağın RSS akışlarını gün boyu tarar,
aynı olayı anlatan haberleri tek bir "hikâye" kartında toplar ("9 kaynakta geçiyor"), hikâyeleri önem sırasına koyar
ve isterseniz yapay zekâyla seçtiğiniz dillerde (örneğin Türkçe ve İngilizce) başlık ve özet yazar. Toplantı listesi, not
defteri, geçmiş günler ve yazdırılabilir çıktılar da içindedir.

Arayüz Türkçe ve İngilizcedir.

---

## Ekran görüntüleri

Aşağıdakiler programın gerçek ekranlarıdır (herkese açık haber akışlarından gelen verilerle).

<p align="center"><img src="docs/screenshots/feed-tr.png" alt="Akış: önem sırasına dizilmiş hikâye kartları" width="860"></p>

**Akış.** Aynı olayı anlatan haberler tek kartta, önem sırasıyla. Kartın altındaki etiketler skorun nedenini söyler
("43 kaynak", "3 saatte 3 kaynak", "Türkiye bağlantısı"); "İlk veren" olayı ilk yayımlayan kaynağı gösterir.

<p align="center"><img src="docs/screenshots/story-tr.png" alt="Hikâye ayrıntısı: özet, skorun dökümü, notlar" width="760"></p>

**Hikâye ayrıntısı.** Özet, skorun nasıl hesaplandığı, günlere göre gelişim, tüm haberler ve notlarınız.

<p align="center"><img src="docs/screenshots/meeting-tr.png" alt="Toplantı listesi" width="760"></p>

**Toplantı listesi.** Hikâyeler tek tıkla eklenir, sürükleyerek sıralanır, her öneriye kısa bir not yazılır.

<p align="center"><img src="docs/screenshots/addpage-tr.png" alt="Sayfa ekle penceresi" width="560"></p>

**Sayfa ekle.** Programları içeri almayan siteler (The Economist, WSJ…) için: haberi kendi tarayıcınızda okuyun, yer
imine tıklayın, buraya yapıştırın. Haber tam metniyle eklenir.

<p align="center"><img src="docs/screenshots/stats-tr.png" alt="İstatistik: konu trendi" width="860"></p>

**İstatistik.** Bir konunun saat saat izi ve gündemdeki payı, kategori ve bölge dağılımı, yükselen hikâyeler.

<p align="center"><img src="docs/screenshots/sources-tr.png" alt="Kaynaklar" width="860"></p>

**Kaynaklar.** Kaynakları açıp kapatın, kendi RSS adresinizi ekleyin; çalışmayan akışlar kırmızıyla ve nedeniyle görünür.

<p align="center"><img src="docs/screenshots/feed-dark-tr.png" alt="Koyu tema" width="860"></p>

**Koyu tema.** Açık, koyu ya da Windows'a uyan tema.

---

## İçindekiler

- [Ekran görüntüleri](#ekran-görüntüleri)
- [Neler yapar?](#neler-yapar)
- [Kurulum](#kurulum)
- [Güncellemeler](#güncellemeler)
- [Yapay zekâ (isteğe bağlı)](#yapay-zekâ-isteğe-bağlı)
  - [Özet dilleri](#özet-dilleri) · [Bulut yapay zekâ](#bulut-yapay-zekâ)
- [Kullanım](#kullanım)
- [Telif ve abonelikler](#telif-ve-abonelikler)
- [Gizlilik ve güvenlik](#gizlilik-ve-güvenlik)
- [Sorun giderme](#sorun-giderme)
- [Geliştirme](#geliştirme)

---

## Neler yapar?

| | |
|---|---|
| **Haber toplama** | 140'a yakın kaynak hazır gelir (Batı basını, ajanslar, Orta Doğu, Rusya/Ukrayna, Asya, Avrupa, Türk basını, spor). Her kaynağın akışı çalışıp çalışmadığı denenerek kataloğa girer. Kendi RSS adreslerinizi de ekleyebilirsiniz. |
| **Hikâyeler** | Aynı olayı anlatan haberler, farklı dillerde olsalar da tek kartta birleşir. Yanlış birleşeni ayırabilir, ayrı kalanları birleştirebilirsiniz. |
| **Önem sırası** | Bağımsız kaynak sayısı, tazelik, **ülkenizle bağlantısı** ve sizin ilgi alanlarınıza göre. Her kartta skorun **neden** yüksek olduğu yazar; yayıncının "Özel" dediği haberler ve hızla yayılan **Son dakika** hikâyeleri rozetle işaretlenir. |
| **Özet** | Seçtiğiniz 1–4 dilde (Türkçe, İngilizce, Portekizce, Arapça…) başlık, 3–5 cümlelik özet, kategori, "neden önemli". Bilgisayarınızdaki Ollama ya da kendi anahtarınızla bir bulut hizmeti yazar. Yalnızca kaynak metne dayanır; orijinal başlık ve bağlantı her zaman bir tık uzakta. |
| **Toplantı ve notlar** | Tek tuşla toplantı listesine ekleme, sürükleyerek sıralama, hikâyeye not, günlere göre not defteri. |
| **Çıktılar** | Toplantı listesi, haber detayı, sabah bülteni ve notlar: biçimli kopyala (Word/Outlook), düz metin (WhatsApp), yazdır/PDF, **e-postayla gönder**. |
| **Geçmiş** | Takvimden bir gün seçip o sabahki sıralamayı görme, tüm günlerde arama, bir hikâyenin gün gün gelişimi. |
| **İstatistik** | Bir konunun saat saat / gün gün izi ve gündemdeki payı, kategori ve bölgelere göre dağılım, yükselen hikâyeler, kaynak ve ülke sayıları. |
| **Tam metin** | Açık siteler ve **sizin aboneliğiniz olan** siteler için makalenin tamamını program içinde okuma ve çevirme. |
| **Arka planda** | Pencere kapansa da sistem tepsisinde taramaya devam eder; önemli bir hikâye hızla yayılırsa Windows bildirimi. |

## Kurulum

**Gerekenler:** Windows 10 veya 11 (64 bit). Kurulum, yönetici izni ya da ek program gerekmez.
Microsoft Edge WebView2 Windows'ta hazır gelir.

1. [Releases](../../releases/latest) sayfasından en yeni `WorldSignal-<sürüm>-windows.zip` dosyasını indirin.
2. Zip'e sağ tıklayın → **Tümünü ayıkla**. Hedef olarak **kendi bilgisayarınızda yazılabilir bir klasör** seçin, örneğin
   `Belgeler\WorldSignal`.
   - `Program Files` gibi korumalı klasörler ve ağ klasörleri **önerilmez**: program oradan çalışır ama kendini
     güncelleyemez.
3. Ayıklanan `WorldSignal` klasöründeki **`WorldSignal.exe`** dosyasına çift tıklayın.
   - İlk açılışta Windows "Windows bilgisayarınızı korudu" diyebilir; program imzalı olmadığı için bu normaldir.
     **Ek bilgi → Yine de çalıştır** deyin. Bu uyarı bir kez çıkar.
   - Bazı antivirüs programları (ör. Trend Micro) da tanımadıkları programı ilk açılışta durdurup sorar; güveniyorsanız
     izin verin.
4. Masaüstüne kısayol: `WorldSignal.exe`'ye sağ tıklayın → **Daha fazla seçenek göster → Gönder → Masaüstü (kısayol oluştur)**.

İlk açılışta kaynaklar hemen taranır; haberler birkaç saniyede, hikâyeler birkaç dakikada dolar.

**Verileriniz** (veritabanı, notlar, ayarlar, yedekler, günlükler) program klasöründe değil, her zaman şurada durur:
`%LOCALAPPDATA%\WorldSignal` (Ayarlar → Veri → **Klasörü aç**). Program klasörünü silmek ya da güncellemek verilerinize
dokunmaz. Veritabanı her gün kendiliğinden yedeklenir (sıkıştırılmış `.zip`; hikâye birleştirmenin yeniden
hesaplanabilen vektörleri yedeğe konmaz, bu yüzden bir yedek veritabanının yaklaşık beşte biri kadardır). Silinen
verinin yeri bakım sırasında diske geri verilir.

## Güncellemeler

Program yeni sürümleri kendisi bulur:

1. Açıldıktan kısa süre sonra ve her 6 saatte bir bu sayfadaki son sürüme bakar.
2. Yeni sürüm varsa arka planda indirir ve dosyanın bozulmadığını **SHA-256 sağlama değeriyle** doğrular.
3. Her ekranın üstünde **"World Signal x.y.z hazır — Yeniden başlat ve güncelle"** şeridi çıkar. **Yenilikler** düğmesi
   o sürümde neyin değiştiğini gösterir.
4. Düğmeye bastığınızda program kapanır, kendi klasörünü yeni sürümle değiştirir ve yeniden açılır. Bir sorun çıkarsa
   eski sürüm geri konur ve bu size söylenir.

Ayarlar → **Güncellemeler** bölümünde otomatik denetimi ya da otomatik indirmeyi kapatabilir, **Şimdi denetle**
diyebilirsiniz. Program ağ klasöründen ya da yazılamayan bir klasörden çalışıyorsa kendini güncelleyemez; bu durumda
yeni zip'i bu sayfadan indirip eski klasörün yerine ayıklayın (verileriniz yerinde kalır).

## Yapay zekâ (isteğe bağlı)

World Signal yapay zekâ olmadan da çalışır: haberler toplanır, orijinal dilinde listelenir, aranır, not alınır.
Yapay zekâ iki iş yapar:

| Özellik | Nerede çalışır | Donanım |
|---|---|---|
| **Hikâye birleştirme** (aynı olayı anlatan haberleri bulmak) | Her zaman bilgisayarınızdaki [Ollama](https://ollama.com), `bge-m3` modeli (1,2 GB) | Ekran kartı gerekmez; işlemcide çalışır. |
| **Başlık ve özet** | Ollama'daki bir dil modeli **ya da** bir bulut hizmeti (bkz. [Bulut yapay zekâ](#bulut-yapay-zekâ)) | Ollama için güçlü bir ekran kartı önerilir; bulut hizmeti için gerekmez. |

Ollama ücretsizdir, kurulumu yönetici izni gerektirmez ve **Ollama ile her şey bilgisayarınızda çalışır; hiçbir
metin dışarı gönderilmez.**

### Ollama kurulumu

1. [ollama.com/download](https://ollama.com/download) adresinden Ollama'yı kurun.
2. Komut İstemi'ni açıp hikâye birleştirme modelini indirin:
   ```
   ollama pull bge-m3
   ```
3. Ekran kartınız yetiyorsa bir dil modeli de indirin ve World Signal'de **Ayarlar → Yapay zekâ → Model**'den seçin:

   | Ekran kartı belleği | Önerilen model | Not |
   |---|---|---|
   | 16 GB ve üstü | Gemma 4 26B-A4B | Testlerde en iyi sonuç |
   | 8–12 GB | `gemma4:12b` ya da `qwen3.5:9b` | İyi, daha hızlı |
   | 6–8 GB | `gemma4` (8B) | Kabul edilebilir; kısa özetler |
   | Ayrı ekran kartı yok | — | Bir [bulut hizmeti](#bulut-yapay-zekâ) seçin ya da özetlemeyi kapatın; hikâye birleştirme yine çalışır |

   Model karşılaştırması gerçek haberlerle yapıldı (bkz. `tools/benchmark_models.py`).
4. Ollama başka bir bilgisayarda çalışıyorsa **Ayarlar → Yapay zekâ → Ollama adresi**'ne o adresi yazabilirsiniz.

### Özetleme kapsamı

Günde binlerce haber gelir; yapay zekâ her birini tek tek özetlemeye çoğu bilgisayarda yetişemez (haber başına
~8 saniye). **Ayarlar → Yapay zekâ → Özetleme kapsamı**:

| Seçenek | Ne yapar | Kime |
|---|---|---|
| **Her haber ayrı** | Her haber tek tek özetlenir. | Güçlü ekran kartı ya da hızlı bir bulut hizmeti |
| **Hikâyeler birlikte** | Birden çok kaynakta geçen olayın haberleri ayrıca işlenmez; hikâye özeti onları kapsar (ülke bağlantısı da özetten çıkarılır). Tek kaynaklı haberler tek tek özetlenir. | Orta |
| **Hızlı** (varsayılan) | Ayrıca tek kaynaklı haberler 10'arlı işlenir: başlık, kategori ve ülke bağlantısı yazılır; özeti, haberde **Özetle** deyince yazılır. | Yavaş bilgisayarlar |

Ülke bağlantısının kuralları üçünde de aynıdır: yapay zekâ yalnızca metindeki ülkeleri ve konuları çıkarır, kararı sabit
kurallar verir.

### Özet dilleri

**Ayarlar → Yapay zekâ → Özet dilleri**'nden 1–4 dil seçersiniz (30'dan fazla dil var; varsayılan: arayüz dili ve
İngilizce). Başlık ve özetler bu dillerin hepsinde yazılır; kartlardaki dil düğmesiyle aralarında geçersiniz, çıktıların
dilini de bunlardan seçersiniz. Sonradan dil eklerseniz eski haberler arka planda tamamlanır. Her dil işi uzatır:
Ollama'da dört dil, tek dilin yaklaşık üç katı sürer.

### Bulut yapay zekâ

Ekran kartınız yoksa ya da yetmiyorsa başlık ve özetleri bir bulut hizmetine yazdırabilirsiniz. **Ayarlar → Yapay zekâ
→ Yapay zekâ nerede çalışsın?** bölümünden seçin:

| Hizmet | Anahtarı nereden alırsınız | Not |
|---|---|---|
| **Google Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Ücretsiz kullanım kotası var. |
| **OpenAI uyumlu** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Aynı arayüzü kullanan başka hizmetler de olur (OpenRouter, Groq, Mistral, DeepSeek…): **Hizmet adresi**'ne onların adresini yazın. Bilgisayarınızdaki LM Studio da bu yolla, anahtarsız kullanılabilir. |
| **Anthropic Claude** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | |

1. Hizmeti seçin, kendi hesabınızdan aldığınız **API anahtarını** yapıştırıp **Kaydet** deyin.
2. **Bağlantıyı test et** hizmetin modellerini listeler; **Model** kutusundan birini seçin.
3. Ücretsiz planlar dakikada az istek kabul eder; **Dakikada en çok istek** değerini planınıza göre ayarlayın. Sınır
   aşılırsa program bekler ve kendiliğinden devam eder.

> **Dikkat:** Bulut hizmeti seçildiğinde haberlerin metni — **abonelikle okuduğunuz tam metinler dahil** — o hizmete
> gönderilir. Hizmetin kullanım koşulları, ücreti ve bu metinlerin telif sorumluluğu size aittir. Bunu istemiyorsanız
> Ollama'yı kullanın.

Anahtar yalnızca bu bilgisayarda, Windows'un kullanıcı hesabınıza bağlı şifrelemesiyle (DPAPI) saklanır; ekranda bir daha
gösterilmez, günlüklere ve yedeklere girmez. Hikâye birleştirme bulut hizmeti seçildiğinde de Ollama'daki `bge-m3` ile
bilgisayarınızda yapılır.

### Sorunlar

Ollama kapalıysa ya da model yoksa program çökmez: ekranın üstünde nedenini söyleyen bir uyarı çıkar ve haberler
orijinal dillerinde gösterilir. Özetlerin sağlamlığı için özetteki sayılar kaynakla karşılaştırılır; kaynakta geçmeyen
bir sayı varsa "Dikkat" uyarısı gösterilir.

## Kullanım

- **Akış** — *Hikâyeler* görünümü aynı olayın haberlerini tek kartta, önem sırasıyla gösterir; kartın altındaki
  etiketler nedenini söyler ("5 kaynak", "3 saatte 4 kaynak", "Türkiye bağlantısı"). *Haberler* görünümü tek tek en
  yeni haberlerdir. Üstte arama, zaman aralığı ve filtreler var (bölge, kaynak grubu, dil, kategori, kaynak,
  "Türkiye bağlantılı"). Bölge filtresinde **Yerel dışı**, Türkiye dışındaki tüm kaynaklardır. **Seçtiğiniz filtreler hatırlanır.** Kaynak grubu filtresinde iki özel seçenek daha var:
  **Özel haberler** (yayıncının "Özel haber" / "Exclusive" diye işaretledikleri) ve **Makaleler** (görüş, analiz,
  köşe yazısı); ikisi de her kaynaktan toplanır.
- **Ülkem** — "(Ülkeniz) bağlantılı" filtresi ve etiketleri Ayarlar → **Ülkem**'de seçtiğiniz ülkeye göre çalışır
  (varsayılan: Windows'un bölge ayarı). Haber, yapay zekâ onu okuduktan sonra değerlendirilir: ülkeniz haberde
  geçiyorsa *doğrudan*, bir komşunuz, seçtiğiniz yakın ülkeler ya da konular geçiyorsa *dolaylı* bağlantılıdır.
  Konuları listeden ekleyip çıkarabilir, kendi konularınızı yazabilirsiniz. İstemezseniz **Ülkem özelliği**ni
  kapatın: ülke bağlantısı önem skoruna katılmaz, filtresi ve etiketleri görünmez; yapay zekâ da ülke ve konu
  sorularını hiç sormaz (daha hızlı çalışır). **Ülke etiketleri** ayrıca kapatılabilir: ülkeyi değiştirince eski haberler
  yeniden derecelendirilmez.
- **Sayfa ekle** — bot korumalı siteler (The Economist, WSJ…) için: haberi kendi tarayıcınızda okuyun, yer imine
  tıklayın, Akış → **Sayfa ekle** penceresine yapıştırın. Haber tam metniyle eklenir; siteye program hiç istek göndermez.
- **Tam metin** — habere (başlığa) tıklayınca program içinde açılır; metin henüz yoksa istenir, beklerken özet görünür.
  Siteye gitmek için **Kaynağa git**. Kartlardaki **Tam metni getir** düğmesi de metni sıraya alır; gelince okunur (yalnızca sizin okumanız içindir; çıktılara konmaz). Ayarlar → Tam metin → **Tam metni de çevir** açılırsa gelen
  her tam metin özet dillerinize de çevrilir; varsayılan yalnızca özettir.
- **Çalışma saatleri** — Ayarlar → Arka plan. Varsayılan gece gündüz sürekli çalışmadır (programı hep açık
  bırakabilirsiniz); isterseniz bir saat aralığı seçersiniz, dışında haber toplama, yapay zekâ ve tam metin dinlenir.
  Elle istedikleriniz (Özetle, tam metni getir, Şimdi tara) yine yapılır.
- **Hikâye ayrıntısı** — özet, skorun dökümü, günlere göre gelişim, tüm haberler ve bağlantıları, notlarınız. Kartta
  **İlk veren** olayı ilk yayımlayan kaynağı gösterir; kaynaklar bir olguda birbirini yalanlıyorsa yapay zekâ
  **Kaynaklar çelişiyor** notuyla farkı yazar (yalnızca yeni yazılan özetlerde).
  Yanlış gruplanmış haberi **Bu hikâyeden ayır**, aynı olayı anlatan iki hikâyeyi **Başka hikâyeyle birleştir**.
- **Toplantı** — bugünün öneri listesi. Hikâyeyi **Toplantıya ekle** (ya da `T`), sürükleyerek sırala, her öneriye kısa
  gerekçe yaz.
- **Not Defteri** — takvimden bir gün seçin: o günün serbest notu, toplantı listesi ve hikâye notları.
- **Çıktılar** — her çıktı penceresinde:
  - **Biçimli kopyala**: Word ve Outlook'a düzgün yapışır;
  - **Düz metin kopyala**: WhatsApp gibi uygulamalar için;
  - **E-postayla gönder**: masaüstü Outlook varsa biçimli bir taslak açar, yoksa bilgisayarın varsayılan e-posta
    uygulamasında düz metin taslak açar (metin uzunsa kısaltılır, tamamı panoya da kopyalanır). Program e-postayı
    kendisi **göndermez**; alıcıyı yazıp gönderen sizsiniz;
  - **Yazdır / PDF**: PDF için yazıcı olarak "Microsoft Print to PDF"i seçin.
  Çıktının dili özet dillerinizden ayrıca seçilir. **Sabah bülteni** seçilen zaman aralığının en önemli hikâyelerini
  kategorilere göre dizer.
- **İstatistik** — üstten dönem seçilir (24 saat, 7 gün, 30 gün); her şey o döneme göre sayılır. *Konu trendi*'ne bir
  konu yazınca (kaynaklarınızın dillerinde de aranır) saat ya da gün başına kaç haberde geçtiği ve tüm haberler
  içindeki payı çizilir. *Kategorilere göre gündem* yalnızca yapay zekânın kategorisini belirlediği haberleri sayar
  (oranı yazar); *Haberi veren basının bölgesi* kaynağın bölgesidir, olayın geçtiği yer değil. *Yükselenler* son
  saatlerde en hızlı büyüyen hikâyelerdir; tıklayınca açılır. *Kaynaklar* tablosu hiç haber vermeyen kaynakları da
  gösterir. Değişimler önceki eşit süreyle karşılaştırılır; toplama o kadar eskiye gitmiyorsa karşılaştırma gösterilmez.
  Her grafik tablo olarak da görülebilir.
- **Geçmiş** — takvimden bir gün; *Sabah 09:00* o sabahki sıralamayı, *Günün tamamı* gün sonundaki sıralamayı gösterir.
  Arama tüm günlerde çalışır; Türkçe karakter ve büyük/küçük harf ayırmaz.
- **Arama başka dillerde de yapılır.** Yazdığınız kelimeler hemen aranır; yapay zekâ açıksa aynı kelimeler birkaç
  saniye içinde kaynaklarınızın yayın dillerine çevrilir ("kuzey kore iha" → "North Korea drone", "Северная Корея
  беспилотник" …) ve bu haberler de listeye eklenir. Arama kutusunun altında hangi çevirilerle arandığı yazar. Çoğu
  yabancı haberin Türkçe özeti olmadığı için, bu olmadan Türkçe arama yalnızca Türkçe ya da özetlenmiş haberleri bulur.
- **Kaynaklar** — kaynakları açıp kapatın, güvenilirlik ağırlığı ve medya grubu verin (aynı gruptan kaynaklar tek
  kaynak sayılır), **Kaynak ekle** ile kendi RSS adresinizi deneyip ekleyin. RSS adresini bilmiyorsanız sitenin
  adresini yazın: program sitenin RSS bağlantılarını ve izin verilen haber site haritalarını önerir. Çalışmayan
  akışlar kırmızıyla ve nedeniyle görünür.
- **Ayarlar** — tema (sistem / açık / koyu), arayüz dili, yapay zekâ, hikâye ve skor ayarları, ilgi profiliniz
  (anahtar kelime, kategori, bölge), ülkem, tam metin, saklama süresi, bildirimler ve sessiz saatler, yedekler,
  güncellemeler.

**Klavye kısayolları:** `J` / `K` sonraki / önceki, `Enter` ya da `O` aç, `T` toplantıya ekle, `/` arama.

## Telif ve abonelikler

World Signal kimsenin içeriğini yeniden yayımlamaz; yalnızca **sizin** ekranınızda gösterir.

- Haberler yayıncıların herkese açık RSS akışlarından gelir: başlık, kısa özet ve bağlantı. RSS vermeyen birkaç kaynak
  için Bing Haberler'in herkese açık RSS araması kullanılır; bağlantılar doğrudan yayıncıya gider. Reuters ve AP'nin
  kendi siteleri otomatik okuyuculara kapalı olduğu için bu ajanslar bölüm bölüm Bing aramasıyla izlenir.
- RSS'i olmayan bazı siteler, arama motorları için yayımladıkları **haber site haritasından** okunur; bu yalnızca
  sitenin robots.txt dosyası otomatik okuyuculara izin veriyorsa yapılır.
- **Ücretli siteler:** Bir makalenin tamamını ancak **sizin** o sitede aboneliğiniz varsa okuyabilirsiniz. Bunun için
  **Kaynaklar → Abonelik siteleri**'nden siteyi açıp kendi hesabınızla bir kez giriş yaparsınız; oturum
  yalnızca bu bilgisayarda, World Signal'e ait ayrı bir tarayıcı profilinde saklanır. Aboneliğiniz yoksa o sitenin
  yalnızca başlığını, kısa özetini ve bağlantısını görürsünüz.
- Program abonelik duvarlarını aşmaz, robot doğrulamalarını (CAPTCHA) çözmez, arşiv/paywall atlatma sitelerini
  kullanmaz. Sayfaları insan temposunda açar: aynı anda tek sayfa, site başına saatte birkaç sayfa. Abonelik
  sitelerinde (tarayıcıyla okunanlar) daha da yavaş: aynı siteden iki sayfa arasında en az 20 dakika (sizin
  istediğiniz sayfalarda 3 dakika), site başına günde en çok 15 sayfa, gece 00:00–07:00 arası kendiliğinden sayfa
  açılmaz, her sayfa açıldıktan sonra 20–60 saniye okunup aşağı kaydırılır. Bunlar Ayarlar → Tam metin'den
  değiştirilebilir.
- **Tam metinler hiçbir çıktıya konmaz.** Kopyalama, yazdırma, PDF ve e-posta yalnızca özetleri, kaynak adlarını ve
  bağlantıları içerir.
- Bir [bulut yapay zekâ](#bulut-yapay-zekâ) hizmeti seçerseniz, özetlenmek üzere o hizmete gönderilen metinlerin
  (tam metinler dahil) sorumluluğu size aittir.
- Kendi eklediğiniz akışlar (örneğin kurumunuzun abone olduğu bir ajansın özel RSS adresi) yalnızca sizin
  veritabanınızda durur; hiçbir yere gönderilmez ve bu depoda yer almaz.

## Gizlilik ve güvenlik

Program yalnızca şu adreslerle konuşur:

- haber kaynaklarının RSS akışları ve (tam metin istediğinizde) makale sayfaları;
- Ollama'nın adresi (varsayılan olarak bilgisayarınızın kendisi: `localhost`);
- **yalnızca siz seçerseniz** bir bulut yapay zekâ hizmeti (Google Gemini, OpenAI uyumlu bir hizmet ya da Anthropic
  Claude): özetlenecek haber metinleri (tam metinler dahil) ve çevrilecek arama kelimeleriniz;
- GitHub, yalnızca yeni sürüm bilgisi ve indirme için (kapatılabilir).

Kullanım verisi, istatistik ya da kişisel bilgi toplanmaz ve gönderilmez. Programın arayüzü yalnızca bu bilgisayardan
(`127.0.0.1`) ve her açılışta değişen gizli bir anahtarla erişilebilen yerel bir sunucudur. Veritabanı, notlar,
tarayıcı profili ve oturum çerezleri yalnızca `%LOCALAPPDATA%\WorldSignal` altında durur. Bulut hizmeti API anahtarları
aynı klasörde, Windows'un kullanıcı hesabınıza bağlı şifrelemesiyle (`secrets.json`, DPAPI) saklanır; yedeklere girmez.

## Sorun giderme

| Durum | Ne yapmalı |
|---|---|
| Program açılmıyor | Bir uyarı penceresi nedenini ve günlük dosyasının yerini gösterir: `%LOCALAPPDATA%\WorldSignal\logs\worldsignal.log`. |
| "Failed to resolve Python.Runtime.Loader.Initialize" | 0.11.2'den eski bir sürüm internetten indirilen zip'ten açılıyor. En yeni sürümü indirin; ya da zip'e sağ tıklayıp **Özellikler → Engellemeyi kaldır**'ı işaretleyip yeniden ayıklayın. |
| İkinci kez çift tıklayınca bir şey olmuyor | Program zaten açık (tepside); var olan pencere öne gelir. Tamamen kapatmak için tepsi simgesine sağ tıklayın → **Çıkış**. |
| Başlıklar ve özetler kendi dilimde değil | Başlık ve özetleri yapay zekâ yazar (Ollama ya da bir bulut hizmeti). Hiçbiri yoksa haberler orijinal dillerinde görünür (bkz. [Yapay zekâ](#yapay-zekâ-isteğe-bağlı)). Dilinizin **Özet dilleri**'nde seçili olduğunu da denetleyin. |
| "Özetler hazırlanamıyor: Ollama hizmetine ulaşılamıyor" | Ollama kapalı ya da kurulu değil. Açın, bir bulut hizmeti seçin ya da Ayarlar → Yapay zekâ'dan özetlemeyi kapatın. |
| "API anahtarı kabul edilmedi" / "istek sınırı doldu" | Anahtar geçersiz ya da süresi dolmuş: Ayarlar → Yapay zekâ'dan yenisini girin. İstek sınırında program bekleyip devam eder; sık oluyorsa **Dakikada en çok istek** değerini düşürün. |
| Özetler çok yavaş, ekran kartı ısınıyor | Daha küçük bir model seçin (bkz. [tablo](#yapay-zekâ-isteğe-bağlı)). |
| Bir kaynak kırmızı görünüyor | Kaynaklar ekranında nedeni yazar (site kapalı, adres değişmiş, otomatik okuyuculara kapalı…). |
| Tam metin "abonelik duvarı" diyor | O siteye Kaynaklar → Abonelik siteleri'nden giriş yapın; aboneliğiniz yoksa tam metin alınamaz. |
| "Güncelleme yapılamadı" | Program klasöründe bir dosya açıktı; bir sonraki denemede yeniden yapılır. Olmazsa yeni zip'i indirip ayıklayın. |
| Bir şey ters gitti | Ayarlar → **Yedekler**'den önceki bir günün yedeğini geri yükleyin; program yeniden başlar. |

## Geliştirme

Yığın: Python 3.12 (FastAPI, SQLite + FTS5, feedparser, trafilatura, patchright) · React 19 + TypeScript + Vite ·
pywebview/WebView2 · PyInstaller. Mimari ayrıntılar: [ARCHITECTURE.md](ARCHITECTURE.md); sürüm geçmişi:
[CHANGELOG.md](CHANGELOG.md); kaynak doğrulama raporu: [docs/KAYNAK_DOGRULAMA.md](docs/KAYNAK_DOGRULAMA.md).

Ülke verisi (`src/worldsignal/catalog/countries.json`): ülke adları [Wikidata](https://www.wikidata.org)'dan (CC0),
kara komşulukları [GeoNames](https://www.geonames.org)'ten (CC BY 4.0) alınmıştır.

```
uv sync --python 3.12                        # Python ortamı
cd frontend && npm ci && npm run build       # arayüzü derle
.venv\Scripts\python -m worldsignal          # pencereyle çalıştır
.venv\Scripts\python -m pytest               # arka uç ve uçtan uca testler
cd frontend && npm test                      # arayüz testleri
.venv\Scripts\python tools\verify_catalog.py # kaynak kataloğunu yeniden doğrula
```

Kaynak kataloğu `tools/catalog_candidates.json`'da düzenlenir; `tools/verify_catalog.py` her akışı gerçekten dener ve
`src/worldsignal/catalog/sources.json`'u yazar (bu dosya elle düzenlenmez).

**Sürüm yayınlamak** (proje sahibi):

1. Sürüm numarasını artırın (`pyproject.toml`, `src/worldsignal/__init__.py`, `frontend/package.json`) ve o
   sürümün bölümünü hem `CHANGELOG.md`'ye (Türkçe) hem `CHANGELOG.en.md`'ye (İngilizce) yazın; ikisi birlikte
   GitHub'daki sürüm notu olur (program "Yenilikler"de arayüz dilindekini gösterir). Biri eksikse paket hazırlanmaz.
2. `scripts\clean-build-release.bat`: temizler, bütün testleri çalıştırır, kaynak yedeği alır, programı derler ve
   `release\<sürüm>\` altında zip + `.sha256` + notları hazırlayıp denetler (eksik parça ya da kullanıcı verisi varsa
   durur).
3. `scripts\publish.bat`: kaynak kodu kişisel veri için tarar, depoya gönderir, `v<sürüm>` etiketiyle GitHub sürümünü
   oluşturur. Kurulu bütün World Signal'ler bu sürümü bir sonraki denetimde görür. Önce denemek için:
   `scripts\publish.bat --dry-run`.
