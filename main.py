from crawler_service import CrawlerService
from database import get_stats, run_init_db, search, set_setting, get_setting


def main():
    crawler = CrawlerService(worker_count=30, queue_maxsize=1000)
    crawler.start_background_loop()
    run_init_db()

    try:
        while True:
            print("\n1. Yeni Tarama Başlat (Index)")
            print("2. Taramaya Devam Et (Resume)")
            print("3. Arama Yap (Search)")
            print("4. Sistem Durumunu Göster (Stats)")
            print("0. Çıkış")
            secim = input("Seçiminiz: ").strip()

            if secim == "1":
                origin = input("Başlangıç URL: ").strip()
                k = int(input("Derinlik (k): ").strip())
                set_setting('max_depth', str(k))
                ok, msg = crawler.start_indexing(origin, k, resume_only=False)
                if ok:
                    print("Tarama arka planda başlatıldı. CLI kullanılmaya devam edilebilir.")
                else:
                    print(msg)

            elif secim == "2":
                print("Kuyruktaki bekleyen işlerden taramaya devam ediliyor...")
                k_str = get_setting('max_depth')
                if k_str is None:
                    print("Önceki taramaya ait derinlik bilgisi bulunamadı. Lütfen önce yeni bir tarama başlatın.")
                    continue
                k = int(k_str)
                print(f"Önceki tarama derinliği bulundu: {k}")
                
                ok, msg = crawler.start_indexing(resume_only=True, max_depth=k)
                if ok:
                    print(f"Devam etme işlemi (hedef derinlik: {k}) arka planda başlatıldı.")
                else:
                    print(msg)

            elif secim == "3":
                q = input("Arama kelimesi: ").strip()
                results = search(q)
                if not results:
                    print("Sonuç bulunamadı.")
                else:
                    print(f"\nSonuçlar ({len(results)} adet):")
                    for i, (url, origin_url, depth) in enumerate(results[:20], 1):
                        print(f"  {i}. URL: {url}")
                        print(f"     Origin: {origin_url} | Depth: {depth}")

            elif secim == "4":
                pages_count, pending_count, processing_count, backpressure = get_stats()
                print(
                    f"Şu an taranan sayfa sayısı: {pages_count}, "
                    f"Kuyrukta (Bekleyen: {pending_count}, İşlenen: {processing_count}), "
                    f"Backpressure durumu: {backpressure}"
                )

            elif secim == "0":
                print("Çıkılıyor...")
                break

            else:
                print("Geçersiz seçim, tekrar deneyin.")

    finally:
        crawler.shutdown()


if __name__ == "__main__":
    main()