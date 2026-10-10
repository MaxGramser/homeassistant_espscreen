// What a module keeps between calls (its state, its caches, a timer still waiting), back to how it was when the module
// loaded. tests/setup.ts starts every test from there, so no test sees what another one left, in whatever order they run
// (npm run test:shuffle). The page loads once and never calls it. A module registers its reset when it loads, so a test
// that never imports the store resets nothing of it, and a test that mocks a module keeps its mock.
const resets: (() => void)[] = [];

export function onReset(reset: () => void) {
  resets.push(reset);
}

export function resetAll() {
  for (const reset of resets) reset();
}
