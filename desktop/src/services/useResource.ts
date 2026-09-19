import { useCallback, useEffect, useRef, useState } from "react";
export function useResource<T>(
  load: () => Promise<T>,
  topics: string[] = [],
  key = "",
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const loader = useRef(load);
  loader.current = load;
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const id = ++generation.current;
    setLoading(true);
    try {
      const value = await loader.current();
      if (id === generation.current) {
        setData(value);
        setError("");
      }
    } catch (e) {
      if (id === generation.current)
        setError(
          e instanceof Error
            ? e.message
            : "This view could not load. Try Refresh.",
        );
    } finally {
      if (id === generation.current) setLoading(false);
    }
  }, []);
  const topicKey = topics.join("|");
  useEffect(() => {
    void refresh();
    const names = topicKey.split("|");
    let pending: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = window.olive.subscribe((e) => {
      if (names.includes(e.topic) && pending === undefined) {
        pending = setTimeout(() => {
          pending = undefined;
          void refresh();
        }, 100);
      }
    });
    return () => {
      generation.current++;
      clearTimeout(pending);
      unsubscribe();
    };
  }, [refresh, topicKey, key]);
  return { data, setData, error, loading, refresh };
}
