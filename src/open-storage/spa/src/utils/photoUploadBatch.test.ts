import { describe, expect, it } from "vitest";
import {
  PHOTO_UPLOAD_CONCURRENCY,
  photoBatchPercent,
  runWithConcurrency,
} from "./photoUploadBatch";

function deferred() {
  let resolve: () => void = () => {};
  const promise = new Promise<void>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function flush() {
  for (let step = 0; step < 5; step += 1) {
    await Promise.resolve();
  }
}

describe("photo upload batch", () => {
  it("weights the bar by file size and caps it at 99 while any item is uploading", () => {
    expect(
      photoBatchPercent([
        { size: 100, progress: 50, status: "uploading" },
        { size: 300, progress: 0, status: "uploading" },
      ]),
    ).toEqual({ isUploading: true, percent: 13 });

    expect(
      photoBatchPercent([
        { size: 100, progress: 100, status: "done" },
        { size: 300, progress: 100, status: "uploading" },
      ]),
    ).toEqual({ isUploading: true, percent: 99 });

    expect(
      photoBatchPercent([{ size: 10, progress: 100, status: "uploading" }]),
    ).toEqual({ isUploading: true, percent: 99 });

    expect(photoBatchPercent([{ size: 0, progress: 0, status: "uploading" }])).toEqual({
      isUploading: true,
      percent: 99,
    });

    expect(
      photoBatchPercent([
        { size: 100, progress: 40, status: "error" },
        { size: 100, progress: 100, status: "done" },
      ]),
    ).toEqual({ isUploading: false, percent: 100 });
  });

  it("runs at most two uploads at once", async () => {
    expect(PHOTO_UPLOAD_CONCURRENCY).toBe(2);

    const gates = Array.from({ length: 5 }, () => deferred());
    let inFlight = 0;
    let maxInFlight = 0;
    const started: number[] = [];

    const finished = runWithConcurrency(
      [0, 1, 2, 3, 4],
      PHOTO_UPLOAD_CONCURRENCY,
      async (item) => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        started.push(item);
        await gates[item].promise;
        inFlight -= 1;
      },
    );

    await flush();
    expect(started).toEqual([0, 1]);
    expect(inFlight).toBe(2);

    gates[0].resolve();
    await flush();
    expect(started).toEqual([0, 1, 2]);
    expect(inFlight).toBe(2);
    expect(maxInFlight).toBe(2);

    gates[1].resolve();
    await flush();
    expect(started).toEqual([0, 1, 2, 3]);
    expect(inFlight).toBe(2);
    expect(maxInFlight).toBe(2);

    gates[2].resolve();
    await flush();
    expect(started).toEqual([0, 1, 2, 3, 4]);
    expect(inFlight).toBe(2);
    expect(maxInFlight).toBe(2);

    gates[3].resolve();
    gates[4].resolve();
    await finished;
    expect(inFlight).toBe(0);
    expect(maxInFlight).toBe(2);
  });
});
