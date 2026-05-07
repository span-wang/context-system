import { useEffect, useRef } from "react";

export function useLatestRequestGate() {
  const activeRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      requestIdRef.current += 1;
    };
  }, []);

  function begin() {
    const nextRequestId = requestIdRef.current + 1;
    requestIdRef.current = nextRequestId;
    return nextRequestId;
  }

  function isCurrent(requestId: number) {
    return activeRef.current && requestIdRef.current === requestId;
  }

  return { begin, isCurrent };
}

export function firstRejectedReason(results: PromiseSettledResult<unknown>[]) {
  return results.find((result) => result.status === "rejected")?.reason;
}

export function hasFulfilled(results: PromiseSettledResult<unknown>[]) {
  return results.some((result) => result.status === "fulfilled");
}

export function allRejected(results: PromiseSettledResult<unknown>[]) {
  return !hasFulfilled(results);
}

export function summarizeRejectedRequests(
  requests: Array<{ label: string; result: PromiseSettledResult<unknown> }>,
  fallback = "请求失败",
) {
  const failures = requests
    .filter((request) => request.result.status === "rejected")
    .map((request) => {
      const reason = request.result.status === "rejected" ? request.result.reason : null;
      return `${request.label}：${toErrorMessage(reason, fallback)}`;
    });

  return failures.length ? `部分数据加载失败：${failures.join("；")}` : "";
}

export function toErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
