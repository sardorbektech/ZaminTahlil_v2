/**
 * Server-Sent Events (SSE) orqali vazifa progressini tinglash.
 */

export function listenToReconEvents(runId, onMessage, onError) {
  const eventSource = new EventSource(`/api/v1/recon/${runId}/events`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (onMessage) onMessage(data);
      if (data.stage === 10) {
        eventSource.close();
      }
    } catch (e) {
      console.error("SSE JSON parsing error:", e);
    }
  };

  eventSource.onerror = (err) => {
    console.warn("SSE aloqa uzildi yoki xatolik:", err);
    eventSource.close();
    if (onError) onError(err);
  };

  return {
    close: () => eventSource.close(),
  };
}
