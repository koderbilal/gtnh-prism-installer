# GTNH Prism Installer

GregTech: New Horizons (GTNH) sürümlerini listeleyip **Prism Launcher**'a kuran ve resmi
"Updating → Method 1" rehberindeki dosya aktarımını yapan Windows/Linux programı (GUI + CLI).

## Özellikler
- GTNH sürüm listesini resmi `versions.json` manifestinden çeker; sürümü seçip Prism'e örnek (instance) olarak kurar.
- Java seçimi Prism'deki gibi: Mojang / Adoptium / Azul Zulu / IBM Semeru, ana sürüm, sürüm tablosu,
  "Önerilen" filtresi, ya da kendi `java`/`javaw` yolunuz. Ayarlar örneğin `instance.cfg` dosyasına yazılır.
- **Yükseltme:** eski örnekten yeni örneğe rehberdeki dosyaları kopyalar (eski örnek asla silinmez/değiştirilmez).
  İsteğe bağlı adımlar onay kutusudur: GregTech Pollution, ana menü müziği, Space Elevator animasyonu,
  lwjgl3ify tam ekran, Tesla Tower animasyonu, Tinkers klasik tezgah, InGameInfoXML, ServerUtilities,
  ek modlar, bellek ve JVM argümanları.
- Büyük sürüm atlama uyarısı (2.6 → 2.8 gibi); CLI'da `--force` gerekir.
- Arayüz Türkçe/İngilizce (`--lang tr|en`, ya da `GTNH_LANG`).

## Kullanım
GUI: `gtnh-prism-installer` (argümansız). CLI: `gtnh-prism-installer-cli`

```
gtnh-prism-installer-cli list [--all]
gtnh-prism-installer-cli instances
gtnh-prism-installer-cli java-list adoptium 21
gtnh-prism-installer-cli install 2.9.2 --java adoptium:25
gtnh-prism-installer-cli update 2.9.2 --from "GT New Horizons 2.8.4" --java adoptium:25 --optional pollution,menu_music
```
`--optional` değerleri: `ingameinfo, pollution, menu_music, space_elevator, lwjgl3ify, tesla_tower, tinkers_layout, serverutilities` (veya `all`).

Yükseltmeden sonra dünyayı ilk açtığınızda "missing blocks/items" sorarsa **Yes** deyin
(sunucuda `/fml confirm`). Yine de dünyalarınızı yedekleyin.

## Geliştirme
```
pip install -r requirements-dev.txt
python -m pytest -q
python run_gtnh_installer.py
pyinstaller --onefile --windowed --name gtnh-prism-installer run_gtnh_installer.py
```
GitHub Actions (`.github/workflows/build.yml`) test eder, Windows ve Linux çalıştırılabilirlerini üretir;
`v*` etiketinde release'e ekler.

## Notlar
Adoptium ve Semeru kurulumları canlı test edildi. GTNH indirme sunucusu, Azul ve Mojang uçları
geliştirme ortamından erişilemediği için sahte sunucu/fixture ile test edildi.
