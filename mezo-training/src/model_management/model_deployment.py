class ModelDeploymentService:
    def promote_to_production(self, version_tag: str) -> dict:
        return {"version": version_tag, "promoted": True, "target": "mezo-ai-engine"}
