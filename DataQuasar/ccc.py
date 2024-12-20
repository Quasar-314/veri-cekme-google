@dataclass
class İşletme:
    """İşletme verilerini tutar"""
    isim: str = None
    adres: str = None
    website: str = None
    telefon: str = None   
    ortalama_puan: float = None
    enlem: float = None
    boylam: float = None
    

@dataclass
class İşletmeListesi:
    """İşletme nesnelerinin listesini tutar ve Excel'e kaydeder"""
    isletme_listesi: list[İşletme] = field(default_factory=list)
    kayit_yolu = 'cikti'

    def veri_cercevesi(self):
        """işletme_listesini pandas veri çerçevesine dönüştürür"""
        return pd.json_normalize(
            (asdict(isletme) for isletme in self.isletme_listesi), sep="_"
        )

    def excele_kaydet(self, dosya_adi):
        """Veri çerçevesini Excel dosyasına kaydeder"""
        if not os.path.exists(self.kayit_yolu):
            os.makedirs(self.kayit_yolu)
        self.veri_cercevesi().to_excel(f"cikti/{dosya_adi}.xlsx", index=False)



class VeriÇekmeThread(QThread):
    sinyal_guncelle = pyqtSignal(list)
    sinyal_tamamlandi = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.arama_terimleri = []
        self.veri_sınırı = None

    def arama_ayarla(self, arama_terimleri):
        self.arama_terimleri = arama_terimleri

    def koordinatlari_ayikla(self, url: str) -> tuple[float, float]:
        """URL'den koordinatları ayıklar"""
        koordinatlar = url.split('/@')[-1].split('/')[0]
        return float(koordinatlar.split(',')[0]), float(koordinatlar.split(',')[1])

    def tum_listeyi_yukle(self, tarayici, wait):
        """Tüm liste görünene kadar sayfayı kaydırır"""
        print("\nListe yükleme başlıyor...")
        son_yukseklik = 0
        ayni_yukseklik_sayaci = 0
        scroll_sayisi = 0

        while True:
            try:
                # Scroll yapmadan önce mevcut link sayısını kontrol et
                onceki_link_sayisi = len(tarayici.find_elements(
                    By.XPATH, '//a[contains(@href, "https://www.google.com/maps/place")]'
                ))
                
                # Sayfayı kaydır
                tarayici.execute_script("""
                    var feed = document.querySelector('div[role="feed"]');
                    if (feed) {
                        feed.scrollTo(0, feed.scrollHeight);
                    } else {
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                """)
                time.sleep(3)  # Yükleme için biraz daha uzun bekle

                # Scroll sonrası link sayısını kontrol et
                sonraki_link_sayisi = len(tarayici.find_elements(
                    By.XPATH, '//a[contains(@href, "https://www.google.com/maps/place")]'
                ))

                # Mevcut yüksekliği kontrol et
                yeni_yukseklik = tarayici.execute_script("""
                    var feed = document.querySelector('div[role="feed"]');
                    return feed ? feed.scrollHeight : document.body.scrollHeight;
                """)

                scroll_sayisi += 1
                print(f"\nScroll #{scroll_sayisi}")
                print(f"Önceki link sayısı: {onceki_link_sayisi}")
                print(f"Sonraki link sayısı: {sonraki_link_sayisi}")
                print(f"Önceki yükseklik: {son_yukseklik}")
                print(f"Yeni yükseklik: {yeni_yukseklik}")

                if yeni_yukseklik == son_yukseklik and sonraki_link_sayisi == onceki_link_sayisi:
                    ayni_yukseklik_sayaci += 1
                    print(f"Aynı yükseklik sayacı: {ayni_yukseklik_sayaci}")
                else:
                    ayni_yukseklik_sayaci = 0
                    son_yukseklik = yeni_yukseklik

                # Daha agresif scroll için sayfayı biraz yukarı da kaydır
                if ayni_yukseklik_sayaci >= 2:
                    print("Yukarı scroll deneniyor...")
                    tarayici.execute_script("""
                        var feed = document.querySelector('div[role="feed"]');
                        if (feed) {
                            feed.scrollTo(0, feed.scrollHeight - 1000);
                        }
                    """)
                    time.sleep(2)

                if ayni_yukseklik_sayaci >= 5:
                    print(f"\nListe yükleme tamamlandı!")
                    print(f"Toplam bulunan link sayısı: {sonraki_link_sayisi}")
                    break

            except Exception as e:
                print(f'\nListe yükleme hatası: {e}')
                break

        # En başa dön
        print("\nListe başına dönülüyor...")
        tarayici.execute_script("""
            var feed = document.querySelector('div[role="feed"]');
            if (feed) {
                feed.scrollTo(0, 0);
            } else {
                window.scrollTo(0, 0);
            }
        """)
        time.sleep(2)

    def run(self):
        options = webdriver.ChromeOptions()
        service = Service(ChromeDriverManager().install())
        tarayici = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(tarayici, 10)

        try:
            tarayici.get("https://www.google.com/maps")
            time.sleep(5)

            tum_isletmeler = []

            for arama_terimi in self.arama_terimleri:
                print(f"\nArama terimi: {arama_terimi}")
                isletme_listesi = İşletmeListesi()
                
                try:
                    # Arama yap
                    arama_kutusu = wait.until(
                        lambda x: x.find_element(By.ID, "searchboxinput")
                    )
                    arama_kutusu.clear()
                    arama_kutusu.send_keys(arama_terimi)
                    time.sleep(3)
                    arama_kutusu.send_keys(Keys.ENTER)
                    time.sleep(5)

                    # Önce tüm listeyi yükle
                    self.tum_listeyi_yukle(tarayici, wait)

                    # Şimdi tüm işletmeleri işle
                    islenen_linkler = set()
                    scroll_position = 0
                    son_scroll_position = 0
                    ayni_position_sayaci = 0

                    while True:
                        try:
                            # Görünür tüm işletme linklerini bul
                            isletme_linkleri = tarayici.find_elements(
                                By.XPATH, '//a[contains(@href, "https://www.google.com/maps/place")]'
                            )
                            
                            print(f"\nBulunan toplam link sayısı: {len(isletme_linkleri)}")
                            print(f"İşlenen link sayısı: {len(islenen_linkler)}")
                            
                            yeni_link_bulundu = False
                            for link in isletme_linkleri:
                                try:
                                    href = link.get_attribute('href')
                                    if href and href not in islenen_linkler:
                                        yeni_link_bulundu = True
                                        islenen_linkler.add(href)
                                        
                                        print(f"\nYeni işletme işleniyor... ({len(islenen_linkler)})")
                                        
                                        # İşletmeye scroll yap ve tıkla
                                        tarayici.execute_script("arguments[0].scrollIntoView(true);", link)
                                        time.sleep(1)
                                        link.click()
                                        time.sleep(4)

                                        # Verileri çek
                                        isletme = self.isletme_verilerini_cek(tarayici)
                                        isletme_listesi.isletme_listesi.append(isletme)
                                        print(f"İşletme adı: {isletme.isim}")
                                        
                                        # Her 10 işletmede bir kaydet
                                        if len(isletme_listesi.isletme_listesi) % 10 == 0:
                                            isletme_listesi.excele_kaydet(
                                                f"{arama_terimi}".replace(' ', '_')
                                            )
                                        
                                        self.sinyal_guncelle.emit([
                                            arama_terimi, 
                                            str(len(isletme_listesi.isletme_listesi))
                                        ])
                                        
                                        # Listeye geri dön
                                        tarayici.back()
                                        time.sleep(3)

                                except Exception as e:
                                    print(f'İşletme verisi çekilirken hata oluştu: {e}')
                                    continue

                            # Scroll pozisyonunu kontrol et
                            scroll_position = tarayici.execute_script("""
                                var feed = document.querySelector('div[role="feed"]');
                                return feed ? feed.scrollTop : window.pageYOffset;
                            """)

                            print(f"Scroll pozisyonu: {scroll_position}")
                            print(f"Son scroll pozisyonu: {son_scroll_position}")

                            if scroll_position == son_scroll_position:
                                ayni_position_sayaci += 1
                            else:
                                ayni_position_sayaci = 0
                                son_scroll_position = scroll_position

                            # Eğer yeni link bulunamadıysa ve pozisyon değişmiyorsa
                            if not yeni_link_bulundu and ayni_position_sayaci >= 3:
                                print("\nYeni işletme bulunamadı ve scroll pozisyonu değişmiyor.")
                                print(f"Toplam işlenen işletme sayısı: {len(islenen_linkler)}")
                                break

                            # Sayfayı biraz aşağı kaydır
                            tarayici.execute_script("""
                                var feed = document.querySelector('div[role="feed"]');
                                if (feed) {
                                    feed.scrollBy(0, 300);
                                } else {
                                    window.scrollBy(0, 300);
                                }
                            """)
                            time.sleep(2)

                        except Exception as e:
                            print(f'İşletme listesi işlenirken hata oluştu: {e}')
                            print(f"Hata detayı: {str(e)}")
                            break

                    # Son kez Excel'e kaydet
                    isletme_listesi.excele_kaydet(f"{arama_terimi}".replace(' ', '_'))
                    tum_isletmeler.extend(isletme_listesi.isletme_listesi)

                except Exception as e:
                    print(f"Arama işlemi başarısız: {e}")
                    print(f"Hata detayı: {str(e)}")
                    continue

        finally:
            tarayici.quit()
            self.sinyal_tamamlandi.emit(tum_isletmeler)