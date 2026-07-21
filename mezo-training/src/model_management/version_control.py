class ModelVersionControl:
    def tag_version(self, checkpoint: str, version_tag: str) -> dict:
        return {"checkpoint": checkpoint, "version": version_tag, "status": "tagged"}
