/** Tiny deterministic force-directed layout (no external graph lib).
 *  Repulsion + link springs + gentle centering; runs a fixed number of
 *  iterations synchronously (fine for < 300 nodes). */

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
}

export function layoutForceGraph(
  nodeIds: string[],
  edges: { src: string; dst: string }[],
  width: number,
  height: number,
  iterations = 160,
): LayoutNode[] {
  const n = nodeIds.length;
  if (n === 0) return [];
  // deterministic pseudo-random seed from id
  const seedOf = (s: string) => {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967295;
  };
  const idx = new Map(nodeIds.map((id, i) => [id, i]));
  const px = new Float64Array(n);
  const py = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const a = seedOf(nodeIds[i]) * Math.PI * 2;
    const r = 80 + seedOf(nodeIds[i] + "#r") * Math.min(width, height) * 0.3;
    px[i] = width / 2 + Math.cos(a) * r;
    py[i] = height / 2 + Math.sin(a) * r;
  }
  const links: [number, number][] = [];
  for (const e of edges) {
    const s = idx.get(e.src);
    const d = idx.get(e.dst);
    if (s !== undefined && d !== undefined) links.push([s, d]);
  }
  const REPULSE = 5200;
  const SPRING = 0.015;
  const LINK_LEN = 95;
  const CENTER = 0.004;
  let temp = 1;
  for (let it = 0; it < iterations; it++) {
    const dx = new Float64Array(n);
    const dy = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ddx = px[i] - px[j];
        let ddy = py[i] - py[j];
        let d2 = ddx * ddx + ddy * ddy;
        if (d2 < 0.01) {
          ddx = (seedOf(nodeIds[i] + i) - 0.5) * 2;
          ddy = (seedOf(nodeIds[j] + j) - 0.5) * 2;
          d2 = ddx * ddx + ddy * ddy + 0.01;
        }
        const f = REPULSE / d2;
        const d = Math.sqrt(d2);
        dx[i] += (ddx / d) * f;
        dy[i] += (ddy / d) * f;
        dx[j] -= (ddx / d) * f;
        dy[j] -= (ddy / d) * f;
      }
    }
    for (const [s, d] of links) {
      const ddx = px[d] - px[s];
      const ddy = py[d] - py[s];
      const dist = Math.max(Math.sqrt(ddx * ddx + ddy * ddy), 0.01);
      const f = SPRING * (dist - LINK_LEN);
      dx[s] += (ddx / dist) * f * dist * 0.02;
      dy[s] += (ddy / dist) * f * dist * 0.02;
      dx[d] -= (ddx / dist) * f * dist * 0.02;
      dy[d] -= (ddy / dist) * f * dist * 0.02;
    }
    for (let i = 0; i < n; i++) {
      dx[i] += (width / 2 - px[i]) * CENTER;
      dy[i] += (height / 2 - py[i]) * CENTER;
      const len = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]);
      if (len > 0.001) {
        const cap = Math.min(len, 12 * temp);
        px[i] += (dx[i] / len) * cap;
        py[i] += (dy[i] / len) * cap;
      }
      px[i] = Math.max(20, Math.min(width - 20, px[i]));
      py[i] = Math.max(20, Math.min(height - 20, py[i]));
    }
    temp *= 0.985;
  }
  return nodeIds.map((id, i) => ({ id, x: px[i], y: py[i] }));
}
