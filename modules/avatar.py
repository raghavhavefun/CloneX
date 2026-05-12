import cv2
import numpy as np
import pyvirtualcam
import threading
import time
import os
import sys
import torch
import joblib
import random
from typing import Any, cast

# Link to the existing LivePortrait installation
LIVE_PORTRAIT_PATH = r"D:\AI\LivePortrait"
if LIVE_PORTRAIT_PATH not in sys.path:
    sys.path.append(LIVE_PORTRAIT_PATH)

try:
    from src.config.inference_config import InferenceConfig  # type: ignore
    from src.config.crop_config import CropConfig  # type: ignore
    from src.utils.cropper import Cropper  # type: ignore
    from src.live_portrait_wrapper import LivePortraitWrapper  # type: ignore
    from src.utils.io import load_image_rgb, resize_to_limit  # type: ignore
    from src.utils.helper import dct2device  # type: ignore
    from src.utils.crop import prepare_paste_back, paste_back  # type: ignore
    LIVE_PORTRAIT_AVAILABLE = True
except ImportError as e:
    print(f"[Avatar] LivePortrait dependencies missing: {e}")
    LIVE_PORTRAIT_AVAILABLE = False


class BaseLipEngine:
    def __init__(self):
        self.smoothed = 0.0

    def compute_lip_ratio(self, volume: float, dt: float, speech_text: str) -> float:
        target = max(0.0, min(1.0, float(volume)))
        attack = 1.0 - np.exp(-dt * 20.0)
        release = 1.0 - np.exp(-dt * 8.0)
        alpha = attack if target > self.smoothed else release
        self.smoothed += (target - self.smoothed) * alpha

        if self.smoothed <= 0.01:
            return 0.0

        shaped = np.power(self.smoothed, 0.7)
        lip_ratio = float(min(1.0, shaped * 0.9))

        if speech_text:
            vowels = sum(1 for c in speech_text if c in "aeiou")
            letters = sum(1 for c in speech_text if c.isalpha())
            if letters > 0:
                vowel_ratio = vowels / letters
                lip_ratio *= (0.92 + min(0.16, vowel_ratio * 0.25))
        return max(0.0, min(1.0, lip_ratio))


class FemaleLipEngine(BaseLipEngine):
    """
    Female-specific lip dynamics:
    - stronger silence lock (avoid idle talking look)
    - faster onset, softer release
    - slightly narrower max opening for natural look
    """
    def compute_lip_ratio(self, volume: float, dt: float, speech_text: str) -> float:
        target = max(0.0, min(1.0, float(volume)))
        attack = 1.0 - np.exp(-dt * 26.0)
        release = 1.0 - np.exp(-dt * 10.0)
        alpha = attack if target > self.smoothed else release
        self.smoothed += (target - self.smoothed) * alpha

        if self.smoothed <= 0.03:
            return 0.0

        shaped = np.power(self.smoothed, 0.62)
        lip_ratio = float(min(0.82, shaped * 0.84))

        if speech_text:
            vowels = sum(1 for c in speech_text if c in "aeiou")
            letters = sum(1 for c in speech_text if c.isalpha())
            if letters > 0:
                vowel_ratio = vowels / letters
                lip_ratio *= (0.95 + min(0.12, vowel_ratio * 0.18))
        return max(0.0, min(1.0, lip_ratio))


class Avatar:
    def __init__(self, initial_mode="3d"):
        self.initial_mode = initial_mode
        self.current_mode = initial_mode
        self.avatar_profiles = {
            "3d": ("assets/avatar_3d.jpg", "assets/new_drive.pkl"),
            "female": ("assets/female.jpg", "assets/female_drive.pkl"),
        }
        self.lip_engines = {
            "3d": BaseLipEngine(),
            "female": FemaleLipEngine(),
        }
        self.image_path, self.pkl_path = self.avatar_profiles.get(initial_mode, self.avatar_profiles["3d"])
            
        self.base_image = cv2.imread(self.image_path)
        if self.base_image is None:
            self.base_image = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        self.h, self.w, _ = self.base_image.shape
        self.current_volume = 0
        self.smoothed_volume = 0.0
        self.current_speech_text = ""
        self.speech_start_time = 0.0
        self.last_frame_time = time.time()
        self.last_speaking_time = 0.0
        self.blink_state = {"next": time.time() + random.uniform(2.5, 5.5), "end": 0.0}
        self._running = False
        self._thread = None
        self.cam = None
        self.crop_info = None
        
        self.motion_frames = None
        self.x_d_0 = None  # First frame keypoints (for relative motion)
        self.x_d_cache = None
        self.frame_idx = 0
        
        if LIVE_PORTRAIT_AVAILABLE:
            print("[Avatar] Initializing Neural Engine (LivePortrait)...")
            self.inf_cfg = InferenceConfig()  # type: ignore
            self.crop_cfg = CropConfig()  # type: ignore
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # type: ignore
            self.lp_wrapper = LivePortraitWrapper(inference_cfg=self.inf_cfg)  # type: ignore
            self.cropper = Cropper(crop_cfg=self.crop_cfg)  # type: ignore
            self._prepare_neural_source()
            
            self._load_motion_pkl(self.pkl_path)
        else:
            print("[Avatar] Neural Engine NOT available. Falling back to basic mode.")

    def _load_motion_pkl(self, pkl_path):
        if not os.path.exists(pkl_path):
            print(f"[Avatar] Motion pkl not found: {pkl_path}")
            self.motion_frames = None
            self.x_d_cache = None
            self.x_d_0 = None
            return

        print(f"[Avatar] Loading motion template from {pkl_path}...")
        try:
            data = joblib.load(pkl_path)
            self.motion_frames = data.get('motion', [])
            print(f"[Avatar] Loaded {len(self.motion_frames)} motion frames.")
        except Exception as e:
            print(f"[Avatar] Error loading pkl: {e}")
            self.motion_frames = None
            return

        print("[Avatar] Pre-caching driving motion on GPU...")
        self.x_d_cache = []
        for m in self.motion_frames:
            self.x_d_cache.append(self._motion_to_keypoints(m))
        self.x_d_0 = self.x_d_cache[0]
        self.frame_idx = 0
        print(f"[Avatar] Cached {len(self.x_d_cache)} frames on GPU. Ready.")
    def _motion_to_keypoints(self, motion_dict):
        """Convert a pkl motion frame dict (with R matrix) into transformed keypoints.
        
        Implements the LivePortrait equation: x = (kp @ R + exp) * scale + t
        All inputs from pkl are numpy arrays with shape (1, ...).
        """
        kp = torch.from_numpy(motion_dict['kp']).float().to(self.device)       # (1, 21, 3)  # type: ignore
        R = torch.from_numpy(motion_dict['R']).float().to(self.device)          # (1, 3, 3)  # type: ignore
        exp = torch.from_numpy(motion_dict['exp']).float().to(self.device)      # (1, 21, 3)  # type: ignore
        t = torch.from_numpy(motion_dict['t']).float().to(self.device)          # (1, 3)  # type: ignore
        scale = torch.from_numpy(motion_dict['scale']).float().to(self.device)  # (1, 1)  # type: ignore
        
        # Eqn 2: s * (kp @ R + exp) + t
        kp_transformed = kp @ R + exp
        kp_transformed *= scale[..., None]                # (1,21,3) * (1,1,1)
        kp_transformed[:, :, 0:2] += t[:, None, 0:2]     # only tx, ty
        
        return kp_transformed

    def _prepare_neural_source(self):
        # Pre-process the source image for LivePortrait
        img_rgb = load_image_rgb(self.image_path)  # type: ignore
        img_rgb = resize_to_limit(img_rgb, self.inf_cfg.source_max_dim, self.inf_cfg.source_division)  # type: ignore
        
        # Crop the face
        self.crop_info = self.cropper.crop_source_image(img_rgb, self.crop_cfg)
        if self.crop_info is None:
            print(f"[Avatar] No face detected in {self.image_path}! Neural engine disabled.")
            return

        self.I_s = self.lp_wrapper.prepare_source(self.crop_info['img_crop_256x256'])
        self.x_s_info = self.lp_wrapper.get_kp_info(self.I_s)
        self.f_s = self.lp_wrapper.extract_feature_3d(self.I_s)
        self.x_s = self.lp_wrapper.transform_keypoint(self.x_s_info)
        
        # Prepare pasteback mask
        self.mask_ori_float = prepare_paste_back(self.inf_cfg.mask_crop, self.crop_info['M_c2o'], dsize=(img_rgb.shape[1], img_rgb.shape[0]))  # type: ignore
        self.source_rgb = img_rgb

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._render_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        if self.cam:
            self.cam.close()

    def set_volume(self, volume):
        self.current_volume = volume
        if volume > 0.01:
            self.last_speaking_time = time.time()

    def set_speech_text(self, text):
        self.current_speech_text = (text or "").strip().lower()
        self.speech_start_time = time.time()

    def change_image(self, avatar_type):
        """Hot-swap the source face. Replicates the full _prepare_neural_source pipeline."""
        self.current_mode = avatar_type if avatar_type in self.avatar_profiles else "3d"
        new_path, new_pkl = self.avatar_profiles.get(avatar_type, self.avatar_profiles["3d"])
            
        print(f"\n[Avatar] Switching image to {new_path}...")
        img = cv2.imread(new_path)
        if img is None:
            print(f"[Avatar] Failed to load image: {new_path}")
            return
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_rgb = resize_to_limit(img_rgb, self.inf_cfg.source_max_dim, self.inf_cfg.source_division)  # type: ignore

        crop_info = self.cropper.crop_source_image(img_rgb, self.crop_cfg)
        if crop_info is None:
            print(f"[Avatar] No face detected in {new_path}!")
            return

        # Recalculate ALL neural engine fields — same as _prepare_neural_source
        I_s = self.lp_wrapper.prepare_source(crop_info['img_crop_256x256'])
        x_s_info = self.lp_wrapper.get_kp_info(I_s)
        f_s = self.lp_wrapper.extract_feature_3d(I_s)
        x_s = self.lp_wrapper.transform_keypoint(x_s_info)
        mask_ori_float = prepare_paste_back(  # type: ignore
            self.inf_cfg.mask_crop, crop_info['M_c2o'],
            dsize=(img_rgb.shape[1], img_rgb.shape[0])
        )

        # Atomically swap all fields so the render loop never sees a half-updated state
        self.base_image = img
        self.source_rgb = img_rgb
        self.crop_info = crop_info
        self.I_s = I_s
        self.x_s_info = x_s_info
        self.f_s = f_s
        self.x_s = x_s
        self.mask_ori_float = mask_ori_float

        self._load_motion_pkl(new_pkl)

        print("[Avatar] Image switched successfully!\n")

    def _resize_keep_aspect(self, frame, target_w, target_h):
        """Resize frame to fit target dimensions while keeping aspect ratio.
        Pads with black bars if needed."""
        h, w = frame.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h))
        
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        return canvas

    def _render_loop(self):
        target_w, target_h = 1280, 720
        try:
            self.cam = pyvirtualcam.Camera(width=target_w, height=target_h, fps=30)
            print(f"\n[Avatar] SUCCESS: Neural Virtual Camera is streaming at {target_w}x{target_h}\n")
        except Exception as e:
            print(f"\n[Avatar] ERROR: Could not start virtual camera: {e}\n")
            self._running = False
            return

        while self._running:
            try:
                if LIVE_PORTRAIT_AVAILABLE and self.crop_info:
                    frame = self._generate_neural_frame()
                else:
                    frame = self.base_image.copy()
            except Exception as e:
                print(f"[Avatar] Frame error: {e}")
                frame = self.base_image.copy()

            frame_resized = self._resize_keep_aspect(frame, target_w, target_h)
            frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            self.cam.send(frame_rgb)
            self.cam.sleep_until_next_frame()

    def _generate_neural_frame(self):
        now = time.time()
        dt = max(1.0 / 120.0, min(0.1, now - self.last_frame_time))
        self.last_frame_time = now

        lip_engine = self.lip_engines.get(self.current_mode, self.lip_engines["3d"])
        lip_ratio = lip_engine.compute_lip_ratio(self.current_volume, dt, self.current_speech_text)
        self.smoothed_volume = lip_engine.smoothed

        # Natural blinking: random interval + occasional double blink.
        eye_ratio = 0.5
        if now >= self.blink_state["next"]:
            blink_len = random.uniform(0.08, 0.16)
            self.blink_state["end"] = now + blink_len
            # 20% chance of quick second blink
            gap = random.uniform(0.06, 0.12) if random.random() < 0.2 else 0.0
            self.blink_state["next"] = now + blink_len + gap + random.uniform(2.5, 5.5)
        if now < self.blink_state["end"]:
            eye_ratio = 0.0
            
        with torch.no_grad():
            # === STEP 1: Base keypoints ===
            # If we have driving video motion, use RELATIVE motion from it
            # This gives us head tilts, expressions, micro-movements
            if self.x_d_cache and self.x_d_0 is not None:
                idx = self.frame_idx % len(self.x_d_cache)
                self.frame_idx += 1
                
                # Already cached on GPU — no conversion needed!
                x_d_i = self.x_d_cache[idx]
                
                # Relative motion: source + (current_frame - first_frame)
                # This transfers the VIDEO's movements onto YOUR face
                x_d_i_new = self.x_s + (x_d_i - self.x_d_0)
            else:
                # No driving video: static face
                x_d_i_new = self.x_s.clone()

            # Very subtle speech-coupled head/jaw motion for liveliness.
            speaking_boost = min(1.0, self.smoothed_volume * 1.4)
            if speaking_boost > 0.03:
                phase = (now - self.speech_start_time) * 8.0
                bob_y = np.sin(phase) * 0.004 * speaking_boost
                sway_x = np.cos(phase * 0.7) * 0.0025 * speaking_boost
                x_d_i_new[:, :, 0] += sway_x
                x_d_i_new[:, :, 1] += bob_y

            # === STEP 2: Override lips with real-time audio ===
            combined_lip_ratio = self.lp_wrapper.calc_combined_lip_ratio([[lip_ratio]], self.crop_info['lmk_crop'])  # type: ignore
            lip_delta = self.lp_wrapper.retarget_lip(self.x_s, combined_lip_ratio)
            if lip_delta is not None:
                # Blend lip delta to keep driving expression and avoid robotic mouth snaps.
                x_d_i_new += (lip_delta * 0.92)

            # === STEP 3: Add eye blinks ===
            combined_eye_ratio = self.lp_wrapper.calc_combined_eye_ratio([[eye_ratio]], self.crop_info['lmk_crop'])  # type: ignore
            eye_delta = self.lp_wrapper.retarget_eye(self.x_s, combined_eye_ratio)
            if eye_delta is not None:
                x_d_i_new += (eye_delta * 0.9)
            
            # === STEP 4: Stitch, warp, decode ===
            x_d_i_new = self.lp_wrapper.stitching(self.x_s, x_d_i_new)
            
            out = self.lp_wrapper.warp_decode(self.f_s, self.x_s, x_d_i_new)
            I_p_i = self.lp_wrapper.parse_output(cast(Any, out)['out'])[0]
            
            # Paste back onto full image
            I_p_pstbk = paste_back(I_p_i, self.crop_info['M_c2o'], self.source_rgb, self.mask_ori_float)  # type: ignore
            
            return cv2.cvtColor(I_p_pstbk, cv2.COLOR_RGB2BGR)
