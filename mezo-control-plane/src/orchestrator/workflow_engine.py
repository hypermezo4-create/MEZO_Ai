class WorkflowEngine:
    def run_workflow(self, workflow_name: str, steps: list) -> dict:
        results = []
        for step in steps:
            results.append({"step": step, "status": "success"})
        return {"workflow": workflow_name, "results": results}
