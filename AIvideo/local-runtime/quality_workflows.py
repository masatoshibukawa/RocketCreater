"""Core-node API graphs derived from the installed official ComfyUI templates."""

from generate import workflow as wan5b_workflow


def node(kind, **inputs):
    return {"class_type": kind, "inputs": inputs}


def video_graph(config, filename, prefix):
    width, height, frames = config["width"], config["height"], config["frames"]
    steps, seed = config["steps"], config["seed"]
    if config["backend"] == "wan5b":
        graph = wan5b_workflow(filename, width, height, frames, steps, seed)
        graph["5"]["inputs"]["text"] = config["positive"]
        graph["6"]["inputs"]["text"] = config["negative"]
        graph["8"]["inputs"]["shift"] = config.get("shift", 8)
        graph["9"]["inputs"].update(cfg=config.get("cfg", 5), sampler_name=config.get("sampler", "uni_pc"))
    else:
        split = config.get("split_step", steps // 2)
        cfg, shift = config.get("cfg", 3.5), config.get("shift", 5)
        graph = {
            "1": node("UNETLoader", unet_name="wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", weight_dtype="default"),
            "2": node("UNETLoader", unet_name="wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", weight_dtype="default"),
            "3": node("CLIPLoader", clip_name="umt5_xxl_fp8_e4m3fn_scaled.safetensors", type="wan", device="default"),
            "4": node("VAELoader", vae_name="wan_2.1_vae.safetensors"),
            "5": node("LoadImage", image=filename),
            "6": node("CLIPTextEncode", clip=["3", 0], text=config["positive"]),
            "7": node("CLIPTextEncode", clip=["3", 0], text=config["negative"]),
            "8": node("WanImageToVideo", positive=["6", 0], negative=["7", 0], vae=["4", 0], width=width, height=height, length=frames, batch_size=1, start_image=["5", 0]),
            "9": node("ModelSamplingSD3", model=["1", 0], shift=shift),
            "10": node("ModelSamplingSD3", model=["2", 0], shift=shift),
            "11": node("KSamplerAdvanced", model=["9", 0], positive=["8", 0], negative=["8", 1], latent_image=["8", 2], add_noise="enable", noise_seed=seed, steps=steps, cfg=cfg, sampler_name=config.get("sampler", "euler"), scheduler="simple", start_at_step=0, end_at_step=split, return_with_leftover_noise="enable"),
            "13": node("KSamplerAdvanced", model=["10", 0], positive=["8", 0], negative=["8", 1], latent_image=["11", 0], add_noise="disable", noise_seed=seed, steps=steps, cfg=cfg, sampler_name=config.get("sampler", "euler"), scheduler="simple", start_at_step=split, end_at_step=steps, return_with_leftover_noise="disable"),
            "10decode": node("VAEDecode", samples=["13", 0], vae=["4", 0]),
            "11video": node("CreateVideo", images=["10decode", 0], fps=config["fps"]),
        }
    if config["backend"] == "wan5b":
        graph["11"]["inputs"]["fps"] = config["fps"]
    graph["12"] = node("SaveVideo", video=["11" if config["backend"] == "wan5b" else "11video", 0], filename_prefix=prefix, format="mp4", codec="h264")
    return graph


def photo_graph(config, prefix):
    """New text-to-image concept image, without editing or uploading source imagery."""
    width, height = config["width"], config["height"]
    return {
        "1": node("UNETLoader", unet_name="flux-2-klein-4b.safetensors", weight_dtype="default"),
        "2": node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2", device="default"),
        "3": node("VAELoader", vae_name="flux2-vae.safetensors"),
        "4": node("CLIPTextEncode", clip=["2", 0], text=config["positive"]),
        "5": node("ConditioningZeroOut", conditioning=["4", 0]),
        "6": node("EmptyFlux2LatentImage", width=width, height=height, batch_size=1),
        "7": node("RandomNoise", noise_seed=config["seed"]),
        "8": node("KSamplerSelect", sampler_name="euler"),
        "9": node("Flux2Scheduler", steps=4, width=width, height=height),
        "10": node("CFGGuider", model=["1", 0], positive=["4", 0], negative=["5", 0], cfg=1.0),
        "11": node("SamplerCustomAdvanced", noise=["7", 0], guider=["10", 0], sampler=["8", 0], sigmas=["9", 0], latent_image=["6", 0]),
        "12": node("VAEDecode", samples=["11", 0], vae=["3", 0]),
        "13": node("SaveImage", images=["12", 0], filename_prefix=prefix),
    }
