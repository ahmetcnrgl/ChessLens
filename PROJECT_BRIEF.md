# ChessLens — Project Brief

## 1. Ürün vizyonu

ChessLens, kullanıcıyla satranç oynayan ve her önemli hamleyi yalnızca puanlamakla kalmayıp **neden iyi, kötü veya öğretici olduğunu anlaşılır biçimde açıklayan** bir AI satranç koçudur.

İlk ürünün odağı “en güçlü hamleyi söylemek” değil; oyuncunun pozisyonu daha iyi okumasına, aday hamle üretmesine ve hatalarının arkasındaki düşünce kalıplarını fark etmesine yardım etmektir.

## 2. İlk MVP

MVP tek oyunculu bir deneyimdir:

1. Kullanıcı uygulama arayüzünde Stockfish'e karşı oynar.
2. Uygulama oyun durumunu ve hamle geçmişini kurallara uygun biçimde yönetir.
3. Stockfish rakip hamlesini üretir ve kullanıcının hamlesini analiz eder.
4. LLM, motorun sayısal/hesaplanmış çıktısını oyuncuya uygun, doğal dilde bir koç açıklamasına dönüştürür.
5. Kullanıcı açıklamayı oyun sırasında veya hamleden sonra görüntüler.

### MVP kapsamındaki temel özellikler

- İnsan vs Stockfish oyunu
- Yasal hamle kontrolü, sıra yönetimi, şah/mat/pat ve oyun sonu tespiti
- Ayarlanabilir basit Stockfish seviyesi
- Kullanıcı hamlesi için önceki ve sonraki pozisyon değerlendirmesi
- En iyi hamle ve kısa ana varyantın (principal variation / PV) çıkarılması
- Hamlenin basit sınıflandırılması: iyi, hata, ciddi hata gibi
- LLM tarafından kısa, anlaşılır ve pozisyona dayalı açıklama
- Hamle listesi ve son koç açıklamasının gösterimi
- Temel hata yönetimi: motor veya LLM kullanılamazsa oyun bozulmadan devam eder

### Bilinçli olarak kapsam dışında

- RAG ve açılış/oyun sonu bilgi tabanı
- Fine-tuning
- Multi-agent mimari
- Multiplayer, hesap sistemi, sosyal özellikler
- Kalıcı kullanıcı profili ve uzun dönem kişiselleştirme
- Gelişmiş turnuva/anti-cheat özellikleri
- Mobil uygulama
- Motor değerlendirmesinden bağımsız “özgün” LLM satranç analizi

Bu maddeler ancak çalışan MVP ve gerçek kullanıcı geri bildirimi sonrasında yeniden değerlendirilecektir.

## 3. Hedef kullanıcı

Birincil kullanıcı, satrancın kurallarını bilen ancak motor değerlendirmelerini ve varyantları tek başına yorumlamakta zorlanan başlangıç–orta seviye oyuncudur.

Kullanıcı şunları öğrenmek ister:

- Hamlem neden zayıftı?
- Pozisyondaki asıl tehdit neydi?
- Hangi taşı veya kareyi gözden kaçırdım?
- Daha iyi hamlenin fikri neydi?
- Bir sonraki benzer pozisyonda neye bakmalıyım?

## 4. Ürün ilkeleri

### Motor hesaplar, LLM açıklar

Stockfish satranç doğruluğunun kaynağıdır. LLM değerlendirme veya varyant uydurmaz; kendisine verilen yapılandırılmış motor analizini açıklar.

### Açıklama kanıta dayanır

Her açıklama mevcut pozisyon, oynanan hamle, motor değerlendirme farkı ve doğrulanmış varyantla ilişkilendirilir. LLM'nin motor verisinin ötesinde kesin iddia üretmesi engellenir.

### Öğretici ama kısa

Varsayılan açıklama üç parçadan oluşur:

1. Hamlenin sonucu
2. Bunun pozisyonel veya taktik nedeni
3. Oyuncunun bir sonraki sefer kullanabileceği düşünme ipucu

### Gecikme deneyimin parçasıdır

Rakip hamlesi ve açıklama beklenirken arayüz açık durum gösterir. LLM yanıtı gelmese bile oyun devam eder.

### Anlamadan ilerleme yok

AI kod üretebilir; ancak kritik parçalar geliştirici tarafından açıklanıp gözden geçirilmeden “tamamlandı” kabul edilmez.

Kritik parçalar:

- FEN, hamle geçmişi ve oyun durumunun tek doğruluk kaynağı
- Yasal hamle doğrulama akışı
- Stockfish süreci ve UCI iletişimi
- Değerlendirme skorlarının oyuncu perspektifine çevrilmesi
- Centipawn/mate skorları ve hamle sınıflandırma eşikleri
- LLM'ye gönderilen veri, prompt ve yapılandırılmış çıktı şeması
- Gizli anahtarlar, hata yönetimi ve istemci–sunucu güven sınırı

Her kritik parça için geliştirici:

1. Akışı kendi cümleleriyle açıklayabilmeli.
2. En az bir başarısızlık senaryosunu söyleyebilmeli.
3. İlgili testleri okuyup beklenen sonucu tahmin edebilmeli.
4. AI tarafından üretilen değişikliği diff üzerinden review etmelidir.

## 5. Başarı ölçütleri

MVP başarılı sayılırsa:

- Kullanıcı baştan sona kurallara uygun bir oyun oynayabilir.
- 20 ardışık yasal kullanıcı hamlesinde oyun durumu bozulmaz.
- Stockfish çıktısı deterministik test pozisyonlarında doğru biçimde ayrıştırılır.
- Açıklama, oynanan hamle ve en iyi alternatifle çelişmez.
- Motor/LLM hatasında kullanıcı oyuna devam edebilir ve anlaşılır hata mesajı görür.
- Kullanıcı beş test pozisyonunun en az dördünde açıklamanın “neden” bölümünü doğru anlayabildiğini belirtir.
- Kritik kod alanları test ve insan review'undan geçmeden tamamlanmış işaretlenmez.

## 6. İlk teknik varsayımlar

Teknoloji seçimi ilk uygulama adımında küçük bir spike ile doğrulanacaktır. Başlangıç varsayımı:

- Web tabanlı tek uygulama
- TypeScript ile istemci ve sunucu
- Satranç kuralları için olgun bir kütüphane (ör. `chess.js`)
- Stockfish'i sunucu tarafında ayrı süreç olarak çalıştırma
- LLM çağrısını yalnızca sunucu tarafında yapma
- MVP'de ilişkisel veritabanı zorunlu değil; oyun durumu bellekte tutulabilir

Bu varsayımlar mimarinin değişmez kararları değildir. Önce en küçük uçtan uca prototip ile gecikme, dağıtım ve entegrasyon riski ölçülür.

## 7. Temel kullanıcı akışı

1. Kullanıcı yeni oyun başlatır ve taraf/seviye seçer.
2. Kullanıcı bir taş sürükler veya hedef kareyi seçer.
3. Kurallar katmanı hamleyi doğrular ve yeni pozisyonu üretir.
4. Analiz servisi hamle öncesi/sonrası motor değerlendirmesini karşılaştırır.
5. Stockfish rakip hamlesini seçer.
6. Koç servisi doğrulanmış analiz paketinden açıklama üretir.
7. Arayüz tahta, hamle listesi, değerlendirme ve açıklamayı günceller.

## 8. Riskler ve koruyucu önlemler

| Risk | Koruyucu önlem |
|---|---|
| LLM satranç bilgisi uydurur | Motor verisini yapılandırılmış ver; şema doğrulaması ve çelişki kontrolleri uygula |
| Skor yanlış oyuncu açısından yorumlanır | Perspektif dönüşümünü tek fonksiyonda tut; siyah/beyaz testleri yaz |
| Stockfish işlemi donar veya çöker | Zaman aşımı, süreç yeniden başlatma ve açıklamasız devam modu |
| Her hamlede iki analiz çok yavaş olur | Derinlik/zaman bütçesi koy; ölç; gerekirse analizleri önbellekle |
| API anahtarı istemciye sızar | Tüm LLM çağrılarını sunucu tarafında yap; gizli değerleri environment değişkenlerinde tut |
| Kapsam hızla büyür | TODO aşamalarına ve kapsam dışı listesine bağlı kal |

## 9. MVP sonrasında değerlendirilebilecek yönler

- Oyun sonu özeti ve tekrar eden hata temaları
- Oyuncu seviyesine göre açıklama derinliği
- Açılış ve motif bilgisi için RAG
- Kişiselleştirilmiş çalışma planı
- Geçmiş oyunlar ve ilerleme takibi
- Ancak ölçülebilir ihtiyaç varsa fine-tuning veya multi-agent yaklaşımı

