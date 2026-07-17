---
description: Resize an uploaded image to the three thumbnail sizes the gallery needs
---

# Workflow: Thumbnail Generator

Use this workflow to resize one uploaded image into the three thumbnail
sizes the gallery needs, validating the result before returning it.

## Inputs

- `image_path`: path to the source image; required

## Control

- Primary agent: this workflow owns reading the image and delegating the
  resize operations; it makes no approval decisions.
- Decision model: deterministic — always produce all three sizes.
- Delegation: a Resize worker, invoked once per target size.

## Steps

1. Load the operating contract
   - OBEY the thumbnail-generation rules before any other workflow action.

2. Establish the target
   - Confirm `image_path` points at a readable image file. Stop and report
     if it does not.

3. Gather required context
   - Read the source image's current dimensions.

4. Execute the work
   - Delegate to the Resize worker three times, once per target size
     (small, medium, large): objective — produce a resized copy at the
     stated dimensions; output format — the resized file's path; tool
     guidance — Resize worker has Read and Write, scoped to the output
     directory only; boundaries — Resize worker may write only the one
     output file it was asked to produce.
   - Validate each returned path exists and is a readable image before
     accepting it; retry once per size on failure, then stop and report if
     the retry also fails.

5. Assemble the result
   - Collect the three validated output paths.

6. Finish
   - Return the three thumbnail paths to the caller.

## Stop Conditions

- Stop and report if `image_path` is unreadable.
- Stop and report if a resize retry still fails.
