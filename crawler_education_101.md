# Web Crawling (Web Tarama) 101: Yeni Başlayanlar İçin Rehber

Web crawling (web tarama) veya web scraping (web kazıma), internetteki devasa bilgi okyanusundan otomatik olarak veri toplama işlemine verilen isimdir. Google'ın arama motorunun temelinde de aynı teknoloji yatar: Botlar web sitelerini gezer, içeriklerini okur ve arama yapabilmeniz için kaydeder.

Bu rehber, daha önce hiç web crawling yapmamış biri için temel kavramları açıklamaktadır.

---

## 1. Web Crawler Nedir ve Nasıl Çalışır?

Bir web crawler'ı yorulmak bilmeyen, çok hızlı okuyan sanal bir kütüphaneci olarak düşünebilirsiniz. Temel çalışma mantığı şu 3 adımdan oluşur:

1. **Ziyaret Et (Fetch):** Crawler'a başlangıç noktası olarak bir URL (örneğin `wikipedia.org`) verirsiniz. Crawler bu adrese gider ve web sayfasının kaynak kodunu (HTML) bilgisayarınıza indirir. Tıpkı sizin tarayıcınızın yaptığı gibi.
2. **Oku ve Çıkar (Parse):** İndirilen HTML kodunun içinden sadece işinize yarayan kısımları (örneğin sayfa başlığı, makale metni veya ürün fiyatları) ayrıştırır ve veritabanına kaydeder.
3. **Yeni Yollar Bul (Discover):** Sayfanın içindeki diğer tıklanabilir bağlantıları (linkleri/URL'leri) bulur ve bunları "daha sonra ziyaret edilecekler listesine" (kuyruğa) ekler.

Crawler daha sonra kuyruktaki sıradaki linki alır ve aynı 3 adımı sonsuza kadar veya siz durdurana kadar tekrarlar.

---

## 2. Temel Kavramlar Sözlüğü

Büyük bir crawler projesiyle karşılaştığınızda şu terimleri sıkça duyarsınız:

- **Seed URL (Başlangıç URL'si):** Taramaya başlayacağınız ilk adres.
- **Queue (Kuyruk):** Crawler'ın henüz gitmediği ama gitmesi gereken linklerin tutulduğu liste. "Gidilecek yerler listesi" de diyebiliriz.
- **Depth (Derinlik):** Başlangıç noktasından ne kadar uzağa gideceğinizin sınırıdır.
  - `Depth 0`: Sadece Başlangıç URL'sini tara ve dur.
  - `Depth 1`: Başlangıç sayfasını ve o sayfanın içindeki tüm linkleri tara.
  - `Depth 2`: Başlangıç sayfasındaki linklerin içindeki linkleri de tara. Çıkarılan sayfa sayısı her derinlikte katlanarak (üstel) artar.
- **Deduplication (Çift Kayıt Engelleme):** Web'de aynı sayfaya giden milyonlarca farklı link olabilir. Crawler'ın aynı sayfayı tekrar tekrar taramasını engellemek için daha önce ziyaret edilen linklerin kaydını tutması gerekir.
- **Politeness (Nezaket/Bekleme Süresi):** Bir web sitesine saniyede binlerce istek atarsanız site çökebilir (buna DDoS saldırısı denir). Crawler'ların sayfalar arası geçişlerde birkaç saniye beklemesi "nezaket kuralı"dır.
- **User-Agent:** Web sunucusuna "Ben kimim?" bilgisini gönderen kimlik kartı. Tarayıcınızla girerseniz "Ben Chrome'um" der. Crawler ile girerseniz "Ben senin sitenden veri okuyan bir botum" veya sadece "Ben Safari'yim" diyerek kendini tanıtabilir. Birçok site (Wikipedia gibi) kimliğini açık etmeyen isimsiz istekleri (`HTTP 403 Forbidden` hatası vererek) engeller.

---

## 3. Crawler Geliştirirken Karşılaşılan Zorluklar

Küçük bir script yazıp bir sayfadan veri çekmek kolaydır. Ancak binlerce sayfayı taramak istediğinizde ciddi mühendislik problemleri başlar:

### A. Senkron vs. Asenkron (Hız Problemi)
Normalde kodunuz bir sayfayı indirmek için istek atar ve sayfa gelene kadar (belki 1-2 saniye) hiçbir şey yapmadan bekler (`HTTP İsteği -> Bekle -> Parse et -> İkinci İstek -> Bekle...`). 
Bunu çözmek için **Asenkron (Async)** mimari kullanılır. Crawler aynı anda yüzlerce sayfaya istek atar, hangisi hazır olursa onu indirip okur, beklerken zaman kaybetmez (Tıpkı bir restorandaki garsonun, yemeği pişmesini beklerken başka masadaki siparişi alması gibi).

### B. Veritabanı Kilitlenmesi (Database is Locked)
Crawler'ınız asenkron olarak saniyede 50 sayfayı tarayıp aynı veritabanı dosyasına yazmaya çalışırsa, veritabanı "Aynı anda çok kişi yazmaya çalışıyor!" diyerek hata verir. Bunu çözmek için istekler sıraya sokulur veya gelişmiş veritabanları (PostgreSQL vb.) kullanılır.

### C. Üstel Büyüme (Queue Patlaması)
Bir sayfada 100 link vardır. O 100 sayfanın her birinde de 100'er link vardır. Daha Derinlik 2'ye geldiğinizde kuyruğunuzda 10.000 link birikir. Depth 4'te 100 milyon linkiniz olur. Bilgisayarınızın belleğinin (`RAM`) bunu kaldırması için akıllı bir kuyruk yönetimi (Backpressure) şarttır.

### D. Yabancı Dil ve Karakter Sorunları (Metin Normalleştirme)
Dünyadaki her web sitesi metinleri standart ve hatasız biçimde sunmaz. Özellikle bir arama motoru / arama fonksiyonu entegre ederken "Büyük-Küçük Harf" dönüşümleri kritiktir. Türkçe'deki "I" harfi küçük harfe çevrilirken standart İngilizce modüllerinde "i" olur, "ı" olmaz. Bu basit hata, arama terimlerinin tamamen başarısız olmasına yol açar. Gelişmiş crawler'lar dili tanıyıp karakterleri doğru analiz edecek ("turkish_lower" gibi) akıllı filtrelere sahip olmalıdır.

### E. Kesintiler ve Veri Kaybını Önleme (Resilience & Resume)
Bir bilgisayarın gücü veya internet bağlantısı her zaman kesilebilir. Hedeflediğiniz 1 milyon sayfanın yarısındayken sistem çökerse baştan başlamak büyük zaman ve kaynak kaybıdır. Sağlam bir mimari, taranan son hedefleri, mevcut derinliği (`max_depth`) ve kuyruğun statüsünü kalıcı bir diskte (örn. SQLite Settings tablosu) yazmalıdır ki "Kaldığı Yerden Devam Et" dendiğinde sıfırdan değil, fişi çekildiği saniyeden itibaren kaldığı kuyruğu okuyarak devam edebilsin.

---

## 4. Etik ve Yasal Sınırlar

- **robots.txt:** Her web sitesinin ana dizininde bir `robots.txt` dosyası bulunur (örn: `google.com/robots.txt`). Bu dosya crawler botlarına "Şu sayfalara girebilirsin, şuraları taramak yasak" talimatı verir. İyi huylu crawler'lar bu dosyayı okur ve kurallarına uyar.
- **Özel Veriler:** Arkasında şifre olan, giriş yapmayı gerektiren veya kişisel/telifli verileri kazımak etik değildir ve yasadışı olabilir.
- **Sunucuya Yük Bindirme:** Aşırı hızlı tarama yapmak sitenin çökmesine ve size dava açılmasına sebep olabilir.

Artık web taramanın temel mantığını biliyorsunuz! Başlangıç için `Python` dili sıkça tercih edilir. Harici bağımlılıkları azaltıp dilin yerel imkanlarını kullanmak istiyorsanız (Language-native), Python standart kütüphanesindeki `html.parser` modülü ile harika crawler'lar inşa edilebilir.
