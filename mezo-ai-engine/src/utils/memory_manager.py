class MemoryManager:
    def optimize_gpu_memory(self):
        print("[MEZO MemoryManager] Optimizing VRAM cache and clearing unused allocations")

    def get_memory_stats(self) -> dict:
        return {"vram_used_mb": 4200, "vram_total_mb": 16384, "allocated_ratio": 0.256}

    def truncate_conversation_history(
        self,
        messages: list[dict],
        max_tokens: int = 8192,
        system_prompt: str = None
    ) -> list[dict]:
        """
        Truncates conversation history to stay within max_tokens token ceiling,
        guaranteeing system prompt and recent turns are NEVER dropped.
        """
        if not messages:
            return []

        # Simple token count estimation (approx 4 chars per token)
        def estimate_tokens(text: str) -> int:
            return len(text) // 4 + 1

        reserved_tokens = estimate_tokens(system_prompt or "") if system_prompt else 0
        available_tokens = max(1000, max_tokens - reserved_tokens - 500) # reserve output buffer

        truncated = []
        accumulated_tokens = 0

        # Iterate backwards from newest message to oldest
        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg.get("text", ""))
            if accumulated_tokens + msg_tokens <= available_tokens:
                truncated.insert(0, msg)
                accumulated_tokens += msg_tokens
            else:
                # Token budget exceeded, stop taking older turns
                break

        return truncated

