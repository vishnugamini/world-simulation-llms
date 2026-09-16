import { useEffect, useRef } from "react";
import type { Run, Snapshot, Agent } from "./api";

type Props = {
  run: Run;
  state: Snapshot;
  selected: number | null;
  onSelect: (id: number) => void;
  compact?: boolean;
};
const COLORS = [
  "#de865d",
  "#d8b857",
  "#82a6b1",
  "#9074a1",
  "#6e9880",
  "#cf7c83",
];
export default function Island({
  run,
  state,
  selected,
  onSelect,
  compact = false,
}: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const positions = useRef<{ id: number; x: number; y: number }[]>([]);
  const latest = useRef({ state, selected });
  latest.current = { state, selected };
  const entered = useRef(performance.now());
  useEffect(() => {
    entered.current = performance.now();
  }, [state.day, run.id]);
  useEffect(() => {
    const canvas = ref.current!;
    const context = canvas.getContext("2d")!;
    let raf = 0;
    let width = 800,
      height = 600;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();
    const land = new Set(run.world.land.map(([x, y]) => `${x},${y}`));
    const draw = (now: number) => {
      const ctx = context;
      const s = latest.current.state;
      const tile = Math.min(width / 49, height / 43);
      const ox = (width - 48 * tile) / 2,
        oy = (height - 48 * tile) / 2;
      const xy = (x: number, y: number) => [
        ox + (x + 0.5) * tile,
        oy + (y + 0.5) * tile,
      ];
      ctx.fillStyle = "#dce9e6";
      ctx.fillRect(0, 0, width, height);
      // Gentle current lines and a hand-drawn coordinate grid.
      ctx.strokeStyle = "rgba(118,157,154,.10)";
      ctx.lineWidth = 1;
      for (let x = ox; x < width; x += tile * 4) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = oy; y < height; y += tile * 4) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
      ctx.strokeStyle = "rgba(107,153,150,.23)";
      for (let i = 0; i < 24; i++) {
        const x = ((i * 137.4 + now * 0.006) % (width + 60)) - 30,
          y = (i * 73.1) % height;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.quadraticCurveTo(x + 8, y - 3, x + 17, y);
        ctx.stroke();
      }
      // Coast shelves around every edge tile, then the contiguous island.
      for (const [x, y] of run.world.land) {
        if (
          !land.has(`${x + 1},${y}`) ||
          !land.has(`${x - 1},${y}`) ||
          !land.has(`${x},${y + 1}`) ||
          !land.has(`${x},${y - 1}`)
        ) {
          const [px, py] = xy(x, y);
          ctx.fillStyle = "#bcd5cb";
          ctx.fillRect(
            px - tile * 1.35,
            py - tile * 1.35,
            tile * 2.7,
            tile * 2.7,
          );
        }
      }
      for (const [x, y] of run.world.land) {
        const [px, py] = xy(x, y);
        const edge =
          !land.has(`${x + 1},${y}`) ||
          !land.has(`${x - 1},${y}`) ||
          !land.has(`${x},${y + 1}`) ||
          !land.has(`${x},${y - 1}`);
        const v = (x * 13 + y * 7 + run.config.seed) % 7;
        ctx.fillStyle = edge
          ? "#e0d7ad"
          : s.weather === "Drought"
            ? ["#c9c39a", "#c7bd91", "#c2bf92"][v % 3]
            : [
                "#b6c796",
                "#b3c393",
                "#b8c899",
                "#afc190",
                "#b7c697",
                "#b1c493",
                "#b6c796",
              ][v];
        ctx.fillRect(
          px - tile * 0.51,
          py - tile * 0.51,
          tile * 1.03,
          tile * 1.03,
        );
      }
      // Foliage and rocks use fixed positions; visuals never feed back into the engine.
      for (const [x, y] of run.world.land) {
        const n = (x * 317 + y * 97 + run.config.seed) % 101;
        if (n > 5 || Math.hypot(x - 24, y - 24) < 6) continue;
        const [px, py] = xy(x, y);
        ctx.fillStyle = "rgba(56,80,52,.13)";
        ctx.beginPath();
        ctx.ellipse(px + 3, py + 5, tile * 0.65, tile * 0.3, 0, 0, 7);
        ctx.fill();
        ctx.fillStyle = "#657956";
        ctx.fillRect(px - 1, py, 2, tile * 0.5);
        ctx.fillStyle = n % 2 ? "#80966a" : "#8da476";
        ctx.beginPath();
        ctx.moveTo(px, py - tile * 0.85);
        ctx.lineTo(px - tile * 0.5, py + tile * 0.15);
        ctx.lineTo(px + tile * 0.5, py + tile * 0.15);
        ctx.fill();
        ctx.fillStyle = "#92a77a";
        ctx.beginPath();
        ctx.moveTo(px, py - tile * 0.9);
        ctx.lineTo(px, py);
        ctx.lineTo(px - tile * 0.5, py + tile * 0.15);
        ctx.fill();
      }
      for (const p of run.world.patches) {
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = "#d5cca9";
        ctx.lineWidth = tile * 0.62;
        ctx.beginPath();
        p.path.forEach(([x, y], i) => {
          const [px, py] = xy(x, y);
          i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        });
        ctx.stroke();
        ctx.strokeStyle = "#e3dac0";
        ctx.lineWidth = tile * 0.28;
        ctx.stroke();
      }
      // Village square and ten little houses.
      const [cx, cy] = xy(24, 24);
      ctx.fillStyle = "#e4d8b6";
      ctx.beginPath();
      ctx.ellipse(cx, cy, tile * 3.1, tile * 2.5, 0, 0, Math.PI * 2);
      ctx.fill();
      run.world.homes.forEach((h, i) => {
        const [x, y] = xy(h.x, h.y);
        ctx.fillStyle = "rgba(67,73,48,.16)";
        ctx.fillRect(x - 3, y + 3, tile * 1.3, tile * 0.85);
        ctx.fillStyle = "#eee3c8";
        ctx.fillRect(x - tile * 0.6, y - tile * 0.35, tile * 1.2, tile * 0.9);
        ctx.fillStyle = i % 3 === 0 ? "#ba806b" : "#9a705b";
        ctx.beginPath();
        ctx.moveTo(x - tile * 0.77, y - tile * 0.3);
        ctx.lineTo(x, y - tile * 0.95);
        ctx.lineTo(x + tile * 0.77, y - tile * 0.3);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "#697662";
        ctx.fillRect(x - tile * 0.12, y, tile * 0.25, tile * 0.55);
      });
      ctx.fillStyle = "#6d8972";
      ctx.fillRect(cx - tile * 0.65, cy - tile * 0.5, tile * 1.3, tile);
      ctx.fillStyle = "#8aa68b";
      ctx.beginPath();
      ctx.moveTo(cx - tile * 0.85, cy - tile * 0.4);
      ctx.lineTo(cx, cy - tile * 1.1);
      ctx.lineTo(cx + tile * 0.85, cy - tile * 0.4);
      ctx.fill();
      for (const p of run.world.patches) {
        const [x, y] = xy(p.x, p.y);
        ctx.fillStyle = "#8caa71";
        ctx.beginPath();
        ctx.ellipse(x, y, tile * 1.9, tile * 1.45, 0, 0, 7);
        ctx.fill();
        for (let i = 0; i < 7; i++) {
          const a = i * 2.4;
          const bx = x + Math.cos(a) * tile,
            by = y + Math.sin(a) * tile * 0.7;
          ctx.fillStyle = "#5f805b";
          ctx.beginPath();
          ctx.arc(bx, by, tile * 0.48, 0, 7);
          ctx.fill();
          ctx.fillStyle = "#d9af65";
          ctx.beginPath();
          ctx.arc(bx + 2, by - 2, Math.max(1, tile * 0.13), 0, 7);
          ctx.fill();
        }
        ctx.fillStyle = "rgba(255,255,244,.94)";
        ctx.beginPath();
        ctx.roundRect(
          x - tile * 1.65,
          y + tile * 1.7,
          tile * 3.3,
          tile * 1.25,
          4,
        );
        ctx.fill();
        ctx.fillStyle = "#445845";
        ctx.font = `600 ${Math.max(8, tile * 0.64)}px system-ui`;
        ctx.textAlign = "center";
        ctx.fillText(
          `P${p.id + 1} · ${Math.round(s.patch_food[p.id])}`,
          x,
          y + tile * 2.53,
        );
      }
      const progress = Math.min(1, (now - entered.current) / 2200);
      positions.current = [];
      for (const a of s.agents) {
        if (!a.alive) continue;
        const home = run.world.homes[a.home];
        let gx = home.x,
          gy = home.y;
        if (a.patch !== null && progress < 1) {
          const path = run.world.patches[a.patch].path;
          let t = progress < 0.5 ? progress * 2 : (1 - progress) * 2;
          t = Math.max(0, Math.min(1, t));
          const f = t * (path.length - 1),
            i = Math.floor(f),
            j = Math.min(i + 1, path.length - 1);
          gx = path[i][0] + (path[j][0] - path[i][0]) * (f - i);
          gy = path[i][1] + (path[j][1] - path[i][1]) * (f - i);
        }
        const [px, py] = xy(
          gx + ((a.id % 4) - 0.5) * 0.23,
          gy + (Math.floor(a.id / 10) - 1.5) * 0.22,
        );
        positions.current.push({ id: a.id, x: px, y: py });
        if (a.id === latest.current.selected) {
          ctx.strokeStyle = "#cf684b";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(px, py, tile * 0.7, 0, 7);
          ctx.stroke();
        }
        ctx.fillStyle = "rgba(47,63,42,.22)";
        ctx.beginPath();
        ctx.ellipse(px + 2, py + tile * 0.3, tile * 0.3, tile * 0.15, 0, 0, 7);
        ctx.fill();
        ctx.fillStyle = a.hunger ? "#c65e49" : COLORS[a.id % COLORS.length];
        ctx.beginPath();
        ctx.roundRect(
          px - tile * 0.2,
          py - tile * 0.08,
          tile * 0.4,
          tile * 0.5,
          2,
        );
        ctx.fill();
        ctx.fillStyle = "#edcdab";
        ctx.beginPath();
        ctx.arc(px, py - tile * 0.24, tile * 0.19, 0, 7);
        ctx.fill();
      }
      if (s.weather === "Rain") {
        ctx.strokeStyle = "rgba(92,132,153,.17)";
        for (let i = 0; i < 80; i++) {
          const x = (i * 53.3) % width,
            y = (i * 71 + now * 0.04) % height;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x - 3, y + 9);
          ctx.stroke();
        }
      }
      ctx.font = "10px ui-monospace, monospace";
      ctx.textAlign = "left";
      ctx.fillStyle = "#64817a";
      ctx.fillText("48 × 48  /  SEEDED TERRAIN", 22, height - 22);
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [run.id, run.world]);
  const click = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const r = ref.current!.getBoundingClientRect();
    const x = event.clientX - r.left,
      y = event.clientY - r.top;
    const closest = [...positions.current].sort(
      (a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y),
    )[0];
    if (closest && Math.hypot(closest.x - x, closest.y - y) < 25)
      onSelect(closest.id);
  };
  return (
    <canvas
      ref={ref}
      onClick={click}
      className={"island-canvas" + (compact ? " compact" : "")}
      aria-label={`Island at day ${state.day}. Select inhabitants using the list below.`}
      role="img"
    />
  );
}
