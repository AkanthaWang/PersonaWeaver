class MemoryService:
    """Reserved memory boundary; persistence can be added without touching conversations."""

    def search(self, query: str):
        return {"items": [], "query": query}
