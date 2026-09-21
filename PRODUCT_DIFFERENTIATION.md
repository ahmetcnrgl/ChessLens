# ChessLens — Ürün Farklılaşması ve Doğrulama

## 1. Mevcut durum

ChessLens'in ilk fikri — insanın Stockfish'e karşı oynaması ve hamlelerinin AI tarafından açıklanması — tek başına yeni değil.

- [PlayStockfish Coaching](https://www.playstockfish.com/coaching), Stockfish'e karşı oyun, her hamlenin ikinci bir motorla değerlendirilmesi, hata sınıflandırması ve pozisyon hakkında düz yazıyla AI açıklaması sunuyor.
- [Chess.com Play Coach](https://support.chess.com/en/articles/10877257-how-do-i-play-against-the-coach), oyun sırasında hamle hamle geri bildirim, ipucu, tehdit okları ve değerlendirme sunuyor.
- [DecodeChess](https://decodechess.com/about/), Stockfish hamlelerini tehdit, taktik, plan ve strateji kavramlarıyla açıklamaya odaklanıyor.
- [WhyThisMove](https://whythismove.com/ai-coaching), içe aktarılan oyunlar için motor hatalarını LLM açıklamalarıyla yorumluyor.

Sonuç: Genel özellik seti doğrulanmış bir kategoriye ait; salt teknik MVP'nin pazar farklılığı zayıf.

## 2. Önerilen odak

### Geçici ürün vaadi

> ChessLens, başlangıç–orta seviye Türkçe konuşan oyunculara Stockfish'in ne düşündüğünü değil, **hangi tehdidi veya fikri kaçırdıklarını** anlaşılır ve kanıtlanabilir biçimde gösterir.

Bu henüz doğrulanmış bir avantaj değil, test edilecek hipotezdir.

### Farklılaşma hipotezleri

| Hipotez | Kullanıcı değeri | Test edilebilir sinyal |
|---|---|---|
| Türkçe ve seviye uyumlu açıklama | Oyuncu motor dilini anlamadan fikri kavrar | Kullanıcı açıklamayı kendi sözleriyle doğru özetler |
| “Kaçırdığın tehdit” odaklı anlatım | En iyi hamle ezberlenmez, pozisyon okunur | Kullanıcı benzer pozisyonda tehdidi daha sık bulur |
| Cevabı geciktiren koç akışı | Oyuncu pasif izleyici olmaz | Kullanıcı ipucu almadan aday hamle üretir |
| Kanıta bağlı açıklama | LLM uydurması azalır | Açıklama, motor PV ve tahta ile çelişmez |
| Hata kalıbı takibi | Tek hamle yerine öğrenme döngüsü oluşur | Aynı hata temasının tekrar oranı düşer |

İlk MVP'de yalnızca ilk üç hipotezden biri seçilmeli; hepsi aynı anda yapılmamalıdır.

## 3. Karar önerisi

Projeyi kapatmak yerine **ürün kodlamasını geçici olarak yavaşlatıp doğrulama yapacağız**. ChessLens iki açıdan değerli kalır:

1. AI engineering öğrenme projesi: Stockfish protokolü, tipli veri sözleşmesi, LLM grounding, test ve hata yönetimi.
2. Daraltılmış ürün deneyi: Türkçe, tehdit-odaklı ve etkileşimli koçluk.

Genel bir Chess.com kopyası yapmayacağız. Seçtiğimiz hipotez kullanıcıda fark yaratmıyorsa, yeni özellik eklemek yerine projeyi durdurma kararı vereceğiz.

## 4. Bir haftalık doğrulama planı

### Gün 1 — Rakip deneyimi

- [ ] PlayStockfish'te iki kısa oyun oyna.
- [ ] Chess.com Play Coach'ta mümkünse bir oyun dene.
- [ ] DecodeChess'te aynı veya benzer üç pozisyonu incele.
- [ ] Her ürün için şu alanları kaydet: açıklama dili, açıklamanın zamanı, en iyi hamlenin ne kadar erken gösterildiği, hata nedeninin somutluğu, kullanıcıya tekrar deneme fırsatı verilip verilmediği.

### Gün 2 — Pozisyon test seti

- [ ] Beş basit pozisyon seç: taş asma, tek hamlelik taktik, savunma, kötü taş, plan gerektiren sessiz hamle.
- [ ] Her pozisyonda kullanıcının doğal sorusunu yaz: “Ne kaçırdım?”, “Rakip ne tehdit ediyor?”, “Neden bu hamle daha iyi?”
- [ ] Her rakibin verdiği yanıtı aynı rubrikle puanla.

### Gün 3 — ChessLens açıklama prototipi

- [ ] Aynı beş pozisyon için Stockfish analiz paketlerini oluştur.
- [ ] LLM olmadan açıklama şablonu yaz: sonuç, kaçırılan fikir/tehdit, daha iyi düşünme sorusu.
- [ ] Sonra aynı girdiyi LLM ile açıklat ve motor verisiyle çelişki kontrolü yap.

### Gün 4–5 — Beş kullanıcı görüşmesi

- [ ] En az üç başlangıç–orta seviye oyuncuya aynı beş pozisyonu göster.
- [ ] Açıklamayı okuduktan sonra “hangi tehdidi kaçırdın?” sorusunu sor.
- [ ] Kullanıcının cevabı açıklamadaki ana fikri taşıyor mu kaydet.
- [ ] En iyi hamleyi söylemeden önce kullanıcının aday hamle üretip üretemediğini ölç.

### Gün 6 — Sonuç analizi

- [ ] Her hipotez için güçlü/zayıf sinyalleri yaz.
- [ ] Rakiplerin açıkça çözemediği bir kullanıcı problemi var mı belirle.
- [ ] “ChessLens neden var?” cümlesini tek cümleye indir.

### Gün 7 — Karar kapısı

Aşağıdaki üç karardan biri seçilir:

- **Devam:** En az bir hipotezde kullanıcılar açıklamayı anlamlı biçimde daha iyi kavrıyor.
- **Yeniden daralt:** Fikir değerli ama hedef kullanıcı veya akış yanlış; kapsam değiştirilir.
- **Durdur:** Rakiplerden anlamlı bir fark bulunmuyor ve öğrenme hedefi de artık değerli değil.

## 5. Değerlendirme rubriği

Her açıklama 0–2 arasında puanlanır:

- **Doğruluk:** Motor analiziyle çelişiyor mu?
- **Somutluk:** Taş, kare, tehdit veya varyant belirtiyor mu?
- **Anlaşılabilirlik:** Kullanıcı ana fikri kendi sözleriyle aktarabiliyor mu?
- **Eyleme dönüklük:** Bir sonraki benzer pozisyonda kullanılabilir bir düşünme sorusu veriyor mu?
- **Müdahale kalitesi:** Kullanıcıyı hemen cevaba bağımlı kılmadan düşündürüyor mu?

İlk geçiş hedefi: beş pozisyonda ortalama en az 7/10 ve kullanıcıların çoğunun ana fikri doğru aktarabilmesi.

## 6. Şimdilik ertelenen geliştirmeler

Doğrulama tamamlanana kadar şunları eklemiyoruz:

- RAG
- fine-tuning
- multi-agent yapı
- hesap sistemi ve sosyal özellikler
- gelişmiş grafikler
- uzun dönem kişiselleştirme

Önce tek bir açıklama deneyiminin rakiplerden gerçekten daha öğretici olup olmadığını kanıtlayacağız.

