// Modified 2026-10-13 for PhotoLab Club: French localization, AI/dust review or standalone branding. See docs/MODIFICATIONS-CLUB.md.
//! Conservative, multi-scale sensor-dust proposals, not automatic scene cleanup.
//! Modified 2026-10-09: real-photo validation showed that fine scene detail was
//! being mistaken for dust and low-contrast spots lost behind the old 60-item cap.
use lightcraft_raster::{Plane, Rgb32f, Rgba8, blur::gaussian};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DustSpot {
    pub x: f64,
    pub y: f64,
    pub radius: f64,
    pub strength: f32,
    /// Relative signal/background quality, not a calibrated probability.
    pub quality: f32,
}

fn luminance(c: [f32; 3]) -> f32 {
    0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
fn rgb_at(rgb: &Rgb32f, x: f32, y: f32) -> [f32; 3] {
    rgb.sample_bilinear(x + 0.5, y + 0.5)
}

/// Search several sizes; require a round darkening, colour-neutral attenuation,
/// a locally explainable background and low surrounding high-frequency texture.
pub fn detect(img: &Rgba8, sensitivity: f32) -> Vec<DustSpot> {
    let (w, h) = (img.width, img.height);
    if w < 32 || h < 32 || w.checked_mul(h).is_none_or(|n| img.data.len() < n) {
        return vec![];
    }
    let long = w.max(h) as f32;
    let sensitivity = if sensitivity.is_finite() { sensitivity.clamp(0., 100.) } else { 50. };
    let rgb = Rgb32f::from_fn(w, h, |x, y| {
        let p = img.data[y * w + x];
        [p[0] as f32 / 255., p[1] as f32 / 255., p[2] as f32 / 255.]
    });
    let l = Plane::from_fn(w, h, |x, y| luminance(rgb.data[y * w + x]));
    let rgb = gaussian(&rgb, 0.7);
    let coarse = gaussian(&l, 1.5);
    let fine_bg = gaussian(&l, 2.0);
    let fine = Plane::from_fn(w, h, |x, y| (l.data[y * w + x] - fine_bg.data[y * w + x]).abs());
    let min_contrast = 0.006 * (1.5 - sensitivity / 100.);
    let min_quality = (20. - sensitivity * 0.2).max(4.);
    let angles: Vec<(f32, f32)> = (0..16)
        .map(|i| {
            let a = i as f32 * std::f32::consts::TAU / 16.;
            (a.cos(), a.sin())
        })
        .collect();
    let mut proposals = Vec::new();
    let mut previous_scale = 0.;
    for fraction in [0.00125, 0.001875, 0.0028125, 0.0040625, 0.005625, 0.008125, 0.01125] {
        let scale = (long * fraction).max(2.);
        if (scale - previous_scale).abs() < 0.1 {
            continue;
        }
        previous_scale = scale;
        let inner = gaussian(&l, scale * 0.45);
        let outer = gaussian(&l, scale * 2.);
        let response: Vec<f32> = outer.data.iter().zip(&inner.data).map(|(a, b)| a - b).collect();
        let r = scale * 1.4;
        let margin = (r * 5. + 2.).ceil() as usize;
        if margin.saturating_mul(2) >= w.min(h) {
            continue;
        }
        for y in margin..h - margin {
            for x in margin..w - margin {
                let i = y * w + x;
                let peak = response[i];
                if peak < min_contrast * 0.6 {
                    continue;
                }
                let mut maximum = true;
                for dy in -2isize..=2 {
                    for dx in -2isize..=2 {
                        if response[((y as isize + dy) as usize) * w + (x as isize + dx) as usize] > peak {
                            maximum = false;
                            break;
                        }
                    }
                }
                if !maximum {
                    continue;
                }
                let (xf, yf) = (x as f32, y as f32);
                // Symmetric annulus gives a small least-squares RGB background plane.
                let mut mean = [0.; 3];
                let mut bx = [0.; 3];
                let mut by = [0.; 3];
                let mut denom = 0.;
                let mut samples = Vec::with_capacity(48);
                for ring in [2.5, 3., 3.5] {
                    for (co, si) in &angles {
                        let (dx, dy) = (co * ring, si * ring);
                        let c = rgb_at(&rgb, xf + dx * r, yf + dy * r);
                        for channel in 0..3 {
                            mean[channel] += c[channel];
                            bx[channel] += c[channel] * dx;
                            by[channel] += c[channel] * dy;
                        }
                        denom += dx * dx;
                        samples.push((dx, dy, c));
                    }
                }
                for c in 0..3 {
                    mean[c] /= 48.;
                    bx[c] /= denom.max(1e-6);
                    by[c] /= denom.max(1e-6);
                }
                let center = rgb_at(&rgb, xf, yf);
                let contrast = luminance([mean[0] - center[0], mean[1] - center[1], mean[2] - center[2]]);
                if contrast < min_contrast || luminance(mean) < 0.08 {
                    continue;
                }
                let residual =
                    (samples.iter().map(|(dx, dy, c)| (0..3).map(|k| (c[k] - mean[k] - bx[k] * dx - by[k] * dy).powi(2)).sum::<f32>()).sum::<f32>()
                        / 144.)
                        .sqrt();
                if residual > 0.004_f32.max(contrast * 0.2) {
                    continue;
                }
                let quality = contrast / (residual + 0.0007);
                // On an exceptionally smooth background, quantization alone can
                // dominate a faint shadow. Keep those proposals without relaxing
                // the threshold in textured regions.
                let required_quality = if residual < 0.0015 { min_quality * 0.7 } else { min_quality };
                if quality < required_quality {
                    continue;
                }
                let sums = (center.iter().sum::<f32>().max(0.01), mean.iter().sum::<f32>().max(0.01));
                let chroma = (0..3).map(|c| (center[c] / sums.0 - mean[c] / sums.1).abs()).fold(0., f32::max);
                if chroma > 0.035 {
                    continue;
                }
                // Strong sharp specks are pixels or scene dirt, not a broad soft shadow.
                if contrast > 0.2 && luminance(mean) - coarse.data[i] < 0.78 * contrast {
                    continue;
                }
                let mut texture = Vec::with_capacity(48);
                for ring in [3., 4., 5.] {
                    for (co, si) in &angles {
                        let sx = (xf + co * ring * r).round() as usize;
                        let sy = (yf + si * ring * r).round() as usize;
                        texture.push(fine.data[sy * w + sx]);
                    }
                }
                texture.sort_by(f32::total_cmp);
                if texture.get(24).copied().unwrap_or(1.) > 0.004 || texture.get(38).copied().unwrap_or(1.) > 0.008 {
                    continue;
                }
                let mut profile = Vec::with_capacity(16);
                for (co, si) in &angles {
                    let c = rgb_at(&rgb, xf + co * r, yf + si * r);
                    profile.push(
                        luminance([
                            mean[0] + bx[0] * co + by[0] * si - c[0],
                            mean[1] + bx[1] * co + by[1] * si - c[1],
                            mean[2] + bx[2] * co + by[2] * si - c[2],
                        ]) / contrast,
                    );
                }
                let good = profile.iter().filter(|v| **v > 0.08 && **v < 0.9).count();
                let average = profile.iter().sum::<f32>() / 16.;
                let spread = (profile.iter().map(|v| (v - average).powi(2)).sum::<f32>() / 16.).sqrt();
                if good < 14 || spread > 0.10 {
                    continue;
                }
                proposals.push(DustSpot {
                    x: (xf as f64 + 0.5) / w as f64,
                    y: (yf as f64 + 0.5) / h as f64,
                    radius: (r * 2. / long) as f64,
                    strength: contrast,
                    quality,
                });
            }
        }
    }
    proposals.sort_by(|a, b| b.quality.total_cmp(&a.quality));
    let mut kept: Vec<DustSpot> = vec![];
    for candidate in proposals {
        if kept.iter().any(|other| {
            let dx = (candidate.x - other.x) * w as f64;
            let dy = (candidate.y - other.y) * h as f64;
            dx.hypot(dy) < candidate.radius.max(other.radius) * long as f64
        }) {
            continue;
        }
        kept.push(candidate);
        if kept.len() >= 256 {
            break;
        } // safety bound, not a target detection count
    }
    kept
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A smooth sky gradient with three soft dark spots: all found, nothing else.
    #[test]
    fn finds_spots_on_smooth_areas() {
        let (w, h) = (600usize, 400usize);
        let spots = [(120.0f32, 90.0f32, 4.0f32), (400.0, 200.0, 6.0), (500.0, 330.0, 3.0)];
        let data: Vec<[u8; 4]> = (0..w * h)
            .map(|i| {
                let (x, y) = ((i % w) as f32, (i / w) as f32);
                let mut v = 0.55 + 0.25 * (y / h as f32) + 0.05 * (x / w as f32);
                for (cx, cy, r) in spots {
                    let d2 = (x - cx).powi(2) + (y - cy).powi(2);
                    v -= 0.06 * (-d2 / (2.0 * r * r)).exp();
                }
                let b = (v * 255.0) as u8;
                [b, b, (b as f32 * 1.1).min(255.0) as u8, 255]
            })
            .collect();
        let found = detect(&Rgba8 { width: w, height: h, data }, 50.0);
        assert_eq!(found.len(), 3, "{found:?}");
        for (cx, cy, _) in spots {
            assert!(
                found.iter().any(|s| (s.x * w as f64 - cx as f64).abs() < 3.0 && (s.y * h as f64 - cy as f64).abs() < 3.0),
                "{cx},{cy}: {found:?}"
            );
        }
    }

    #[test]
    fn textured_scenes_give_few_false_spots() {
        let img = lightcraft_scenes::demo_library()[2].render(600, 400);
        let data = img
            .data
            .iter()
            .map(|c| {
                let e = |v: f32| (lightcraft_color::transfer::linear_to_srgb(v.clamp(0.0, 1.0)) * 255.0) as u8;
                [e(c[0]), e(c[1]), e(c[2]), 255]
            })
            .collect();
        let found = detect(&Rgba8 { width: 600, height: 400, data }, 50.0);
        assert!(found.len() <= 3, "{} false spots", found.len());
    }

    #[test]
    fn isolated_pixel_noise_is_not_sensor_dust() {
        let (w, h) = (400usize, 300usize);
        let mut data = vec![[175, 175, 175, 255]; w * h];
        for y in (20..h - 20).step_by(35) {
            for x in (20..w - 20).step_by(35) {
                for dy in 0..2 {
                    for dx in 0..2 {
                        data[(y + dy) * w + x + dx] = [80, 80, 80, 255];
                    }
                }
            }
        }
        let found = detect(&Rgba8 { width: w, height: h, data }, 50.0);
        assert!(found.is_empty(), "Pixel noise mistaken for dust: {}", found.len());
    }

    #[test]
    fn faint_neutral_dust_is_found_but_coloured_scene_details_are_not() {
        let (w, h) = (600usize, 400usize);
        let data = (0..w * h)
            .map(|i| {
                let (x, y) = ((i % w) as f32, (i / w) as f32);
                let dust = 0.016 * (-((x - 180.).powi(2) + (y - 100.).powi(2)) / (2. * 25.)).exp();
                let scene = (-((x - 420.).powi(2) + (y - 240.).powi(2)) / (2. * 36.)).exp();
                let mut rgb = [0.55 + 0.04 * x / w as f32; 3];
                for value in &mut rgb {
                    *value -= dust;
                }
                rgb[0] -= scene * 0.18;
                rgb[1] -= scene * 0.03;
                rgb[2] -= scene * 0.08;
                [(rgb[0] * 255.) as u8, (rgb[1] * 255.) as u8, (rgb[2] * 255.) as u8, 255]
            })
            .collect();
        let found = detect(&Rgba8 { width: w, height: h, data }, 50.);
        assert!(found.iter().any(|p| (p.x * w as f64 - 180.).hypot(p.y * h as f64 - 100.) < 4.), "faint dust missed: {found:?}");
        assert!(!found.iter().any(|p| (p.x * w as f64 - 420.).hypot(p.y * h as f64 - 240.) < 20.), "coloured detail selected: {found:?}");
    }
}
