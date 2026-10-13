# Modified 2026-10-13 for the standalone club distribution. MIT OR Apache-2.0.
"""Local inference bridge for the LightCraft / PhotoLab club prototype.

Input and output are linear-sRGB float32 TIFFs. Only the new result is written.
PhotoLab's existing AI implementation is loaded independently of its GUI/RAW code.
"""
from __future__ import annotations
import json, os, sys, traceback, time
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def mask_from_strokes(strokes, height, width):
    import numpy as np
    import cv2
    if len(strokes) > 2048 or sum(len(s['points']) for s in strokes) > 100_000:
        raise ValueError('Masque trop complexe')
    mask = np.zeros((height, width), np.float32)
    for stroke in strokes:
        radius = float(stroke['radius'])
        points = np.asarray(stroke['points'], np.float64)
        if not 0.001 <= radius <= 0.2 or points.ndim != 2 or points.shape[1] != 2 or not len(points):
            raise ValueError('Masque invalide')
        if not np.isfinite(points).all() or np.any(points < 0) or np.any(points > 1):
            raise ValueError('Coordonnées de masque invalides')
        px = np.rint(points * [max(1, width-1), max(1, height-1)]).astype(np.int32)
        r = max(1, int(round(radius * max(height, width))))
        for point in px:
            cv2.circle(mask, tuple(point), r, 1.0, -1)
        if len(px) > 1:
            cv2.polylines(mask, [px], False, 1.0, thickness=2*r)
    return mask


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding='utf-8'))
    # Configure the AI process before importing any native runtime.
    os.environ['PHOTOLAB_DATA_DIR'] = str(job['data_dir'])
    Path(job['data_dir']).mkdir(parents=True, exist_ok=True)
    if not getattr(sys, 'frozen', False) and job.get('photolab_source'):
        sys.path.insert(0, str(job['photolab_source']))
    try:
        from core.worker_safety import configure_worker
        configure_worker()
        import faulthandler
        faulthandler.enable()
        import numpy as np
        import tifffile
        from core.ai import AIManager
        from core.performance import PerformanceSettings
        import onnxruntime as ort
        ort.set_default_logger_severity(3)
        class BridgeAIManager(AIManager):
            def _run(self, key, session, output_names, inputs):
                if key != 'inpaint':
                    return super()._run(key, session, output_names, inputs)
                # This OpenCV-exported LaMa model uses BGR, whereas PhotoLab uses RGB.
                image_key = next(k for k,v in inputs.items() if v.ndim==4 and v.shape[1]==3)
                mask_key = next(k for k,v in inputs.items() if v.ndim==4 and v.shape[1]==1)
                feeds=dict(inputs)
                feeds[image_key]=np.ascontiguousarray(inputs[image_key][:,::-1]*(1-inputs[mask_key]),np.float32)
                values=super()._run(key,session,output_names,feeds)
                return [np.ascontiguousarray(v[:,::-1]) if v.ndim==4 and v.shape[1]==3 else v for v in values]
        source = Path(job['input']).resolve()
        output = Path(job['output']).resolve()
        if os.path.normcase(str(source)) == os.path.normcase(str(output)) or output.exists():
            raise ValueError('Le résultat doit être un nouveau fichier, distinct de la source')
        with tifffile.TiffFile(source) as tf:
            image = tf.asarray()
            tag = tf.pages[0].tags.get(34675)
            profile = bytes(tag.value) if tag is not None else None
        if image.dtype != np.float32 or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError('Le raccord exige une image TIFF RGB linéaire float32')
        if image.shape[0] * image.shape[1] > 120_000_000 or not np.isfinite(image).all():
            raise ValueError('Image trop grande ou pixels invalides')
        strength = float(job.get('strength', 0.75))
        if not np.isfinite(strength) or not 0 <= strength <= 1:
            raise ValueError('Intensité invalide')
        mode = str(job.get('mode', 'comfort'))
        if mode not in ('comfort', 'quality', 'extreme', 'auto'):
            raise ValueError('Mode de débruitage inconnu')
        settings = PerformanceSettings(provider=job.get('provider', 'auto')).normalized()
        manager = BridgeAIManager(model_dir=job['models'], performance=settings)
        last_progress = [0.0]
        def progress(done, total):
            now = time.monotonic()
            if now - last_progress[0] < 0.15 and done < total:
                return
            last_progress[0] = now
            try:
                atomic_json(job['progress'], {'fraction': min(1, max(0, done/max(1, total))),
                                            'phase': 'Calcul IA local'})
            except OSError:
                pass  # Telemetry must never abort a successfully running inference.
        if job['operation'] == 'denoise':
            result = manager.denoise(image, strength=strength, mode=mode, iso=job.get('iso'), progress=progress)
        elif job['operation'] == 'inpaint':
            mask = mask_from_strokes(job.get('strokes', []), *image.shape[:2])
            if not np.any(mask):
                raise ValueError('Masque vide : peignez un objet avant de lancer la suppression')
            # Reflection padding can duplicate the object outside its mask, making
            # LaMa reconstruct that same object. Replicate only the edge instead.
            h,w=image.shape[:2]
            padded=np.pad(image,((0,max(0,512-h)),(0,max(0,512-w)),(0,0)),mode='edge')
            padded_mask=np.pad(mask,((0,max(0,512-h)),(0,max(0,512-w))),mode='constant')
            result = manager.inpaint(padded,padded_mask,progress=progress)[:h,:w]
        else:
            raise ValueError('Opération IA inconnue')
        result = np.asarray(result, np.float32)
        if result.shape != image.shape or not np.isfinite(result).all():
            raise ValueError('Résultat IA invalide')
        tags = [(34675, 'B', len(profile), profile, False)] if profile else []
        temporary = output.with_suffix('.tmp.tif')
        tifffile.imwrite(temporary, result, photometric='rgb', metadata=None, compression='deflate',
                         extratags=tags, description='PhotoLab Club AI derivative - float32 linear sRGB')
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        check = tifffile.imread(temporary)
        if check.shape != result.shape or check.dtype != np.float32 or not np.array_equal(check, result):
            raise ValueError('La vérification du TIFF de résultat a échoué')
        # The unique job directory prevents collisions; never replace a prior result.
        if output.exists():
            raise FileExistsError('Un résultat existe déjà à cet emplacement')
        temporary.rename(output)
        atomic_json(job['result'], {'ok': True, 'output': str(output), 'provider': manager.provider_label(),
                                   'shape': list(result.shape), 'operation': job['operation']})
        progress(1, 1)
        return 0
    except Exception as exc:
        atomic_json(job['result'], {'ok': False, 'error': str(exc)})
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
