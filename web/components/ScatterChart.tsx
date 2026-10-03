"use client";

import dynamic from "next/dynamic";
import type { Data, Layout, PlotMouseEvent, PlotlyHTMLElement } from "plotly.js";
import { useEffect, useMemo, useRef, useState } from "react";

import { useTheme } from "@/components/ThemeProvider";
import { trendlinePoints } from "@/lib/regression";
import { FUEL_COLORS, type Listing } from "@/lib/types";

function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type Axis = "year" | "mileage_km";
type AxisRange = [number, number];

type Props = {
  listings: Listing[];
  x: Axis;
  title: string;
  xTitle: string;
};

type AxisLayout = {
  range: number[];
  _offset: number;
  _length: number;
  p2l: (px: number) => number;
  l2p: (value: number) => number;
};

type FullLayout = {
  xaxis: AxisLayout;
  yaxis: AxisLayout;
};

type PanSession = {
  mode: "pan" | "pending-pan" | "stretch-y";
  originX: number;
  originY: number;
  xRange: AxisRange;
  yRange: AxisRange;
  xLength: number;
  yLength: number;
  anchorY?: number;
  requiresSpace?: boolean;
};

function readAxisRange(axis: AxisLayout): AxisRange | null {
  const a = Number(axis.range?.[0]);
  const b = Number(axis.range?.[1]);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return null;
  return [a, b];
}

function fullLayout(gd: PlotlyHTMLElement) {
  return (gd as PlotlyHTMLElement & { _fullLayout: FullLayout })._fullLayout;
}

function currentRanges(gd: PlotlyHTMLElement) {
  const layout = fullLayout(gd);
  const xa = layout?.xaxis;
  const ya = layout?.yaxis;
  if (!xa || !ya) return null;
  const xRange = readAxisRange(xa);
  const yRange = readAxisRange(ya);
  if (!xRange || !yRange) return null;
  if (!Number.isFinite(xa._length) || !Number.isFinite(ya._length)) return null;
  if (xa._length <= 0 || ya._length <= 0) return null;
  return {
    xRange,
    yRange,
    xLength: xa._length,
    yLength: ya._length,
    xOffset: xa._offset,
    yOffset: ya._offset,
  };
}

function scaleRange(range: AxisRange, anchor: number, scale: number): AxisRange | null {
  const next: AxisRange = [
    anchor - (anchor - range[0]) * scale,
    anchor + (range[1] - anchor) * scale,
  ];
  if (![...next].every(Number.isFinite) || next[0] === next[1]) return null;
  return next;
}

function zoomAroundCursor(
  gd: PlotlyHTMLElement,
  event: WheelEvent,
  axes: "both" | "y" = "both",
) {
  const layout = fullLayout(gd);
  const xa = layout?.xaxis;
  const ya = layout?.yaxis;
  if (!xa || !ya) return null;

  const rect = gd.getBoundingClientRect();
  const xPx = event.clientX - rect.left - xa._offset;
  const yPx = event.clientY - rect.top - ya._offset;

  const xRange = readAxisRange(xa);
  const yRange = readAxisRange(ya);
  if (!xRange || !yRange) return null;

  const scale = event.deltaY > 0 ? 1.15 : 1 / 1.15;

  if (axes === "y") {
    // Allow stretching from the left price-axis strip or anywhere with Shift.
    const yClamped = Math.min(Math.max(yPx, 0), ya._length);
    const yVal = Number(ya.p2l(yClamped));
    if (!Number.isFinite(yVal)) return null;
    const nextY = scaleRange(yRange, yVal, scale);
    if (!nextY) return null;
    return { x: xRange, y: nextY };
  }

  if (
    !Number.isFinite(xa._offset) ||
    !Number.isFinite(ya._offset) ||
    xPx < 0 ||
    yPx < 0 ||
    xPx > xa._length ||
    yPx > ya._length
  ) {
    return null;
  }

  const xVal = Number(xa.p2l(xPx));
  const yVal = Number(ya.p2l(yPx));
  if (![xVal, yVal].every(Number.isFinite)) return null;

  const nextX = scaleRange(xRange, xVal, scale);
  const nextY = scaleRange(yRange, yVal, scale);
  if (!nextX || !nextY) return null;
  return { x: nextX, y: nextY };
}

function shiftRange(range: AxisRange, pixelDelta: number, axisLength: number, invert: boolean): AxisRange {
  const span = range[1] - range[0];
  const dataDelta = (pixelDelta / axisLength) * span;
  const shift = invert ? dataDelta : -dataDelta;
  return [range[0] + shift, range[1] + shift];
}

function pointerZone(gd: PlotlyHTMLElement, clientX: number, clientY: number) {
  const live = currentRanges(gd);
  if (!live) return "outside" as const;
  const rect = gd.getBoundingClientRect();
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const inY = y >= live.yOffset && y <= live.yOffset + live.yLength;
  const inX = x >= live.xOffset && x <= live.xOffset + live.xLength;
  if (inY && x < live.xOffset && x >= 0) return "y-axis" as const;
  if (inX && inY) return "plot" as const;
  return "outside" as const;
}

export function ScatterChart({ listings, x, title, xTitle }: Props) {
  const { theme } = useTheme();
  const wrapRef = useRef<HTMLDivElement>(null);
  const gdRef = useRef<PlotlyHTMLElement | null>(null);
  const spaceDownRef = useRef(false);
  const panRef = useRef<PanSession | null>(null);
  const draggedRef = useRef(false);
  const dragEndedAtRef = useRef(0);
  const boundsRef = useRef<{ x: AxisRange; y: AxisRange } | null>(null);
  const rangesRef = useRef<{ x?: AxisRange; y?: AxisRange }>({});
  const [ranges, setRanges] = useState<{ x?: AxisRange; y?: AxisRange }>({});
  const [isPanning, setIsPanning] = useState(false);
  const [overPriceAxis, setOverPriceAxis] = useState(false);
  const [chartHeight, setChartHeight] = useState(320);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    rangesRef.current = ranges;
  }, [ranges]);

  const bounds = useMemo(() => {
    if (listings.length === 0) return null;
    let xLo = Infinity;
    let xHi = -Infinity;
    let yLo = Infinity;
    let yHi = -Infinity;
    for (const row of listings) {
      const xv = x === "year" ? row.year : row.mileage_km;
      const yv = row.price_eur;
      if (!Number.isFinite(xv) || !Number.isFinite(yv)) continue;
      if (xv < xLo) xLo = xv;
      if (xv > xHi) xHi = xv;
      if (yv < yLo) yLo = yv;
      if (yv > yHi) yHi = yv;
    }
    if (!Number.isFinite(xLo) || !Number.isFinite(yLo)) return null;
    return { x: [xLo, xHi] as AxisRange, y: [yLo, yHi] as AxisRange };
  }, [listings, x]);

  boundsRef.current = bounds;

  useEffect(() => {
    const updateSize = () => {
      const width = window.innerWidth;
      const mobile = width < 640;
      setIsMobile(mobile);
      setChartHeight(mobile ? 280 : width < 1024 ? 360 : 460);
    };
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  useEffect(() => {
    setRanges({});
    rangesRef.current = {};
    panRef.current = null;
    setIsPanning(false);
    setOverPriceAxis(false);
  }, [listings, x]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const isTypingTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target.isContentEditable
      );
    };

    const releaseSpace = () => {
      spaceDownRef.current = false;
      if (panRef.current?.requiresSpace) {
        panRef.current = null;
        setIsPanning(false);
      }
    };

    // Keeps the view tied to the data so it can never become empty or invalid.
    const clampAxis = (range: AxisRange, data: AxisRange): AxisRange | null => {
      if (!range.every(Number.isFinite)) return null;
      const span = range[1] - range[0];
      const dataSpan = data[1] - data[0] || Math.max(Math.abs(data[0]) * 0.1, 1);
      if (!(span > 0) || span < dataSpan * 0.005 || span > dataSpan * 20) {
        return null;
      }
      const keep = Math.min(span, dataSpan) * 0.2;
      let shift = 0;
      if (range[0] > data[1] - keep) shift = data[1] - keep - range[0];
      else if (range[1] < data[0] + keep) shift = data[0] + keep - range[1];
      return [range[0] + shift, range[1] + shift];
    };

    const applyRanges = (next: { x: AxisRange; y: AxisRange }) => {
      const limits = boundsRef.current;
      if (!limits) return;
      const cx = clampAxis(next.x, limits.x);
      const cy = clampAxis(next.y, limits.y);
      if (!cx || !cy) return;
      const clamped = { x: cx, y: cy };
      rangesRef.current = clamped;
      setRanges(clamped);
    };

    const resetRanges = () => {
      rangesRef.current = {};
      setRanges({});
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space" || isTypingTarget(event.target)) return;

      if (spaceDownRef.current || el.matches(":hover")) {
        event.preventDefault();
      }
      if (event.repeat || spaceDownRef.current) return;
      if (!el.matches(":hover")) return;

      spaceDownRef.current = true;
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      event.preventDefault();
      releaseSpace();
    };

    const onWheel = (event: WheelEvent) => {
      const gd = gdRef.current;
      if (!gd || spaceDownRef.current) return;

      const zone = pointerZone(gd, event.clientX, event.clientY);

      // Left price-axis strip: wheel stretches price only.
      if (zone === "y-axis") {
        event.preventDefault();
        event.stopPropagation();
        const next = zoomAroundCursor(gd, event, "y");
        if (next) applyRanges(next);
        return;
      }

      // Plot area: Ctrl+wheel zooms both; Ctrl+Shift+wheel stretches price only.
      if (!event.ctrlKey) return;
      event.preventDefault();
      event.stopPropagation();
      const next = zoomAroundCursor(gd, event, event.shiftKey ? "y" : "both");
      if (next) applyRanges(next);
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const gd = gdRef.current;
      if (!gd) return;
      const live = currentRanges(gd);
      if (!live) return;

      // If the live view is broken (no overlap with the data), start fresh.
      const limits = boundsRef.current;
      if (
        limits &&
        (!clampAxis(live.xRange, limits.x) ||
          !clampAxis(live.yRange, limits.y) ||
          live.xRange[1] < limits.x[0] ||
          live.xRange[0] > limits.x[1] ||
          live.yRange[1] < limits.y[0] ||
          live.yRange[0] > limits.y[1])
      ) {
        resetRanges();
        return;
      }

      const zone = pointerZone(gd, event.clientX, event.clientY);

      if (zone === "plot" || spaceDownRef.current) {
        draggedRef.current = false;
        const panNow = spaceDownRef.current && zone !== "plot";
        if (panNow) {
          event.preventDefault();
          event.stopPropagation();
        }
        panRef.current = {
          mode: panNow ? "pan" : "pending-pan",
          originX: event.clientX,
          originY: event.clientY,
          xRange: live.xRange,
          yRange: live.yRange,
          xLength: live.xLength,
          yLength: live.yLength,
          requiresSpace: panNow,
        };
        if (panNow) {
          setIsPanning(true);
          try {
            el.setPointerCapture(event.pointerId);
          } catch {
            // Capture is optional; panning still follows the pointer.
          }
        }
        return;
      }

      // Drag on the left price axis to stretch/compress price only.
      if (zone === "y-axis") {
        event.preventDefault();
        event.stopPropagation();
        const rect = gd.getBoundingClientRect();
        const yPx = Math.min(
          Math.max(event.clientY - rect.top - live.yOffset, 0),
          live.yLength,
        );
        const ya = fullLayout(gd).yaxis;
        const anchorY = Number(ya.p2l(yPx));
        if (!Number.isFinite(anchorY)) return;

        panRef.current = {
          mode: "stretch-y",
          originX: event.clientX,
          originY: event.clientY,
          xRange: live.xRange,
          yRange: live.yRange,
          xLength: live.xLength,
          yLength: live.yLength,
          anchorY,
        };
        setIsPanning(true);
        try {
          el.setPointerCapture(event.pointerId);
        } catch {
          // Capture is optional; stretching still follows the pointer.
        }
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      const gd = gdRef.current;
      if (gd && !panRef.current) {
        setOverPriceAxis(pointerZone(gd, event.clientX, event.clientY) === "y-axis");
      }

      const session = panRef.current;
      if (!session) return;

      // Left button is no longer held: end the gesture and keep the view as is.
      if ((event.buttons & 1) === 0) {
        endGesture(event.pointerId);
        return;
      }

      if (session.mode === "pending-pan") {
        const dx = event.clientX - session.originX;
        const dy = event.clientY - session.originY;
        if (dx * dx + dy * dy < 16) return;
        session.mode = "pan";
        draggedRef.current = true;
        setIsPanning(true);
        try {
          if (!el.hasPointerCapture(event.pointerId)) {
            el.setPointerCapture(event.pointerId);
          }
        } catch {
          // Capture is optional; panning still follows the pointer.
        }
      }

      event.preventDefault();

      if (session.mode === "pan") {
        if (session.requiresSpace && !spaceDownRef.current) return;
        event.preventDefault();
        const next = {
          x: shiftRange(session.xRange, event.clientX - session.originX, session.xLength, false),
          y: shiftRange(session.yRange, event.clientY - session.originY, session.yLength, true),
        };
        if (![...next.x, ...next.y].every(Number.isFinite)) return;
        applyRanges(next);
        return;
      }

      // Stretch price: drag up zooms in, drag down zooms out, around the grab price.
      const dy = event.clientY - session.originY;
      const scale = Math.exp(dy / 160);
      const nextY = scaleRange(session.yRange, session.anchorY ?? session.yRange[0], scale);
      if (!nextY) return;
      applyRanges({ x: session.xRange, y: nextY });
    };

    function endGesture(pointerId: number) {
      if (!panRef.current) return;
      if (draggedRef.current) dragEndedAtRef.current = performance.now();
      panRef.current = null;
      setIsPanning(false);
      const node = wrapRef.current;
      try {
        if (node?.hasPointerCapture(pointerId)) {
          node.releasePointerCapture(pointerId);
        }
      } catch {
        // Nothing to release when the pointer was never captured.
      }
    }

    const onPointerUp = (event: PointerEvent) => endGesture(event.pointerId);
    const onWindowMouseUp = () => endGesture(-1);

    const onPointerLeave = () => {
      if (!panRef.current) setOverPriceAxis(false);
    };

    window.addEventListener("keydown", onKeyDown, { capture: true });
    window.addEventListener("keyup", onKeyUp, { capture: true });
    window.addEventListener("blur", releaseSpace);
    window.addEventListener("pointerup", onPointerUp, { capture: true });
    window.addEventListener("pointercancel", onPointerUp, { capture: true });
    window.addEventListener("mouseup", onWindowMouseUp, { capture: true });
    el.addEventListener("lostpointercapture", onPointerUp);
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("pointerdown", onPointerDown);
    // Listen on window: Plotly covers the page during a press, so the chart
    // element itself would not receive the drag movement.
    window.addEventListener("pointermove", onPointerMove, { capture: true });
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerUp);
    el.addEventListener("pointerleave", onPointerLeave);

    return () => {
      window.removeEventListener("keydown", onKeyDown, { capture: true });
      window.removeEventListener("keyup", onKeyUp, { capture: true });
      window.removeEventListener("blur", releaseSpace);
      window.removeEventListener("pointerup", onPointerUp, { capture: true });
      window.removeEventListener("pointercancel", onPointerUp, { capture: true });
      window.removeEventListener("mouseup", onWindowMouseUp, { capture: true });
      el.removeEventListener("lostpointercapture", onPointerUp);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove, { capture: true });
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerUp);
      el.removeEventListener("pointerleave", onPointerLeave);
    };
  }, []);

  const data = useMemo<Data[]>(() => {
    const byFuel = new Map<string, Listing[]>();
    for (const row of listings) {
      const key = row.fuel_type || "Unknown";
      const group = byFuel.get(key) ?? [];
      group.push(row);
      byFuel.set(key, group);
    }

    const traces: Data[] = Array.from(byFuel.entries()).map(([fuel, rows]) => ({
      type: "scatter",
      mode: "markers",
      name: fuel,
      x: rows.map((row) => (x === "year" ? row.year : row.mileage_km)),
      y: rows.map((row) => row.price_eur),
      customdata: rows.map((row) => [
        row.link,
        row.transmission,
        row.year,
        row.mileage_km,
        row.horsepower,
      ]),
      marker: {
        color: FUEL_COLORS[fuel] ?? "#94a3b8",
        size: rows.map((row) => Math.max(8, Math.min(22, row.horsepower / 12))),
        opacity: 0.75,
      },
      cliponaxis: false,
      hovertemplate:
        x === "year"
          ? "<b>€%{y:,.0f}</b><br>Year: %{x}<br>Mileage: %{customdata[3]:,} km<br>HP: %{customdata[4]}<br>Transmission: %{customdata[1]}<extra>%{fullData.name}</extra>"
          : "<b>€%{y:,.0f}</b><br>Mileage: %{x:,} km<br>Year: %{customdata[2]}<br>HP: %{customdata[4]}<br>Transmission: %{customdata[1]}<extra>%{fullData.name}</extra>",
    }));

    const xs = listings.map((row) => (x === "year" ? row.year : row.mileage_km));
    const ys = listings.map((row) => row.price_eur);
    const trendColor = cssVar("--plot-trend", "#e2e8f0");
    const line = trendlinePoints(xs, ys);
    if (line.length === 2) {
      traces.push({
        type: "scatter",
        mode: "lines",
        name: "OLS trend",
        x: line.map((point) => point.x),
        y: line.map((point) => point.y),
        line: { color: trendColor, width: 2, dash: "dot" },
        hovertemplate: "Trend: €%{y:,.0f}<extra></extra>",
      });
    }

    return traces;
  }, [listings, x, theme]);

  // Explicit default view computed from the data. Never rely on Plotly
  // autorange, which can briefly fall back to a meaningless 0..6 range.
  const defaultView = useMemo(() => {
    if (!bounds) return null;
    const pad = (lo: number, hi: number, ratio: number, min: number) => {
      const p = Math.max((hi - lo) * ratio, min);
      return [lo - p, hi + p] as AxisRange;
    };
    const xr =
      x === "year"
        ? pad(bounds.x[0], bounds.x[1], 0.04, 1)
        : pad(bounds.x[0], bounds.x[1], 0.05, 1000);
    const yr = pad(bounds.y[0], bounds.y[1], 0.06, 500);
    if (bounds.y[0] >= 0 && yr[0] < 0) yr[0] = 0;
    return { x: xr, y: yr };
  }, [bounds, x]);

  const viewX = ranges.x ?? defaultView?.x;
  const viewY = ranges.y ?? defaultView?.y;

  const yearTickStep = useMemo(() => {
    const span = viewX ? viewX[1] - viewX[0] : 10;
    // Whole-year steps only, thinned out so labels never crowd each other.
    const maxTicks = isMobile ? 6 : 12;
    return Math.max(1, Math.ceil(span / maxTicks));
  }, [viewX, isMobile]);

  const layout = useMemo<Partial<Layout>>(() => {
    const plotText = cssVar("--plot-text", "#cbd5e1");
    const plotTitle = cssVar("--plot-title", "#e2e8f0");
    const plotBg = cssVar("--plot-bg", "rgba(15,23,42,0.4)");
    const plotGrid = cssVar("--plot-grid", "#1e293b");

    return {
      title: isMobile
        ? undefined
        : { text: title, font: { color: plotTitle, size: 16 } },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: plotBg,
      font: { color: plotText, family: "inherit", size: isMobile ? 11 : 12 },
      margin: isMobile
        ? { t: 24, r: 8, b: 72, l: 48 }
        : { t: 48, r: 16, b: 56, l: 72 },
      xaxis: {
        title: { text: xTitle },
        type: "linear",
        gridcolor: plotGrid,
        zeroline: false,
        fixedrange: false,
        // Year chart: only whole years on the axis (no 2019.5 and similar).
        ...(x === "year"
          ? {
              tickmode: "linear" as const,
              tick0: 0,
              dtick: yearTickStep,
              tickformat: "d",
              hoverformat: "d",
            }
          : {}),
        ...(viewX
          ? { range: viewX, autorange: false }
          : { autorange: true }),
      },
      yaxis: {
        title: { text: isMobile ? "€" : "Price (€)" },
        type: "linear",
        gridcolor: plotGrid,
        zeroline: false,
        fixedrange: false,
        ...(viewY
          ? { range: viewY, autorange: false }
          : { autorange: true }),
      },
      legend: {
        orientation: "h",
        y: isMobile ? -0.28 : -0.22,
        font: { size: isMobile ? 10 : 12 },
      },
      hovermode: "closest",
      // Left-drag panning is handled manually so Plotly box-zoom does not fight it.
      dragmode: false,
      uirevision: `${x}-${title}-${theme}-${isMobile ? "m" : "d"}`,
    };
  }, [title, xTitle, x, viewX, viewY, theme, isMobile, yearTickStep]);

  function openListing(event: PlotMouseEvent) {
    // Never open an offer right after a drag.
    if (
      spaceDownRef.current ||
      panRef.current ||
      performance.now() - dragEndedAtRef.current < 300
    ) {
      return;
    }
    const point = event.points?.[0];
    const gd = gdRef.current;
    const mouse = event.event;
    if (!point || !gd || !mouse) return;

    // Only accept clicks that really land on the circle, not on empty space.
    const layout = fullLayout(gd);
    const rect = gd.getBoundingClientRect();
    const px =
      rect.left + layout.xaxis._offset + layout.xaxis.l2p(Number(point.x));
    const py =
      rect.top + layout.yaxis._offset + layout.yaxis.l2p(Number(point.y));
    const marker = (point.data as { marker?: { size?: number | number[] } }).marker;
    const sizes = marker?.size;
    const size = Array.isArray(sizes)
      ? sizes[point.pointNumber]
      : typeof sizes === "number"
        ? sizes
        : 10;
    const radius = (Number(size) || 10) / 2 + 3;
    if (Math.hypot(mouse.clientX - px, mouse.clientY - py) > radius) return;

    const payload = point?.customdata;
    const link = Array.isArray(payload) ? payload[0] : undefined;
    if (typeof link === "string" && link) {
      window.open(link, "_blank", "noopener,noreferrer");
    }
  }

  const cursor = isPanning
    ? "grabbing"
    : overPriceAxis || panRef.current?.mode === "stretch-y"
      ? "ns-resize"
      : "grab";

  return (
    <div
      ref={wrapRef}
      className={`w-full max-w-full select-none ${isMobile ? "" : "touch-none"}`}
      style={{ cursor, height: chartHeight }}
    >
      <Plot
        data={data}
        layout={layout}
        config={{
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
          doubleClick: false,
        }}
        style={{ width: "100%", height: chartHeight }}
        useResizeHandler
        onClick={openListing}
        onInitialized={(_figure, gd) => {
          gdRef.current = gd as PlotlyHTMLElement;
        }}
        onUpdate={(_figure, gd) => {
          gdRef.current = gd as PlotlyHTMLElement;
        }}
        onDoubleClick={() => {
          rangesRef.current = {};
          setRanges({});
        }}
      />
    </div>
  );
}
