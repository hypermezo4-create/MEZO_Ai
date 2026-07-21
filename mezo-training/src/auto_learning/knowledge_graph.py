class KnowledgeGraphManager:
    def add_node(self, concept: str, relations: list) -> dict:
        return {"concept": concept, "relations_added": len(relations)}
