class TextGenerator:
    def __init__(self, model_path: str = "models/base-model"):
        self.model_path = model_path

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        return f"[MEZO Text Generator] Output for prompt: '{prompt}' (max_tokens={max_tokens}, temp={temperature})"
