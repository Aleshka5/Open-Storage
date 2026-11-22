# task-16 Cutover

Story: [US-01](../init.md)

## Outcome

One switch. Stop the old TLS layer and the old auth and user stacks. Start the new proxy. Run `make verify`.

## Done when

`make verify` passes. Google login works on three different hosts. One real operation works in each of the four products (storage, image, rag, audio).

Task 14 is finished before this task starts.
