class DockerPlugin:
    def list_containers(self) -> list:
        return [
            {"id": "c1", "name": "mezo-frontend", "status": "running"},
            {"id": "c2", "name": "mezo-backend", "status": "running"},
            {"id": "c3", "name": "mezo-ai-engine", "status": "running"}
        ]
