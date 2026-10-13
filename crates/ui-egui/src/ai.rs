// Modified 2026-10-13 for PhotoLab Club: French localization, AI/dust review or standalone branding. See docs/MODIFICATIONS-CLUB.md.
//! Local PhotoLab AI bridge. Modified 2026-10-09 for the club prototype.
//! The Rust renderer hands a linear-sRGB float TIFF to a separate process.
//! Originals are never written; each successful job creates a new derived TIFF.
use crate::{
    LightcraftApp,
    state::{RightPanel, ViewMode},
};
use egui::{Color32, Rect, Stroke};
use lightcraft_catalog::PhotoId;
use lightcraft_engine::export::{ExportOptions, prepare_export, write_file_durable};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct BrushStroke {
    pub points: Vec<[f32; 2]>,
    pub radius: f32,
}

#[derive(Clone, Deserialize)]
pub struct Runtime {
    #[serde(default)]
    pub python: Option<PathBuf>,
    pub worker: PathBuf,
    #[serde(default)]
    pub photolab_source: PathBuf,
    pub models: PathBuf,
    pub results: PathBuf,
}

impl Runtime {
    fn load() -> Result<Self, String> {
        let path = std::env::var_os("LIGHTCRAFT_AI_CONFIG")
            .map(PathBuf::from)
            .or_else(|| std::env::current_exe().ok().and_then(|p| p.parent().map(|p| p.join("ai-runtime.json"))))
            .ok_or("Configuration IA introuvable")?;
        let mut config: Self = serde_json::from_slice(&std::fs::read(&path).map_err(|e| format!("Configuration IA : {e}"))?)
            .map_err(|e| format!("Configuration IA invalide : {e}"))?;
        let base = path.parent().ok_or("Dossier IA introuvable")?;
        for p in [&mut config.worker, &mut config.models, &mut config.photolab_source] {
            if p.is_relative() {
                *p = base.join(&*p);
            }
        }
        if let Some(python) = &mut config.python
            && python.is_relative()
        {
            *python = base.join(&*python);
        }
        if config.results.is_relative() {
            let home = std::env::var_os("PHOTOLAB_CLUB_DATA")
                .map(PathBuf::from)
                .or_else(|| std::env::var_os("LOCALAPPDATA").map(|p| PathBuf::from(p).join("PhotoLabClub")))
                .or_else(|| std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".local/share/PhotoLabClub")))
                .ok_or("Dossier personnel introuvable pour enregistrer les résultats IA")?;
            config.results = home.join(&config.results);
        }
        for p in std::iter::once(&config.worker).chain(config.python.iter()) {
            if !p.is_file() {
                return Err(format!("Fichier IA absent : {}", p.display()));
            }
        }
        if !config.models.is_dir() || (config.python.is_some() && !config.photolab_source.join("core/ai.py").is_file()) {
            return Err("Le moteur PhotoLab ou ses modèles sont introuvables".into());
        }
        Ok(config)
    }
}

pub struct AiState {
    pub strength: f32,
    pub mode: String,
    pub brush_radius: f32,
    pub painting: bool,
    pub show_mask: bool,
    pub preview: bool,
    pub mask_photo: Option<PhotoId>,
    pub geometry_key: String,
    pub strokes: Vec<BrushStroke>,
    pub busy: bool,
    pub progress: Arc<Mutex<(f32, String)>>,
    pub cancel: Arc<AtomicBool>,
    pub last_result: Option<String>,
    pub last_source: Option<PhotoId>,
    pub message: String,
}
impl Default for AiState {
    fn default() -> Self {
        Self {
            strength: 0.75,
            mode: "comfort".into(),
            brush_radius: 0.015,
            painting: false,
            show_mask: true,
            preview: false,
            mask_photo: None,
            geometry_key: String::new(),
            strokes: vec![],
            busy: false,
            progress: Arc::new(Mutex::new((0.0, String::new()))),
            cancel: Arc::new(AtomicBool::new(false)),
            last_result: None,
            last_source: None,
            message: String::new(),
        }
    }
}
impl Drop for AiState {
    fn drop(&mut self) {
        self.cancel.store(true, Ordering::Relaxed);
    }
}
impl AiState {
    pub fn status(&self) -> Value {
        let (fraction, phase) = self.progress.lock().map(|p| p.clone()).unwrap_or_default();
        json!({"running": self.busy, "fraction": fraction, "phase": phase, "maskStrokes": self.strokes.len(),
            "maskPhoto": self.mask_photo.map(|p| p.0), "lastResult": self.last_result,
            "source": self.last_source.map(|p| p.0), "message": self.message})
    }
    fn sync_photo(&mut self, id: PhotoId) {
        if self.mask_photo != Some(id) {
            self.strokes.clear();
            self.mask_photo = Some(id);
        }
    }
}

fn set_progress(p: &Arc<Mutex<(f32, String)>>, fraction: f32, label: &str) {
    if let Ok(mut value) = p.lock() {
        *value = (fraction.clamp(0.0, 1.0), label.to_string());
    }
}

fn sync_geometry(app: &mut LightcraftApp, photo: PhotoId) {
    app.ai.sync_photo(photo);
    let develop = app.session.develop_of(photo).unwrap_or_default();
    if let Ok(key) = serde_json::to_string(&(&develop.crop, &develop.geometry, &develop.orientation, &develop.optics))
        && key != app.ai.geometry_key
    {
        app.ai.strokes.clear();
        app.ai.geometry_key = key;
    }
}

fn validate_strokes(strokes: &[BrushStroke]) -> Result<(), String> {
    if strokes.len() > 2048 || strokes.iter().map(|s| s.points.len()).sum::<usize>() > 100_000 {
        return Err("Masque trop complexe".into());
    }
    for s in strokes {
        if !s.radius.is_finite()
            || !(0.001..=0.2).contains(&s.radius)
            || s.points.is_empty()
            || s.points.iter().flatten().any(|x| !x.is_finite() || !(0.0..=1.0).contains(x))
        {
            return Err("Coordonnées ou taille de pinceau invalides".into());
        }
    }
    Ok(())
}

pub fn command(app: &mut LightcraftApp, id: &str, p: &Value) -> Option<Result<Value, String>> {
    let result = match id {
        "panel.ai" => {
            app.ui.right = if app.ui.right == RightPanel::Ai { RightPanel::None } else { RightPanel::Ai };
            app.ui.view = ViewMode::Detail;
            app.ui.tool.clear();
            Ok(Value::Null)
        }
        "ai.mask.set" => (|| {
            let photo = app.session.active().ok_or("Aucune photo sélectionnée")?;
            if app.ai.busy {
                return Err("Un traitement IA est en cours".into());
            }
            let strokes: Vec<BrushStroke> =
                serde_json::from_value(p.get("strokes").cloned().unwrap_or_else(|| json!([]))).map_err(|e| format!("Masque invalide : {e}"))?;
            validate_strokes(&strokes)?;
            sync_geometry(app, photo);
            app.ai.strokes = strokes;
            Ok(app.ai.status())
        })(),
        "ai.mask.clear" | "ai.mask.undo" => {
            if app.ai.busy {
                Err("Un traitement IA est en cours".into())
            } else {
                if id == "ai.mask.clear" {
                    app.ai.strokes.clear();
                } else {
                    app.ai.strokes.pop();
                }
                Ok(app.ai.status())
            }
        }
        "ai.cancel" => {
            app.ai.cancel.store(true, Ordering::Relaxed);
            Ok(Value::Null)
        }
        "ai.denoise" | "ai.inpaint" => start(app, if id == "ai.denoise" { "denoise" } else { "inpaint" }, p),
        "ai.result" => (|| {
            let path = app.ai.last_result.clone().ok_or("Aucun résultat IA")?;
            let existing = app
                .session
                .catalog
                .photos()
                .find(|photo| {
                    matches!(&photo.source,
                lightcraft_catalog::Source::File { path: source } if source == &path)
                })
                .map(|p| p.id);
            app.ui.view = ViewMode::Detail;
            match existing {
                Some(photo) => app.run("library.select", json!({"ids": [photo.0]})),
                None => crate::import::start_paths(app, vec![path]),
            }
        })(),
        "ai.original" => (|| {
            let photo = app.ai.last_source.ok_or("Aucun original associé")?;
            app.run("library.select", json!({"ids": [photo.0]}))
        })(),
        _ => return None,
    };
    Some(result)
}

fn start(app: &mut LightcraftApp, operation: &str, p: &Value) -> Result<Value, String> {
    if cfg!(target_arch = "wasm32") {
        return Err("Le prototype IA fonctionne dans la version Windows locale".into());
    }
    if app.ai.busy {
        return Err("Un traitement IA est déjà en cours".into());
    }
    let photo = app.session.active().ok_or("Aucune photo sélectionnée")?;
    sync_geometry(app, photo);
    if operation == "inpaint" && app.ai.strokes.is_empty() {
        return Err("Peignez la zone à supprimer avant de lancer l’IA".into());
    }
    validate_strokes(&app.ai.strokes)?;
    let config = Runtime::load()?;
    let strength = p.get("strength").and_then(Value::as_f64).unwrap_or(f64::from(app.ai.strength));
    if !strength.is_finite() || !(0.0..=1.0).contains(&strength) {
        return Err("Intensité IA invalide".into());
    }
    let mode = p.get("mode").and_then(Value::as_str).unwrap_or(&app.ai.mode).to_string();
    if !["comfort", "quality", "extreme", "auto"].contains(&mode.as_str()) {
        return Err("Mode de débruitage inconnu".into());
    }
    let preview = p.get("preview").and_then(Value::as_bool).unwrap_or(app.ai.preview);
    let options = ExportOptions::from_json(&json!({"format": "tiff", "bitDepth": 32, "colorSpace": "sRGB",
        "longEdge": if preview { 1600 } else { 0 }, "metadata": "all"}));
    let prepared = prepare_export(&mut app.session, photo, &options, 1)?;
    let iso = app.session.catalog.photo(photo).and_then(|p| p.meta.iso);
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
    let dir = config.results.join(format!("{}-{stamp}", std::process::id()));
    let input = dir.join("source-linear-srgb.tif");
    let output = dir.join(if operation == "denoise" { "photo-debruitee.tif" } else { "photo-suppression-ia.tif" });
    let job_path = dir.join("job.json");
    let strokes = app.ai.strokes.clone();
    let operation = operation.to_string();
    let progress = Arc::new(Mutex::new((0.0, "Préparation du rendu".into())));
    let cancel = Arc::new(AtomicBool::new(false));
    app.ai.cancel = cancel.clone();
    app.ai.progress = progress.clone();
    app.ai.busy = true;
    app.ai.message.clear();
    app.ai.painting = false;
    let background = crate::tasks::spawn(
        app,
        "Traitement IA PhotoLab",
        move || -> Result<String, String> {
            if cancel.load(Ordering::Relaxed) {
                return Err("Traitement annulé".into());
            }
            std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
            let exported = prepared.run()?;
            if cancel.load(Ordering::Relaxed) {
                return Err("Traitement annulé".into());
            }
            write_file_durable(&input.to_string_lossy(), &exported.bytes)?;
            let mut job = json!({"operation": operation, "input": input, "output": output, "iso": iso,
            "photolab_source": config.photolab_source, "models": config.models, "strength": strength,
            "mode": mode, "strokes": strokes, "progress": dir.join("progress.json"), "result": dir.join("result.json"),
            "data_dir": dir.join("runtime"), "provider": "auto", "linear": true});
            set_progress(&progress, 0.05, "Calcul IA local");
            // A native DirectML crash stays in the child process; retry once on CPU.
            let first = run_worker(&config, &job_path, &job, &progress, &cancel);
            if first.is_err() && !cancel.load(Ordering::Relaxed) {
                job["provider"] = json!("CPUExecutionProvider");
                set_progress(&progress, 0.05, "Reprise du calcul sur le processeur");
                run_worker(&config, &job_path, &job, &progress, &cancel)?;
            } else {
                first?;
            }
            if !output.is_file() {
                return Err("Le moteur IA n’a pas produit de résultat".into());
            }
            Ok(output.to_string_lossy().to_string())
        },
        move |app, ctx, result| {
            app.ai.busy = false;
            match result {
                Ok(path) => {
                    app.ai.last_result = Some(path);
                    app.ai.last_source = Some(photo);
                    app.ai.message = "Terminé. Ouvrez le résultat pour le comparer à l’original.".into();
                }
                Err(error) => {
                    app.ai.message = error;
                }
            }
            ctx.request_repaint();
        },
    );
    if let Err(e) = background {
        app.ai.busy = false;
        return Err(e);
    }
    Ok(json!({"background": true, "source": photo.0}))
}

fn run_worker(config: &Runtime, path: &Path, job: &Value, progress: &Arc<Mutex<(f32, String)>>, cancel: &AtomicBool) -> Result<(), String> {
    std::fs::write(path, serde_json::to_vec_pretty(job).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let stderr = std::fs::File::create(path.with_extension("stderr.log")).map_err(|e| e.to_string())?;
    let mut command = if let Some(python) = &config.python {
        let mut c = std::process::Command::new(python);
        c.arg(&config.worker);
        c
    } else {
        std::process::Command::new(&config.worker)
    };
    command.arg(path).stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(stderr);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|e| format!("Démarrage du moteur IA : {e}"))?;
    let started = std::time::Instant::now();
    loop {
        if cancel.load(Ordering::Relaxed) || started.elapsed() > Duration::from_secs(3600) {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Traitement annulé ou délai maximal dépassé".into());
        }
        if let Some(file) = job.get("progress").and_then(Value::as_str)
            && let Ok(bytes) = std::fs::read(file)
            && let Ok(value) = serde_json::from_slice::<Value>(&bytes)
        {
            let fraction = value["fraction"].as_f64().unwrap_or(0.0) as f32;
            let phase = value["phase"].as_str().unwrap_or("Calcul IA local");
            set_progress(progress, 0.05 + 0.95 * fraction, phase);
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                if status.success() {
                    return Ok(());
                }
                let detail = job
                    .get("result")
                    .and_then(Value::as_str)
                    .and_then(|p| std::fs::read(p).ok())
                    .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
                    .and_then(|v| v["error"].as_str().map(str::to_string));
                return Err(detail.unwrap_or_else(|| {
                    format!("Le moteur IA s’est arrêté ({status}) ; diagnostic : {}", path.with_extension("stderr.log").display())
                }));
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(100)),
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e.to_string());
            }
        }
    }
}

pub fn show(app: &mut LightcraftApp, ui: &mut egui::Ui, photo: PhotoId) {
    sync_geometry(app, photo);
    crate::panels::right::header(ui, "IA — PhotoLab Club");
    ui.add_space(8.0);
    ui.label("Traitement local • nouvel exemplaire • original conservé");
    ui.add_space(12.0);
    ui.strong("Réduction du bruit par IA");
    ui.add_space(6.0);
    ui.add(egui::Slider::new(&mut app.ai.strength, 0.0..=1.0).text("Intensité"));
    egui::ComboBox::from_id_salt("aiMode")
        .selected_text(match app.ai.mode.as_str() {
            "quality" => "Qualité",
            "extreme" => "Extrême",
            "auto" => "Automatique",
            _ => "Confort",
        })
        .show_ui(ui, |ui| {
            for (mode, label) in [("comfort", "Confort — NAFNet"), ("quality", "Qualité — SCUNet"), ("extreme", "Extrême"), ("auto", "Automatique")]
            {
                ui.selectable_value(&mut app.ai.mode, mode.into(), label);
            }
        });
    action(app, ui, "ai.denoise", "Réduire le bruit", !app.ai.busy);
    ui.add_space(18.0);
    ui.separator();
    ui.add_space(12.0);
    ui.strong("Suppression d’objet par IA");
    ui.label("Peignez entièrement l’objet en rouge, avec une petite marge. LaMa reconstruit la zone.");
    ui.small("Espace change le zoom. Désactivez le pinceau pour déplacer la vue.");
    ui.add_space(6.0);
    ui.add_enabled_ui(!app.ai.busy, |ui| {
        let r = ui
            .selectable_label(app.ai.painting, if app.ai.painting { "Pinceau actif — peignez sur la photo" } else { "Peindre la zone à supprimer" });
        crate::widgets::register(ui.ctx(), "button:aiBrush", r.rect);
        if r.clicked() {
            app.ai.painting = !app.ai.painting;
        }
        ui.add(egui::Slider::new(&mut app.ai.brush_radius, 0.002..=0.1).text("Taille du pinceau"));
        ui.checkbox(&mut app.ai.show_mask, "Afficher le masque rouge");
    });
    action(app, ui, "ai.mask.undo", "Annuler le dernier trait", !app.ai.busy && !app.ai.strokes.is_empty());
    action(app, ui, "ai.mask.clear", "Effacer le masque", !app.ai.busy && !app.ai.strokes.is_empty());
    action(app, ui, "ai.inpaint", "Supprimer avec l’IA", !app.ai.busy && !app.ai.strokes.is_empty());
    ui.add_space(16.0);
    ui.separator();
    ui.add_space(8.0);
    ui.checkbox(&mut app.ai.preview, "Test rapide — résultat limité à 1600 px");
    if app.ai.busy {
        let (fraction, phase) = app.ai.progress.lock().map(|p| p.clone()).unwrap_or_default();
        ui.add_space(8.0);
        ui.label(phase);
        ui.add(egui::ProgressBar::new(fraction).show_percentage());
        action(app, ui, "ai.cancel", "Annuler le traitement", true);
        ui.ctx().request_repaint_after(Duration::from_millis(100));
    }
    if !app.ai.message.is_empty() {
        ui.add_space(8.0);
        ui.label(&app.ai.message);
    }
    if app.ai.last_result.is_some() {
        ui.add_space(8.0);
        action(app, ui, "ai.result", "Afficher le résultat", !app.ai.busy);
        action(app, ui, "ai.original", "Afficher l’original", !app.ai.busy);
    }
    ui.add_space(16.0);
    ui.small("Prototype : les réglages actuels sont intégrés au résultat. Le masque est propre à cette photo et n’est pas encore enregistré entre sessions.");
}

fn action(app: &mut LightcraftApp, ui: &mut egui::Ui, command: &str, label: &str, enabled: bool) {
    let r = ui.add_enabled(enabled, egui::Button::new(label));
    crate::widgets::register(ui.ctx(), format!("button:{command}"), r.rect);
    if r.clicked()
        && let Err(e) = app.run(command, json!({}))
    {
        app.ai.message = e;
    }
}

pub fn overlay(app: &mut LightcraftApp, ui: &mut egui::Ui, response: &egui::Response, image: Rect, photo: PhotoId) {
    sync_geometry(app, photo);
    let point = ui
        .input(|i| i.pointer.interact_pos())
        .filter(|p| image.contains(*p))
        .map(|p| [(p.x - image.left()) / image.width().max(1.0), (p.y - image.top()) / image.height().max(1.0)]);
    if app.ai.painting && !app.ai.busy {
        if response.drag_started()
            && let Some(point) = point
            && app.ai.strokes.len() < 2048
            && app.ai.strokes.iter().map(|s| s.points.len()).sum::<usize>() < 100_000
        {
            app.ai.strokes.push(BrushStroke { points: vec![point], radius: app.ai.brush_radius });
        }
        if response.dragged()
            && let Some(point) = point
            && app.ai.strokes.iter().map(|s| s.points.len()).sum::<usize>() < 100_000
            && let Some(stroke) = app.ai.strokes.last_mut()
            && stroke.points.len() < 10_000
            && stroke.points.last().is_none_or(|last| (point[0] - last[0]).hypot(point[1] - last[1]) >= stroke.radius * 0.1)
        {
            stroke.points.push(point);
        }
        if response.clicked()
            && let Some(point) = point
            && app.ai.strokes.len() < 2048
            && app.ai.strokes.iter().map(|s| s.points.len()).sum::<usize>() < 100_000
        {
            app.ai.strokes.push(BrushStroke { points: vec![point], radius: app.ai.brush_radius });
        }
        if let Some(point) = point {
            ui.painter().circle_stroke(
                image.left_top() + egui::vec2(point[0] * image.width(), point[1] * image.height()),
                app.ai.brush_radius * image.width().max(image.height()),
                Stroke::new(1.5, Color32::WHITE),
            );
        }
    }
    if app.ai.show_mask {
        let painter = ui.painter().with_clip_rect(image.intersect(response.rect));
        for stroke in &app.ai.strokes {
            let radius = stroke.radius * image.width().max(image.height());
            let points: Vec<_> = stroke.points.iter().map(|p| image.left_top() + egui::vec2(p[0] * image.width(), p[1] * image.height())).collect();
            for point in &points {
                painter.circle_filled(*point, radius, Color32::from_rgba_unmultiplied(240, 45, 60, 95));
            }
            for pair in points.windows(2) {
                if let (Some(a), Some(b)) = (pair.first(), pair.get(1)) {
                    painter.line_segment([*a, *b], Stroke::new(radius * 2.0, Color32::from_rgba_unmultiplied(240, 45, 60, 95)));
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_masks_are_rejected_and_photo_changes_clear_them() {
        assert!(validate_strokes(&[BrushStroke { points: vec![[f32::NAN, 0.5]], radius: 0.02 }]).is_err());
        assert!(validate_strokes(&[BrushStroke { points: vec![[0.5, 0.5]], radius: 0.02 }]).is_ok());
        let mut state = AiState::default();
        state.sync_photo(PhotoId(1));
        state.strokes.push(BrushStroke { points: vec![[0.5, 0.5]], radius: 0.02 });
        state.sync_photo(PhotoId(2));
        assert!(state.strokes.is_empty());
    }
    #[test]
    fn panel_commands_and_empty_mask_validation() {
        let mut app = LightcraftApp::new(lightcraft_engine::Session::with_demo(), Default::default());
        assert!(command(&mut app, "panel.ai", &json!({})).unwrap().is_ok());
        assert_eq!(app.ui.right, RightPanel::Ai);
        assert!(command(&mut app, "ai.inpaint", &json!({})).unwrap().unwrap_err().contains("Peignez"));
        assert!(!app.ai.busy);
    }
}
