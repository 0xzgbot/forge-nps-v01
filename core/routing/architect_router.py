from typing import Dict, Any
from abc import ABC, abstractmethod

class BaseKernelGenerator(ABC):
    """Abstract interface for all model kernels."""
    @abstractmethod
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        pass

class FluxKernelGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        # FLUX 2 Dev Schema based on Kimi Research
        cinematic_descriptors = "shot on Arri Alexa 65, Zeiss Master Prime lenses, visible natural skin or material texture, realistic surface imperfections, motivated volumetric light, natural lens falloff, specific depth of field"
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

class ZImageTurboKernelGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        fast_prompt = f"{concept}, crisp outlines, vibrant colors, studio lighting, high-contrast, digital art style, sharp focus."
        return {
            "prompt": fast_prompt,
            "parameters": {"aspect_ratio": "1:1", "steps": 8}
        }

class LTXKernelGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        motion_descriptors = "fluid cinematic movement, smooth temporal transitions, professional color grading"
        if anchor_data:
            palette = ", ".join(anchor_data.get("palette", []))
            motion_descriptors += f", maintaining visual identity with palette [{palette}]"
        return {
            "prompt": f"{concept}, {motion_descriptors}, 4k resolution quality, consistent textures, high dynamic range.",
            "parameters": {
                "fps": 24, 
                "motion_bucket": 127, 
                "resolution": [1280, 720],
                "seed": anchor_data.get("seed") if anchor_data else -1
            }
        }

class WanKernelGenerator(BaseKernelGenerator):
    def generate_payload(self, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        motion_descriptors = "fluid realistic motion, high-speed camera aesthetic, dynamic scene composition"
        if anchor_data:
            palette = ", ".join(anchor_data.get("palette", []))
            motion_descriptors += f", color consistency [{palette}]"
        return {
            "prompt": f"{concept}, {motion_descriptors}, extremely detailed textures, consistent temporal stability.",
            "parameters": {
                "fps": 30, 
                "motion_strength": 0.8, 
                "resolution": [1280, 720],
                "seed": anchor_data.get("seed") if anchor_data else -1
            }
        }

INTENT_KERNEL_MAP = {
    "high_fidelity_image": "flux_2_dev",
    "rapid_prototype": "z_image_turbo",
    "video_generation": "ltx_2_3",
    "long_video": "wan_2_1",
    "image_to_video": "ltx_2_3",
}

class KernelFactory:
    """Orchestrates the creation of specific kernel generators."""
    _generators = {
        "flux_2_dev": FluxKernelGenerator(),
        "z_image_turbo": ZImageTurboKernelGenerator(),
        "ltx_2_3": LTXKernelGenerator(),
        "wan_2_1": WanKernelGenerator()
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
    Translates high-level concepts into model-specific payload instructions.
    """
    def __init__(self):
        self.intent_to_kernel = INTENT_KERNEL_MAP

    def route(self, intent: str, concept: str, anchor_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Primary entry point. Determines the kernel and dispatches to a generator.
        """
        kernel_id = self.intent_to_kernel.get(intent, "flux_2_dev")
        try:
            generator = KernelFactory.get_generator(kernel_id)
            payload = generator.generate_payload(concept, anchor_data)
            return {
                "status": "success",
                "kernel": kernel_id,
                "prompt": payload["prompt"] if isinstance(payload["prompt"], str) else payload["prompt"]["text"],
                "payload": payload
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    def generate_anchor_prompt(self, concept: str, anchor_data: Dict[str, Any]) -> str:
        """Critical for character consistency across shots (CCP v1.0)."""
        palette = ", ".join(anchor_data.get("palette", []))
        temp = anchor_data.get("color_temperature", "5600K")
        return f"{concept}, palette [{palette}], temperature {temp}"
