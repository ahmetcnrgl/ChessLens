# ChessLens — MVP Architecture

## 1. Mimari hedefler

Mimari şu özellikleri önceliklendirir:

- Satranç doğruluğu LLM'den bağımsız olmalı.
- Oyun, LLM veya motor analizi başarısız olsa bile mümkün olduğunca devam etmeli.
- Her bileşenin sorumluluğu ve veri sözleşmesi test edilebilir olmalı.
- İlk MVP küçük kalmalı; RAG, fine-tuning ve multi-agent için erken soyutlama yapılmamalı.
- Kritik hesaplamalar kullanıcı arayüzüne veya prompt metnine dağılmamalı.

## 2. Önerilen sistem görünümü

```text
┌──────────────────────── Web istemcisi ────────────────────────┐
│ Satranç tahtası │ Hamle listesi │ Koç paneli │ Yükleniyor/hata │
└────────────────────────────┬───────────────────────────────────┘
                             │ HTTP/JSON
┌────────────────────────────▼───────────────────────────────────┐
│                     Uygulama sunucusu                         │
│                                                               │
│  Game Service ── Analysis Orchestrator ── Coach Service       │
│       │                    │                    │               │
│  chess rules          Engine Adapter       LLM Adapter         │
│                            │                    │               │
└────────────────────────────┼────────────────────┼───────────────┘
                             │ UCI                │ HTTPS
                       ┌─────▼─────┐        ┌─────▼─────┐
                       │ Stockfish │        │ LLM API   │
                       └───────────┘        └───────────┘
```

## 3. Bileşenler ve sorumluluklar

### Web istemcisi

- Tahtayı ve mevcut oyun durumunu gösterir.
- Kullanıcı hamle niyetini sunucuya gönderir.
- Sunucudan gelen doğrulanmış durumu esas alır.
- Analiz/koç yanıtının bekleme, başarı ve hata durumlarını gösterir.
- API anahtarı veya Stockfish süreç yönetimi içermez.

İstemci geçici görsel optimizasyon yapabilir, fakat otoritatif oyun durumu sunucudadır.

### Game Service

- Yeni oyun oluşturur.
- FEN, PGN/hamle geçmişi, aktif taraf ve oyun sonucunu yönetir.
- Kullanıcı ve motor hamlelerinin yasal olduğunu doğrular.
- Satranç kural kütüphanesini uygulamanın geri kalanından izole eder.

Tek doğruluk kaynağı: sunucu tarafındaki oyun durumu. İstemciden gelen tam FEN'e güvenilmez; istemci oyun kimliği ve hamle niyetini gönderir.

### Engine Adapter

- Stockfish sürecini başlatır ve UCI protokolüyle konuşur.
- Pozisyon, düşünme bütçesi ve seçenekleri motora iletir.
- Hamle, skor, mate bilgisi ve PV çıktısını tipli bir modele dönüştürür.
- Zaman aşımı, süreç kapanması ve bozuk çıktı durumlarını yönetir.

Motorun ham metni bu katmanın dışına çıkmaz.

Örnek normalize edilmiş çıktı:

```ts
type EngineAnalysis = {
  bestMove: string;          // UCI: e2e4
  score: {
    kind: "centipawn" | "mate";
    value: number;
    perspective: "white";
  };
  depth: number;
  principalVariation: string[];
};
```

Perspektif açıkça taşınır. Stockfish'in `side to move` açısından verdiği skor, adapter veya tek bir domain fonksiyonunda standart olarak beyaz perspektifine çevrilir.

### Analysis Orchestrator

Bir kullanıcı hamlesinin analiz akışını yönetir:

1. Hamle öncesi pozisyonda en iyi seçeneği analiz eder.
2. Kullanıcı hamlesini doğrular ve uygular.
3. Hamle sonrası pozisyonu analiz eder.
4. Skorları hamleyi yapan oyuncının perspektifinde karşılaştırır.
5. Kayıp, en iyi hamle, PV ve basit etiket üretir.
6. Koç için yalnızca doğrulanmış analiz paketi hazırlar.

Bu katman HTTP veya prompt ayrıntılarını bilmez.

Örnek analiz paketi:

```ts
type MoveAnalysis = {
  fenBefore: string;
  fenAfter: string;
  playedMove: { uci: string; san: string };
  bestMove: { uci: string; san?: string };
  mover: "white" | "black";
  evaluationBefore: Evaluation;
  evaluationAfter: Evaluation;
  lossInCentipawns?: number;
  mateOutcome?: "found-forced-mate" | "missed-forced-mate" | "mated" | "mate-evaluation-changed";
  classification: "best" | "good" | "inaccuracy" | "mistake" | "blunder";
  bestMoveLine: string[];       // SAN line from the position before the user's move
  opponentBestLine: string[];   // SAN line from the position after the user's move
  principalVariation: string[]; // compatibility alias for opponentBestLine
};
```

İlk eşikler ürün varsayımıdır, satranç gerçeği değildir. Konfigürasyonda tutulmalı ve test edilmelidir. Mate skorları centipawn'a körlemesine dönüştürülmemeli; ayrı kurallarla ele alınmalıdır.

### Coach Service

- `MoveAnalysis` verisini kullanıcı seviyesine uygun prompt'a dönüştürür.
- LLM'den yapılandırılmış yanıt ister.
- Yanıt şemasını doğrular, uzunluğunu sınırlar ve güvenli fallback üretir.
- Motor verisiyle açık çelişki varsa yanıtı reddeder veya sade şablon kullanır.

Python MVP'de takip soruları `CoachQuestionRequest` ile alınır. `GameRecord`, son
`MoveAnalysis`, en güçlü olası cevap, gerçekten oynanan rakip hamlesi ve son koç
açıklamasını sunucuda tutar. Soru konusu `last-move` veya `current-position`
olarak seçilir. Sonraki hamle sorusunda mevcut tahtanın kopyası güçlü Stockfish
ayarlarıyla yeniden analiz edilir. `OllamaCoach.answer_question`, o konunun
verisini ve en fazla üç önceki soru/yanıt çiftini gönderir. Mevcut konum prompt'u
eski hamlenin açıklamasını içermez. Konu değişince kısa sohbet geçmişi temizlenir;
"neden?" gibi takip soruları önceki konuyu korur. Yeni hamle geldiğinde bağlam
sıfırlanır; yanıt hazırlanırken hamle kimliği veya FEN değişirse yanıt reddedilir.

Devam adımları python-chess ile ayrı ayrı yürütülür ve her hamlenin taş/kare
açıklaması o adımdaki konumdan üretilir. Şah çekme, taş alma ve taşın kontrol
ettiği merkez kareleri sunucuda hesaplanan olgulardır. Çıktı kontrolü çıplak
hamle notasyonunu, verilen analiz dışındaki açık hamleleri ve bilinen desteksiz
üstünlük sloganlarını yakalar; tüm satranç gerekçelerinin doğruluğunu kanıtlamaz.
Otomatik hamle özetindeki oynanan hamle ve sınıflandırma sunucuda oluşturulur;
LLM bu özeti rakibin cevabıyla değiştiremez. Prompt, kullanıcı/rakip renklerini
ve yasal konumdan çıkarılan hamle kimliklerini taşır. Açık başlangıç/hedef
kareleriyle anlatılan hamlelerde taş türü ve açıkça belirtilen oyuncu/rengi
bu kimliklerle karşılaştırılır. Bu sınırlı kontrol tüm doğal dil ifadelerini
veya stratejik iddiaları doğrulayan bir çözüm değildir.
Model yanıtı geçersizse sonraki hamle sorusunda boş hata metni yerine taze yasal
öneri ve doğrulanmış olgular döner. Tahta önizlemesi yanıtın ilgili konumunu alır.

Kullanıcıya gösterilen öneri taşın adını, başlangıç ve hedef karesini içerir.
Kare adları açıklama içinde kullanılabilir; motor metrikleri ve sıkıştırılmış
hamle notasyonu gösterilmez. Fallback ayrıntılı koç yanıtının kullanılamadığını
açıkça belirtir.

Önerilen çıktı:

```ts
type CoachExplanation = {
  verdict: string;
  reason: string;
  betterIdea: string;
  thinkingTip: string;
};
```

Prompt ilkeleri:

- Yalnızca verilen analiz verisini kullan.
- Yeni varyant, skor veya taş konumu uydurma.
- SAN/PV'yi açıklarken kesin olmayan iddiayı kesinmiş gibi sunma.
- Başlangıç–orta seviye oyuncuya kısa, sade Türkçe yaz.
- En önemli tek fikre öncelik ver.

### API katmanı

İlk API yüzeyi küçük tutulur:

```text
POST /api/games
POST /api/games/:gameId/moves
GET  /api/games/:gameId
```

Örnek hamle isteği:

```json
{
  "from": "e2",
  "to": "e4",
  "promotion": "q"
}
```

Hamle yanıtı oyun durumunu hemen döndürebilir; analiz aynı yanıtta bekletilebilir veya daha sonra ayrı durum alanıyla alınabilir. İlk spike, basit senkron yaklaşımın gecikmesini ölçer. Kabul edilemezse job/polling veya SSE eklenir; başlangıçta mesaj kuyruğu kurulmaz.

## 4. Ana veri akışı

```text
Kullanıcı hamlesi
  → API doğrulama
  → Game Service: yasal mı?
  → Analysis Orchestrator: önce/sonra motor analizi
  → Hamle sınıflandırması
  → Game Service: durum güncelleme
  → Engine Adapter: Stockfish rakip hamlesi
  → Game Service: motor hamlesini doğrulama ve uygulama
  → Coach Service: açıklama üretme
  → İstemci: tahta + hamle listesi + koç kartı
```

Uygulamada algılanan gecikmeyi azaltmak için sıralama yeniden düzenlenebilir. Ancak analiz edilen `fenBefore`, `fenAfter` ve hamle kimliği birlikte saklanmalı; geç gelen açıklama yanlış pozisyona bağlanmamalıdır.

## 5. Hata ve dayanıklılık modeli

| Arıza | Beklenen davranış |
|---|---|
| Geçersiz kullanıcı hamlesi | `400`, durum değişmez, anlaşılır mesaj |
| Stockfish zaman aşımı | İstek iptal edilir; süreç sağlık kontrolü/yeniden başlatma; oyun korunur |
| LLM zaman aşımı | Motor analizi gösterilir, şablon açıklama veya “açıklama alınamadı” durumu |
| LLM şema ihlali | Bir sınırlı yeniden deneme; sonra fallback |
| Eski/geç analiz yanıtı | Oyun/hamle kimliği eşleşmiyorsa istemci uygulamaz |
| Sunucu yeniden başlatma | MVP bellekteyse aktif oyun kaybolabilir; bu kısıt açıkça gösterilir |

## 6. Güvenlik ve gizlilik sınırları

- LLM anahtarı yalnızca sunucuda tutulur ve loglanmaz.
- İstemci verisi şema ile doğrulanır; istemcinin FEN veya skor iddiasına güvenilmez.
- Prompt'a giden alanlar allowlist ile oluşturulur.
- Serbest metin koç sorusu ayrı `user` mesajında tutulur; sistem talimatları ve
  sunucunun analiz bağlamı ayrı gönderilir. Model çıktısı doğrulanır, oyun
  durumunu değiştiremez ve yeni motor analizi yerine geçmez.
- Hata loglarında gizli değerler ve tam LLM istek başlıkları bulunmaz.
- Stockfish komutları sabit UCI komutlarından oluşturulur; kullanıcı metni kabuk komutuna eklenmez.

## 7. Test stratejisi

### Birim testleri

- Skor perspektifi dönüşümü
- Centipawn kaybı hesabı
- Mate durumlarının sınıflandırılması
- UCI çıktı ayrıştırma
- LLM çıktı şeması ve fallback
- Game Service yasal/yasa dışı hamleleri

### Entegrasyon testleri

- Gerçek Stockfish ile bilinen FEN → beklenen yasal `bestmove`
- Hamle isteği → güncellenmiş oyun durumu + analiz paketi
- Sahte LLM ile prompt girdisi → doğrulanmış koç yanıtı
- Stockfish/LLM zaman aşımı → bozulmayan oyun durumu

### Uçtan uca test

- Yeni oyun aç, birkaç hamle oyna, motor yanıtını ve koç kartını gör, oyunu bitir.

Motorun tam skoruna kırılgan assertion yazmak yerine pozisyonun ve hamlenin yasal olması, beklenen kritik hamle veya kabul edilebilir seçenek kümesi test edilir.

## 8. Gözlemlenebilirlik

Her hamle için yapılandırılmış log:

- `gameId`, `moveId`
- motor süresi, derinlik ve sonuç durumu
- LLM süresi, model ve sonuç durumu
- hamle sınıflandırması
- hata kodu (varsa)

Prompt ve yanıt içeriğini varsayılan olarak üretim loguna tamamen yazmak yerine geliştirme modunda kontrollü kayıt veya redaksiyon kullanılmalıdır.

## 9. Öğrenilmesi gereken kavramlar

### Satranç gösterimleri ve durum

- FEN: tek bir pozisyonun gösterimi
- PGN: oyun ve hamle geçmişi
- SAN: insan-okur hamle gösterimi (`Nf3`, `O-O`)
- UCI hamle biçimi (`g1f3`) ve UCI motor protokolü
- Legal move generation, check, mate, stalemate, promotion

**Anlama kontrolü:** FEN ile PGN'nin farkını; `e7e8q` ile `e8=Q` gösterimlerinin nerede kullanıldığını açıklayabilmek.

### Motor değerlendirmesi

- Centipawn skoru ve skor perspektifi
- Mate skoru
- Arama derinliği ile düşünme zamanı farkı
- Principal variation ve `bestmove`
- MultiPV'nin ne olduğu (MVP için şart değil)

**Anlama kontrolü:** Aynı `+120` skorunun beyaz perspektifi ve hamle sırası perspektifinde nasıl farklı yorumlanabileceğini açıklayabilmek.

### Uygulama mimarisi

- İstemci–sunucu güven sınırı
- Adapter ve service ayrımı
- Senkron/asenkron iş akışı
- Timeout, cancellation, retry ve idempotency
- Tipli veri sözleşmeleri ve runtime şema doğrulama

**Anlama kontrolü:** LLM isteği zaman aşımına uğradığında oyunun neden ve nasıl devam ettiğini çizebilmek.

### LLM entegrasyonu

- System/developer/user talimatlarının rolü
- Structured output / JSON schema
- Grounding ve hallucination riski
- Prompt sürümleme ve değerlendirme seti
- Token, gecikme ve maliyet dengesi

**Anlama kontrolü:** LLM'ye yalnızca FEN vermenin neden güvenilir koçluk için yetersiz olduğunu açıklayabilmek.

### Test ve review

- Saf fonksiyonlarda birim test
- Dış servisleri fake/mock ile ayırma
- Entegrasyon ve uçtan uca test farkı
- Diff review, hata senaryosu ve regression testi

**Anlama kontrolü:** Bir Stockfish parser değişikliğinin hangi test katmanlarıyla güvenceye alınacağını seçebilmek.

## 10. Kritik kararlar ve ertelenen kararlar

İlk spike sonrasında kayda geçirilecek kararlar:

- Web framework ve sunucu runtime'ı
- Stockfish'in native süreç, container veya WASM olarak çalışması
- Senkron analiz yeterli mi?
- Oyun durumunun bellekte mi, dosyada mı tutulacağı
- LLM sağlayıcısı/modeli ve yapılandırılmış çıktı desteği

Şimdilik ertelenenler:

- Veritabanı şeması
- Queue/event bus
- RAG/vector store
- Fine-tuning veri hattı
- Agent orkestrasyonu
- Mikroservis ayrımı

## 11. AI ile geliştirme çalışma protokolü

Her küçük değişiklik şu döngüyü izler:

1. **Amaç:** Değişikliğin tek cümlelik davranış hedefi yazılır.
2. **Ön açıklama:** AI, uygulanacak akışı ve kritik varsayımları açıklar.
3. **Küçük diff:** Bir seferde tek kavram veya dikey dilim değiştirilir.
4. **Test:** Normal akış ve en az bir hata/kenar durumu test edilir.
5. **İnsan anlatımı:** Geliştirici kodun kritik yolunu kendi cümleleriyle açıklar.
6. **Review:** Diff; doğruluk, güvenlik, hata yönetimi ve gereksiz karmaşıklık açısından incelenir.
7. **Kapı:** Açıklanamayan kritik kod varsa görev tamamlanmaz; sadeleştirilir veya yeniden çalışılır.

