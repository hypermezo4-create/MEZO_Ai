from fastapi import FastAPI
from pydantic import BaseModel
from src.inference.text_generator import TextGenerator
from src.inference.code_generator import CodeGenerator
from src.inference.reasoning import ReasoningEngine
from src.utils.memory_manager import MemoryManager

app = FastAPI(title="MEZO AI Engine", version="1.0.0")

text_gen = TextGenerator()
code_gen = CodeGenerator()
reasoning = ReasoningEngine()
memory_mgr = MemoryManager()

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7

@app.get("/")
def read_root():
    return {"service": "MEZO AI Engine", "status": "active"}

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
