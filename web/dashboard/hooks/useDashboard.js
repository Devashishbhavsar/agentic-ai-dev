import { useState, useEffect, useRef } from "react";

export function useDashboard() {
  const [data, setData]         = useState(null);
  const [streamState, setStreamState] = useState("connecting");
  const [updatedAt, setUpdatedAt]     = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    function connect() {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${location.host}/v1/dashboard/stream`);
      wsRef.current = ws;
      ws.onopen  = () => setStreamState("live");
      ws.onclose = () => { setStreamState("reconnecting"); setTimeout(connect, 3000); };
      ws.onerror = () => setStreamState("reconnecting");
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          setData(d);
          setUpdatedAt(new Date());
        } catch { }
      };
    }
    connect();
    return () => { wsRef.current?.close(); };
  }, []);

  return { data, streamState, updatedAt };
}
