class ResourceManager:
    def allocate(self, service: str, cpus: float, memory_mb: int) -> dict:
        return {"service": service, "allocated_cpus": cpus, "allocated_memory_mb": memory_mb, "status": "allocated"}
