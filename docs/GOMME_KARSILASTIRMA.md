# Gömme (embedding) modeli karşılaştırması (Faz 3)

`tools/benchmark_embeddings.py` ile üretilir. Doğru cevap anahtarı: `tools/embedding_gold.json` — veritabanındaki gerçek haberlerden elle doğrulanmış 12 olay (82 haber) ve 13 ilgisiz haber; diller: ar, az, de, en, fr, ru, tr.
Modeller işlemcide (CPU) çalıştırıldı; ekran kartı kullanılmadı.

- **AUC**: aynı olaya ait haber çiftlerinin farklı olay çiftlerinden daha benzer bulunma oranı (1,0 = kusursuz).
- **Kümeleme F1**: haberler zaman sırasıyla tek tek geldiğinde “en yakın habere katıl” kuralının doğruluğu (1,0 = kusursuz), en iyi eşikte. (Uygulama buna ek olarak zincirlenmeyi önleyen ikinci bir koşul kullanır; bkz. `docs/BIRLESTIRME_KARSILASTIRMA.md`.)
- **Zor çiftler**: birbirine benzeyen ama farklı olayların en yüksek benzerliği; eşiğin altında kalmalı.

| Model | Metin | AUC | Kümeleme F1 (eşik) | Zor çiftler (en yüksek) | Hız (haber/sn, CPU) |
|---|---|---|---|---|---|
| bge-m3:latest | title | 0.9955 | 0.923 (0.55) | 0.657 | 18.6 |
| bge-m3:latest | title+summary | 0.9967 | 0.916 (0.59) | 0.726 | 9.3 |
| qwen3-embedding:0.6b | title | 0.9904 | 0.907 (0.67) | 0.8 | 13.8 |
| qwen3-embedding:0.6b | title+summary | 0.9947 | 0.905 (0.73) | 0.865 | 5.3 |
| embeddinggemma:latest | title | 0.9587 | 0.818 (0.84) | 0.956 | 21.5 |
| embeddinggemma:latest | title+summary | 0.9766 | 0.846 (0.82) | 0.94 | 11.3 |

## Eşiğe göre kümeleme F1

- **bge-m3:latest / title**: 0.4: 0.778, 0.45: 0.881, 0.5: 0.892, 0.55: 0.923, 0.6: 0.901, 0.65: 0.835, 0.7: 0.758, 0.75: 0.69, 0.8: 0.605, 0.85: 0.53, 0.9: 0.479, 0.95: 0.459
- **bge-m3:latest / title+summary**: 0.4: 0.596, 0.45: 0.67, 0.5: 0.89, 0.55: 0.91, 0.6: 0.893, 0.65: 0.864, 0.7: 0.806, 0.75: 0.758, 0.8: 0.667, 0.85: 0.569, 0.9: 0.522, 0.95: 0.44
- **qwen3-embedding:0.6b / title**: 0.4: 0.561, 0.45: 0.609, 0.5: 0.771, 0.55: 0.858, 0.6: 0.881, 0.65: 0.883, 0.7: 0.864, 0.75: 0.842, 0.8: 0.821, 0.85: 0.677, 0.9: 0.532, 0.95: 0.479
- **qwen3-embedding:0.6b / title+summary**: 0.4: 0.354, 0.45: 0.618, 0.5: 0.651, 0.55: 0.662, 0.6: 0.801, 0.65: 0.855, 0.7: 0.905, 0.75: 0.873, 0.8: 0.855, 0.85: 0.747, 0.9: 0.6, 0.95: 0.47
- **embeddinggemma:latest / title**: 0.4: 0.152, 0.45: 0.152, 0.5: 0.152, 0.55: 0.152, 0.6: 0.152, 0.65: 0.191, 0.7: 0.496, 0.75: 0.745, 0.8: 0.782, 0.85: 0.815, 0.9: 0.757, 0.95: 0.57
- **embeddinggemma:latest / title+summary**: 0.4: 0.152, 0.45: 0.152, 0.5: 0.152, 0.55: 0.171, 0.6: 0.171, 0.65: 0.378, 0.7: 0.652, 0.75: 0.728, 0.8: 0.829, 0.85: 0.755, 0.9: 0.695, 0.95: 0.568

## Zor çiftler ayrıntısı

- **bge-m3:latest / title**: hormuz_drone~hormuz_plan_rejected = 0.547, sayan_kaya~ozata_resignation = 0.548, taiz_saudi_strike~taiz_government_bombing = 0.657
- **bge-m3:latest / title+summary**: hormuz_drone~hormuz_plan_rejected = 0.587, sayan_kaya~ozata_resignation = 0.713, taiz_saudi_strike~taiz_government_bombing = 0.726
- **qwen3-embedding:0.6b / title**: hormuz_drone~hormuz_plan_rejected = 0.704, sayan_kaya~ozata_resignation = 0.681, taiz_saudi_strike~taiz_government_bombing = 0.8
- **qwen3-embedding:0.6b / title+summary**: hormuz_drone~hormuz_plan_rejected = 0.734, sayan_kaya~ozata_resignation = 0.776, taiz_saudi_strike~taiz_government_bombing = 0.865
- **embeddinggemma:latest / title**: hormuz_drone~hormuz_plan_rejected = 0.892, sayan_kaya~ozata_resignation = 0.866, taiz_saudi_strike~taiz_government_bombing = 0.956
- **embeddinggemma:latest / title+summary**: hormuz_drone~hormuz_plan_rejected = 0.88, sayan_kaya~ozata_resignation = 0.895, taiz_saudi_strike~taiz_government_bombing = 0.94
