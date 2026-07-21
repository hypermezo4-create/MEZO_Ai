class ProcessControlSkill:
    def kill_process(self, pid: int) -> dict:
        return {"pid": pid, "status": "terminated"}
