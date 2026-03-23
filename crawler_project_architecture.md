# Web Crawler Projesi Mimari Rehberi ("Mini Google")

Bu doküman, `azizgocer5/web-crawler` projesinin iç işleyişini, teknik kararları ve veri akışını detaylı bir şekilde açıklamaktadır. 

Proje, Python'ın `asyncio` kütüphanesi kullanılarak yazılmış **asenkron**, **çoklu iş parçacıklı (multi-threaded)** ve SQLite destekli bir mini arama motorudur. 

---

## 1. Sistemin Genel Mimarisi

Sistem temelde 3 ana parçadan oluşur:

1. **CLI (Komut Satırı Arayüzü) - `main.py`:** Kullanıcıdan girdileri alır (tarama başlat, arama yap, durumu göster). Bu arayüz ana (main) thread üzerinde senkron olarak çalışır, böylece arka planda tarama sürerken siz donma yaşamadan komut girmeye devam edebilirsiniz.
2. **Crawler Motoru - `crawler_service.py`:** Arka planda (`background thread`) tamamen izole bir şekilde çalışan ve web sayfalarını hızla indiren/ayrıştıran motordur. Motorun içinde işleri dağıtan **1 Yönetici (Producer)** ve işleri yapan **30 İşçi (Worker)** (varsayılan değer) bulunur. 
3. **Veritabanı Katmanı - `database.py`:** SQLite kullanan veritabanı katmanıdır. Hem kuyruktaki linkleri hem de taranan sayfaların içeriklerini kalıcı olarak (hard diskte) saklar. 

---

## 2. Crawler Motorunun İç İşleyişi (Producer-Worker Modeli)

Web tarama işlemi I/O-bound (işlemciden çok ağ hızı beklenen) bir süreçtir. Bu yüzden Python'un asenkron yapısı (`asyncio` ve `aiohttp`) kullanılmıştır. 

### A) Producer (Yönetici Döngüsü)
`_run_index_job` isimli fonksiyon yöneticidir. Sorumlulukları:
1. Veritabanındaki `Queue` (Kuyruk) tablosuna bakar.
2. Durumu `pending` (bekliyor) olan bir link bulursa, veritabanını güncelleyerek onu `processing` (işleniyor) yapar.
3. Bu linki alıp RAM üzerindeki `asyncio.Queue` (Hafıza Kuyruğu) içine atar.
4. Çılgınca veritabanını sorgulayıp sistemi kilitlenmemesi için 0.5 saniyede bir bekleyerek `while True` döngüsünde sürekli bunu yapar.

Dış kaynaktaki devasa kuyrukla (veritabanı), içeride çalışan işçiler arasında bir **tampon (buffer)** görevi görür. Buna **Backpressure Yönetimi** diyoruz. Eğer hafıza kuyruğu doluyorsa (100 link sınırı varsa), yönetici veritabanından daha fazla okuma yapmayı bırakıp bekler. Böylece RAM şişmez.

### B) Workers (İşçiler)
Motor başladığında `_worker` isimli fonksiyondan 30 adet klon yaratılır. Bu 30 işçi eşzamanlı olarak şunları yapar:
1. Hafıza kuyruğundan bir link (URL) alır.
2. O URL'ye gidip `HTTP GET` isteği atarak sayfa HTML'ini indirir (`aiohttp`). (Eğer sayfa yoksa veya PDF falansa es geçer).
3. Python kütüphanesi olan `html.parser`'ı modifiye eden (`MiniParser`) yapısıyla HTML'i parçalar. Sadece görünür metni (`body`) ve başlığı (`title`) alır. (Harici parser kullanılmaz).
4. Aynı sayfa içindeki tüm `<a href="...">` linklerini bulup tam URL'lere (`urljoin`) dönüştürür.
5. Sayfayı ve bulduğu yeni yüzlerce linki **tek bir veritabanı kilidi (`asyncio.Lock`) altında tek seferde** `Pages` ve `Queue` tablolarına kaydeder.
6. İşlemi biten hedef adresi kuyrukta `done` (tamamlandı) olarak işaretleyip yeni iş almaya geçer.

---

## 3. SQLite Veritabanı ve Kilit Çözümü (Concurrency)

Projede veritabanı olarak `SQLite` kullanılmıştır. Normalde SQLite aynı anda çoklu yazma işlemlerine (Multi-writer concurrency) uygun değildir ve kilitlenip **"database is locked"** hatası verir. 

**Projede Bu Sorun Nasıl Çözüldü?**
1. **WAL (Write-Ahead Logging) Modu:** SQLite'a `PRAGMA journal_mode=WAL;` komutu verilmiştir. Bu sayede bir süreç veritabanına yazarken, başka bir süreç (örneğin siz CLI'da arama yaparken) veri _okumaya_ devam edebilir. Aksi halde arka planda tarama sürerken CLI donardı.
2. **Tekil Bağlantı ve asyncio.Lock:** 30 işçinin (worker) aynı anda yazıp dosyayı kilitlemesini önlemek için kod içinde `self.db_lock` isimli bir trafik polisi yaratıldı. İşçiler sayfayı indirme (ağ bekleme) ve parse etme (işlemci) işlerini özgürce aynı anda kendi başlarına yapıyor. Ancak iş veritabanına veri **yazmaya** geldiğinde sıraya girip milisaniyelik kilidi alıyorlar, işlerini bitirip kilidi sıradakine bırakıyorlar.
3. **Toplu Yazma (executemany):** Bir sayfada bulunan 1500 linki teker teker veritabanına eklemek ("Dur ben ekleyip kilidi vereyim, aa yine ben alayım") sistemi inanılmaz yavaşlatır. Bunun yerine `executemany` komutuyla 1500 link tek bir pakete (batch) konup tek seferde anında yazılmaktadır. Bu sayede binlerce sayfa dakikalar içinde işlenebilir hale gelmiştir.

---

## 4. Veritabanı Şeması

Veritabanında 2 ana tablo bulunur:

### A) Pages (Sayfalar Tablosu)
Gerçek indeksi oluşturur. Başarıyla indirilip okunmuş belgelerin deposudur.
- `id`: Benzersiz kimlik numarası
- `url`: Taranan sayfanın URL'si (UNIQUE - iki kez eklenmesini önler)
- `origin_url`: Taramayı başlatan ilk ata (seed) URL (Hangi taramaya ait olduğunu bilmek için)
- `depth`: Bu sayfanın derinlik seviyesi (Başlangıç 0'dır, onun çocukları 1, torunları 2...)
- `title`: Sayfa başlığı (<title> etiketi)
- `body`: Sayfadaki görünür ana metin içeriği

### B) Queue (Kuyruk Tablosu)
Crawler'ın hafızasıdır. Programı aniden kapatsanız bile, tekrar açtığınızda crawler'ın kaldığı yerden devam edebilmesini sağlayan şey bu tablonun kalıcı olmasıdır. Program beklenmedik şekilde kesildiğinde (örn: CTRL+C) `processing` (işleniyor) durumunda takılı kalan linkler, "Devam Et (Resume)" komutuyla tekrar çalıştırılırken otomatik olarak aranarak tekrar `pending` durumuna çekilir ve hiçbir kayıp yaşanmaz.
- `id`: Benzersiz sıra numarası
- `url`: Gidilecek veya gidilmiş adres (UNIQUE - aynı link kuyruğa ikinci kez giremez, Deduplication)
- `state`: URL'nin güncel durumu 
  - `pending` (Henüz gidilmedi, sırada bekliyor)
  - `processing` (Şu anda bir işçi bu sayfayı indiriyor)
  - `done` (Başarıyla taranıp işi bitti veya sayfa bozuktu geçildi)
- `depth`: Bu linkin indirildiğinde sahip olacağı derinlik seviyesi. Eğer tarama başlatırken "Derinlik: 2" dediyseniz, Crawler tablodan sadece `depth <= 2` olan linkleri alır ve işler. 

### C) Settings (Ayarlar Tablosu)
Sistemin genel ayarlarını ve durumsal bilgilerini (Key-Value şeklinde) saklar. Örneğin tarama başlatıldığında kullanıcının girdiği `max_depth` (hedef derinlik) değeri burada `key='max_depth'` olarak tutulur. Böylece sistem aniden kapansa bile, "Kaldığı Yerden Devam Et" (Resume) dendiğinde kullanıcıdan tekrar derinlik bilgisi istenmez, sistem bu tablodan okuyup otomatik olarak devam eder.

---

## 5. Arama Motoru (Ranking) Algoritması
Projede basit bir metin tabanlı TF (Term Frequency) ve Title Boost algoritması kullanılarak arama (`search`) işlemi yapılır:
1. Türkçe karakter (Örn: I/ı, İ/i) ve büyük/küçük harf duyarlılığını çözen özel bir algoritma kullanılır (`turkish_lower`).
2. SQLite LIKE (%) komutu yerine, tüm sayfalar Python tarafına liste olarak çekilir (`SELECT * FROM Pages`).
3. Her bir sayfanın başlık (`title`) ve gövde (`body`) kısımları ile kullanıcının sorgusu Türkçe harf dönüşümü yapılarak (küçük harfe indirilerek) karşılaştırılır.
4. **Puanlama (Scoring):**
   - Arama terimi sayfa başlığında (`title`) geçiyorsa sayfaya direkt **+10 puan** verilir.
   - Arama terimi sayfa gövdesinde (`body`) kaç kez geçiyorsa, **geçtiği sayı kadar (her kelime için +1)** puan verilir.
5. Sayfalar aldıkları bu toplam puanlara göre sıralanarak (en yüksek puanı alan en üstte) `(url, origin_url, depth)` üçlüsü ("triple") formatında kullanıcıya listelenir. Sıfır çekenler gösterilmez.
