class ReasoningEngine:
    def __init__(self):
        pass

    def evaluate_steps(self, query: str) -> list[str]:
        return [
            f"1. تحليل الخلاف والهدف في السؤال: {query}",
            "2. استخراج المعطيات والقيود الهيكلية",
            "3. بناء خطوات التفكير المنطقي خطوة بخطوة (Chain of Thought)",
            "4. الاستنتاج النهائي والتحقق من صحته"
        ]
