import { useEffect, useState } from "react";

export function ConnectionStatus() {
  const [online, setOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  if (online) return null;
  return (
    <div className="connection-banner" role="status" aria-label="Connection status">
      You are offline. FireLens cannot fetch official records or reviewed guidance until the
      connection returns. Retry when you are back online.
    </div>
  );
}
