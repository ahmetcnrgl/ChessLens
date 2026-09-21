# ChessLens — MVP Roadmap

Bu plan küçük, doğrulanabilir dikey dilimlerden oluşur. Kutular ancak kod, test, geliştirici açıklaması ve review tamamlandığında işaretlenir.

## Çalışma kuralları

Kavramları ezber sorularıyla ölçmek yerine çalışan küçük çıktılar üzerinden öğreneceğiz. AI, koddan önce yaklaşımı açıklar; koddan sonra kritik akışı satır satır anlatır. Benim ilerleme kapım, kavramı tanım olarak tekrar etmek değil, ilgili veri akışını ve hata senaryosunu kendi projem üzerinden açıklayabilmemdir. Belirsizlik yoksa ayrıca quiz sorusu sorulmaz.

Her geliştirme görevi için “tamamlandı” tanımı:

- [ ] Davranış ve kabul ölçütü görev başlamadan yazıldı.
- [ ] AI değişiklikten önce yaklaşımı ve riskli noktayı açıkladı.
- [ ] Değişiklik küçük ve odaklı bir diff olarak yapıldı.
- [ ] Normal akış ve en az bir hata/kenar durumu test edildi.
- [ ] Ben kritik akışı kendi cümlelerimle açıklayabildim.
- [ ] Diff review edildi; açık bulgular çözüldü veya kayda geçirildi.
- [ ] İlgili dokümantasyon güncel.

## Aşama 0 — Temel kavramlar ve karar spike'ı

Amaç: Teknoloji seçmeden önce sistemin temel veri biçimlerini anlamak ve en riskli entegrasyonları küçük deneylerle doğrulamak.

- [ ] FEN, PGN, SAN ve UCI hamle biçimi için kısa notlar ve örnekler hazırla.
- [ ] Beş örnek pozisyonda yasal hamle, şah, mat, pat ve terfi davranışını elle incele.
- [ ] Stockfish'i yerelde çalıştır; `uci`, `isready`, `position`, `go`, `bestmove` akışını gözlemle.
- [ ] Bir FEN için Stockfish `info` ve `bestmove` çıktısını küçük bir spike ile ayrıştır.
- [ ] Centipawn ve mate skorlarının perspektifini örneklerle doğrula.
- [ ] Bir LLM'ye sabit bir `MoveAnalysis` JSON'u verip yapılandırılmış koç çıktısı al.
- [ ] Framework/çalışma zamanı seçeneklerini; sadelik, Stockfish entegrasyonu ve dağıtım açısından karşılaştır.
- [ ] Seçimleri kısa Architecture Decision Record (ADR) olarak kaydet.

**Öğrenme kapısı:** FEN/PGN/SAN/UCI farkını, Stockfish komut akışını ve skor perspektifini kod bakmadan açıklayabilmeliyim.

**Çıkış ölçütü:** Gerçek Stockfish çıktısından tipli analiz ve sahte/sabit veriden şeması doğrulanmış LLM yanıtı alınmış olmalı.

## Aşama 1 — Proje iskeleti ve saf satranç çekirdeği

Amaç: Arayüz ve dış servis olmadan güvenilir oyun durumunu kurmak.

- [ ] Seçilen TypeScript proje iskeletini oluştur; lint, format, type-check ve test komutlarını ekle.
- [ ] Ortam değişkeni örneği oluştur; gerçek anahtarları git dışında tut.
- [ ] Domain tiplerini tanımla: `GameState`, `Move`, `Evaluation`, `MoveAnalysis`.
- [ ] Satranç kural kütüphanesini Game Service arkasına al.
- [ ] Yeni oyun, yasal hamle, yasa dışı hamle, rok, terfi ve oyun sonu testlerini yaz.
- [ ] Oyun durumunun tek doğruluk kaynağını ve istemci güven sınırını belge/test et.

**Öğrenme kapısı:** Bir hamle isteğinin neden doğrudan istemci FEN'ine güvenmemesi gerektiğini ve Game Service'in durumu nasıl koruduğunu açıklayabilmeliyim.

**Çıkış ölçütü:** Komut satırı/test üzerinden tam bir yasal oyun akışı dış servis olmadan yürütülebilmeli.

## Aşama 2 — Stockfish adapter'ı

Amaç: Motorla güvenli ve test edilebilir bir sınır oluşturmak.

- [ ] Stockfish binary/çalıştırma yöntemini sabitle ve geliştirme kurulumunu belgele.
- [ ] UCI süreç yaşam döngüsünü uygula: başlatma, hazır olma, komut, kapanma.
- [ ] `info` ve `bestmove` satırlarını normalize edilmiş tipe ayrıştır.
- [ ] Zaman bütçesi veya derinlik konfigürasyonu ekle.
- [ ] Timeout, bozuk çıktı ve beklenmedik süreç kapanması davranışını uygula.
- [ ] Parser için fixture tabanlı birim testleri yaz.
- [ ] Gerçek Stockfish ile birkaç bilinen FEN entegrasyon testi yaz.

**Öğrenme kapısı:** UCI isteğinin baştan sona sırasını, süreç kapanırsa ne olacağını ve ham motor metninin neden adapter dışına çıkmadığını açıklayabilmeliyim.

**Çıkış ölçütü:** `analyze(fen)` çağrısı süre sınırı içinde tipli skor, PV ve yasal en iyi hamleyi döndürmeli.

## Aşama 3 — İnsan vs Stockfish, arayüzsüz dikey dilim

Amaç: Önce API veya CLI üzerinden gerçek bir oyunu tamamlamak.

- [ ] Oyun oluşturma ve kullanıcı hamlesi application service'ini yaz.
- [ ] Kullanıcı hamlesinden sonra Stockfish rakip hamlesi üret.
- [ ] Her iki hamleyi de Game Service üzerinden doğrula ve uygula.
- [ ] Zorluk için basit, belgelenmiş motor ayarı ekle.
- [ ] Geçersiz hamle, oyun sonu ve motor timeout akışlarını test et.
- [ ] En az bir kısa oyunu uçtan uca otomatik test et.

**Öğrenme kapısı:** Kullanıcı hamlesinden motor cevabına kadar her fonksiyonun sorumluluğunu bir akış diyagramıyla anlatabilmeliyim.

**Çıkış ölçütü:** CLI veya API testiyle insan–Stockfish oyunu kurallara uygun başlayıp bitebilmeli.

## Aşama 4 — Hamle analizi ve sınıflandırma

Amaç: LLM eklemeden önce güvenilir, yapılandırılmış öğretici veriyi üretmek.

- [ ] Hamle öncesi ve sonrası analiz akışını uygula.
- [ ] Skorları hamleyi yapan oyuncının perspektifine dönüştüren saf fonksiyonu yaz.
- [ ] Centipawn kaybını hesapla.
- [ ] Mate giriş/kaçırma durumları için ayrı sınıflandırma kuralları yaz.
- [ ] İlk `best/good/inaccuracy/mistake/blunder` eşiklerini konfigürasyona al.
- [ ] En iyi hamle ve kısa PV'yi `MoveAnalysis` içine ekle.
- [ ] Beyaz/siyah perspektifi ve mate senaryoları için tablo tabanlı testler yaz.
- [ ] En az 10 sabit test pozisyonundan küçük bir değerlendirme seti oluştur.

**Öğrenme kapısı:** Bir hamlenin centipawn kaybını hem beyaz hem siyah için elle hesaplayabilmeli; mate skorunun neden normal sayı gibi ele alınmadığını açıklayabilmeliyim.

**Çıkış ölçütü:** Test pozisyonlarında tutarlı ve açıklanabilir `MoveAnalysis` JSON'u üretilmeli.

## Aşama 5 — LLM koç

Amaç: Motor analizini kısa ve güvenilir Türkçe açıklamaya dönüştürmek.

- [ ] `CoachExplanation` şemasını ve maksimum uzunlukları tanımla.
- [ ] Prompt'u yalnızca allowlist ile seçilen `MoveAnalysis` alanlarından oluştur.
- [ ] İlk Türkçe koç prompt'unu yaz ve sürümle.
- [ ] Sunucu tarafı LLM adapter'ı ve runtime şema doğrulaması ekle.
- [ ] Timeout, bir sınırlı retry ve deterministik fallback açıklaması ekle.
- [ ] Motor verisiyle açık çelişkileri yakalayan temel kontroller yaz.
- [ ] 10+ sabit pozisyonda açıklamaları doğruluk, sadelik ve yararlılık rubriğiyle elle değerlendir.
- [ ] Maliyet ve gecikmeyi ölçüp kayıt altına al.

**Öğrenme kapısı:** Prompt'un her bölümünün amacını, LLM'nin hangi veriye dayanabildiğini ve kötü/bozuk yanıtın nasıl sınırlandığını açıklayabilmeliyim.

**Çıkış ölçütü:** Test setinde açıklamalar oynanan hamle, en iyi hamle ve motor değerlendirmesiyle çelişmemeli; LLM yokken fallback çalışmalı.

## Aşama 6 — Web MVP

Amaç: En küçük kullanılabilir oyun ve koç deneyimini sunmak.

- [ ] Tahta, hamle listesi, sıra ve oyun sonucu bileşenlerini oluştur.
- [ ] Sürükle-bırak veya tıkla-hamle etkileşimi ekle.
- [ ] Yeni oyun ve basit seviye seçimi ekle.
- [ ] Analiz bekleme ve hata durumlarını görünür yap.
- [ ] Koç kartında karar, neden, daha iyi fikir ve düşünme ipucunu göster.
- [ ] Geç gelen yanıtın yanlış hamleye bağlanmasını `gameId/moveId` ile engelle.
- [ ] Klavye kullanımı, renk kontrastı ve mobil olmayan dar ekran için temel erişilebilirlik kontrolü yap.
- [ ] Ana kullanıcı akışı için uçtan uca test yaz.

**Öğrenme kapısı:** UI'daki her yükleniyor/hata durumunun hangi sunucu durumuna karşılık geldiğini ve stale response korumasını açıklayabilmeliyim.

**Çıkış ölçütü:** Kullanıcı tarayıcıda baştan sona oyun oynayıp her hamle için anlaşılır koç geri bildirimi alabilmeli.

## Aşama 7 — Sağlamlaştırma ve MVP doğrulaması

Amaç: Demo yerine güvenilir bir MVP çıkarmak.

- [ ] En az 20 ardışık hamlelik stabilite senaryosu çalıştır.
- [ ] Stockfish ve LLM arızalarını kontrollü olarak enjekte et.
- [ ] Yapılandırılmış log ve temel süre/maliyet ölçümlerini ekle.
- [ ] API anahtarı, girdi doğrulama, log redaksiyonu ve süreç komutları için güvenlik review'u yap.
- [ ] Üç ila beş hedef kullanıcıyla kısa kullanılabilirlik testi yap.
- [ ] Kullanıcıların “neden” açıklamasını anlayıp anlamadığını beş pozisyonla ölç.
- [ ] Kurulum, geliştirme, test ve çalıştırma talimatlarını README'ye yaz.
- [ ] Açık kısıtları ve MVP sonrası fikirleri ayrı backlog'a taşı.

**Öğrenme kapısı:** En büyük üç teknik/ürün riskini, ölçülen sonuçları ve bir sonraki yatırım kararını savunabilmeliyim.

**Çıkış ölçütü:** `PROJECT_BRIEF.md` başarı ölçütleri karşılanmalı ve açık kritik review bulgusu kalmamalı.

## İlk üç geliştirme oturumu

### Oturum 1 — Gösterimleri öğren ve Stockfish ile konuş

- [ ] FEN/PGN/SAN/UCI mini notu
- [ ] Stockfish kurulumu
- [ ] Elle UCI oturumu
- [ ] Bir pozisyonu analiz eden en küçük script
- [ ] Script review'u ve sözlü/kısa yazılı anlatım

### Oturum 2 — Oyun çekirdeği

- [ ] TypeScript/test iskeleti
- [ ] Game Service
- [ ] Yasal/yasa dışı hamle testleri
- [ ] State ownership review'u

### Oturum 3 — Tipli motor adapter'ı

- [ ] UCI parser
- [ ] `EngineAnalysis` tipi
- [ ] Perspektif testleri
- [ ] Timeout senaryosu
- [ ] Diff review ve anlama kapısı

## MVP için “şimdilik yapma” listesi

- [ ] RAG/vector database ekleme
- [ ] Fine-tuning veri hattı kurma
- [ ] Multi-agent veya agent framework ekleme
- [ ] Mikroservislere bölme
- [ ] Erken kullanıcı hesabı/veritabanı tasarlama
- [ ] Gelişmiş analiz grafikleriyle temel oyun akışını geciktirme

Bu kutular görev değil, kapsam koruyucusudur; MVP boyunca işaretlenmeden kalmalıdır.
