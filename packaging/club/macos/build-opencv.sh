#!/usr/bin/env bash
# Modified 2026-10-13: minimal Apache-licensed OpenCV for the Mac AI bridge.
# PyPI Mac wheels contain FFmpeg/x264; never distribute those wheels in this fork.
set -euo pipefail
export CMAKE_BUILD_PARALLEL_LEVEL=2
export ENABLE_HEADLESS=1
export ENABLE_CONTRIB=0
export CMAKE_ARGS="-DBUILD_LIST=core,imgproc,imgcodecs,features2d,flann,photo,python3 -DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DWITH_IPP=OFF -DWITH_ITT=OFF -DWITH_QT=OFF -DWITH_OPENGL=OFF -DWITH_OPENCL=OFF -DBUILD_opencv_apps=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DWITH_AVFOUNDATION=OFF -DWITH_JPEG=OFF -DWITH_PNG=OFF -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_JASPER=OFF -DWITH_OPENJPEG=OFF -DWITH_OPENEXR=OFF -DWITH_AVIF=OFF"
python -m pip install scikit-build==0.18.1 ninja==1.13.0 cmake==3.31.10 wheel==0.45.1 setuptools==84.0.0
python -m pip install --no-binary=opencv-python-headless --no-build-isolation --no-deps opencv-python-headless==4.12.0.88
python - <<'PY'
import cv2
info=cv2.getBuildInformation()
assert cv2.__version__.startswith('4.12.')
assert not __import__('re').search(r'FFMPEG:\s+YES',info)
assert 'videoio' not in next(line for line in info.splitlines() if 'To be built:' in line)
print(info)
PY
