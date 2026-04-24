#!/usr/bin/env python3
import asyncio, json, logging, time, uuid
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("Test3090s")

GPU1 = "http://localhost:8188"
GPU2 = "http://localhost:8189"
OUT = Path("~/Desktop/forge_nps_v01/data/renders/3090_tests")
OUT.mkdir(parents=True, exist_ok=True)

def zimg(prompt, unet="z_image_turbo_bf16.safetensors", seed=42, w=1024, h=1024):
    wf = dict()
    wf["1"] = dict(class_type="UNETLoader", inputs=dict(unet_name=unet, weight_dtype="default"))
    wf["2"] = dict(class_type="CLIPLoader", inputs=dict(clip_name="qwen_3_4b.safetensors", type="lumina2", device="default"))
    wf["3"] = dict(class_type="VAELoader", inputs=dict(vae_name="ae.safetensors"))
    wf["4"] = dict(class_type="ModelSamplingAuraFlow", inputs=dict(shift=3, model=["1", 0]))
    wf["6"] = dict(class_type="CLIPTextEncode", inputs=dict(text=prompt, clip=["2", 0]))
    wf["7"] = dict(class_type="ConditioningZeroOut", inputs=dict(conditioning=["6", 0]))
    wf["8"] = dict(class_type="EmptySD3LatentImage", inputs=dict(width=w, height=h, batch_size=1))
    wf["9"] = dict(class_type="KSampler", inputs=dict(seed=seed, control_after_generate="fixed", steps=8, cfg=1, sampler_name="res_multistep", scheduler="simple", denoise=1, model=["4", 0], positive=["6", 0], negative=["7", 0], latent_image=["8", 0]))
    wf["10"] = dict(class_type="VAEDecode", inputs=dict(samples=["9", 0], vae=["3", 0]))
    wf["11"] = dict(class_type="SaveImage", inputs=dict(filename_prefix="zimg_test", images=["10", 0]))
    return wf

def flux1(prompt, seed=42, w=1024, h=1024):
    wf = dict()
    wf["1"] = dict(class_type="UNETLoader", inputs=dict(unet_name="flux1-dev-fp8.safetensors", weight_dtype="fp8_e4m3fn"))
    wf["2"] = dict(class_type="CLIPLoader", inputs=dict(clip_name="clip_l.safetensors", type="flux", device="default"))
    wf["3"] = dict(class_type="CLIPLoader", inputs=dict(clip_name="t5xxl_fp8_e4m3fn_scaled.safetensors", type="flux", device="default"))
    wf["4"] = dict(class_type="VAELoader", inputs=dict(vae_name="ae.safetensors"))
    wf["5"] = dict(class_type="ModelSamplingFlux", inputs=dict(max_shift=1.15, base_shift=0.5, width=w, height=h, model=["1", 0]))
    wf["6"] = dict(class_type="CLIPTextEncode", inputs=dict(text=prompt, clip=["2", 0]))
    wf["7"] = dict(class_type="CLIPTextEncode", inputs=dict(text=prompt, clip=["3", 0]))
    wf["8"] = dict(class_type="EmptySD3LatentImage", inputs=dict(width=w, height=h, batch_size=1))
    wf["9"] = dict(class_type="KSampler", inputs=dict(seed=seed, control_after_generate="fixed", steps=20, cfg=1, sampler_name="euler", scheduler="simple", denoise=1, model=["5", 0], positive=["6", 0], negative=["7", 0], latent_image=["8", 0]))
    wf["10"] = dict(class_type="VAEDecode", inputs=dict(samples=["9", 0], vae=["4", 0]))
    wf["11"] = dict(class_type="SaveImage", inputs=dict(filename_prefix="flux1_test", images=["10", 0]))
    return wf

def sdxl(prompt, seed=42, w=1024, h=1024):
    wf = dict()
    wf["1"] = dict(class_type="CheckpointLoaderSimple", inputs=dict(ckpt_name="sd_xl_turbo_1.0_fp16.safetensors"))
    wf["2"] = dict(class_type="CLIPTextEncode", inputs=dict(text=prompt, clip=["1", 1]))
    wf["3"] = dict(class_type="CLIPTextEncode", inputs=dict(text="blurry, low quality, watermark", clip=["1", 1]))
    wf["4"] = dict(class_type="EmptyLatentImage", inputs=dict(width=w, height=h, batch_size=1))
    wf["5"] = dict(class_type="KSampler", inputs=dict(seed=seed, control_after_generate="fixed", steps=4, cfg=1, sampler_name="euler_ancestral", scheduler="normal", denoise=1, model=["1", 0], positive=["2", 0], negative=["3", 0], latent_image=["4", 0]))
    wf["6"] = dict(class_type="VAEDecode", inputs=dict(samples=["5", 0], vae=["1", 2]))
    wf["7"] = dict(class_type="SaveImage", inputs=dict(filename_prefix="sdxl_test", images=["6", 0]))
    return wf

async def run(host, wf, name, timeout=300):
    cid = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30.0) as c:
        logger.info(f"[{name}] Submitting to {host}...")
        r = await c.post(f"{host}/prompt", json=dict(prompt=wf, client_id=cid))
        r.raise_for_status()
        pid = r.json()["prompt_id"]
        logger.info(f"[{name}] Prompt ID: {pid}")
        t0 = time.time()
        while time.time() - t0 < timeout:
            await asyncio.sleep(3)
            h = await c.get(f"{host}/history/{pid}")
            if h.status_code == 200:
                data = h.json()
                if pid in data:
                    st = data[pid].get("status", {})
                    if st.get("status_str") == "success":
                        logger.info(f"[{name}] SUCCESS in {time.time()-t0:.1f}s")
                        return dict(status="ok", elapsed=time.time()-t0)
                    elif st.get("status_str") == "error":
                        logger.error(f"[{name}] FAILED: {st}")
                        return dict(status="error", details=st)
        logger.error(f"[{name}] TIMEOUT")
        return dict(status="timeout")

async def main():
    jobs = []
    # GPU1 tests
    jobs.append(run(GPU1, zimg("a cyberpunk neon cityscape at night, rain reflections, cinematic", seed=1001), "GPU1_zimg_turbo"))
    jobs.append(run(GPU1, flux1("a portrait of a warrior woman with glowing tattoos, dramatic lighting", seed=2001), "GPU1_flux1"))
    jobs.append(run(GPU1, sdxl("a futuristic sports car on a coastal highway at sunset", seed=3001), "GPU1_sdxl_turbo"))
    # GPU2 tests
    jobs.append(run(GPU2, zimg("an ancient temple in a misty jungle, golden light rays, detailed", unet="z_image_bf16.safetensors", seed=4001), "GPU2_zimg"))
    jobs.append(run(GPU2, flux1("a steampunk airship floating above victorian london, foggy", seed=5001), "GPU2_flux1"))
    jobs.append(run(GPU2, sdxl("a cozy mountain cabin with snow falling, warm lights", seed=6001), "GPU2_sdxl_turbo"))
    results = await asyncio.gather(*jobs, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Exception: {r}")
        else:
            logger.info(f"Result: {r}")

if __name__ == "__main__":
    asyncio.run(main())
