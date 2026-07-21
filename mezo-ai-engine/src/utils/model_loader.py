class ModelLoader:
    def load_model(self, path: str):
        print(f"[MEZO ModelLoader] Loading model weights from {path}")
        return {"name": "mezo-loaded-model", "path": path, "status": "ready"}
