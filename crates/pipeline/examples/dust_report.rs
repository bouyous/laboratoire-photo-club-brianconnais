// Modified 2026-10-13 for PhotoLab Club: French localization, AI/dust review or standalone branding. See docs/MODIFICATIONS-CLUB.md.
use serde_json::json;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).ok_or("image path required")?;
    let image = image::open(path)?.resize(1600, 1600, image::imageops::FilterType::Lanczos3).to_rgba8();
    let img =
        lightcraft_raster::Rgba8 { width: image.width() as usize, height: image.height() as usize, data: image.pixels().map(|p| p.0).collect() };
    let found = lightcraft_pipeline::dust::detect(&img, 50.);
    println!(
        "{}",
        json!({"width":img.width,"height":img.height,"spots":found.iter().map(|p|json!({"x":p.x,"y":p.y,"size":p.radius,"quality":p.quality})).collect::<Vec<_>>()})
    );
    Ok(())
}
