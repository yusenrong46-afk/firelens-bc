import { postProductEvent, type ProductEventName } from "./api/api";

export function emitProductEvent(event: ProductEventName): void {
  void postProductEvent(event).catch(() => undefined);
}
