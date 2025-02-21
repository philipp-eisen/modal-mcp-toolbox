# based on https://github.com/modal-labs/modal-examples/blob/main/06_gpu_and_ml/stable_diffusion/flux.py
import logging
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from typing import Annotated

import modal
from mcp.server.fastmcp import Context, Image
from mcp.types import Annotations, ImageContent
from modal.exception import NotFoundError
from modal.runner import deploy_app
from pydantic import Field

logger = logging.getLogger(__name__)

MINUTES = 60  # seconds
VARIANT = "schnell"  # or "dev", but note [dev] requires you to accept terms and conditions on HF
NUM_INFERENCE_STEPS = 4  # use ~50 for [dev], smaller for [schnell]
IMAGE_FORMAT = "JPEG"


cuda_version = "12.4.0"  # should be no greater than host CUDA version
flavor = "devel"  # includes full CUDA toolkit
operating_sys = "ubuntu22.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"

cuda_dev_image = modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.11").entrypoint([])
diffusers_commit_sha = "81cf3b2f155f1de322079af28f625349ee21ec6b"

flux_image = (
    cuda_dev_image.apt_install(
        "git",
        "libglib2.0-0",
        "libsm6",
        "libxrender1",
        "libxext6",
        "ffmpeg",
        "libgl1",
    )
    .pip_install(
        "invisible_watermark==0.2.0",
        "transformers==4.44.0",
        "huggingface_hub[hf_transfer]==0.26.2",
        "accelerate==0.33.0",
        "safetensors==0.4.4",
        "sentencepiece==0.2.0",
        "torch==2.5.0",
        f"git+https://github.com/huggingface/diffusers.git@{diffusers_commit_sha}",
        "numpy<2",
        "mcp>=1.3.0",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HUB_CACHE": "/cache"})
)


flux_image = flux_image.env(
    {
        "TORCHINDUCTOR_CACHE_DIR": "/root/.inductor-cache",
        "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
    }
)
flux_image.add_local_python_source("modal_mcp_toolbox", copy=True)


app_name = "mcp-toolbox--flux"
app = modal.App(app_name, image=flux_image)

with flux_image.imports():
    import torch
    from diffusers import FluxPipeline


@app.cls(
    gpu="L40S",
    container_idle_timeout=5 * MINUTES,
    image=flux_image,
    volumes={
        "/cache": modal.Volume.from_name("hf-hub-cache", create_if_missing=True),
    },
    enable_memory_snapshot=True,
)
class Model:
    @modal.enter(snap=True)
    def load(self):
        print("🔄 loading model...")
        pipe = FluxPipeline.from_pretrained(f"black-forest-labs/FLUX.1-{VARIANT}", torch_dtype=torch.bfloat16)
        self.pipe = _optimize(pipe)

    @modal.enter(snap=False)
    def setup(self):
        print("🔄 moving model to GPU...")
        self.pipe = self.pipe.to("cuda")

    @modal.method()
    def inference(self, prompt: str) -> bytes:
        print("🎨 generating image...")
        out = self.pipe(
            prompt,
            output_type="pil",
            num_inference_steps=NUM_INFERENCE_STEPS,
        ).images[0]

        byte_stream = BytesIO()
        out.save(byte_stream, format=IMAGE_FORMAT)
        return byte_stream.getvalue()


@app.function(
    image=modal.Image.debian_slim().pip_install("mcp>=1.3.0").add_local_python_source("modal_mcp_toolbox", copy=True),
    container_idle_timeout=5 * MINUTES,
)
def get_version():
    try:
        print("modal_mcp_toolbox version:", version("modal_mcp_toolbox"))
        return version("modal_mcp_toolbox")
    except PackageNotFoundError:
        print("modal_mcp_toolbox version: unknown")
        return "unknown"


def _optimize(pipe):
    # fuse QKV projections in Transformer and VAE
    pipe.transformer.fuse_qkv_projections()
    pipe.vae.fuse_qkv_projections()

    # switch memory layout to Torch's preferred, channels_last
    pipe.transformer.to(memory_format=torch.channels_last)
    pipe.vae.to(memory_format=torch.channels_last)

    return pipe


async def _ensure_app_deployment_is_up_to_date(ctx: Context):
    try:
        fn = modal.Function.from_name(app_name, "get_version")
        remote_version = await fn.remote.aio()

        if remote_version != version("modal_mcp_toolbox"):
            await ctx.info("App is out of date. Deploying ...")
            logger.info("App is out of date. Deploying ...")
            deploy_app(app)
    except NotFoundError:
        await ctx.info("App not found. Deploying...")
        logger.info("App not found. Deploying...")
        deploy_app(app)


async def generate_flux_image(prompt: Annotated[str, Field(description="The prompt to generate an image for")], ctx: Context) -> ImageContent:
    """Let's you generate an image using the Flux model."""
    await _ensure_app_deployment_is_up_to_date(ctx)

    cls = modal.Cls.from_name(app_name, Model.__name__)
    image_bytes = await cls().inference.remote.aio(prompt)
    image_content = Image(data=image_bytes, format=IMAGE_FORMAT).to_image_content()
    image_content.annotations = Annotations(audience=["user", "assistant"], priority=0.5)
    return image_content


if __name__ == "__main__":
    deploy_app(app)


@app.local_entrypoint()
async def main():
    print(await get_version.remote.aio())
