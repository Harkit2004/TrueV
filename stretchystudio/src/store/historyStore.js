import { create } from 'zustand';

// Simple undo/redo manager
export const useHistoryStore = create((set) => ({
  past: [],
  future: [],
  
  pushPatch: (patch) => set((state) => ({
    past: [...state.past, patch],
    future: [] // Truncate redo stack when new action is performed
  })),

  undo: () => set((state) => {
    if (state.past.length === 0) return state;
    const previous = state.past[state.past.length - 1];
    const newPast = state.past.slice(0, state.past.length - 1);
    
    // In a real implementation with immer patches, we'd apply the inverse patch
    // to the projectStore here.
    return {
      past: newPast,
      future: [previous, ...state.future]
    };
  }),

  redo: () => set((state) => {
    if (state.future.length === 0) return state;
    const next = state.future[0];
    const newFuture = state.future.slice(1);
    
    // In a real implementation with immer patches, we'd apply the patch
    // to the projectStore here.
    return {
      past: [...state.past, next],
      future: newFuture
    };
  })
}));
