class DataProcessor:
    def preprocess(self, raw_data: list) -> list:
        processed = []
        for item in raw_data:
            processed.append({"prompt": item.get("prompt", ""), "response": item.get("response", "")})
        return processed
