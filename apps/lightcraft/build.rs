// Modified 2026-10-13 for PhotoLab Club: French localization, AI/dust review or standalone branding. See docs/MODIFICATIONS-CLUB.md.
//! Windows only: embed the app icon and version info (VERSIONINFO) into `lightcraft.exe`, so
//! Explorer, the taskbar, the Start menu and Alt-Tab show the lynx.
//!
//! On every other target this does nothing. A missing resource compiler is a warning, so a
//! cross-compile from macOS or Linux still links, unless `LIGHTCRAFT_REQUIRE_WINRES=1` turns it
//! into an error (for release builds).

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=../../assets/club/club.ico");
    println!("cargo:rerun-if-env-changed=LIGHTCRAFT_REQUIRE_WINRES");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }
    let mut res = winresource::WindowsResource::new();
    res.set_icon("../../assets/club/club.ico")
        .set("ProductName", "PhotoLab Club Briançonnais")
        .set("ProductVersion", "0.5.0")
        .set("FileVersion", "0.5.0")
        .set("FileDescription", "PhotoLab Club - bibliotheque photo et retouche IA")
        .set("LegalCopyright", "Copyright (c) the LightCraft authors. MIT OR Apache-2.0.")
        .set("OriginalFilename", "lightcraft.exe")
        .set("InternalName", "lightcraft");
    if let Err(e) = res.compile() {
        if std::env::var_os("LIGHTCRAFT_REQUIRE_WINRES").is_some() {
            panic!("embedding Windows resources failed: {e}");
        }
        println!("cargo:warning=lightcraft.exe built without icon/version resources: {e}");
    }
}
