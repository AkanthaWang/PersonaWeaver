import { defineStore } from "pinia";
import { api } from "../api/client.js";
export const useWorkspaceStore = defineStore("workspace", {
  state: () => ({ books: [], selectedId: "", loading: false, generation: 0 }),
  getters: { selected: (state) => state.books.find((book) => book.book_id === state.selectedId) },
  actions: {
    async refresh() {
      const current = ++this.generation;
      this.loading = true;
      try {
        const result = await api.get("/books");
        if (current !== this.generation) return;
        this.books = result.books;
        if (!this.books.some((book) => book.book_id === this.selectedId)) this.selectedId = this.books[0]?.book_id || "";
      } finally { if (current === this.generation) this.loading = false; }
    },
    reset() { this.generation++; this.books = []; this.selectedId = ""; this.loading = false; },
  },
});
