# World Signal — Mimari

Bu belge programın nasıl kurulduğunu anlatır. Ürün tanımı ve kullanım için `README.md`'ye bakın.

## Genel görünüm

```
┌──────────────────────── World Signal süreci (tek program) ─────────────────────────┐
│                                                                                     │
│  Masaüstü penceresi (pywebview + WebView2)                                          │
│     └─ React arayüzü (frontend/dist, derlenmiş statik dosyalar)                     │
│            │  HTTP + oturum anahtarı (X-WorldSignal-Token)                          │
│            ▼                                                                        │
│  Yerel sunucu (FastAPI/uvicorn, yalnızca 127.0.0.1, rastgele port)                  │
│     ├─ api/app.py        → uç noktalar, girdi doğrulama, hata kodları               │
│     ├─ repo/*            → depo katmanı: tüm veri erişimi buradan                   │
│     ├─ collector/*       → arka plan RSS toplama (asyncio görevi)                   │
│     ├─ ai/*              → Ollama/bulut istemcileri, başlık/özet çalışanı           │
│     ├─ stories/*         → gömme, hikâye birleştirme, önem skoru (asyncio görevi)   │
│     └─ db/*              → SQLite bağlantısı, sürümlü göçler, yedek                 │
│                                                                                     │
│  Veri: %LOCALAPPDATA%\WorldSignal\  (worldsignal.db, backups\, logs\, webview\)     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Katmanlar: **toplama → işleme → depolama → sunum**. Arayüz veriye hiçbir zaman doğrudan erişmez;
her şey API'den geçer. API de SQL yazmaz; depo (repository) sınıflarını çağırır.

## Teknoloji yığını ve gerekçeleri

| Parça | Seçim | Neden |
|---|---|---|
| Arka uç | Python 3.12 | Haber işleme, RSS ve yapay zekâ kütüphaneleri en olgun burada. |
| Sunucu | FastAPI + uvicorn | Hafif; ileride "ortak mod"da aynı API ağa açılabilir. |
| Pencere | pywebview (WebView2) | Gerçek masaüstü penceresi; WebView2 Windows 10/11'de hazır gelir. |
| Arayüz | React 19 + TypeScript + Vite | Derlenmiş statik dosya olarak pakete girer; diğer bilgisayarlarda Node gerekmez. |
| Veritabanı | SQLite (WAL) + FTS5 | Kurulumsuz, tek dosya, hızlı tam metin arama. |
| RSS | httpx + feedparser | httpx ile koşullu indirme (ETag/Last-Modified), feedparser ile sağlam çözümleme. |
| Tam metin çıkarma | trafilatura | Sayfadan haber metnini (menü, reklam, yorum olmadan) ayıklar; çok dilli, olgun. |
| Tarayıcı otomasyonu | patchright (Playwright çatalı) | Kullanıcının kendi Brave/Chrome/Edge'ini açar; otomasyon izlerini (CDP `Runtime.enable` vb.) göstermez. Sahte parmak izi üretmez. |
| Test | pytest, Vitest, Playwright | Birim, entegrasyon ve gerçek tarayıcıda uçtan uca. |

Bilerek **kullanılmayanlar**: ORM (SQLAlchemy), göç aracı (Alembic), zamanlayıcı kütüphanesi,
vektör veritabanı, arayüz bileşen kütüphanesi, simge kütüphanesi. Hepsi bu ölçekte gereksiz karmaşıklık getirir.

## Klasör yapısı

```
src/worldsignal/
  __main__.py          Giriş noktası: tek kopya kilidi, sunucu iş parçacığı, pencere
  bootstrap.py         Bileşenleri birbirine bağlar (veritabanı, depolar, toplayıcı)
  paths.py             Veri klasörü ve paket içi kaynak yolları
  single_instance.py   İkinci kopya açılırsa ilkini öne getirir
  textnorm.py          Türkçe duyarlı arama normalleştirmesi
  api/app.py           HTTP uç noktaları
  collector/rss.py     Tek bir akışı indirme + çözümleme
  collector/service.py Arka planda sürekli toplama döngüsü
  ai/                  ollama.py (istemci), cloud.py (Gemini / OpenAI uyumlu / Anthropic istemcileri),
                       languages.py (özet dilleri), enrich.py + story.py (istemler), translate.py (tam metin
                       çevirisi), worker.py (YZ kuyruğu)
  apikeys.py           Bulut API anahtarları (DPAPI ile şifreli, veritabanı dışında)
  fulltext/            extract.py (sayfadan metin), fetch.py (indirme, tarayıcı oturumu), worker.py (tam metin kuyruğu)
  stories/             embedding.py (ne gömülür), score.py (önem skoru), worker.py (birleştirme)
  repo/                sources.py, articles.py, ai.py, stories.py, notebook.py, fulltext.py, history.py, settings.py
                       (depo katmanı)
  maintenance.py       Saklama politikası ve günlük yedek
  backup.py            Yedek alma, doğrulama, geri yükleme
  notify.py            Hızla yayılan hikâye bildirimleri
  tray.py, desktop.py  Sistem tepsisi (Win32/ctypes) ve pencere davranışı
packaging/             PyInstaller tanımı ve programın giriş noktası
  db/database.py       Bağlantı, işlem (transaction), göç, yedek
  db/migrations/       0001_initial.sql, 0002_… (sırayla uygulanır)
  catalog/sources.json Doğrulanmış kaynak kataloğu (araçla üretilir)
frontend/src/
  api/                 Tipler ve API istemcisi
  i18n/                tr.ts (ana sözlük), en.ts, çeviri yardımcıları
  pages/               Akış, Kaynaklar, Ayarlar ve diyaloglar
  components/          Ortak bileşenler (düğme, anahtar, diyalog, bildirim…)
  styles/app.css       Tasarım sistemi (açık/koyu tema değişkenleri)
tools/verify_catalog.py  Tüm RSS adreslerini gerçekten test edip kataloğu üretir
tools/benchmark_*.py     Sohbet ve gömme modeli karşılaştırmaları (gerçek haberlerle)
tests/                   Arka uç + uçtan uca testler
```

## Veritabanı

- **WAL modu**: arayüz okurken toplayıcı yazabilir.
- **İş parçacığı başına bir bağlantı**; her yazma `Database.transaction()` içinde, `BEGIN IMMEDIATE` ile.
  Yarıda kesilen işlem tamamen geri alınır.
- **Göçler**: `db/migrations/NNNN_ad.sql`. Sürüm `PRAGMA user_version` içinde tutulur. Her göç kendi
  işleminde uygulanır. Var olan bir veritabanı göç edilmeden önce `backups\` klasörüne tam yedeği alınır;
  "geri dönüş" yolu bu yedektir. Program kendinden yeni şemalı bir veritabanını açmayı reddeder.
- **Zaman**: tüm zamanlar UTC ISO-8601 metin (`2026-09-27T07:33:19Z`); metin olarak doğru sıralanır.
  Arayüz yerel saate çevirir.
- **Arama**: `articles_fts` (FTS5). SQLite'ın hazır büyük/küçük harf katlaması Türkçede yanlış çalıştığı için
  (`IRAK` ≠ `ırak`, test edildi) metin Python'da `fold_for_search` ile normalleştirilip indekslenir; arama
  sorgusuna da aynı işlem uygulanır. Kullanıcı girdisi FTS sözdizimine hiçbir zaman doğrudan geçmez.
- **Özetleme kapsamı** (0.13, `ai.depth`, göç 0011): "full" her haber ayrı; "stories" 2+ kaynaklı ve özeti
  başarısız olmamış hikâyelerin haberleri kuyruğa girmez (`AiRepository.enqueue_recent(covered_by_stories)`),
  hikâye özeti Ülkem bilgilerini (ülkeler, Türkiye, konular) raporla aynı alan tanımlarıyla çıkarır
  (`EnrichTask.fact_fields`), `country.py` kuralları hikâyeyi derecelendirir (`stories.ai_home_relevance`),
  skor üyelerin ve hikâyenin derecesinin yükseğini alır; bilgisiz eski özetler yeniden yazılır (`need_facts`).
  "fast" ayrıca tek kaynaklıları `BATCH_SIZE` (10) haberlik tek istekte, özetsiz işler (`article_ai.brief = 1`);
  kullanıcı "Özetle" deyince tam özet yazılır. Ölçüm (gemma4-26b-a4b, gerçek haber): tek tek ~8 sn, toplu ~3,3 sn
  / haber, 30/30 kullanılabilir.
- **Yedekler ve yer** (0.13): yedek = SQLite yedekleme API'siyle tutarlı kopya, vektörler silinip VACUUM, zip
  (`db.database.write_backup`; 80 MB → ~15 MB); eski `.db` yedekler okunur. Vektörler float16 (göç 0010, `dtype`)
  ve 4 gün tutulur; boş sayfalar dosyanın %20'sini ve 16 MB'ı aşınca bakım VACUUM yapar.
- **Özel haber / makale grupları** (0.13): kaynak kataloğunda grup değil, haberin kendisinden okunur
  (`flags.article_kind`: başlıktaki "Exclusive"/"Özel haber" işareti; adreste yayıncının görüş bölümü ya da başlıkta
  "Opinion:" etiketi). Veritabanında saklanmaz; bağlantı açılırken SQLite'a `ws_kind(title, url)` işlevi olarak
  kaydedilir ve akış filtresi (`flags.group_condition`) katalog gruplarıyla VEYA'lanır — kural değişince eski
  haberler de hemen yeni kurala uyar. Ölçüm: 24 saatlik süzme 0,03 sn (haber) / 0,2 sn (hikâye).
- **Ülkem kapalı** (0.13.1, `home.enabled`): skor (`weights_from`: ülke ağırlığı 0), filtre ve rozetler gizli;
  YZ'de `EnrichTask.facts = False` istemden ve şemadan ülke/konu sorularını çıkarır (hikâye özeti dahil),
  `need_facts` özet yeniden yazdırmaz. `home.labels` ayrı: kapalıyken `HomeSync.sync` derecelendirmeyi yenilemez
  (açılınca ülke değişmişse yenilenir).
- **Akışta tam metin** (0.13.1): `ArticleRepository.list` `article_fulltext`'i birleştirir (`fulltext_status/error/chars/
  translate_status`), hikâye kartı `representative` üyesinin aynı alanlarını kullanır; arayüzde `CardFullText`
  (`components/FullText.tsx`) durumu kartta tutar ve bekleyen metni 4 sn'de bir sorar. `fulltext.translate` (varsayılan
  kapalı): açıkken tam metin işçisi metni kaydedince `request_translation` ile çeviriyi kuyruğa alır ve YZ işçisini
  uyandırır (YZ kapalıysa kuyruğa almaz).
- **Bölge filtresi "Yerel dışı"** (0.13.1, `repo.sources.region_condition`): kaynağın bölgesi yerel bölge
  (`HOME_REGION = "turkey"`) olmayan her haber; kaynağın bölgesine bakar, haberin konusuna değil. `meta.home_region`
  yalnızca ülkesi TR olanlarda dolu, arayüz seçeneği ona göre gösterir. "Küresel" bölgesi (dört ajans) filtreden çıktı,
  kaynak bölgesi olarak durur; ajanslar Kaynak grubu → Ajanslar ile süzülür.
- **Çalışma saatleri** (0.13.1, `worktime.py`, `work.limited/start/end`, varsayılan sürekli): `WorkHours.resting()`
  toplayıcıya, YZ işçisine ve tam metin işçisine verilir. Dinlenirken toplayıcı döngüyü atlar ("Şimdi tara" bir kez
  aşar), YZ yalnızca kullanıcının istediği işleri (`next_jobs(requested_only=True)`, elle hikâye özeti, çeviri) yapar,
  tam metin yalnızca `reason = 'user'` işleri okur. Hikâye işçisi ve bakım dinlenmez.
- **Engel bekleme süresi** (0.13.1, `repo.fulltext.store_failure`): bot doğrulaması ve 401/403/429'da site
  beklemeye alınır; aynı engel `ESCALATE_WINDOW` (3 gün) içinde tekrarlanırsa süre her seferinde ikiye katlanır
  (`MAX_PAUSE` 72 sa).
- **Bozuk karakter onarımı** (0.13.1, `textnorm.repair_mojibake`): UTF-8'in Windows-1252 okunmasından doğan
  "Ã/Ä/Å + devam karakteri" örüntüsü, yalnızca temiz biçimde geri çözülüyorsa düzeltilir (`strip_html` içinde, yani
  başlık/özet/yazar okunurken); kayıtlı haberler bakımda bir kez onarılır (`HistoryRepository.repair_mojibake`, ayar
  `repair.mojibake`).
- **İstatistik** (0.12, `repo/stats.py`, `GET /api/stats`, `GET /api/stats/topic`): istek anında SQL ile sayılır,
  saklanmaz (30 günlük dönem ~20.000 haberde ~0,25 sn). Dönemler yerel saate hizalı; önceki dönem eşit uzunlukta
  (süren gün yarım günle kıyaslanır) ve toplamanın başladığı andan (`MIN(first_seen_at)`) eskiyse karşılaştırma
  kapatılır. Bağımsız kaynak = skordaki gibi medya grubu. Haberin kategorisi: kendi YZ kategorisi, yoksa hikâyesininki.
  Grafikler kütüphanesiz SVG (`components/charts.tsx`), tek renk `--chart-1`, her grafiğin tablo karşılığı var.
- **Başka dillerde arama** (0.12): çoğu haber hiç özetlenmediği için Türkçe kelime yabancı haberi bulamıyordu.
  Arayüz `GET /api/search/translations?q=` ile arama kelimelerini seçili YZ hizmetine (`AiWorker.expand_query`,
  `ai/query.py`) etkin kaynakların dillerine (en çok 8) çevirtir; listeler çevirileri `qx` olarak alır ve
  `build_fts_query` her ifadeyi ayrı bir `AND` grubu yapıp `OR` ile bağlar. Yazılan kelimeler hemen aranır, çeviri
  gelince liste genişler. Yanıtlar oturum boyunca bellekte tutulur. bge-m3 ile anlamsal arama ölçülüp elendi: kısa
  Türkçe sorgularda aynı dildeki başlıkları öne çıkarıyor, yabancı haberi bulmuyordu.

### Tablolar (şema v1)

- `sources`: haber kuruluşu (ad, grup, **medya grubu/sahip**, bölge, dil, güvenilirlik 0–2, ücretli mi, köken: katalog/kullanıcı).
- `feeds`: bir kaynağın RSS akışları (aralık, ETag/Last-Modified, son durum, hata kodu, ardışık hata sayısı).
- `articles`: haberler. `(source_id, dedupe_key)` benzersiz; `dedupe_key` izleme parametreleri temizlenmiş bağlantıdır.
  `published_at`: akışın bildirdiği ham zaman. `sort_at`: gerçek zamanın en iyi tahmini:
  - Bazı siteler yerel saati UTC diye bildiriyor (ör. CNN Türk, Jerusalem Post: +3 sa). Bir akışta en az iki haber
    gelecekte görünüyorsa kayma tam saat olarak hesaplanır ve o akışın tüm haberlerine uygulanır (`timezone_correction`).
  - Düzeltmeden sonra hâlâ gelecekteyse ya da tarih yoksa: ilk görülme zamanı.
- `articles_fts`: arama indeksi.
- `settings`: anahtar/JSON değer.
- `article_ai` (şema v2): haber başına YZ kuyruğu + sonucu (başlık/özet, kategori, bulunan ülkeler ve konular,
  `mentions_turkey`, uyarılar). Eski `turkey_relevance/turkey_links` sütunları 0.9'dan beri okunmaz.
  Şema v9'dan beri metinler dile göre tek JSON sütununda: `article_ai.texts` = `{"tr": {"title", "summary"}, "pt": …}`;
  aynı biçim `stories.ai_texts` ve `meeting_items.texts` (`{dil: {title, summary, why}}`) ile
  `article_fulltext.translations` (`{dil: metin}`) için de geçerli. Eski `*_tr/*_en` sütunları göçte JSON'a
  kopyalandı; artık okunmaz (SQLite'ta sütun silmek tabloyu yeniden kurmayı gerektirir).
- `articles.home_relevance / home_links` (şema v8): haberin **kullanıcının ülkesiyle** bağlantısı (aşağıda "Ülkem").
- `article_ai_fts`: YZ metinleri için arama indeksi (tüm dillerin başlık/özetleri tek satırda).
- `article_embeddings` (şema v3): haber başına gömme vektörü (float32 blob) ve hangi modelle üretildiği.
- `stories`: hikâye (olay). Skor, skor parçaları + gerekçe etiketleri (JSON), ülke bağlantısı (sütun adı tarihsel
  olarak `turkey_relevance`), kategori, temsilci
  haber, hikâye YZ özeti ve kuyruk durumu.
- `story_articles`: haber → hikâye (her haber tek hikâyede). `assigned_by` = `auto` | `user`; kullanıcının yerleştirdiği
  haberi program bir daha taşımaz.
- `story_notes` (şema v4): hikâye başına bir not; `day` = notun başlandığı yerel gün (defterde dosyalandığı yer).
- `meeting_items`: günün toplantı listesi (`day`, `position`, kullanıcının kısa gerekçesi).
- `day_notes`: güne ait serbest not.
  Hikâyeye bağlanan kayıtlar hikâyenin başlığının (ve toplantı öğelerinde özet, gerekçe, kaynak bağlantılarının) bir
  kopyasını saklar; hikâye silinirse bağlantı `NULL` olur ama geçmiş günün defteri okunur kalır. İki hikâye birleşince
  notlar ve toplantı öğeleri aynı işlem içinde hayatta kalan hikâyeye taşınır (`repo/notebook.py: reassign_story`).

## Haber toplama

- Her akış kendi aralığıyla (varsayılan 15 dk, 5–1440) taranır; ±60 sn rastgele kaydırma ile yük yayılır.
- Aynı anda en fazla 6 istek, **aynı siteye aynı anda tek istek**.
- Dürüst kimlik: `User-Agent: Mozilla/5.0 (compatible; WorldSignal/x.y; RSS reader)`. Engel (403) veren siteler
  aşılmaya çalışılmaz; hata arayüzde görünür.
- Hatalı akış giderek seyrekleşen aralıklarla (×1, ×2, ×4, ×8) yeniden denenir.
- Bir turdaki tüm istekler ağ hatasıyla düşerse bilgisayar çevrimdışı kabul edilir: akışlar cezalandırılmaz,
  arayüzde "çevrimdışı" gösterilir, 2 dk sonra yeniden denenir.

## Yapay zekâ (Ollama ya da bulut)

```
articles ──(son 24 sa, otomatik)──► article_ai [pending] ──► AiWorker ──► Ollama /api/chat ya da bulut (JSON şema)
                      ▲                                           │
  "Türkçeleştir" (öne alır)                                       ▼
                                          validate + uydurma denetimi ──► article_ai [done] + article_ai_fts
```

- `ai/ollama.py`: istemci. Hatalar koda çevrilir: `unreachable`, `model_missing`, `timeout`, `bad_response`, `http_<n>`.
- **Özet dilleri** (0.11, `ai/languages.py`): `ai.languages` = 1–4 dil kodu (`OUTPUT_LANGUAGES`, 31 dil); `null` =
  arayüz dili + İngilizce. `EnrichTask(languages, topics, ask_turkey)` istemi ve düz JSON şemasını
  (`title_<dil>`, `summary_<dil>`…) bu dillere göre kurar; çıktı uzunluğu dil sayısıyla büyür. Dil eklenince eksik
  dili olan sonuçlar (`repo/ai.py: lacking_sql`) yeni işler bittikten sonra arka planda yeniden üretilir; başarısız
  olursa eski metin korunur. Arayüz her metni kendi dil kodunun yazı yönüyle (`dir`, Arapça/Farsça/İbranice sağdan
  sola) gösterir.
- **Sağlayıcı** (0.11, `ai.provider`): `ollama` (varsayılan) ya da kullanıcının kendi anahtarıyla `gemini`, `openai`
  (OpenAI uyumlu her hizmet; `ai.openai_url`, yerel LM Studio anahtarsız), `anthropic`. `ai/cloud.py` üç istemciyi
  Ollama istemcisiyle aynı arayüzde sunar (`chat_json`, `list_models`, aynı hata kodları); JSON şeması Gemini'de
  `responseSchema`, OpenAI'da `json_schema` (desteklemeyen hizmette `json_object`), Anthropic'te zorunlu araç çağrısıyla
  verilir. Ek hata kodları: `no_key`, `bad_key` (401/403), `rate_limited` (429) — bunlar hizmet hatasıdır, haber
  cezalandırılmaz, çalışan duraklar. İstekler `ai.cloud_rpm` ile seyreltilir (iş arası en az 60/rpm sn). Kibar mod
  (`gpu_busy`) yalnızca Ollama'da uygulanır. Hikâye birleştirme (gömme) her zaman Ollama'da kalır.
  **Karar (2026-09-28)**: bulut hizmetine her şey, abonelikle alınan tam metinler dahil, gönderilebilir; telif ve kullanım
  koşulları sorumluluğu kullanıcıdadır ve Ayarlar'da açıkça yazar.
- `ai/enrich.py`: istem (İngilizce talimat, seçili dillerde çıktı), JSON şeması, `PROMPT_VERSION`, doğrulama.
  - Kategoriler sabit listeden (`CATEGORIES`); arayüz çevirir.
  - **Ülke bağlantısını model değil kod belirler** ("Ülkem", `country.py`). Model yalnızca metinde olanı çıkarır:
    ülkeler (ISO kodu), Türkiye geçiyor mu, açıkça geçen konular (Karadeniz, Doğu Akdeniz, NATO, AB genişlemesi, göç,
    Türk devletleri). `HomeProfile.relevance()` sabit kurallarla karar verir: kullanıcının ülkesi listede ya da adı
    metinde geçiyorsa (Türkiye için eski çok dilli kelime listesi ve modelin "Türkiye geçiyor" cevabı) `direct`;
    listede kara komşusu, kullanıcının seçtiği yakın ülke ya da seçtiği konu varsa `indirect`; yoksa `none`. Gerekçe
    kodları (`home_mentioned`, `neighbour:GR`, `related:KZ`, `topic:nato`) saklanır ve arayüzde cümleye çevrilir.
    Neden: karşılaştırmada modeller Afganistan, İsrail ve Rusya'yı "komşu" saydı; istemde olumsuz liste vermek durumu kötüleştirdi.
  - **Ülkem** (0.9): ülke ayarı `home.country` ("" = Windows'un bölgesi, `GetUserDefaultGeoName`), `home.related`,
    `home.topics` (null = ülkenin varsayılanı; Türkiye için Türk devletleri ve altı konu, diğerleri için boş),
    `home.keywords`. Ülke adları (18 dil, Wikidata CC0) ve kara komşuları (GeoNames CC BY 4.0; Türkiye'ye Kıbrıs eklenir)
    `catalog/countries.json`'dadır; `tools/make_countries.py` üretir. Değerlendirme YZ sonucu kaydedilirken yapılır
    (`repo/articles.py: rate_home`) ve `articles.home_relevance`'a yazılır. Ayar değişince `home_sync.py` YZ'nin
    okuduğu tüm haberleri saklı bulgulardan yeniden değerlendirir (model yeniden çalışmaz) ve son 7 günün hikâyelerini
    yeniden puanlar; ne zaman gerektiğini `home.applied` anahtarı (`RULES_VERSION` dahil) belirler. Arayüz metinleri
    `{home}` yer tutucusuyla ülke adını alır.
  - **Uydurma denetimi** (`fidelity_issues`): çıktıdaki her sayı kaynak metinde de olmalı. Olmayan sayı çıktıyı reddetmez
    ama işaretler; arayüz kartta uyarı gösterir. (Model karşılaştırmasında qwen3:14b'nin uydurduğu tarihleri yakaladı.)
    Bilinen sınır: kaynakta yazıyla geçen sayı ("altı") çıktıda rakamla yazılırsa yanlış alarm verir.
- `repo/ai.py`: `article_ai` tablosu hem kuyruk (`pending`) hem önbellek (`done`). Öncelik = haberin zaman damgası
  (yeni haber önce); kullanıcı isteği her şeyin önüne geçer. Aynı haber otomatik olarak bir daha işlenmez.
  Otomatik kuyruğa yalnızca son `ai.max_age_hours` saatteki haberler girer; daha eskiler yalnızca istekle.
  3 başarısız denemeden sonra `failed`; "Yeniden dene" ile kuyruğa döner.
- `ai/worker.py`: sunucuyla birlikte başlayan asyncio görevi; **aynı anda tek iş** (tek GPU).
  - Ollama kapalı / model yok / zaman aşımı → haber cezalandırılmaz, çalışan duraklar, durum arayüzde görünür, 30 sn sonra
    ya da "Yeniden dene" ile tekrar dener.
  - **Kibar mod** (`ai.yield_gpu`, varsayılan açık): Ollama'da başka bir model yüklüyse (kullanıcının kendi işi) onu
    bellekten atmamak için bekler (`gpu_busy`). İşlemcide çalışan modeller (`size_vram` 0, ör. bizim bge-m3) sayılmaz.
  - Çıktı uzunluğu `num_predict` ile sınırlı; model döngüye girse bile GPU'yu tutamaz.
- Arama: YZ başlık/özetleri ayrı FTS indeksinde (`article_ai_fts`); arama hem orijinal hem YZ metinlerinde yapılır.
- Model seçimi `tools/benchmark_models.py` ile gerçek haberler üzerinde yapıldı; rapor `docs/MODEL_KARSILASTIRMA.md`.

## Hikâyeler ve önem skoru (Faz 3)

```
articles ─► StoryWorker: gömme (Ollama /api/embed, işlemcide) ─► article_embeddings
                  │
                  └─► çevrimiçi birleştirme ─► story_articles ─► skor ─► stories ─► AiWorker: hikâye özeti
```

- **Gömme**: `bge-m3` (çok dilli), yalnızca başlık. Model **işlemcide** çalışır (`num_gpu: 0`), sohbet modeliyle ekran
  kartı için yarışmaz. Karşılaştırma (3 model × 2 metin, 95 elle doğrulanmış gerçek haber, 7 dil):
  `docs/GOMME_KARSILASTIRMA.md`, araç `tools/benchmark_embeddings.py`, cevap anahtarı `tools/embedding_gold.json`.
- **Birleştirme** (`stories/worker.py: choose_story`): haberler zaman sırasıyla işlenir ve son 72 saatte bir hikâyeye
  girmiş haberlerle karşılaştırılır (kosinüs benzerliği). Yeni haber bir hikâyeye ancak iki koşulla katılır:
  1. hikâyede ona en az `stories.threshold` (0,55) benzeyen bir haber vardır (aynı olayın yakın bir haberi), **ve**
  2. hikâyenin tüm haberlerine ortalama benzerliği en az `stories.cohesion` (0,50)'dir.
  İkinci koşul **zincirlenmeyi** önler: yalnızca birinci koşulla A haberi B'ye, C de A'ya benzediği için alakasız
  olaylar tek hikâyede toplanıyordu (gerçek akışta 494 haberlik karışık "hikâye"). Ölçüm: gerçek veritabanındaki 6.919
  haber zaman sırasıyla yeniden oynatıldı (`tools/benchmark_clustering.py`, `docs/BIRLESTIRME_KARSILASTIRMA.md`).
  Koşul sağlanmazsa yeni hikâye açılır. Olay sürdükçe hikâye yeni haberleri almaya devam eder; böylece günlere yayılan
  olay tek hikâye zinciri olur. Eşikler modele göre değişir (benzerlik ölçekleri çok farklı); model değişince o modelin
  ölçülmüş değerlerine geçilir (`stories/embedding.py: RECOMMENDED`). Model değişirse eski vektörler silinip yeniden
  hesaplanır. Eşik değişikliği yeni gelen haberlere uygulanır.
- **Temsilci haber** (kartın başlığı, YZ özeti yokken): hikâyenin anlam merkezine en yakın haber
  (`repo/stories.py: pick_representative`); Türkçe YZ başlığı ve güvenilir kaynak küçük bir öncelik alır.
- **Elle düzeltme**: "Bu hikâyeden ayır" haberi kendi hikâyesine taşır; "Başka hikâyeyle birleştir" iki hikâyeyi
  birleştirir. İkisi de `assigned_by = 'user'` yazar; otomatik birleştirme bu haberlere dokunmaz.
- **Skor** (`stories/score.py`) = 100 × dört bileşenin ağırlıklı ortalaması (ağırlıklar ayarlardan):
  1. *Bağımsız kaynak*: aynı medya grubunun kaynakları tek sayılır; güvenilirlikle ağırlıklı, logaritmik (40 kaynak = tam). Bölge başına en fazla 6 bağımsız
     kaynak sayılır (en güvenilirleri; 0.13): kaynağı çok olan bir bölge — kullanıcının kendi basını — tabloyu tek
     başına dolduramaz. Ölçüm (gerçek akış, 24 saat): ilk 20'de çoğu Türk kaynaklı hikâye 11 → 4; en çok yabancı
     kaynakta geçen hikâyeler 28./36./53. sıradan 2./4./8. sıraya.
  2. *Tazelik ve yayılma*: son haberin yaşı (yarı ömür 8 sa) + son 3 saatteki bağımsız kaynak sayısı.
  3. *Ülke* (tarihsel adıyla `turkey`): doğrudan 1, dolaylı 0,5 (kural tabanlı karar, bkz. "Ülkem").
  4. *İlgi profili*: anahtar kelime (Türkçe harf duyarsız), kategori, bölge eşleşmeleri.
  Her bileşen bir gerekçe etiketi üretir ("5 kaynak", "3 saatte 4 kaynak", "Türkiye bağlantısı", "İlgi alanınız: enerji");
  ayrıntı penceresi bileşen × ağırlık dökümünü gösterir. Skorlar her 5 dakikada ve ayar değişince yeniden hesaplanır.
- **Rozetler** (`flags.py`, 0.9): *Özel* = başlığın başında yayıncının "Exclusive/Özel/Эксклюзив…" işareti;
  *Son dakika* = 60 dakikada en az 3 bağımsız sahipten haber ya da başlıkta "Son dakika/Breaking" işareti ve haber
  2 saatten yeni. İstek anında hesaplanır, saklanmaz.
- **Hikâye özeti** (`ai/story.py`): en az 2 bağımsız kaynaklı hikâyeler için, her kaynaktan bir haber (en çok 8) modele
  verilir; Türkçe başlık, 3–5 cümle özet, kategori ve "neden toplantıda" cümlesi üretilir. Aynı uydurma denetimi uygulanır.
  Hikâye işleri haber işlerinin önündedir (skor sırasıyla); hikâye %50 ve en az 2 haber büyüyünce özet yenilenir.
- **Uyandırma**: toplayıcı yeni haber kaydedince hikâye ve YZ çalışanlarını hemen uyandırır (`on_new_articles`).

## Not defteri, toplantı listesi ve çıktılar (Faz 4)

- **Gün**: her şey kullanıcının yerel takvim gününe göre dosyalanır (sunucu ve arayüz aynı bilgisayarda).
- **Toplantı listesi**: bugünün listesi hikâyeleri canlı izler (YZ özeti gelince, kaynaklar artınca güncellenir); geçmiş
  günlerin listesi o günkü haliyle kalır. Sıralama tek istekle yazılır (`PUT /api/meeting/order`, eksik/fazla kimlik reddedilir).
- **Otomatik kayıt** (`frontend/src/lib/autosave.ts`): yazma durduktan 0,7 sn sonra, alan kapanırken ve pencere kapanırken
  kaydedilir; başarısız kayıt metni ekranda tutar ve 5 sn'de bir yeniden dener. Sunucu kaydı onaylayana kadar metin
  ayrıca yerel taslak olarak (`localStorage`) tutulur; program sunucuya ulaşamadan kapanırsa taslak bir sonraki açılışta
  geri gelir ve kaydedilir.
- **Çıktılar** (`frontend/src/lib/outputs.ts`): dört şablon (toplantı önerileri, haber detayı, kategori başlıklı sabah
  bülteni, defterden seçilenler). Her biri satır içi stilli HTML (Word/Outlook'a biçimli yapıştırılır) ve düz metin
  (WhatsApp; başlıklar `*kalın*`) üretir. Kopyalama önce Clipboard API'yi, izin yoksa seçim + kopyala yolunu dener.
  Yazdırma, önizleme çerçevesinin tarayıcı yazdırmasıdır; Windows yazdırma penceresindeki "PDF olarak kaydet" PDF'i
  üretir (ek kütüphane yok). **Telif**: çıktılara yalnızca Türkçe YZ metni, başlık, kaynak adı ve bağlantı girer;
  yayıncının kendi özeti ya da tam metni asla girmez (testle korunur).

## İngilizce ve tam metin (Faz 5)

### Türkçe + İngilizce (0.11'de seçilebilir dillere genişledi)
- Haber istemi v5 ve hikâye istemi v2, tek çağrıda hem Türkçe hem İngilizce başlık/özet/gerekçe üretiyordu. 0.11'den beri
  diller kullanıcı seçimidir ve metinler dile göre JSON'da durur (bkz. "Özet dilleri"). Uydurma denetimi her dile
  uygulanır; FTS tüm dilleri indeksler.
- Eski (yalnızca Türkçe) sonuçlar, yeni işler bittikten sonra "yükseltme" işi olarak yeniden üretilir; yükseltme
  başarısız olursa Türkçe sonuç korunur (`Job.upgrade`, `store_upgrade_failure`).

### Tam metin
- **Karar (2026-09-27)**: proje kurallarındaki "stealth yok" kuralı, proje sahibinin açık izniyle bu proje için
  değiştirildi: amaç kendi aboneliklerini tek panelde okumak, veri madenciliği değil. Uygulanan biçim: **patchright** ile
  kullanıcının gerçek Brave'i (yoksa Chrome/Edge), gerçek kullanıcı profili; sahte parmak izi, sahte kimlik, paywall
  atlatma sitesi yok. **Değişmeyen sınırlar**: CAPTCHA/robot doğrulaması asla çözülmez (haber `blocked`, site 12 saat
  bekletilir); insan temposu (tek sekme, site başına saatte sınır, sayfalar arası rastgele bekleme); tam metin çıktılara
  girmez; Ollama kullanılırken hiçbir veri dışarı gönderilmez (bulut sağlayıcı seçilirse bkz. "Sağlayıcı").
- **Kaynak başına yöntem** (`sources.fulltext_mode`): `off` (yalnızca RSS), `http` (ücretsiz siteler; dürüst bir
  User-Agent'la sade indirme), `browser` (abonelik siteleri). Ücretli kaynaklar `off` başlar; kullanıcı abone olduklarını
  açar. Kullanıcı açıkça isterse `off` kaynak da bir kez denenir (ücretliyse tarayıcıyla).
- **Profil**: varsayılan, World Signal'e özel kalıcı profil (`%LOCALAPPDATA%\WorldSignal\browser-profile`); kullanıcı
  Ayarlar → **Oturum aç** ile açılan normal (otomasyonsuz) pencerede sitelerine bir kez girer. İsteğe bağlı "kendi
  profilim" modu, tarayıcı kapalıyken ana profili kullanır (açık profil kilitlidir; kopyalanan çerezler Chrome'un
  uygulamaya bağlı şifrelemesi yüzünden çözülemez — denendi). Pencere varsayılan olarak ekran dışında açılır; 5 dk boşta
  kalan tarayıcı kapatılır.
- **Kuyruk** (`article_fulltext`): öncelik kullanıcı isteği > not defteri/toplantı > otomatik (skoru ≥ 60 olan
  hikâyelerin en fazla 2 haberi). Hata kodları: `bot_check`, `paywall`, `http_N`, `not_article`, `timeout`, `network`,
  `profile_in_use`, `browser_failed`. `bot_check` ve `403/429` siteyi bekletir (`fulltext_paused_until`); Ayarlar'dan
  "Devam ettir" denebilir.
- **Çıkarma** (`fulltext/extract.py`): trafilatura; 400 karakterden kısa metin "vitrin" sayılır. Sayfa schema.org
  `wordCount` bildiriyorsa ve çıkarılan metin bunun yarısından azsa sonuç `paywall` olur (yalnızca ücretsiz kısmı
  gösterilmiş sayfa; gerçek Washington Post sayfasında görüldü).
- **YZ ile bağlantı**: tam metin gelince haberin YZ özeti tam metinle yeniden üretilir (istem kaynağı:
  `ft.text` varsa o, yoksa RSS özeti). Tam metnin özet dillerine çevirisi yalnızca istek üzerine yapılır
  (`ai/translate.py`: paragraf sınırında ~1800 karakterlik parçalar), YZ kuyruğunda en önce çalışır; haberin kendi
  diline çeviri yapılmaz.

## Geçmiş ve saklama (Faz 6)

- **Geçmiş bir günün sıralaması yeniden hesaplanır, saklanmaz** (`repo/history.py`). Bir hikâyenin T anındaki skoru,
  T'ye kadar yayımlanmış haberleriyle ve "şimdi" = T alınarak aynı skor fonksiyonuyla bulunur. Böylece özellik
  eklenmeden önceki günler de gösterilebilir, ek tablo gerekmez ve sonradan yapılan elle düzeltmeler (ayırma,
  birleştirme) geçmişe de yansır. YZ metinleri günceldir. Ölçüm: gerçek veritabanında bir gün 0,05–0,11 sn.
- **İki an**: *Sabah* = o gün `history.morning_hour` (varsayılan 09:00) itibarıyla, önceki 24 saat (akışın o sabahki
  hali); *Günün tamamı* = o takvim gününde yayımlananlar, gün sonundaki sırayla. İkisi de "şimdi"yi geçmez.
- Hikâye oluşturma başlamadan önce toplanmış günlerde hikâye yoktur; ekran bunu söyler ve günün tek tek haberlerini
  gösterir (`/api/articles?day=`).
- **Arama**: tüm günlerde hikâye ve haber araması (mevcut FTS5, Türkçe katlama), zaman sınırı olmadan.
- **Dönüm noktaları** (`/api/stories/{id}` → `milestones`): ilk haber; 3/5/10/20/40 bağımsız kaynağa ulaşma; ilk doğrudan
  ülke bağlantısı; arayüz dilindeki ilk kaynak (`own_language_source`, hikâye o dilde başlamadıysa); son haber.
- **Saklama** (`maintenance.py`, açılıştan 1 dk sonra ve 6 saatte bir): `retention.fulltext_days` (varsayılan 30; 0 =
  silme) günden eski haberlerin tam metni ve çevirisi silinir. Hikâye eşleştirme vektörleri yalnızca son 7 gün için
  tutulur (eşleştirme son 72 saate bakar; haber başına ~4 KB, yılda GB'lar tutardı). Başlık, özet, YZ metinleri,
  hikâyeler ve notlar hiçbir zaman silinmez.

## Kaynak kataloğu

`tools/catalog_candidates.json` → `tools/verify_catalog.py` → `src/worldsignal/catalog/sources.json` +
`docs/KAYNAK_DOGRULAMA.md`. Bir akış ancak indirilebiliyor, RSS/Atom olarak çözülebiliyor, en az 3 haber
içeriyor ve en yeni haberi 7 günden eski değilse "doğrulandı" sayılır. Doğrulanamayan kaynaklar kapalı gelir ve
arayüzde ayrı bölümde listelenir. Katalog her açılışta yalnızca **eksik** kaynakları ekler; kullanıcının
düzenlemelerine dokunmaz, sildiği katalog kaynağını geri getirmez. İki istisna (0.7.3): `retired_feeds` listesindeki
ölü adresler katalog kaynaklarından silinir; hiç çalışan akışı olmayan (kapalı gelmiş) bir katalog kaynağı, katalog
ona doğrulanmış bir akış getirince açılır.

**Toplayıcı akışlar**: RSS vermeyen ya da otomatik okuyuculara kapalı siteler için Bing Haberler'in herkese açık RSS
araması kullanılır (`https://www.bing.com/news/search?q=site:<alan>&format=rss&qft=sortbydate="1"`). Bing her haberi
`bing.com/news/apiclick.aspx?url=<yayıncı adresi>` olarak sarar; `collector/rss.py: unwrap_aggregator_link` yayıncı
adresini saklar, böylece bağlantı, yinelenen haber ayıklama ve tam metin doğrudan yayıncıda çalışır. Google News
(0.7.2'ye kadar) terk edildi: Google News makale bağlantıları yayıncı adresini içermez, çözmek Google'ın iç uç noktasını
ister ve şirket ağından bu istek robot doğrulamasına düşüyor (bağlantılar tarayıcıda "geçersiz adres" hatası veriyordu).
Önceden toplanmış Google bağlantıları arayüzde başlık aramasına çevrilerek açılır (`frontend/src/lib/links.ts`);
tam metin onları hiç açmaz (`aggregator_link`).

Bing'in `pubDate`'i ABD Pasifik yerel saatidir ama "GMT" diye yazılır; `bing_time_to_utc` yaz/kış saatiyle (+7/+8 sa)
düzeltir. Bing tek aramada ~12 haber verdiği için büyük ajanslar (Reuters 18, AP 16 arama) bölüm bölüm aranır;
aynı haber birkaç aramada çıkarsa yayıncı adresine göre tek kayıt olur.

**Haber site haritaları** (0.10, `collector/sitemap.py`): `fetch_feed` indirdiği dosya `<urlset>`/`<sitemapindex>` ise
onu Google News site haritası olarak okur (`news:title`, `news:publication_date`, `news:language`). Önce robots.txt
sorulur (`Robots`, site başına 24 saat önbellek, ürün adı `WorldSignal`; RFC 9309: 4xx = izin, 5xx/ağ hatası = izin
yok) ve izin yoksa `robots_disallow` hatası verilir. Dizin dosyasında adında "news" geçen (yoksa en yeni) en çok iki
alt harita okunur. Başlıksız düz haritalar `sitemap_no_titles` ile reddedilir. Veritabanında ayrı bir akış türü
yoktur: tür, dosyanın içeriğinden anlaşılır. `POST /api/feeds/test` bir web sayfasıyla karşılaşınca (`not_a_feed`)
`discover` ile sayfadaki `<link rel="alternate">` akışlarını ve robots.txt'deki izinli haber haritalarını önerir.

## Güvenlik

- Sunucu yalnızca `127.0.0.1`'de dinler. Her açılışta rastgele port ve rastgele oturum anahtarı üretilir.
- Anahtar pencereye adres parametresiyle verilir; arayüz onu hemen adres çubuğundan silip oturum belleğine alır.
  Anahtarsız istek `401` alır. Böylece bilgisayarda açık bir web sayfası bu sunucuya istek atamaz.
- Tek kopya kilidi (`instance.lock`, işletim sistemi düzeyinde): iki kopyanın aynı veritabanına yazması engellenir.
  Program çökerse kilit kendiliğinden kalkar.
- **Bulut API anahtarları** (`apikeys.py`): `<veri>/secrets.json`, her anahtar Windows DPAPI (`CryptProtectData`,
  kullanıcı hesabına bağlı) ile şifreli; atomik yazılır. Veritabanında değildir, bu yüzden yedeklere girmez. API yalnızca
  yazılabilir: `GET /api/ai/keys` hangi hizmette anahtar olduğunu söyler, anahtarın kendisini asla döndürmez; anahtar
  günlüklere yazılmaz. Anahtar yalnızca ilgili hizmetin kendi adresine, başlıkta gönderilir.

## Çok dillilik (arayüz)

- `frontend/src/i18n/tr.ts` ana sözlüktür. Diğer diller (`en.ts`) aynı anahtarların tamamını tanımlamak
  zorundadır; eksik ya da fazla anahtar **derleme hatasıdır**. Testler yer tutucuların (`{count}`) dillerde aynı
  olduğunu da denetler.
- Sunucu metin döndürmez, **hata kodu** döndürür (`feed_exists`, `http_403`…); arayüz bunları çevirir.
- Yeni dil eklemek: `i18n/xx.ts` oluştur, `DICTIONARIES`'e ekle, sunucudaki `SUPPORTED_LANGUAGES`'e ekle.
- Arayüz dili ile haber/yapay zekâ çıktı dili ayrı kavramlardır. YZ her metni Türkçe **ve** İngilizce üretir; ekranda
  arayüz dilindeki gösterilir, EN/TR düğmesiyle öbürüne geçilir; çıktı penceresinde dil ayrıca seçilir (Faz 5).

## İleride: ekip / ortak mod (şimdi uygulanmıyor)

Mimari buna hazır tutuldu:

1. **Depo katmanı**: tüm veri erişimi `repo/` sınıflarında. Ortak modda aynı sınıflar kullanılır; SQLite tek
   makinede (sunucu makinesi) kalır. Başka bir veritabanına (PostgreSQL) geçmek gerekirse yalnızca bu katman değişir.
2. **API zaten ağ protokolü**: ortak modda sunucu `127.0.0.1` yerine ağ arayüzünde dinler; istemci bilgisayarlar
   aynı React arayüzünü sunucunun adresine bağlar. Gerekenler:
   - Oturum anahtarı yerine kullanıcı hesapları ve kısa ömürlü giriş jetonları (`require_token` bağımlılığı
     tek noktada değişir).
   - Kişisel veriler (notlar, toplantı listesi) için tablolara `user_id` sütunu; haberler/hikâyeler ortak kalır.
   - HTTPS (kurum içi sertifika) ve güvenlik duvarı kuralı.
   - Toplayıcı ve yapay zekâ kuyruğu yalnızca sunucu makinesinde çalışır; istemciler yalnızca okur/yazar.
3. İstemci bilgisayarlarda veritabanı olmaz; bu, "SQLite ağ klasöründe tutulmaz" kuralını ortak modda da korur.

## Arka plan, bildirimler, yedekler (Faz 7)

- **Sistem tepsisi** (`tray.py`): ek paket yok; Win32 API'si ctypes ile (gizli pencere + `Shell_NotifyIconW`, kendi
  iş parçacığında mesaj döngüsü). Sol tık pencereyi açar; sağ tık menüsü: son tarama, Aç, Şimdi tara, Çıkış.
  Explorer yeniden başlarsa simge yeniden eklenir. Bir işleyicinin hatası tepsiyi durdurmaz.
- **Kapatınca arka planda** (`desktop.py`): pywebview'in `closing` olayı iptal edilip pencere gizlenir
  (`app.close_to_tray`); ilk seferde bir bildirim bunu söyler. Tepsi kurulamazsa kapatmak programı kapatır.
- **Bildirimler** (`notify.py`): dakikada bir; skor ≥ `notify.min_score` ve son 3 saatte ≥ `notify.min_sources`
  bağımsız kaynak (skorun "yayılıyor" etiketi). Her hikâye bir kez (`stories.notified_at`, şema v7); en az 10 dk
  arayla; birden çok hikâye tek bildirimde; sessiz saatlerde gösterilmez, sonra gösterilir. Gösterim tepsinin balonu
  (Windows 10/11'de bildirim olarak görünür; uygulama kaydı gerekmez); tıklanınca `#/feed?story=ID` açılır.
  Pencere yoksa (sunucu modu) hiçbir şey "bildirildi" sayılmaz.
- **Yedekler** (`backup.py`): bakım işi günde bir kez SQLite yedek API'siyle tutarlı kopya alır (`backup.keep_daily`,
  varsayılan 14; diğer kopyalardan son 10). Geri yükleme iki adımlı: yedek doğrulanır (`quick_check`, şema sürümü) ve
  `restore.json` ile işaretlenir → program yeniden başlar (`--after-pid` ile eski süreç bitene kadar bekler) →
  veritabanı açılmadan önce değiştirilir; önce mevcut veritabanının `pre-restore` kopyası alınır. Kilitli dosyada
  birkaç saniye yeniden denenir; başarısızlıkta veritabanı olduğu gibi kalır ve neden ayarlarda görünür.
- **İlk açılış**: eşleştirmeyi bekleyen 100'den fazla haber varken otomatik hikâye özeti yazılmaz (hikâyeler dakika
  dakika büyürken aynı özet tekrar tekrar yazılıyordu; paketli sürümün ilk açılışında görüldü). Kullanıcının
  istediği özet beklemez.

## Paketleme (Faz 7)

- `tools/build.py`: arayüzü derler, PyInstaller "onedir" (`packaging/worldsignal.spec`) çalıştırır, `version.txt`
  (güncelleyici okur) ve `build.txt` (sürüm + derleme zamanı, günlüğe yazılır) yazar. Sonuç `dist\WorldSignal`
  (~2.760 dosya, 221 MB; bunun ~100 MB'ı patchright'ın tarayıcı sürücüsü). Pakete giren veriler: arayüz, katalog,
  göçler, simge, trafilatura/justext/courlan/htmldate dil verileri, patchright sürücüsü. Konsol penceresi yok; simge
  `assets/worldsignal.ico` (`tools/make_icon.py` ile üretilir, ek kütüphane yok).
- **Dağıtım (0.8.0)**: GitHub Releases. Her kullanıcı zip'i kendi bilgisayarında yazılabilir bir klasöre ayıklar ve tek
  exe'yi çalıştırır (0.7.2'deki ağ klasörü başlatıcısı ve ağdan kendini taşıma kaldırıldı).
  - `tools/release.py` → `release\<sürüm>\WorldSignal-<sürüm>-windows.zip` (tek üst klasör `WorldSignal`), `.sha256`
    ve `NOTES.md` (CHANGELOG'daki o sürümün bölümü). Denetim: exe, arayüz, katalog, göçler, tarayıcı sürücüsü, sürüm
    numarası, sağlama değeri; pakette veritabanı, günlük, tarayıcı profili ya da örnek dosyası varsa durur.
  - `tools/publish.py` → herkese açık depoya yayın. Yalnızca git'in izlediği dosyalar, `PRIVATE` listesi hariç
    (`CLAUDE.md`, yayıncı metni alıntılayan `docs/MODEL_KARSILASTIRMA.md`), ayrı bir çalışma kopyasına aktarılır;
    her dosya `publish.private.json`'daki (git dışı, yalnızca bu bilgisayarda) kişisel/şirket verisi listesine ve genel
    kurallara (kullanıcı klasörü yolları, kişisel e-posta) karşı taranır; tek eşleşme yayını durdurur. Herkese açık
    depo her sürümde tek commit alır, bu bilgisayarın geçmişini hiç görmez. Ardından `v<sürüm>` etiketi ve
    `gh release create` (zip + sha256 + notlar).
  - Betikler: `scripts/clean-build-release.bat` (temizle → test → kaynak yedeği → derle → paket), `scripts/publish.bat`
    (`--dry-run` ile göndermeden dener).
- **Güncelleyici** (`updater.py`): açılıştan 90 sn sonra ve 6 saatte bir `api.github.com/repos/<depo>/releases/latest`.
  Daha yeni sürüm → (`update.auto_download` açıksa) `%LOCALAPPDATA%\WorldSignal\updates\<sürüm>\` altına indirme,
  SHA-256 denetimi, zip'in dışına yazan yol varsa ret, `staging\WorldSignal\version.txt` sürümle eşleşmeli.
  Kurulum yalnızca kullanıcının isteğiyle: yeni exe `--apply-update=<program klasörü> --after-pid=<eski süreç>` ile
  başlar, eski programın kapanmasını bekler, eski klasörü `<klasör>.old` yapar, kendini kopyalar, güncellenen programı
  başlatır. Kopyalama başarısızsa eski klasör geri konur. Sonuç `update-result.json`'a yazılır, arayüz bir kez gösterir;
  artıklar (`.old`, eski indirmeler) sonraki açılışta silinir. Kaynaktan çalışırken (`dev`), ağ klasöründe (`network`)
  ya da yazılamayan klasörde (`readonly`) kurulum yapılmaz; arayüz nedenini ve indirme sayfasını gösterir.
  Veri klasörü güncellemeden etkilenmez; şema göçü her açılıştaki gibi önce yedek alarak yapılır.
- **E-posta** (`mailer.py`): masaüstü Outlook (`Outlook.Application` kayıtlıysa) PowerShell + COM ile HTML taslak;
  yoksa `mailto:` ile varsayılan e-posta uygulamasında düz metin taslak (1.800 karakterde kısaltılır; biçimli metin
  önceden panoya konur). Program e-posta göndermez, yalnızca taslak açar; şifre ya da SMTP gerekmez.
- Doğrulananlar (paketli exe, boş veri klasörü): şema v7, 124 kaynak, toplama (6.457 haber), hikâye oluşturma,
  YZ özetleri, doğrudan tam metin (Guardian), Brave ile tarayıcı yolu, pencere/tepsi/bildirim, yedekten geri yükleme
  ve yeniden başlama, tepsiden çıkış.

## Geliştirme

```
uv sync --python 3.12                    # Python ortamı
cd frontend && npm ci && npm run build   # arayüzü derle
.venv\Scripts\python -m worldsignal      # pencereyle çalıştır
.venv\Scripts\python -m worldsignal --server-only --port 8765 --token dev --data-dir .devdata
cd frontend && npm run dev               # sıcak yeniden yüklemeli arayüz (VITE_DEV_TOKEN=dev)
.venv\Scripts\python -m pytest           # arka uç + uçtan uca testler
.venv\Scripts\python -m pytest -m network   # gerçek internet testleri
cd frontend && npm test                  # arayüz testleri
.venv\Scripts\python tools\verify_catalog.py  # kaynak kataloğunu yeniden doğrula
```
