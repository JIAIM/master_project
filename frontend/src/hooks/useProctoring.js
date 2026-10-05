import { useEffect, useRef, useState } from "react";

const MP_VERSION = "0.10.14";
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`;
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Пороги визначення відволікання
export const THRESHOLDS = {
  yawDeg: 25,          // поворот голови вліво/вправо
  pitchDeg: 20,        // нахил угору/вниз
  gazeSide: 0.6,       // blendshape eyeLookIn/Out
  gazeDown: 0.75,      // blendshape eyeLookDown (погляд униз)
};
const DETECT_INTERVAL_MS = 100;   // ~10 кадрів/с
const OK_HYSTERESIS_MS = 700;

const RAD2DEG = 180 / Math.PI;

export function classifyFrame(result) {
  const faces = result?.faceLandmarks?.length ?? 0;
  if (faces === 0) return { reason: "face_not_detected" };
  if (faces > 1) return { reason: "multiple_faces", faces };

  const details = {};
  const m = result.facialTransformationMatrixes?.[0]?.data;
  if (m) {
    // Матриця 4x4 column-major: r_ij = m[j * 4 + i]
    const yaw = Math.atan2(m[8], m[10]) * RAD2DEG;
    const pitch = Math.asin(Math.max(-1, Math.min(1, -m[9]))) * RAD2DEG;
    details.yaw = Math.round(yaw);
    details.pitch = Math.round(pitch);
    if (Math.abs(yaw) > THRESHOLDS.yawDeg || Math.abs(pitch) > THRESHOLDS.pitchDeg) {
      return { reason: "distraction_warning", source: "head_pose", ...details };
    }
  }

  const cats = result.faceBlendshapes?.[0]?.categories;
  if (cats) {
    const g = Object.fromEntries(cats.map((c) => [c.categoryName, c.score]));
    const side = Math.max(
      (g.eyeLookOutLeft + g.eyeLookInRight) / 2,
      (g.eyeLookInLeft + g.eyeLookOutRight) / 2
    );
    const down = (g.eyeLookDownLeft + g.eyeLookDownRight) / 2;
    if (side > THRESHOLDS.gazeSide || down > THRESHOLDS.gazeDown) {
      return { reason: "distraction_warning", source: "gaze", side: +side.toFixed(2), down: +down.toFixed(2) };
    }
  }
  return { reason: null };
}

export function useProctoring({ enabled, thresholdSec = 3, onEvent }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | loading | ready | denied | error
  const [attention, setAttention] = useState("ok");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  // --- Камера та розпізнавання ---
  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let stream;
    let landmarker;
    let rafId;
    let lastRun = 0;
    let awaySince = null;
    let okSince = null;
    let alertSent = false;
    let lastAttention = "ok";

    const setAttentionIfChanged = (value) => {
      if (value !== lastAttention) {
        lastAttention = value;
        setAttention(value);
      }
    };

    const handle = ({ reason, ...details }) => {
      const t = Date.now();
      if (reason) {
        okSince = null;
        setAttentionIfChanged(reason);
        if (awaySince === null) awaySince = t;
        if (!alertSent && t - awaySince >= thresholdSec * 1000) {
          alertSent = true;
          onEventRef.current?.({ event: reason, client_ts: t, details });
        }
      } else if (awaySince !== null) {
        if (okSince === null) okSince = t;
        if (t - okSince >= OK_HYSTERESIS_MS) {
          if (alertSent) {
            onEventRef.current?.({ event: "attention_restored", duration_ms: okSince - awaySince, client_ts: t });
          }
          awaySince = null;
          okSince = null;
          alertSent = false;
          setAttentionIfChanged("ok");
        }
      }
    };

    (async () => {
      setStatus("loading");
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: "user" },
          audio: false,
        });
      } catch {
        if (!cancelled) setStatus("denied");
        return;
      }
      if (cancelled) return;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play().catch(() => {});

      try {
        const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
        const fileset = await FilesetResolver.forVisionTasks(WASM_URL);
        landmarker = await FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
          runningMode: "VIDEO",
          numFaces: 2,
          outputFaceBlendshapes: true,
          outputFacialTransformationMatrixes: true,
        });
      } catch (err) {
        console.error("Не вдалося запустити MediaPipe", err);
        if (!cancelled) setStatus("error");
        return;
      }
      if (cancelled) return;
      setStatus("ready");

      const loop = () => {
        if (cancelled) return;
        const now = performance.now();
        if (now - lastRun >= DETECT_INTERVAL_MS && video.readyState >= 2) {
          lastRun = now;
          try {
            handle(classifyFrame(landmarker.detectForVideo(video, now)));
          } catch (err) {
            console.warn("Помилка розпізнавання кадру", err);
          }
        }
        rafId = requestAnimationFrame(loop);
      };
      loop();
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      landmarker?.close();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [enabled, thresholdSec]);

  // --- Вкладка та повноекранний режим ---
  useEffect(() => {
    if (!enabled) return undefined;
    let hiddenAt = null;

    const onVisibility = () => {
      if (document.hidden) {
        hiddenAt = Date.now();
        onEventRef.current?.({ event: "tab_hidden", client_ts: hiddenAt });
      } else if (hiddenAt) {
        onEventRef.current?.({ event: "attention_restored", duration_ms: Date.now() - hiddenAt, client_ts: Date.now() });
        hiddenAt = null;
      }
    };
    const onFullscreen = () => {
      if (!document.fullscreenElement) {
        onEventRef.current?.({ event: "fullscreen_exit", client_ts: Date.now() });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreen);
    };
  }, [enabled]);

  return { videoRef, status, attention };
}
