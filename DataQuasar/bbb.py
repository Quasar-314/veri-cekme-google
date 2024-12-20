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

    def arama_ayarla(self, arama_terimleri):
        self.arama_terimleri = arama_terimleri

    def koordinatlari_ayikla(self, url: str) -> tuple[float, float]:
        """URL'den koordinatları ayıklar"""
        koordinatlar = url.split('/@')[-1].split('/')[0]
        return float(koordinatlar.split(',')[0]), float(koordinatlar.split(',')[1])

    def run(self):
        with sync_playwright() as p:
            tarayici = p.chromium.launch(headless=False)
            sayfa = tarayici.new_page()
            sayfa.goto("https://www.google.com/maps", timeout=60000)
            sayfa.wait_for_timeout(5000)

            tum_isletmeler = []

            for arama_terimi in self.arama_terimleri:
                isletme_listesi = İşletmeListesi()
                sayfa.locator('//input[@id="searchboxinput"]').fill(arama_terimi)
                sayfa.wait_for_timeout(3000)
                sayfa.keyboard.press("Enter")
                sayfa.wait_for_timeout(5000)

                # Kaydırma ve veri toplama işlemi
                sayfa.hover('//a[contains(@href, "https://www.google.com/maps/place")]')
                onceki_sayim = 0

                while True:
                    sayfa.mouse.wheel(0, 10000)
                    sayfa.wait_for_timeout(3000)

                    listings = sayfa.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()

                    if len(listings) == onceki_sayim:
                        break
                    else:
                        onceki_sayim = len(listings)
                        self.sinyal_guncelle.emit([arama_terimi, str(len(listings))])

                    # Sınır kontrolü
                    if self.veri_sınırı and len(listings) >= self.veri_sınırı:
                        break

                # Belirlenen sınır kadar işletme çek
                for liste in listings[:self.veri_sınırı or len(listings)]:
                    try:
                        liste.click()
                        sayfa.wait_for_timeout(5000)

                        # Title etiketinden ismi al
                        title_text = sayfa.title()
                        isim = title_text.split(' - ')[0] if ' - ' in title_text else title_text

                        adres_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                        website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                        telefon_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'                       
                        puan_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]'
                        

                        isletme = İşletme()
                        isletme.isim = isim

                        isletme.adres = sayfa.locator(adres_xpath).inner_text() if sayfa.locator(adres_xpath).count() > 0 else ""
                        isletme.website = sayfa.locator(website_xpath).inner_text() if sayfa.locator(website_xpath).count() > 0 else ""
                        isletme.telefon = sayfa.locator(telefon_xpath).inner_text() if sayfa.locator(telefon_xpath).count() > 0 else ""
                        
                        
                        
                        if sayfa.locator(puan_xpath).count() > 0:
                            isletme.ortalama_puan = float(sayfa.locator(puan_xpath).get_attribute('aria-label').split()[0].replace(',','.'))
                        else:
                            isletme.ortalama_puan = 0.0

                        isletme.enlem, isletme.boylam = self.koordinatlari_ayikla(sayfa.url)

                        isletme_listesi.isletme_listesi.append(isletme)
                    except Exception as e:
                        print(f'Hata oluştu: {e}')
                        continue

                # Excel'e kaydet
                isletme_listesi.excele_kaydet(f"{arama_terimi}".replace(' ', '_'))
                tum_isletmeler.extend(isletme_listesi.isletme_listesi)

            tarayici.close()
            self.sinyal_tamamlandi.emit(tum_isletmeler)
