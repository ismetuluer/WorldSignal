# Hikâye birleştirme kuralı karşılaştırması (Faz 3)

`tools/benchmark_clustering.py` ile üretilir. Gerçek veritabanındaki 6919 haberin tamamı zaman sırasıyla yeniden oynatıldı (model bge-m3:latest, yalnızca başlık, 72 saatlik pencere). Doğruluk, bu akışın içindeki 95 elle etiketlenmiş haber (`tools/embedding_gold.json`) üzerinde ölçüldü.

- **Kesinlik**: bir hikâyedeki haberlerin gerçekten aynı olay olma oranı (düşükse alakasız olaylar karışıyor).
- **Duyarlılık**: aynı olayın haberlerinin gerçekten aynı hikâyede toplanma oranı.
- **En büyük**: akıştaki en kalabalık hikâyenin haber sayısı; **Büyük hikâyelerde**: 40+ haberli hikâyelere düşen haber oranı (zincirlenmenin işareti).

| Kural | Eşik | Kesinlik | Duyarlılık | F1 | Hikâye sayısı | En büyük | Büyük hikâyelerde |
|---|---|---|---|---|---|---|---|
| nn | t=0.55 | 0.895 | 0.952 | 0.923 | 2107 | 494 | 0.355 |
| nn | t=0.6 | 0.972 | 0.883 | 0.925 | 2972 | 300 | 0.2 |
| nn | t=0.65 | 0.972 | 0.747 | 0.845 | 3721 | 115 | 0.07 |
| nn | t=0.7 | 1.0 | 0.598 | 0.748 | 4386 | 56 | 0.023 |
| avg | t=0.45 | 0.936 | 0.841 | 0.886 | 1269 | 235 | 0.26 |
| avg | t=0.5 | 0.972 | 0.896 | 0.932 | 2020 | 147 | 0.172 |
| avg | t=0.55 | 0.972 | 0.802 | 0.879 | 2824 | 88 | 0.087 |
| avg | t=0.6 | 0.972 | 0.73 | 0.834 | 3489 | 82 | 0.053 |
| centroid | t=0.6 | 1.0 | 0.817 | 0.899 | 2761 | 209 | 0.216 |
| centroid | t=0.65 | 0.972 | 0.774 | 0.862 | 3579 | 170 | 0.124 |
| centroid | t=0.7 | 0.975 | 0.692 | 0.809 | 4306 | 95 | 0.052 |
| centroid | t=0.75 | 1.0 | 0.481 | 0.649 | 4921 | 38 | 0.0 |
| hybrid | t1=0.55 t2=0.4 | 0.937 | 0.901 | 0.918 | 2230 | 340 | 0.285 |
| hybrid | t1=0.55 t2=0.45 | 0.936 | 0.907 | 0.921 | 2323 | 244 | 0.231 |
| hybrid | t1=0.55 t2=0.5 | 0.972 | 0.896 | 0.932 | 2512 | 146 | 0.174 |
| hybrid | t1=0.55 t2=0.55 | 0.972 | 0.802 | 0.879 | 2824 | 88 | 0.087 |
| hybrid | t1=0.6 t2=0.4 | 0.972 | 0.847 | 0.905 | 3004 | 258 | 0.175 |
| hybrid | t1=0.6 t2=0.45 | 0.972 | 0.847 | 0.905 | 3062 | 200 | 0.152 |
| hybrid | t1=0.6 t2=0.5 | 0.972 | 0.883 | 0.925 | 3122 | 149 | 0.131 |
| hybrid | t1=0.6 t2=0.55 | 0.972 | 0.798 | 0.876 | 3280 | 88 | 0.079 |
| hybrid | t1=0.65 t2=0.4 | 0.972 | 0.747 | 0.845 | 3722 | 114 | 0.07 |
| hybrid | t1=0.65 t2=0.45 | 0.972 | 0.747 | 0.845 | 3729 | 109 | 0.069 |
| hybrid | t1=0.65 t2=0.5 | 0.972 | 0.747 | 0.845 | 3744 | 106 | 0.067 |
| hybrid | t1=0.65 t2=0.55 | 0.972 | 0.741 | 0.841 | 3808 | 84 | 0.053 |

## En büyük 5 hikâyeden örnek başlıklar — eski kural (yalnızca en yakın haber ≥ 0,55)

- **494 haber**: Let’s beat California on AI, key Democrat says · Culinary diplomacy on the menu for Xi and Trump at the White House · Trump, Xi wrap up summit with tea and tour of US archives · Pope warns a 'paradise of machines' could undermine humanity as he ope · Russia accuses Europe of seeking to thwart Ukraine talks · AI Startup Urges Optimism from Europe despite Safety Fears
- **402 haber**: Trump dünyaya ilan etti: Grönland ve Danimarka ile anlaşma sağlandı: B · 'Bully at home, victim abroad': Iranians on Pezeshkian's UN speech · Trump asks Supreme Court to revive rapid 3rd-country deportations · Oil Prices Fall as U.S.-Iran Diplomacy, Regional Tensions Remain in Fo · Iran will defend itself against any threat or military attack: Pezeshk · In photos: President Pezeshkian returns home from New York
- **309 haber**: 3 Dead in Moscow Region, Drones Hit Oil Refinery in Russian Capital · Kyiv’s High Council of Justice Suffers Damage in Russian Strike · Rusya'nın Belgorod bölgesinde Ukrayna ordusunun saldırıları sonucu üç  · Kiyevdə bir sıra Ukrayna telekanallarının siqnalı kəsilib · Силы ПВО сбили за ночь над Россией 96 беспилотников ВСУ · Russia says it struck military infrastructure, vessel in Ukraine
- **158 haber**: Iran Ready to Reopen Strait of Hormuz if US Eases Military Pressure, L · Iran's FM Araqchi says now up to US to accept 7-day plan · ABD Başkanı Trump, İran'ın sunduğu 7 günlük Hürmüz Boğazı planını redd · Russia calls for lifting Cuba blockade, urgent humanitarian measures — · İran’da kararları altı kişi alıyor · Rusya’dan Filistin çıkışı: Devletin kurulması için zaman geldi
- **120 haber**: Heavy rain intensifies across Istanbul, raising flood risk · Turistlerin akın ettiği şehir afet bölgesi ilan edildi: Sular yükseliy · Nor'easter Massachusetts tracker: What we know about alerts, power out · Çanakkale Boğazı’nda tanker alarmı! · Sıcaklık azalıyor, kuvvetli yağış etkili oluyor! · Powerful storm pummels northeast US with rain, high winds

## En büyük 5 hikâyeden örnek başlıklar — uygulamanın varsayılanı (en yakın ≥ 0.55, ortalama ≥ 0.5)

- **146 haber**: When Xi Visits Washington, Trump Must Raise China’s ‘Ethnic Unity’ Law · Trump-Xi Summit in Washington Features Great Fanfare but Low Expectati · Trump: ABD ile Çin arasındaki ilişkiler hiç bu kadar iyi olmamıştı · ‘Xi, You’re Not Welcome’: As Trump Hosts China’s Leader, Thousands Pro · Trump, Xi end summit with tea, tour of US archives - and little sign o · Trump: Şi ile görüşmemiz dostluk güç ve başarı doluydu
- **135 haber**: 3 Dead in Moscow Region, Drones Hit Oil Refinery in Russian Capital · 14-Year-Old Boy Killed as Russian Drone Hits Kyiv High-Rise · Reuters: Russia’s seventh-largest refinery halts operations after a Uk · Russian Attacks Destroy Ukrainian Books · Russian strike on Zaporizhzhia region leaves one killed, four injured · Large fire breaks out in Odesa region after Russian attack: One killed
- **118 haber**: Iran Ready to Reopen Strait of Hormuz if US Eases Military Pressure, L · Iran rules out nuclear concessions even if US accepts Hormuz proposal · Iran awaits US reply to seven-day Hormuz plan · Trump rejects Iranian proposal to open Hormuz and end fighting · Iran insists on diplomatic solution after Trump rejects peace plan · 'Only negotiated solution can end deadlock': Iran as Trump rejects pea
- **88 haber**: (Asiad) S. Korea wins silver in women's team sepaktakraw · (Asiad) Kim Min-seop wins bronze in men's 200m butterfly swimming · (LEAD) (Asiad) S. Korea beats China to reach women's basketball final · (LEAD) (Asiad) S. Korea beats China to advance to men's handball semif · (Asiad) S. Korea ends worst table tennis campaign with 3 bronze medals · (URGENT) S. Korea wins gold in men's street skateboarding at Asian Gam
- **88 haber**: Pope Leo's Paris trip to highlight support for Christians in Arab worl · BESuch von Leo XIV.: „Papamania“ in Frankreich · Pope Leo to meet clergy sexual abuse victims in Lourdes · 'A once-in-a-lifetime event': Faithful and curious flock to Pope Leo X · Pope Leo XIV celebrates open-air Mass in front of 800,000 people in ce · Leo XIV, a calm and unifying pope, draws huge crowds in Paris for Mass
