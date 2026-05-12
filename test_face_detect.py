"""Quick test: Can LivePortrait detect a face in avatar_3d.jpg?"""
import cv2
import sys
import os

LIVE_PORTRAIT_PATH = r"D:\AI\LivePortrait"
if LIVE_PORTRAIT_PATH not in sys.path:
    sys.path.append(LIVE_PORTRAIT_PATH)

from src.config.inference_config import InferenceConfig  # type: ignore
from src.config.crop_config import CropConfig  # type: ignore
from src.utils.cropper import Cropper  # type: ignore

crop_cfg = CropConfig()
cropper = Cropper(crop_cfg=crop_cfg)
inf_cfg = InferenceConfig()

for name in ["assets/avatar.jpg", "assets/avatar_3d.jpg"]:
    img = cv2.imread(name)
    if img is None:
        print(f"[{name}] CANNOT READ FILE")
        continue
    print(f"[{name}] Shape: {img.shape}")
    
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    crop_info = cropper.crop_source_image(img_rgb, crop_cfg)
    
    if crop_info is None:
        print(f"[{name}] NO FACE DETECTED!")
    else:
        print(f"[{name}] Face detected OK. Crop keys: {list(crop_info.keys())}")
