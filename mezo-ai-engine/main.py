from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import socket
from src.inference.text_generator import TextGenerator
from src.inference.code_generator import CodeGenerator
from src.inference.reasoning import ReasoningEngine
from src.utils.memory_manager import MemoryManager
from src.providers.local_provider import LocalAIProvider
from src.providers.gemini_provider import GeminiAIProvider
from src.providers.provider_router import ProviderRouter, GeminiQuotaException
from src.persona.system_prompt import get_system_prompt, MEZO_AI_SYSTEM_PROMPT

app = FastAPI(title="MEZO AI Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

text_gen = TextGenerator()
code_gen = CodeGenerator()
reasoning = ReasoningEngine()
memory_mgr = MemoryManager()
local_provider = LocalAIProvider()
gemini_provider = GeminiAIProvider()
router = ProviderRouter(local_provider, gemini_provider)

class GenerateRequest(BaseModel):
    prompt: str
    preferred_provider: Optional[str] = "auto"
    system_prompt: Optional[str] = None
    user_id: Optional[str] = None       # for personalization context
    max_tokens: int = 512
    temperature: float = 0.7
    stream: bool = True

@app.get("/")
def read_root():
    return {"service": "MEZO AI", "version": "2.0.0", "status": "active"}


@app.get("/persona")
def get_persona():
    """Returns the current MEZO AI system prompt. For debugging and transparency."""
    return {"persona": MEZO_AI_SYSTEM_PROMPT, "source": "src/persona/system_prompt.py"}

@app.get("/providers/capabilities")
async def get_provider_capabilities():
    return {
        "local": local_provider.capabilities().model_dump(),
        "gemini": gemini_provider.capabilities().model_dump()
    }

@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        gen, provider_name, reason = await router.route_and_generate(
            prompt=req.prompt,
            preferred_provider=req.preferred_provider,
            system_prompt=req.system_prompt,
            stream=req.stream
        )

        if req.stream:
            async def sse_event_stream():
                # Send metadata event first
                yield f"data: {json.dumps({'event': 'meta', 'provider': provider_name, 'reason': reason})}\n\n"
                async for chunk in gen:
                    chunk_data = chunk.model_dump()
                    yield f"data: {json.dumps({'event': 'token', 'chunk': chunk_data})}\n\n"

            return StreamingResponse(sse_event_stream(), media_type="text/event-stream")
        else:
            return {
                "status": "success",
                "provider": provider_name,
                "reason": reason,
                "result": gen.model_dump()
            }
    except GeminiQuotaException as e:
        raise HTTPException(status_code=429, detail=f"Gemini quota exceeded: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/local")
async def check_local_health():
    is_online = await local_provider.health_check()
    return {
        "provider": "local",
        "online": is_online,
        "capabilities": local_provider.capabilities().model_dump()
    }

@app.get("/doctor")
async def mezo_doctor():
    local_status = await local_provider.health_check()
    return {
        "status": "ok",
        "doctor": {
            "local_engine_online": local_status,
            "local_engine_url": local_provider.base_url,
            "lan_ip": get_local_ip()
        }
    }

@app.post("/generate/text")
def generate_text(req: GenerateRequest):
    output = text_gen.generate(req.prompt, req.max_tokens, req.temperature)
    return {"status": "success", "result": output}

@app.post("/generate/code")
def generate_code(req: GenerateRequest):
    output = code_gen.generate_code(req.prompt)
    return {"status": "success", "result": output}

@app.post("/reasoning")
def get_reasoning(req: GenerateRequest):
    steps = reasoning.evaluate_steps(req.prompt)
    return {"status": "success", "steps": steps}

@app.get("/memory/stats")
def get_memory_stats():
    return memory_mgr.get_memory_stats()

