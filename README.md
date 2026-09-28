# World Signal

**Dünya gündemini tek ekranda toplayan, aynı olayı anlatan haberleri birleştiren, önem sırasına dizen ve Türkçe
özetleyen bir Windows masaüstü programı.**

Haber merkezlerinde sabah toplantısına hazırlanmak için yapıldı: yüzlerce kaynağın RSS akışlarını gün boyu tarar,
aynı olayı anlatan haberleri tek bir "hikâye" kartında toplar ("9 kaynakta geçiyor"), hikâyeleri önem sırasına koyar
ve isterseniz bilgisayarınızdaki yapay zekâyla Türkçe (ve İngilizce) başlık ve özet yazar. Toplantı listesi, not
defteri, geçmiş günler ve yazdırılabilir çıktılar da içindedir.

> *English: World Signal is a Windows desktop app that collects news from hundreds of RSS feeds, merges reports of
> the same event into one story, ranks stories by importance and — with a local AI model (Ollama) — writes Turkish and
> English headlines and summaries. The interface is available in Turkish and English. Everything runs on your own
> computer; see [Privacy](#gizlilik-ve-güvenlik) and [Copyright](#telif-ve-abonelikler).*

---

## İçindekiler

- [Neler yapar?](#neler-yapar)
- [Kurulum](#kurulum)
- [Güncellemeler](#güncellemeler)
- [Yapay zekâ (isteğe bağlı)](#yapay-zekâ-isteğe-bağlı)
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
| **Türkçe özet** | Bilgisayarınızda Ollama varsa: Türkçe ve İngilizce başlık, 3–5 cümlelik özet, kategori, "neden önemli". Yalnızca kaynak metne dayanır; orijinal başlık ve bağlantı her zaman bir tık uzakta. |
| **Toplantı ve notlar** | Tek tuşla toplantı listesine ekleme, sürükleyerek sıralama, hikâyeye not, günlere göre not defteri. |
| **Çıktılar** | Toplantı listesi, haber detayı, sabah bülteni ve notlar: biçimli kopyala (Word/Outlook), düz metin (WhatsApp), yazdır/PDF, **e-postayla gönder**. |
| **Geçmiş** | Takvimden bir gün seçip o sabahki sıralamayı görme, tüm günlerde arama, bir hikâyenin gün gün gelişimi. |
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
4. Masaüstüne kısayol: `WorldSignal.exe`'ye sağ tıklayın → **Daha fazla seçenek göster → Gönder → Masaüstü (kısayol oluştur)**.

İlk açılışta kaynaklar hemen taranır; haberler birkaç saniyede, hikâyeler birkaç dakikada dolar.

**Verileriniz** (veritabanı, notlar, ayarlar, yedekler, günlükler) program klasöründe değil, her zaman şurada durur:
`%LOCALAPPDATA%\WorldSignal` (Ayarlar → Veri → **Klasörü aç**). Program klasörünü silmek ya da güncellemek verilerinize
dokunmaz. Veritabanı her gün kendiliğinden yedeklenir.

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
Aşağıdaki iki özellik bilgisayarınızda [Ollama](https://ollama.com) ister. Ollama ücretsizdir, kurulumu yönetici izni
gerektirmez ve **her şey bilgisayarınızda çalışır; hiçbir metin dışarı gönderilmez.**

| Özellik | Gereken model | Donanım |
|---|---|---|
| **Hikâye birleştirme** (aynı olayı anlatan haberleri bulmak) | `bge-m3` (1,2 GB) | Ekran kartı gerekmez; işlemcide çalışır. Çoğu bilgisayar için uygundur. |
| **Türkçe başlık ve özet** | Bir dil modeli (aşağıda) | Güçlü bir ekran kartı önerilir. |

Kurulum:

1. [ollama.com/download](https://ollama.com/download) adresinden Ollama'yı kurun.
2. Komut İstemi'ni açıp hikâye birleştirme modelini indirin:
   ```
   ollama pull bge-m3
   ```
3. Ekran kartınız yetiyorsa bir dil modeli de indirin ve World Signal'de **Ayarlar → Yapay zekâ → Model**'den seçin:

   | Ekran kartı belleği | Önerilen model | Not |
   |---|---|---|
   | 16 GB ve üstü | Gemma 4 26B-A4B | En iyi Türkçe; testlerde seçilen model |
   | 8–12 GB | `gemma4:12b` ya da `qwen3.5:9b` | İyi Türkçe, daha hızlı |
   | 6–8 GB | `gemma4` (8B) | Kabul edilebilir; kısa özetler |
   | Ayrı ekran kartı yok | — | **Ayarlar → Yapay zekâ**'dan özetlemeyi kapatın; hikâye birleştirme yine çalışır |

   Model karşılaştırması gerçek haberlerle yapıldı (bkz. `tools/benchmark_models.py`).
4. Ollama başka bir bilgisayarda çalışıyorsa **Ayarlar → Yapay zekâ → Ollama adresi**'ne o adresi yazabilirsiniz.

Ollama kapalıysa ya da model yoksa program çökmez: ekranın üstünde nedenini söyleyen bir uyarı çıkar ve haberler
orijinal dillerinde gösterilir. Özetlerin sağlamlığı için özetteki sayılar kaynakla karşılaştırılır; kaynakta geçmeyen
bir sayı varsa "Dikkat" uyarısı gösterilir.

## Kullanım

- **Akış** — *Hikâyeler* görünümü aynı olayın haberlerini tek kartta, önem sırasıyla gösterir; kartın altındaki
  etiketler nedenini söyler ("5 kaynak", "3 saatte 4 kaynak", "Türkiye bağlantısı"). *Haberler* görünümü tek tek en
  yeni haberlerdir. Üstte arama, zaman aralığı ve filtreler var (bölge, kaynak grubu, dil, kategori, kaynak,
  "Türkiye bağlantılı"). **Seçtiğiniz filtreler hatırlanır.**
- **Ülkem** — "Türkiye bağlantılı" filtresi ve etiketleri Ayarlar → **Ülkem**'de seçtiğiniz ülkeye göre çalışır
  (varsayılan: Windows'un bölge ayarı). Haber, yapay zekâ onu okuduktan sonra değerlendirilir: ülkeniz haberde
  geçiyorsa *doğrudan*, bir komşunuz, seçtiğiniz yakın ülkeler ya da konular geçiyorsa *dolaylı* bağlantılıdır.
- **Hikâye ayrıntısı** — Türkçe özet, skorun dökümü, günlere göre gelişim, tüm haberler ve bağlantıları, notlarınız.
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
  Çıktının dili (Türkçe/İngilizce) ayrıca seçilir. **Sabah bülteni** seçilen zaman aralığının en önemli hikâyelerini
  kategorilere göre dizer.
- **Geçmiş** — takvimden bir gün; *Sabah 09:00* o sabahki sıralamayı, *Günün tamamı* gün sonundaki sıralamayı gösterir.
  Arama tüm günlerde çalışır; Türkçe karakter ve büyük/küçük harf ayırmaz.
- **Kaynaklar** — kaynakları açıp kapatın, güvenilirlik ağırlığı ve medya grubu verin (aynı gruptan kaynaklar tek
  kaynak sayılır), **Kaynak ekle** ile kendi RSS adresinizi deneyip ekleyin. Çalışmayan akışlar kırmızıyla ve nedeniyle
  görünür.
- **Ayarlar** — tema (sistem / açık / koyu), arayüz dili, yapay zekâ, hikâye ve skor ayarları, ilgi profiliniz
  (anahtar kelime, kategori, bölge), ülkem, tam metin, saklama süresi, bildirimler ve sessiz saatler, yedekler,
  güncellemeler.

**Klavye kısayolları:** `J` / `K` sonraki / önceki, `Enter` ya da `O` aç, `T` toplantıya ekle, `/` arama.

## Telif ve abonelikler

World Signal kimsenin içeriğini yeniden yayımlamaz; yalnızca **sizin** ekranınızda gösterir.

- Haberler yayıncıların herkese açık RSS akışlarından gelir: başlık, kısa özet ve bağlantı. RSS vermeyen birkaç kaynak
  için Bing Haberler'in herkese açık RSS araması kullanılır; bağlantılar doğrudan yayıncıya gider. Reuters ve AP'nin
  kendi siteleri otomatik okuyuculara kapalı olduğu için bu ajanslar bölüm bölüm Bing aramasıyla izlenir.
- **Ücretli siteler:** Bir makalenin tamamını ancak **sizin** o sitede aboneliğiniz varsa okuyabilirsiniz. Bunun için
  **Ayarlar → Tam metin → Abonelik siteleri**'nden siteyi açıp kendi hesabınızla bir kez giriş yaparsınız; oturum
  yalnızca bu bilgisayarda, World Signal'e ait ayrı bir tarayıcı profilinde saklanır. Aboneliğiniz yoksa o sitenin
  yalnızca başlığını, kısa özetini ve bağlantısını görürsünüz.
- Program abonelik duvarlarını aşmaz, robot doğrulamalarını (CAPTCHA) çözmez, arşiv/paywall atlatma sitelerini
  kullanmaz. Sayfaları insan temposunda açar (site başına saatte birkaç sayfa, aynı anda tek sayfa).
- **Tam metinler hiçbir çıktıya konmaz.** Kopyalama, yazdırma, PDF ve e-posta yalnızca Türkçe/İngilizce özetleri,
  kaynak adlarını ve bağlantıları içerir.
- Kendi eklediğiniz akışlar (örneğin kurumunuzun abone olduğu bir ajansın özel RSS adresi) yalnızca sizin
  veritabanınızda durur; hiçbir yere gönderilmez ve bu depoda yer almaz.

## Gizlilik ve güvenlik

Program yalnızca şu adreslerle konuşur:

- haber kaynaklarının RSS akışları ve (tam metin istediğinizde) makale sayfaları;
- Ollama'nın adresi (varsayılan olarak bilgisayarınızın kendisi: `localhost`);
- GitHub, yalnızca yeni sürüm bilgisi ve indirme için (kapatılabilir).

Kullanım verisi, istatistik ya da kişisel bilgi toplanmaz ve gönderilmez. Programın arayüzü yalnızca bu bilgisayardan
(`127.0.0.1`) ve her açılışta değişen gizli bir anahtarla erişilebilen yerel bir sunucudur. Veritabanı, notlar,
tarayıcı profili ve oturum çerezleri yalnızca `%LOCALAPPDATA%\WorldSignal` altında durur.

## Sorun giderme

| Durum | Ne yapmalı |
|---|---|
| Program açılmıyor | Bir uyarı penceresi nedenini ve günlük dosyasının yerini gösterir: `%LOCALAPPDATA%\WorldSignal\logs\worldsignal.log`. |
| İkinci kez çift tıklayınca bir şey olmuyor | Program zaten açık (tepside); var olan pencere öne gelir. Tamamen kapatmak için tepsi simgesine sağ tıklayın → **Çıkış**. |
| Başlıklar ve özetler Türkçe değil | Arayüz dili Türkçedir, ama haberlerin Türkçe başlık ve özetleri bilgisayarınızdaki yapay zekâ (Ollama) ile üretilir. Ollama yoksa haberler orijinal dillerinde görünür (bkz. [Yapay zekâ](#yapay-zekâ-isteğe-bağlı)). |
| "Özetler hazırlanamıyor: Ollama'ya ulaşılamıyor" | Ollama kapalı ya da kurulu değil. Açın ya da Ayarlar → Yapay zekâ'dan özetlemeyi kapatın. |
| Özetler çok yavaş, ekran kartı ısınıyor | Daha küçük bir model seçin (bkz. [tablo](#yapay-zekâ-isteğe-bağlı)). |
| Bir kaynak kırmızı görünüyor | Kaynaklar ekranında nedeni yazar (site kapalı, adres değişmiş, otomatik okuyuculara kapalı…). |
| Tam metin "abonelik duvarı" diyor | O siteye Ayarlar → Tam metin → Abonelik siteleri'nden giriş yapın; aboneliğiniz yoksa tam metin alınamaz. |
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

1. Sürüm numarasını artırın (`pyproject.toml`, `src/worldsignal/__init__.py`, `frontend/package.json`) ve
   `CHANGELOG.md`'ye o sürümün bölümünü yazın; bu metin GitHub'daki sürüm notu olur.
2. `scripts\clean-build-release.bat`: temizler, bütün testleri çalıştırır, kaynak yedeği alır, programı derler ve
   `release\<sürüm>\` altında zip + `.sha256` + notları hazırlayıp denetler (eksik parça ya da kullanıcı verisi varsa
   durur).
3. `scripts\publish.bat`: kaynak kodu kişisel veri için tarar, depoya gönderir, `v<sürüm>` etiketiyle GitHub sürümünü
   oluşturur. Kurulu bütün World Signal'ler bu sürümü bir sonraki denetimde görür. Önce denemek için:
   `scripts\publish.bat --dry-run`.
