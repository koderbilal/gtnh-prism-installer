"""Tiny Turkish/English string table (UI language follows the OS locale unless overridden)."""

from __future__ import annotations

import locale
import os

_lang = "en"

STRINGS: dict[str, tuple[str, str]] = {
    # key: (Türkçe, English)
    "app_title": ("GTNH Prism Yükleyici", "GTNH Prism Installer"),
    "prism_folder": ("Prism Launcher klasörü:", "Prism Launcher folder:"),
    "browse": ("Gözat…", "Browse…"),
    "instances_folder": ("Örnekler klasörü: {path}", "Instances folder: {path}"),
    "prism_not_found": (
        "Prism Launcher klasörü bulunamadı. Lütfen elle seçin.",
        "Prism Launcher folder not found. Please choose it manually.",
    ),
    "tab_install": ("Kur", "Install"),
    "tab_update": ("Yükselt", "Update"),
    "col_version": ("Sürüm", "Version"),
    "col_date": ("Tarih", "Date"),
    "col_channel": ("Kanal", "Channel"),
    "col_java": ("En yüksek Java", "Max Java"),
    "channel_stable": ("Kararlı", "Stable"),
    "channel_beta": ("Beta/Özel", "Beta/Special"),
    "show_beta": ("Beta ve özel sürümleri göster", "Show beta and special versions"),
    "refresh": ("Yenile", "Refresh"),
    "changelog": ("Değişiklik günlüğü", "Changelog"),
    "loading_versions": ("Sürümler yükleniyor…", "Loading versions…"),
    "variant": ("Paket türü:", "Pack type:"),
    "variant_modern": ("Java 17+ (önerilen)", "Java 17+ (recommended)"),
    "variant_java8": ("Java 8 (eski)", "Java 8 (legacy)"),
    "instance_name": ("Örnek adı:", "Instance name:"),
    "install_btn": ("Kur", "Install"),
    "update_btn": ("Yükselt", "Update"),
    "cancel": ("İptal", "Cancel"),
    "java_group": ("Java", "Java"),
    "java_override": ("Java kurulumu", "Java installation"),
    "java_exe": ("Java çalıştırılabilir dosyası:", "Java executable:"),
    "java_installed": ("Kurulu Java:", "Installed Java:"),
    "java_download": ("Java indir…", "Download Java…"),
    "java_test": ("Ayarları test et", "Test settings"),
    "java_skip_compat": ("Java uyumluluk kontrollerini atla", "Skip Java compatibility checks"),
    "java_test_ok": ("Java {major} çalışıyor:\n{line}", "Java {major} works:\n{line}"),
    "java_test_fail": ("Java çalıştırılamadı:\n{line}", "Could not run Java:\n{line}"),
    "java_incompatible": (
        "Java {major}, bu paketle uyumlu görünmüyor (önerilen: {rec}). Yine de devam edilsin mi?",
        "Java {major} does not look compatible with this pack (recommended: {rec}). Continue anyway?",
    ),
    "java_dialog_title": ("Java'yı Yükle", "Install Java"),
    "java_vendor_hdr": ("Sağlayıcı", "Vendor"),
    "java_major_hdr": ("Ana sürüm", "Major version"),
    "java_col_version": ("Sürüm", "Version"),
    "java_col_name": ("Java adı", "Java name"),
    "java_col_released": ("Yayınlanma", "Released"),
    "java_col_type": ("Tür", "Type"),
    "recommended": ("Önerilen", "Recommended"),
    "download": ("İndir", "Download"),
    "search": ("Ara", "Search"),
    "no_builds": ("Bu platform için sürüm bulunamadı", "No builds for this platform"),
    "update_instance": ("Yükseltilecek örnek:", "Instance to update:"),
    "detected_version": ("Algılanan sürüm: {v}", "Detected version: {v}"),
    "unknown": ("bilinmiyor", "unknown"),
    "target_version": ("Hedef sürüm:", "Target version:"),
    "skip_major_warning": (
        "Uyarı: GTNH, tek seferde yalnızca bir ana sürüm atlayarak (örn. 2.6 → 2.7) güncellemeyi öneriyor. "
        "Önce ara sürüme yükseltin.",
        "Warning: GTNH recommends updating one major version at a time (e.g. 2.6 → 2.7). "
        "Update to the intermediate version first.",
    ),
    "always_group": ("Her zaman aktarılır (varsa)", "Always migrated (if present)"),
    "always_text": (
        "saves, journeymap, visualprospecting, TCNodeTracker, resourcepacks, shaderpacks, schematics, screenshots, "
        "backups, ESM, options.txt, optionsnf.txt, servers.dat, localconfig.cfg, BotaniaVars.dat, "
        "vendingmachine favourites, shaders.properties",
        "saves, journeymap, visualprospecting, TCNodeTracker, resourcepacks, shaderpacks, schematics, screenshots, "
        "backups, ESM, options.txt, optionsnf.txt, servers.dat, localconfig.cfg, BotaniaVars.dat, "
        "vendingmachine favourites, shaders.properties",
    ),
    "optional_group": ("Opsiyonel (işaretleyin)", "Optional (tick what you want)"),
    "opt_ingameinfo": ("Oyun içi bilgi HUD ayarları (InGameInfoXML)", "In-game info HUD (InGameInfoXML)"),
    "opt_pollution": ("Kirlilik ayarı (GregTech/Pollution.cfg)", "Pollution setting (GregTech/Pollution.cfg)"),
    "opt_menu_music": ("Ana menü müziği ayarı (txloader sounds.json)", "Main menu music (txloader sounds.json)"),
    "opt_space_elevator": (
        "Uzay asansörü animasyonu (gtnhintergalactic.cfg)",
        "Space Elevator animation (gtnhintergalactic.cfg)",
    ),
    "opt_lwjgl3ify": ("Kenarlıksız tam ekran (lwjgl3ify.cfg)", "Borderless fullscreen (lwjgl3ify.cfg)"),
    "opt_tesla_tower": ("Tesla Kulesi animasyonu (tectech.cfg)", "Tesla Tower animation (tectech.cfg)"),
    "opt_tinkers_layout": (
        "Klasik Tinkers tezgâhı (TinkersConstruct.cfg)",
        "Classic Tinkers crafting station (TinkersConstruct.cfg)",
    ),
    "opt_serverutilities": (
        "ServerUtilities (rütbeler, evler, chunk yükleme) — riskli olabilir",
        "ServerUtilities (ranks, homes, chunk loading) — may be risky",
    ),
    "opt_mods": ("Ek olarak kurduğum modlar", "Additional mods I installed"),
    "opt_mods_choose": ("Seç…", "Choose…"),
    "opt_memory": ("Bellek (RAM) ayarlarını aktar", "Carry over memory (RAM) settings"),
    "opt_jvm_args": ("Özel JVM argümanlarını aktar", "Carry over custom JVM arguments"),
    "mods_dialog_title": ("Aktarılacak modlar", "Mods to carry over"),
    "mods_none": ("Yeni pakette olmayan ek mod bulunamadı.", "No extra mods found compared to the new pack."),
    "mods_hint": (
        "Eski örnekte olup yeni paketin içermediği modlar. Aktarmak istediklerinizi seçin.",
        "Mods in the old instance that the new pack doesn't ship. Select the ones to carry over.",
    ),
    "mods_hint_all": (
        "Eski paketin mod listesi alınamadı; tüm modlar listeleniyor. Yalnızca kendi eklediklerinizi seçin.",
        "Could not read the stock mod list; showing all mods. Select only the ones you added yourself.",
    ),
    "ok": ("Tamam", "OK"),
    "no_instance": ("Yükseltilecek bir örnek seçin.", "Select an instance to update."),
    "no_prism": ("Önce geçerli bir Prism klasörü seçin.", "Choose a valid Prism folder first."),
    "no_version": ("Bir sürüm seçin.", "Select a version."),
    "keep_zip": ("İndirilen zip'i sakla", "Keep downloaded zip"),
    "backup_notice": (
        "Eski örneğiniz silinmez ve değiştirilmez; veriler yeni örneğe kopyalanır. "
        "Yine de önemli dünyalarınızı yedekleyin.",
        "Your old instance is never deleted or modified; data is copied to the new instance. "
        "Back up important worlds anyway.",
    ),
    "done_install": ("Kurulum tamamlandı:\n{path}", "Installation finished:\n{path}"),
    "done_update": (
        "Yükseltme tamamlandı:\n{path}\n\nDünyayı ilk açışınızda 'eksik blok/eşya' sorusuna Evet deyin "
        "(sunucuda /fml confirm). Onayladıktan sonra eski sürüme dönülemez.",
        "Update finished:\n{path}\n\nConfirm the 'missing blocks/items' prompt when first loading a world "
        "(servers: /fml confirm). After confirming you cannot go back to the old version.",
    ),
    "cancelled": ("İptal edildi.", "Cancelled."),
    "error": ("Hata", "Error"),
    "info": ("Bilgi", "Info"),
    "warning": ("Uyarı", "Warning"),
    "java_ready": ("Java hazır: {path}", "Java ready: {path}"),
}


def detect_language() -> str:
    env = os.environ.get("GTNH_LANG")
    if env:
        return "tr" if env.lower().startswith("tr") else "en"
    try:
        code = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        code = os.environ.get("LANG", "")
    return "tr" if (code or "").lower().startswith("tr") else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = "tr" if lang.lower().startswith("tr") else "en"


def t(key: str, **kw) -> str:
    pair = STRINGS.get(key)
    text = pair[0 if _lang == "tr" else 1] if pair else key
    return text.format(**kw) if kw else text


set_language(detect_language())
