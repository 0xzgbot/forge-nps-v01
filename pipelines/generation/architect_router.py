import os
import json
from typing import Dict, Any
from abc import ABC, abstractmethod

class BaseKernelGenerator(ABC):
    """Abstract interface for all model kernels."""
    @abstractmethod
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        pass

class FluxDevGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        # FLUX 2 Dev Schema based on Kimi Research
        # Incorporating structured cinematic descriptors for high-fidelity adherence.
        
        cinematic_descriptors = "shot on Arri Alexa 65, Zeiss Master Prime lenses, ultra-photorealistic, extremely detailed textures, natural skin tones, volumetric lighting, cinematic depth of field, 8k resolution"
        
        # If anchor data (color/lighting) exists from a previous still, inject it.
        if anchor_data:
            palette = ", ".join(anchor_data.get("palette", []))
            temp = anchor_data.get("color_temperature", "5600K")
            cinematic_descriptors += f", color palette [{palette}], temperature {temp}"

        prompt = f"{concept}, {cinematic_descriptors}, highly controlled shadows, professional color grading."
        
        return {
            "prompt": {
                "text": prompt,
                "clip_l": f"{concept}, {cinematic_descriptors}"
            },
            "parameters": {
                "aspect_ratio": anchor_data.get("aspect_ratio", "16:9") if anchor_data else "16:9",
                "steps": 30,
                "guidance_scale": 3.5,
                "seed": anchor_data.get("seed") if anchor_data else -1
            }
        }

class ZImageTurboGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        fast_prompt = f"{concept}, crisp outlines, vibrant colors, studio lighting, high-contrast, digital art style, sharp focus."
        return {
            "prompt": fast_prompt,
            "parameters": {"aspect_ratio": "1:1", "steps": 8}
        }

class LTX23Generator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        # LTX 2.3 Video Generation - Incorporating Temporal Consistency Anchors from Kimi
        # We use the Anchor Data to ensure motion doesn't drift from the visual essence of the still.
        
        motion_descriptors = "fluid cinematic movement, smooth temporal transitions, professional color grading"
        
        if anchor_data:
            palette = ", ".join(anchor_data.get("palette", []))
            motion_descriptors += f", maintaining visual identity with palette [{palette}]"

        video_prompt = f"{concept}, {motion_descriptors}, 4k resolution quality, consistent textures, high dynamic range."
        
        return {
            "prompt": f"{concept}, {motion_descriptors}, 4k resolution quality, consistent textures, high dynamic range.",
            "parameters": {
                "fps": 24, 
                "motion_bucket": 127, 
                "resolution": [1280, 720],
                "seed": anchor_data.get("seed") if anchor_data else -1
            }
        }

class Wan21Generator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        # Wan 2.1 High-Motion Video Generation
        motion_descriptors = "fluid realistic motion, high-speed camera aesthetic, dynamic scene composition"
        
        if anchor_data:
            palette = ", ".join(anchor_data.get("palette", []))
            motion_descriptors += f", color consistency [{palette}]"

        video_prompt = f"{concept}, {motion_descriptors}, extremely detailed textures, consistent temporal stability."
        

        return {
            "prompt": f"{concept}, {motion_descriptors}, extremely detailed textures, consistent temporal stability.",
            "parameters": {
                "fps": 30, 
                "motion_strength": 0.8, 
                "resolution": [1280, 720],
                "seed": anchor_data.get("seed") if anchor_data else -1
            }
        }

class KernelFactory:
    """Orchestrates the creation of specific kernel generators."""
    _generators = {
        "flux_2_dev": FluxDevGenerator(),
        "zimage_turbo": ZImageTurboGenerator(),
        "ltx_2_3": LTX23Generator(),
        "wan_2_1": Wan21Generator()
    }

    @classmethod
    def get_generator(cls, kernel_name: str) -> BaseKernelGenerator:
        generator = cls._generators.get(kernel_name)
        if not generator:
            raise ValueError(f"Kernel '{kernel_name}' not found in factory.")
        return generator

class ArchitectRouter:
    """
    The central intelligence node of the Cinesmith Multi-Kernel Prompt Compiler.
    Translates high-level concepts into model-specific payload instructions, 
    now capable of 'Anchor-to-Video' visual translation via Kimi Protocols.
    """

    def __init__(self):
        # Map intent to specific kernel IDs
        self.intent_to_kernel = {
            "high_fidelity_image": "flux_2_dev",
            "fast_preview_image": "zimage_turbo",
            "cinematic_video": "ltx_2_3",
            "high_motion_video": "wan_2_1",
        }

    def route(self, intent: str, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Primary entry point. Determines the kernel and dispatches to a generator.
        Accepts optional 'anchor_data' for cross-model visual continuity (CCP v1.0).
        """
        kernel_id = self.intent_to_kernel.get(intent, "flux_2_dev")
        print(f"[ARCHITECT] Routing intent '{intent}' -> Kernel ID '{kernel_id}'")
        if anchor_data:
            print(f"[ARCHITECT] Applying Anchor Data for visual continuity.")

        try:
            generator = KernelFactory.get_generator(kernel_id)
            payload = generator.generate_payload(concept, anchor_data)
            return {
                "status": "success",
                "kernel_id": kernel_id,
                "payload": payload
            }
        except Exception as e:
            print(f"[ARCHITECT ERROR] {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

if __name__ == "__main__":
    router = ArchitectRouter()
    
    # Test case 1: Standalone Image
    print("\n--- TEST 1: STANDALONE FLUX IMAGE ---")
    res1 = router.route("high_fidelity_image", "A lone nomad in a desert")
    print(json.dumps(res1, indent=2))

    # Test case 2: Anchor-to-Video (Visual Continuity)
    print("\n--- TEST 2: ANCHOR-TO-VIDEO (CCP v1.0) ---")
    anchor = {
        "palette": ["#E6BE8A", "#4B3621", "#F5F5DC"],
        "color_temperature": "3200K",
        "aspect_ratio": "16:9",
        "seed": 12345
    }
    res2 = router.route("high_motion_video", "The desert dunes shifting under moonlight", anchor_data=anchor)
    print(json.dumps(res2, indent=2))

    # Test case 3: LTX Cinematic Video
    print("\n--- TEST 3: LTX CINEMATIC VIDEO ---")
    res3 = router.route("cinematic_video", "Drone shot over a mountain range")
    print(json.dumps(res3, indent=2))
