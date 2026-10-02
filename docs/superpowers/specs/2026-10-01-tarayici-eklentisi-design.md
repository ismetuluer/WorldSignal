# World Signal tarayıcı eklentisi — tasarım

Tarih: 2026-10-01 · Durum: uygulandı (0.14.0); abonelik siteleri kullanıcının makinesinde henüz denenmedi · Hedef sürüm: 0.14.0

## 1. Amaç ve ölçüt

Abonelik sitelerindeki (Economist, WSJ, FT, NYT, Japan Times …) haberleri, özellikle yalnızca orada çıkan özel haberleri,
**kullanıcı hiçbir şey açmadan ve okumadan** tam metniyle programa getirmek. Haber akışta, hikâye kartında ve toplantı
listesinde özet ve önemli noktalarla kendiliğinden görünür.

Başarı ölçütü:
- Kullanıcıdan istenen iş yalnızca **bir kerelik kurulumdur**: eklentiyi yüklemek, eşleşme kodunu girmek, abonelik
  sitelerine o tarayıcıda giriş yapmış olmak. Günlük iş yoktur.
- Sayfaları otomasyon tarayıcısı (patchright) değil, kullanıcının **kendi Brave/Chrome'u** açar: gerçek profil, gerçek
  geçmiş ve oturum, otomasyon izi yok.
- Ekranda hiçbir şey belirmez (ayrı, küçültülmüş pencere).

Değişmeyen kurallar (CLAUDE.md §4.2): robot doğrulaması / CAPTCHA **çözülmez** (çıkarsa haber atlanır, site
bekletilir); sahte parmak izi yok; insan temposu (site başına aralık, günlük sınır, gece dinlenme, çalışma saatleri);
tam metin çıktılara girmez.

Kapsam dışı: siz okurken kendiliğinden kaydetme (kullanıcı istemedi); e-posta bültenleri ve ücretsiz kaynaktan tam metin
(ayrı işler).

## 2. Seçilen yaklaşım ve gerekçe

| Yaklaşım | Neden seçilmedi / seçildi |
|---|---|
| Otomasyon tarayıcısını güçlendirmek (patchright, Scrapling vb.) | Otomasyon izi ve boş profil yüzünden yakalanıyor; güçlü araçlar doğrulama çözmeye dayanıyor (kural dışı). |
| Yer imi + yapıştırma (0.13.3) | Her haberde elle iş; kaldırıldı. |
| **Kullanıcının tarayıcısında MV3 eklentisi, işi program dağıtır** | **Seçildi.** Tarayıcı gerçek, tempo ve kuyruk programda (tek yerde), eklenti ince kalır. |

Eklenti "ince istemci"dir: hangi haberin ne zaman okunacağına program karar verir, eklenti yalnızca sayfayı açıp
okur ve HTML'ini geri verir. Metni çıkarma, engel algılama, bekletme ve yeniden deneme mevcut sunucu kodundadır.

## 3. Bileşenler

### 3.1 Eklenti (`extension/`, depoda yeni klasör)
Manifest V3, derleme adımı yok (düz JS modülleri), Chrome ve Brave'de çalışır.
- `manifest.json`: izinler `alarms`, `tabs`, `scripting`, `storage` (bildirim izni yok); `host_permissions`:
  `http://127.0.0.1/*` ve `<all_urls>` (abonelik sitelerinde sayfa okuyabilmek için; eklenti yalnızca programın
  verdiği adresleri açar — README'de açıkça yazar). `_locales/tr`, `_locales/en`.
- `background.js` (service worker): `chrome.alarms` ile programa "iş var mı" diye sorar (programın verdiği
  `wait_seconds` kadar sonra; en erken 30 sn), iş varsa okur, sonucu gönderir. Aynı anda tek sayfa. Tek seferlik alarm
  yalnızca tur sonunda kurulduğu için ayrıca dakikada bir **bekçi alarmı** döngüyü, planlanan süre geçmişse, yeniden
  başlatır; okurken 20 sn'de bir bir eklenti API çağrısı işçiyi uyanık tutar.
- `lib.js` (tarayıcısız sınanabilen kısım): okuma — her sayfa için `chrome.windows.create({state: "minimized",
  focused: false})` ile **kendi küçültülmüş penceresi**, sayfa yüklenince `chrome.scripting.executeScript` ile sayfada
  3–8 sn bakıp 4–9 adımda, adımlar arası 2,5–7 sn, kullanıcı gibi kaydırır, sonra `document.documentElement.outerHTML`
  ve son adresi alır; **pencere sayfa bitince kapanır** (uygulama yapılırken "10 dk boşta kalınca kapanan ortak
  pencere" bırakıldı: hizmet işçisi sayfalar arasında durdurulabildiği için pencere bırakmamak daha güvenli). İşçi
  okurken durdurulursa pencerenin kimliği `chrome.storage.session`'da tutulur, sonraki tur kalanı kapatır. Ayrıca
  programın adresini bulma (10 port yoklama) ve isteklerin anahtarla gönderilmesi ve tek turluk iş döngüsü (`tick`).
- `popup.html/js`: durum (bağlı / bağlı değil, bugün okunan, son site, son hata), eşleşme kodu kutusu, "Duraklat".

### 3.2 Program tarafı
- **Ayar `fulltext.reader`**: `automation` (bugünkü patchright) | `extension`. `extension` iken tam metin işçisi
  "tarayıcı ile" kaynakların işlerini **almaz**, onları eklenti alır; "doğrudan indir" kaynakları eskisi gibi işçi
  okur. Kaynak yöntemleri (`off/http/browser`) değişmez → **veritabanı göçü yok.** Eklenti bağlı değilken
  otomasyon tarayıcısına geri dönülmez (yakalanan yol odur); iş sırada bekler.
- **Sabit adres**: eklentinin programı bulabilmesi için program, `extension` açıkken önce sabit bir port dener
  (`47821`, doluysa `47822 … 47830`); hepsi doluysa rastgele port ve arayüzde "eklenti programı bulamıyor" uyarısı.
  Eklenti bu 10 portu `GET /api/ext/hello` ile yoklar.
- **Eşleşme anahtarı**: 32 baytlık rastgele anahtar, `apikeys.SecretStore`'da (DPAPI) saklanır; Ayarlar → Tam metin →
  Eklenti bölümünde **eşleşme kodu** olarak gösterilir, "Yenile" ile değiştirilir (eski eklenti bağlantısı kopar).
  Loglanmaz, `/api/settings`'te dönmez.
- **Uç noktalar** (`/api/ext/*`, oturum anahtarı yerine `X-WorldSignal-Extension` başlığı ile):
  - `GET /api/ext/hello` → `{app: "worldsignal", version}` (anahtarsız; yalnızca tanışma).
  - `POST /api/ext/next` → sıradaki iş `{lease, article_id, url, source}` ya da `{wait_seconds, reason}`
    (dinleniyor, gece, site bekletmede, iş yok). Sunucu mevcut `next_job(..., BrowserPace)` ile seçer, denemeyi işler
    ve işi 5 dk'lık bir **kira** ile eklentiye verir (kira dolarsa iş sıraya döner, hak yemez).
  - `POST /api/ext/result` → `{lease, final_url, title, lang, html}` ya da `{lease, error: "tab_closed" | "timeout" |
    "load_failed"}`. Sunucu HTML'i mevcut `extract` ile işler ve sonucu tam metin işçisiyle **aynı fonksiyonla** yazar
    (başarı → `store_text` + çeviri isteği; `bot_check` / `paywall` / 401–403 → `store_failure` ve sitenin
    bekletilmesi, kademeli artış aynen). Eklentinin kendi hatası (sekme kapandı vb.) haberin hakkını yemez.
  - `GET /api/ext/status` → popup için özet.
- **Uygulamada eklenen**: eklentinin kendi hataları `tab_closed | load_failed | timeout | script_failed`; bu hatalardan
  ya da kira dolumundan sonra ilgili site 1, 2, 4 … en çok 30 dk dinlendirilir (yalnızca bellekte; diğer siteler
  beklemez), sitenin gerçek bir yanıtı (başarı ya da engel) sayacı sıfırlar.
- **Güvenlik**: `/api/ext/*` yalnızca `Host: 127.0.0.1:<port>` olan istekleri kabul eder (DNS yeniden bağlama
  saldırısına karşı); `Origin` bir web sitesiyse (`http(s)://`) reddeder; anahtar `hmac.compare_digest` ile
  karşılaştırılır; HTML en çok 8 MB.
- **Tarayıcıyı başlatma**: eklenti modu açıkken ve son 10 dk'da eklentiden ses yoksa, kullanıcının tarayıcısı
  çalışmıyorsa program onu **normal biçimde** (otomasyon bayrağı olmadan, kullanıcının kendi profiliyle)
  `--no-startup-window` ile pencere açmadan başlatır; eklenti uyanınca kendi küçültülmüş penceresini açar. Tarayıcı
  zaten açıksa dokunulmaz. (Ayarla kapatılabilir.)
- **Hangi haberler okunur** (`auto_candidates` genişler): "tarayıcı ile" kaynaklarda (1) başlığı "özel" sayılanlar
  (`flags.is_exclusive`), (2) toplantı listesi / not defteri hikâyelerinin üyeleri, (3) önemli hikâyelerin üyeleri,
  (4) kalan yeni haberler — site başına günlük sınıra kadar (`fulltext.browser_per_day`, varsayılan 15; eklenti
  modunda ayarlardan artırılabilir). Öncelik katmanları: `user` > `notebook` > `exclusive` (yeni) > `auto`.

### 3.3 Arayüz
- Ayarlar → Tam metin → **Eklenti** bölümü: "Okuyucu: Eklenti / Programın kendi tarayıcısı" seçimi; kurulum adımları
  (`brave://extensions` → Geliştirici modu → Paketlenmemiş öğe yükle → "Eklenti klasörünü aç" düğmesi); eşleşme kodu
  (kopyala / yenile); durum (bağlı, son görülme, bugün okunan, son hata).
- Kaynaklar sayfasındaki abonelik siteleri bölümü aynen; "Oturum aç" eklenti modunda kullanıcının kendi tarayıcısında
  siteyi açar (giriş orada yapılır).
- Eklenti 10 dk'dır görünmüyorsa kenar çubuğundaki durum alanında ve Ayarlar'da tek satırlık uyarı ("Eklenti bağlı değil: tarayıcı kapalı ya
  da eklenti duraklatıldı"). Sürekli bildirim yok. Sistem tepsisi değişmez (tepsi toplayıcının durumunu gösterir;
  kenar çubuğu satırı ve Ayarlar yeterli).

### 3.4 Kaldırılanlar
- `clip.py`, `POST /api/clips`, `FullTextRepository.store_clip`, "Elle eklenenler" kaynağını yaratan kod: eklenti
  mevcut haberleri tamamladığı (yeni haber eklemediği) için kullanılmıyor. Daha önce eklenen haberler ve "Elle
  eklenenler" kaynağı veritabanında kalır.

## 4. Veri akışı

```
Program (kuyruk + tempo)            Eklenti (kullanıcının Brave'i)              Abonelik sitesi
  next_job ── POST /ext/next ──────▶ küçük pencerede sekme aç ──────────────────▶ sayfa (kullanıcının oturumu)
                                     20–60 sn bekle, kaydır, HTML al
  extract ◀── POST /ext/result ───── sekmeyi kapat
  store_text / store_failure
  → YZ özeti + önemli noktalar → akış, hikâye, toplantı listesi
```

## 5. Hata durumları

| Durum | Davranış |
|---|---|
| Robot doğrulaması sayfası | `extract` → `bot_check`; haber "engellendi", site kademeli bekletilir. Doğrulama çözülmez, kullanıcıya iş çıkmaz. |
| Oturum düşmüş (401 / paywall) | Site bekletilir; Kaynaklar'da "oturum açın" notu (tek seferlik iş). |
| Tarayıcı kapalı / eklenti duraklatılmış | Kuyruk bekler, hak yanmaz; 10 dk sonra tek satır uyarı; program tarayıcıyı başlatabilir (§3.2). |
| Sekme kullanıcı tarafından kapatıldı, sayfa yüklenmedi | `tab_closed` / `load_failed`: hak yanmaz, sonraki turda yeniden. |
| Kira süresi doldu (eklenti çöktü) | İş sıraya döner. |
| Program kapalı | Eklenti dakikada bir yoklar, bulamazsa bekler; hiçbir site açılmaz. |
| Port dolu | Rastgele porta düşer, arayüzde uyarı. |

## 6. Test

- **Sunucu (pytest)**: anahtar ve Host/Origin denetimi, kira verme / süre dolumu / hak yanmaması, sonuç yazma yolunun
  işçiyle aynı olması (başarı, bot_check, paywall, 401), `fulltext.reader = extension` iken işçinin tarayıcı işlerini
  almaması, `exclusive` önceliği, sabit port düşme sırası.
- **Eklenti (vitest, `chrome` API'si sahte)**: port yoklama, eşleşme, iş döngüsü (aynı anda tek iş), okuma
  penceresinin yönetimi, kaydırma süreleri, hata eşlemeleri.
- **Elle (kullanıcının makinesinde)**: Brave'e yükleme ve eşleşme; ücretsiz bir sitede (Guardian) uçtan uca okuma;
  küçültülmüş pencerede gizli sekme davranışı (bazı siteler gizli sekmede içerik yüklemeyebilir — ilk ölçülecek
  risk); ardından abonelik siteleri. **Abonelik sitelerinde çalıştığı ancak kullanıcı denedikten sonra "test edildi" diye
  yazılır.**

## 7. Riskler ve açık noktalar

1. **Gizli/küçültülmüş sekme**: tarayıcılar gizli sekmelerde zamanlayıcıları yavaşlatır, bazı siteler içeriği görünür
   olunca yükler. Prototipte ölçülecek; gerekirse pencere ekran dışında ama "normal" durumda açılır.
2. **Site davranış analizi**: gerçek tarayıcıda bile günde çok sayıda sayfa açmak şüphe çekebilir; tempo sınırları
   aynen uygulanır, varsayılanlar düşük.
3. **Kullanım şartları**: sitelerin çoğu otomatik okumayı abonelere de yasaklar; risk kullanıcının, README ve
   arayüzde açıkça yazılır.
4. **`--no-startup-window` ile başlatma** Brave'de eklentiyi uyandırıyor mu: prototipte doğrulanacak; olmazsa program
   yalnızca uyarır.
5. Eklenti Chrome Web Mağazası'nda yayınlanmayacak (paketlenmemiş yükleme); güncellemesi program güncellemesiyle
   gelir, kullanıcı tarayıcıda bir kez "yenile"ye basar (popup bunu söyler).

## 8. Uygulama sırası (plan ayrıntısı ayrı belgede)

1. Prototip: eklenti iskeleti + `/api/ext/hello|next|result` + ücretsiz sitede uçtan uca (risk 1 ve 4 ölçülür).
2. Sunucu: ayar, kira, tempo, sonuç yazma birleştirmesi, öncelik katmanı, güvenlik denetimleri, testler.
3. Arayüz: Ayarlar → Eklenti bölümü, uyarılar, i18n.
4. `clip.py` ve ilgili kodun kaldırılması.
5. Paketleme (`extension/` sürüm zip'inde), README / CHANGELOG / ARCHITECTURE.
