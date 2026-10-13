// Modified 2026-10-13 for PhotoLab Club: French localization, AI/dust review or standalone branding. See docs/MODIFICATIONS-CLUB.md.
//! Review sensor-dust proposals before adding any correction to the photo.
use crate::LightcraftApp;
use egui::{Color32, Stroke};
use lightcraft_catalog::PhotoId;
use lightcraft_geom::Point;
use lightcraft_pipeline::dust::DustSpot;
use serde_json::{Value, json};

pub struct Proposal {
    pub spot: DustSpot,
    pub selected: bool,
}
pub struct Review {
    pub photo: Option<PhotoId>,
    pub proposals: Vec<Proposal>,
    pub sensitivity: f32,
    pub busy: bool,
    pub message: String,
    pub signature: String,
}
impl Default for Review {
    fn default() -> Self {
        Self { photo: None, proposals: vec![], sensitivity: 50., busy: false, message: String::new(), signature: String::new() }
    }
}
fn signature(app: &LightcraftApp, id: PhotoId) -> String {
    let mut settings = (*app.session.develop_of(id).unwrap_or_default()).clone();
    settings.spots.clear();
    serde_json::to_string(&settings).unwrap_or_default()
}
pub fn status(app: &LightcraftApp) -> Value {
    json!({"photo":app.dust_review.photo.map(|p|p.0),"running":app.dust_review.busy,"message":app.dust_review.message,
        "proposals":app.dust_review.proposals.iter().enumerate().map(|(i,p)|json!({"index":i,"x":p.spot.x,"y":p.spot.y,"size":p.spot.radius,"quality":p.spot.quality,"selected":p.selected})).collect::<Vec<_>>()})
}
pub fn command(app: &mut LightcraftApp, id: &str, params: &Value) -> Option<Result<Value, String>> {
    let result = match id {
        "dust.scan" => start(app),
        "dust.select" => (|| {
            let index = params["index"].as_u64().ok_or("Indice de proposition absent")? as usize;
            let proposal = app.dust_review.proposals.get_mut(index).ok_or("Proposition inexistante")?;
            proposal.selected = params["selected"].as_bool().unwrap_or(!proposal.selected);
            Ok(status(app))
        })(),
        "dust.clear" => {
            app.dust_review.proposals.clear();
            app.dust_review.message.clear();
            Ok(Value::Null)
        }
        "dust.apply" => (|| {
            let photo = app.session.active().ok_or("Aucune photo sélectionnée")?;
            if app.dust_review.photo != Some(photo) || app.dust_review.signature != signature(app, photo) {
                return Err("La photo ou ses réglages ont changé : relancez la recherche".into());
            }
            let spots: Vec<Value> =
                app.dust_review.proposals.iter().filter(|p| p.selected).map(|p| json!({"x":p.spot.x,"y":p.spot.y,"size":p.spot.radius})).collect();
            if spots.is_empty() {
                return Err("Sélectionnez les propositions qui correspondent vraiment à des taches du capteur".into());
            }
            let result = app.run("spot.applyDust", json!({"spots":spots}))?;
            app.dust_review.proposals.clear();
            app.dust_review.message = "Corrections appliquées. Annuler restaure la photo.".into();
            Ok(result)
        })(),
        _ => return None,
    };
    Some(result)
}
fn start(app: &mut LightcraftApp) -> Result<Value, String> {
    if app.dust_review.busy {
        return Err("La recherche est déjà en cours".into());
    }
    let photo = app.session.active().ok_or("Aucune photo sélectionnée")?;
    let snapshot = signature(app, photo);
    let mut settings = (*app.session.develop_of(photo).unwrap_or_default()).clone();
    settings.spots.clear();
    settings.crop = Default::default();
    settings.geometry = Default::default();
    settings.orientation = Default::default();
    settings.optics = Default::default();
    let job = app.session.preview_job(photo, 1600, 1600, false, &settings).ok_or("Rendu de recherche indisponible")?;
    let sensitivity = app.dust_review.sensitivity;
    app.dust_review.proposals.clear();
    app.dust_review.busy = true;
    app.dust_review.photo = Some(photo);
    app.dust_review.message = "Recherche sur l’image non corrigée…".into();
    let result = crate::tasks::spawn(
        app,
        "Recherche de poussières",
        move || job.run().rendered.map(|r| lightcraft_pipeline::dust::detect(&r.image, sensitivity)),
        move |app, ctx, result| {
            app.dust_review.busy = false;
            match result {
                Ok(found) => {
                    app.dust_review.signature = snapshot;
                    app.dust_review.message = format!("{} proposition(s), aucune correction appliquée.", found.len());
                    app.dust_review.proposals = found.into_iter().map(|spot| Proposal { spot, selected: false }).collect();
                }
                Err(e) => app.dust_review.message = e,
            }
            ctx.request_repaint();
        },
    );
    if let Err(e) = result {
        app.dust_review.busy = false;
        return Err(e);
    }
    Ok(json!({"background":true}))
}
pub fn show(app: &mut LightcraftApp, ui: &mut egui::Ui, id: PhotoId) {
    ui.add_space(8.);
    ui.strong("Poussières du capteur — propositions");
    ui.label("La recherche ne retouche rien. Vérifiez les cercles jaunes ; cochez uniquement les vraies taches du capteur.");
    ui.add(egui::Slider::new(&mut app.dust_review.sensitivity, 0.0..=100.0).text("Sensibilité"));
    if app.dust_review.busy {
        ui.label("Recherche en cours…");
    }
    if !app.dust_review.message.is_empty() {
        ui.label(&app.dust_review.message);
    }
    if app.dust_review.photo != Some(id) {
        return;
    }
    if !app.dust_review.proposals.is_empty() && app.dust_review.signature != signature(app, id) {
        app.dust_review.proposals.clear();
        app.dust_review.message = "Les réglages ont changé : relancez la recherche.".into();
        return;
    }
    for (index, proposal) in app.dust_review.proposals.iter_mut().enumerate() {
        let r = ui.checkbox(&mut proposal.selected, format!("Proposition {}", index + 1));
        crate::widgets::register(ui.ctx(), format!("dustProposal:{index}"), r.rect);
        r.on_hover_text("Un motif rond peut aussi être un détail réel : sa présence ici ne confirme pas une poussière.");
    }
    let selected = app.dust_review.proposals.iter().filter(|p| p.selected).count();
    let apply = ui.add_enabled(selected > 0 && !app.dust_review.busy, egui::Button::new(format!("Corriger les {selected} sélectionnée(s)")));
    crate::widgets::register(ui.ctx(), "button:dustApply", apply.rect);
    if apply.clicked()
        && let Err(e) = app.run("dust.apply", json!({}))
    {
        app.dust_review.message = e;
    }
    if !app.dust_review.proposals.is_empty() && ui.button("Fermer les propositions").clicked() {
        let _ = app.run("dust.clear", json!({}));
    }
    ui.add_space(10.);
    ui.separator();
}
pub fn overlay(app: &mut LightcraftApp, ui: &mut egui::Ui, map: &crate::panels::detail::CanvasMap) -> bool {
    if app.dust_review.photo != app.session.active() {
        return false;
    }
    let Some(photo) = app.session.active() else {
        return false;
    };
    if app.dust_review.signature != signature(app, photo) {
        return false;
    }
    let mut clicked = false;
    let long = app.image_rect.map(|r| r.width().max(r.height())).unwrap_or(1.);
    let clip = app.canvas_rect.unwrap_or(ui.max_rect());
    for (index, proposal) in app.dust_review.proposals.iter_mut().enumerate() {
        let point = map.screen(Point::new(proposal.spot.x, proposal.spot.y));
        if !clip.contains(point) {
            continue;
        }
        let radius = proposal.spot.radius as f32 * long;
        let color = if proposal.selected { Color32::from_rgb(85, 220, 125) } else { Color32::from_rgb(255, 200, 65) };
        ui.painter_at(clip).circle_stroke(point, radius, Stroke::new(1.8, color));
        ui.painter_at(clip).text(
            point + egui::vec2(radius + 3., 0.),
            egui::Align2::LEFT_CENTER,
            (index + 1).to_string(),
            egui::FontId::proportional(12.),
            color,
        );
        let response = ui.interact(
            egui::Rect::from_center_size(point, egui::vec2(radius.max(10.) * 2., radius.max(10.) * 2.)),
            egui::Id::new(("dustProposalPin", index)),
            egui::Sense::click(),
        );
        if response.clicked() {
            proposal.selected = !proposal.selected;
            clicked = true;
        }
    }
    clicked
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_reviewed_proposals_apply_and_changed_settings_invalidate_them() {
        let mut app = LightcraftApp::new(lightcraft_engine::Session::with_demo(), Default::default());
        let photo = app.session.active().unwrap();
        app.dust_review.photo = Some(photo);
        app.dust_review.signature = signature(&app, photo);
        app.dust_review.proposals.push(Proposal { spot: DustSpot { x: 0.4, y: 0.4, radius: 0.01, strength: 0.04, quality: 20. }, selected: false });
        assert!(command(&mut app, "dust.apply", &json!({})).unwrap().is_err());
        assert!(app.session.develop_of(photo).unwrap().spots.is_empty());
        assert!(command(&mut app, "dust.select", &json!({"index":0,"selected":true})).unwrap().is_ok());
        let result = command(&mut app, "dust.apply", &json!({})).unwrap().unwrap();
        assert_eq!(result["added"], 1);
        assert!(app.session.develop_of(photo).unwrap().spots[0].dust);
        app.run("edit.undo", json!({})).unwrap();
        assert!(app.session.develop_of(photo).unwrap().spots.is_empty());
        app.dust_review.signature = signature(&app, photo);
        app.dust_review.proposals.push(Proposal { spot: DustSpot { x: 0.4, y: 0.4, radius: 0.01, strength: 0.04, quality: 20. }, selected: true });
        app.run("develop.set", json!({"control":"light.exposure","value":0.4})).unwrap();
        assert!(command(&mut app, "dust.apply", &json!({})).unwrap().unwrap_err().contains("réglages"));
    }
}
