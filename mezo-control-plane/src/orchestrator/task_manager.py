import uuid

class TaskManager:
    def __init__(self):
        self.tasks = {}

    def create_task(self, name: str, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"id": task_id, "name": name, "payload": payload, "status": "pending"}
        return task_id

    def get_task(self, task_id: str) -> dict:
        return self.tasks.get(task_id, {})
