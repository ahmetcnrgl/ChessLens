# ChessLens — Kanıta Dayalı Koç: Taktik Değerlendirme Örnekleri

Durum: At çatalı yalnızca bir test örneğidir; genel koç davranışının çözümü değildir.
Bu belge uygulama kodunun tamamlandığını iddia etmez.

## Mimari yön değişikliği

Koçu çatal, şiş, açmaz, çift saldırı vb. için ayrı ayrı yazılmış açıklama
şablonlarıyla kurmayacağız. Bu liste açık uçludur ve birkaç motifi tanımak,
rakibin bütün tehditlerini gördüğümüz anlamına gelmez. Bunun yerine:

1. **Konum ve zaman çizgisi:** Oynanmış hamleler ile motorun önerdiği olası
   devamları ayrı tutulur. Her açıklamanın hangi tahta konumuna ait olduğu
   kaydedilir.
2. **Aday devamlar:** Stockfish güçlü devamları ve skoru sağlar. Tek bir en iyi
   devam bütün tehlikeleri göstermez; aday hamle ve karşı cevaplar için sınırlı,
   bütçeli ek arama gerekir.
3. **Genel tahta kanıtı:** Her incelenen devamın yasal hamleleri, şah tehditleri,
   alınan/tehdit edilen taşları, korunma ve karşı hamle imkânları `python-chess`
   ile doğrulanır. Motif adı (ör. at çatalı) varsa öğretici etiket olabilir,
   temel karar mekanizması olamaz.
4. **İddia denetimi:** Model yalnızca doğrulanmış olayları anlatır. “Saldırıyor”,
   “bu örnek devamda alınabilir” ve “zorunlu kayıp” ayrı kanıt seviyeleridir.
   Satrançta bütün olası geleceği kesin çözmeyi vaat etmeyiz. Yeterli kanıt
   yoksa koç belirsizliği açıkça söyler.
5. **Öğretici dil:** Koç önce somut neden-sonucu açıklar, sonra gerekiyorsa
   taktik kavramını öğretir. “Merkezi kontrol et” gibi genel bir sloganı
   tek başına gerekçe olarak kullanmaz.

Mevcut `backend/tactics.py` yalnızca bu hattı sınayan geometrik çatal
prototipidir; henüz ürün koçuna bağlı değildir. Yeni kod ona bağımlı bir
motif-kataloğu şeklinde büyütülmemelidir.

İlk genel tahta gözlemi `backend/position_evidence.py` içindeki `observe_move`
ile başladı. Girdi: hamle öncesi FEN, yasal UCI hamlesi ve `actual` veya
`hypothetical` durumu. Çıktı: hamle öncesi/sonrası konum, taş ve kare kimliği,
alınan taş, şah/mat durumu, yeni geometrik saldırılar ve hamle yapan taşı
hemen alabilen yasal cevaplar. `evidenceLevel=board_observation_only` şunu
özellikle söyler: saldırı gözlemi, güvenli taş kazanma veya en iyi hamle
hükmü değildir. Listelenen geri alışlar da bütün savunmaların listesi değildir.
Bu verinin kısa özeti oynanan hamle, gerçek rakip cevabı, önerilen hamle ve
olası devam adımları için Ollama prompt'una bağlandı. API yanıtına ayrıca
eklenmedi. Prompt kuralı tek başına modelin bütün yanlış taktik iddialarını
önleyemez. Çıktı denetimi açık kesin taş/mat iddialarını, belirsiz “bu hamle”
atıflarını ve otomatik yorumda somut tahta etkisinin atlanmasını reddeder;
tahtadan üretilen yedek açıklama devreye girer. Modelin serbest Türkçe
cümlelerinin tümünü kanıtlama iddiası yoktur.

7 Ekim 2026 yerel Qwen denemesinde iki elle seçilmiş konum çalıştırıldı:
savunulabilen vezir/kale saldırısı ve e4/e5 açılış cevabı. İki model yanıtı da
somut etkiyi atladığı için kapsama denetiminden geçmedi. Bu, genel bir başarı
oranı değildir; değerlendirme setini farklı taş, tempo ve oyun safhalarıyla
büyütmek gerekir. Tekrarlanabilir deneme: `py -m scripts.evaluate_coach`.

## Ürün davranışı

Koç, oynanan hamleyi ve rakibin **gerçekten oynadığı** cevabı ayrı ayrı anlatır.
Bir sonraki hamle veya plan sorusunda, mevcut konumdan başlayan **olası** devamı
anlatır. Bu iki zaman çizgisi karışmamalıdır.

At çatalı bu plandaki ilk değerlendirme örneğidir: Bir at hamlesinden sonra aynı anda en az iki
rakip taşa saldırır. Şahın da hedef olduğu durumda önce şah tehdidine cevap
vermek gerekir. Ancak çatal geometrisi tek başına taş kazanıldığını kanıtlamaz:
atak yapan at alınabilir, hedefler kurtulabilir veya daha güçlü bir karşı hamle
bulunabilir.

Koçun iddia düzeyleri:

1. **Doğrulanmış saldırı:** “At, şahına ve kalene saldırıyor.” Taşlar ve saldırı
   kareleri yasal tahta durumundan hesaplanır.
2. **Hesaplanan risk:** “Bu devamda kaleni kaybedebilirsin.” Kısa motor devamında
   kale alınır; bu derinlik sınırlı bir öngörüdür, kesin sonuç garantisi değildir.
3. **Kesin kayıp:** İlk dilimde kullanılmaz. Bunu söylemek için bütün ilgili
   savunmaların yeterli kapsamda çürütülmesi gerekir.

İlk çatal açıklamasında öğretici cümle de bulunur: “Bir taşın aynı hamlede iki
hedefe saldırmasına çatal denir.” Sonraki açıklamalarda tanım tekrar edilmez.
Motif yoksa koç taktik icat etmez; gerekirse yalnızca doğrulanmış konumsal
etkileri anlatır.

## Küçük değerlendirme seti

FEN, pozisyonun tek anlık fotoğrafıdır; UCI hamlesi değerlendirme girdisidir.
Aşağıdaki konumlar motifleri izole etmek için bilerek seyrek kurulmuştur.
Her FEN `python-chess` ile geçerli, belirtilen hamleler yasaldır. Motorun tam
puanını veya tek bir PV'yi sabit doğru kabul etmiyoruz.

| Kimlik | FEN | İncelenen hamle | Beklenen gözlem ve koç sınırı |
| --- | --- | --- | --- |
| F1 — siyah şah çatalı | `4k3/7p/8/8/1n6/8/7P/R3K3 b Q - 0 1` | `b4c2` | Siyah at c2'den beyaz şah e1'e şah çeker ve kale a1'e saldırır. Kısa motor devamı kalenin alınabildiğini gösterir; koç “kaybedebilirsin” der. |
| F2 — aday hamlenin sonucu | `4k3/7p/8/8/1n6/8/7P/R3K3 w Q - 0 1` | Beyaz `h2h3`; sonra olası `b4c2` | Beyaz h piyonunu sürerse siyahın `Nc2+` cevabı F1'deki riski doğurur. Olası cevabı, gerçekten oynanan cevap gibi sunma. Aynı başlangıçta `a1b1` oynanırsa bu at hamlesi şahı tehdit etse de a1'de artık kale yoktur. |
| F3 — savunulabilen çatal | `4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1` | `b4c2` | At c2'den a1 kalesine ve e3 vezirine saldırır. Beyaz filin `f5c2` ile atı alması yasaldır; motor daha güçlü bir karşı oyun da bulabilir. “Siyah veziri veya kaleyi zorunlu kazanır” deme. |
| F4 — tek hedef | `4k3/7p/8/8/1n6/8/7P/4K3 b - - 0 1` | `b4c2` | Şah çekilir ama a1'de kale yoktur. “Şah-kale çatalı” etiketi verme. |
| F5 — beyaz perspektifi | `r3k3/7p/8/1N6/8/8/7P/4K3 w q - 0 1` | `b5c7` | Beyaz at c7'den siyah şah e8'e şah çeker ve kale a8'e saldırır. Renk/oyuncu rolleri F1'in tersidir. |
| F6 — çatal kanıtı yok | `rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2` | Mevcut konum | e4 ve e5 piyon hamlelerinden sonraki konum. Bu konum için doğrulanmış bir at çatalı olmadan koç çatal veya zorunlu taş kaybı iddiası üretmez. Bu, oyunun ilerleyen safhalarında taktik olmayacağı anlamına gelmez. |

F1 ve F2 için yerel Stockfish derinlik 12 incelemesinde örnek devam
`...Nc2+`, şahın uzaklaşması, `...Nxa1` oldu. Bu gözlem bir kabul testi için
tam hamle dizisini sabitlemek anlamına gelmez; aday ve cevap yine gerçek
pozisyondan analiz edilmelidir.

## Mevcut koda ekleme noktaları

`backend/stockfish_adapter.py` artık skor, en iyi çizgi ve her MultiPV adayı
için ayrı skor/hamle çizgisi döndürür. İnsan hamlesinden sonraki analiz ve
mevcut konum koç analizi üç PV ister; en iyi çizgiden ayrı en fazla iki adayın
ilk dört yarım hamlesi taranır. Yalnız şah, alış veya yeni taş saldırısı
gösteren alternatif çizgiler koç bağlamına eklenir. Bu bütün yasal hamleleri
tarama veya taktiklerin kaçırılmayacağı garantisi değildir. Mevcut motor zaman
sınırı korunur; MultiPV aynı süre içinde daha fazla çizgi aradığı için çizgi
derinliği değişebilir. Bot zorluk ayarı ayrı kalır.

`backend/coach.py` içindeki `move_facts` şu an şah çekmeyi, taş almayı ve
merkez karelerini açıklar; rakibin somut karşı tehditlerini sistematik olarak
çıkarmaz. Yeni saf kanıt inceleyici, `python-chess` ile yasal devamları
uygular; tehdit edilen taşları, doğrudan alınabilecek taşları ve şah durumunu
taş türünden bağımsız kaydeder. At çatalı prototipi bunun yerine geçmez. Sınırlı
MultiPV aday taraması eklendi; sonraki iş, bu taramanın hangi taktikleri
yakalayıp hangilerini kaçırdığını daha geniş örneklerle ölçmek ve kullanıcı
hamlesi seçtiğinde aday hamle sonrası rakip cevabını aramaktır. Kısa bir PV
matematiksel zorunluluk kanıtı değildir.

`backend/main.py` gerçek kullanıcı ve bot hamlelerini ayrı tutar. Taktik kanıtı
hangi FEN'den üretildiyse aynı hamle kimliğiyle taşınmalıdır. Oynanmış bot
hamlesi `actual`, incelenen olası cevap `hypothetical` olarak işaretlenir.
İlk aşamada incelenecek aday hamle sunucunun yasal hamle verisinden veya
arayüzün seçili taş/hedef karesinden gelir; serbest metinden hamle uydurulmaz.

`backend/llm_integration.py` yalnızca bu doğrulanmış kanıt paketini Türkçe
açıklar. LLM'ye giden prompt'ta FEN, SAN/UCI ve ham koordinat/kanıt nesneleri
yerine sunucuda üretilmiş taş-kare açıklamaları, doğrulanmış etkiler ve yeni
saldırı cümleleri kullanılır. Ham hamle kimlikleri yalnızca sunucu tarafındaki
yanıt doğrulamasında tutulur; modelin kısaltılmış notasyonu kopyalama riski
azaltılır ama sıfırlanmaz. Otomatik son-hamle incelemesinde açıklamada yer
alması gereken tek somut etki sunucudan seçilip prompt'a eklenir. Model bunu
atlamışsa ve diğer doğrulamalardan geçmişse sunucu bu kanıtlı cümleyi açıkça
ekler; diğer iddia hatalarında deterministik fallback kullanılır. Yanıtta
`serverSupplemented` bu eklemeyi işaretler. Analiz çizgisinde oyuncunun taşına
yeni bir saldırı varsa koç, gerçek rakip cevabını oynanmış olarak ayırır ve
sonraki cevabı koşullu bir devam şeklinde açıklar; eksik kalırsa sunucu kanıtlı
uyarıyı ekler. Bu bir zorunlu kazanç veya taş kaybı iddiası değildir. Örnek paket alanları:
`fen`, `playerColor`, `candidateMove`,
`opponentMove`, `status` (`actual`/`hypothetical`), `attacks`, `captures`,
`checksKing`, `legalDefenses`, `evidenceLevel`, `verifiedLine`. Motif adı
opsiyonel bir öğretim etiketidir, kanıtın kendisi değildir.
Modelden paket dışında yeni taş, hamle veya zorunlu kayıp iddiası beklenmez.

## Güncel uygulama sırası ve gözden geçirme kapısı

1. At çatalı örneklerini koru; bunlara farklı taşlarla tehdit, savunulabilen
   saldırı, gerçek rakip cevabı ve sakin konum örnekleri ekle.
2. Motif adından bağımsız `PositionEvidence` sözleşmesini birlikte incele:
   başlangıç konumu, incelenen yasal hamle, `actual`/`hypothetical` durumu,
   saldırı/alış/şah olayları, yasal savunmalar, doğrulanmış motor devamı ve
   kanıt seviyesi. Motorun skoru tek başına stratejik neden değildir.
3. Saf tahta kanıtı ve üçlü MultiPV taraması eklendi. Şimdi kapsama ve gecikme
   ölçülmeli; bütün yasal hamleleri her turda derin analiz etmeyiz.
4. Koç prompt'unu ve çıktı denetimini bu kanıt sözleşmesine bağla. Farklı taş
   ve konum örneklerinde somut neden-sonuç, yanlış kesinlik, geçmiş/gelecek
   ayrımı ve kullanıcı sorusuna cevap verme kalitesini değerlendir.

At çatalı koduna verilen ilk review, saldırı ile taş kaybının ayrı iddialar
olduğunu doğruladı. Sonraki review konusu: **Bir motorun en iyi devamında
görünmeyen ama kullanıcı için önemli olan rakip cevabını nasıl tararız ve bunu
gerçekten oynanmış hamleden nasıl ayırırız?**
